import os
import urllib.parse
import pandas as pd
import sqlalchemy as sa
from sqlalchemy import text

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, '.env')
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, 'r', encoding='utf-8') as f:
        for linea in f:
            linea = linea.strip()
            if linea and not linea.startswith('#') and '=' in linea:
                k, v = linea.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
ES_POSTGRES = False

def inicializar_esquema_postgres(eng):
    """Garantiza que las tablas existan en Supabase automáticamente sin tener que pegar SQL a mano."""
    try:
        with eng.begin() as conn:
            existe = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'dbo' AND table_name = 'repuestos'"
            )).scalar()
            if not existe:
                ruta_sql = os.path.join(BASE_DIR, "supabase_setup.sql")
                if os.path.exists(ruta_sql):
                    with open(ruta_sql, "r", encoding="utf-8") as f:
                        conn.execute(text(f.read()))
                    print("✅ Tablas y datos iniciales creados automáticamente en Supabase.")
    except Exception as e:
        print(f"Aviso inicialización Supabase: {e}")

if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
    elif DATABASE_URL.startswith("postgresql://") and "+psycopg2" not in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
    engine = sa.create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=280,
        pool_timeout=20,
        connect_args={
            "connect_timeout": 10,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
    )
    ES_POSTGRES = True
    import threading
    threading.Thread(target=inicializar_esquema_postgres, args=(engine,), daemon=True).start()
else:
    # Conexión local en Windows (SQL Server Express)
    import pyodbc
    drivers_disponibles = pyodbc.drivers()
    driver_preferido = "ODBC Driver 17 for SQL Server"
    for candidato in ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server Native Client 11.0", "SQL Server"]:
        if candidato in drivers_disponibles:
            driver_preferido = candidato
            break

    params = urllib.parse.quote_plus(
        f'DRIVER={{{driver_preferido}}};'
        r'SERVER=.\SQLEXPRESS;'
        r'DATABASE=InventarioMotos_Pro;'
        r'Trusted_Connection=yes;'
        r'Encrypt=no;'
        r'TrustServerCertificate=yes;'
    )
    engine = sa.create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

def adaptar_sql(sql_str):
    if not ES_POSTGRES:
        return sql_str
    import re
    s = str(sql_str)
    s = re.sub(r'\bGETDATE\(\)', 'CURRENT_TIMESTAMP', s, flags=re.IGNORECASE)
    m = re.search(r'\bSELECT\s+TOP\s+(\d+)\b', s, flags=re.IGNORECASE)
    if m:
        limite = m.group(1)
        s = re.sub(r'\bSELECT\s+TOP\s+\d+\b', 'SELECT', s, count=1, flags=re.IGNORECASE)
        s = s.rstrip().rstrip(';') + f' LIMIT {limite}'
    return s

def consultar(sql, params_dict=None):
    try:
        sql_ejecutar = text(adaptar_sql(str(sql)))
        with engine.connect() as conn:
            return pd.read_sql(sql_ejecutar, conn, params=params_dict)
    except Exception as e:
        print(f"Error en consulta: {e}")
        return pd.DataFrame()
