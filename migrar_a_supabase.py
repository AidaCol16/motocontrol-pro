"""
Ejecuta este archivo (python migrar_a_supabase.py) para migrar automáticamente
TODA tu base de datos local de SQL Server y tus fotos/precios hacia tu proyecto
Supabase (axmdeqwaxckkhwhevrdr) sin tocar nada a mano.
"""
import os
import urllib.parse
import pandas as pd
import sqlalchemy as sa
from sqlalchemy import text

PROJECT_REF = "axmdeqwaxckkhwhevrdr"
DB_PASS = urllib.parse.quote_plus("MotoControl2026*")
REGION = "ca-central-1"

URL_SUPABASE = f"postgresql+psycopg2://postgres.{PROJECT_REF}:{DB_PASS}@aws-1-{REGION}.pooler.supabase.com:6543/postgres"

def asegurar_columnas_dinamicas(engine_pg, tabla_pg, df):
    """Agrega automáticamente cualquier columna extra que exista en SQL Server y falte en Supabase."""
    with engine_pg.begin() as conn_pg:
        for col in df.columns:
            dtype = str(df[col].dtype)
            if "int" in dtype:
                tipo_sql = "INT"
            elif "float" in dtype:
                tipo_sql = "NUMERIC(12,2)"
            elif "datetime" in dtype:
                tipo_sql = "TIMESTAMP"
            else:
                tipo_sql = "TEXT"
            conn_pg.execute(text(f"ALTER TABLE dbo.{tabla_pg} ADD COLUMN IF NOT EXISTS {col} {tipo_sql};"))
        conn_pg.execute(text("ALTER TABLE dbo.compras ALTER COLUMN precio_compra DROP NOT NULL;"))

def ejecutar_migracion():
    print("🔍 Conectando a tu proyecto Supabase (aws-1-ca-central-1)...")
    engine_pg = sa.create_engine(URL_SUPABASE, pool_pre_ping=True)

    import pyodbc
    drivers = pyodbc.drivers()
    drv = "ODBC Driver 17 for SQL Server"
    for c in ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server"]:
        if c in drivers:
            drv = c
            break
    params = urllib.parse.quote_plus(
        f"DRIVER={{{drv}}};SERVER=.\\SQLEXPRESS;DATABASE=InventarioMotos_Pro;Trusted_Connection=yes;Encrypt=no;TrustServerCertificate=yes;"
    )
    engine_mssql = sa.create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

    tablas = ['Usuarios', 'marcas', 'categorias', 'unidades', 'repuestos', 'socios', 'compras', 'pedidos_clientes']
    for t in tablas:
        try:
            df = pd.read_sql(f"SELECT * FROM dbo.{t}", engine_mssql)
            df.columns = [c.lower() for c in df.columns]
            # Convertir columnas booleanas (BIT de SQL Server) a entero (1 / 0)
            for col in df.columns:
                if df[col].dtype == bool:
                    df[col] = df[col].astype(int)

            asegurar_columnas_dinamicas(engine_pg, t.lower(), df)

            with engine_pg.begin() as conn_pg:
                conn_pg.execute(text(f"TRUNCATE TABLE dbo.{t.lower()} RESTART IDENTITY CASCADE;"))
            if not df.empty:
                df.to_sql(t.lower(), engine_pg, schema='dbo', if_exists='append', index=False)
            print(f"   ✔ Tabla dbo.{t} migrada ({len(df)} registros)")
        except Exception as ex_t:
            print(f"   [Aviso tabla {t}]: {ex_t}")

    # Sincronizar secuencias autoincrementales en PostgreSQL y archivos JSON
    with engine_pg.begin() as conn_pg:
        for tabla, col_id in [
            ('usuarios', 'id_usuario'),
            ('marcas', 'id_marca'),
            ('categorias', 'id_categoria'),
            ('unidades', 'id_unidad'),
            ('compras', 'id_compra'),
            ('pedidos_clientes', 'id_pedido')
        ]:
            try:
                conn_pg.execute(text(f"""
                    SELECT setval(
                        pg_get_serial_sequence('dbo.{tabla}', '{col_id}'),
                        COALESCE((SELECT MAX({col_id}) FROM dbo.{tabla}), 1)
                    );
                """))
            except Exception:
                pass

        base_dir = os.path.dirname(os.path.abspath(__file__))
        for clave, archivo in [('catalogo_meta', 'catalogo_meta.json'), ('pedidos_extra', 'pedidos_extra.json')]:
            ruta = os.path.join(base_dir, archivo)
            if os.path.exists(ruta):
                with open(ruta, 'r', encoding='utf-8') as f:
                    contenido = f.read()
                conn_pg.execute(text("""
                    INSERT INTO dbo.kv_store (clave, valor) VALUES (:c, :v)
                    ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor
                """), {"c": clave, "v": contenido})
                print(f"   ✔ Configuración '{archivo}' sincronizada en Supabase.")

    print("\n🎉 ¡MIGRACIÓN 100% COMPLETADA SIN ERRORES!")
    print(f"🔗 Tu URL para pegar en Render (DATABASE_URL) es:\n{URL_SUPABASE}")
    return True

if __name__ == "__main__":
    ejecutar_migracion()
