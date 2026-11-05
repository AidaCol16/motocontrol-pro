import os
import json
import pandas as pd
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from sqlalchemy import text
from database import engine, consultar, ES_POSTGRES

app = Flask(__name__)
app.secret_key = 'moto_control_secret_2026'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
CATALOGO_JSON = os.path.join(BASE_DIR, 'catalogo_meta.json')
PEDIDOS_EXTRA_JSON = os.path.join(BASE_DIR, 'pedidos_extra.json')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

ROLES_VENTAS = ['admin', 'analista_compras', 'usuario_pedidos', 'vendedor']
ROLES_COMPRAS = ['admin', 'analista_compras']
IVA_VENEZUELA = 0.16  # 16% IVA estándar en Venezuela

COSTOS_REFERENCIA_DEFAULT = {
    1: 18.00,   # KIT DE ARRASTRE
    2: 22.00,   # Bateria-Seca
    3: 15.00,   # kit de rodaje
    4: 25.00,   # CUACHO 18/90
    5: 5.00,    # CDI-ELECTONICO
    6: 24.00,   # CAUCHO-110
    7: 4.50,    # PASTILLAS DE FRENO-150
    8: 26.00,   # CAUCHO-17
    9: 4.80,    # CDI-MECANICO
    90: 4.80,   # CDI-MECANICO
    501: 8.50,  # Pastillas Freno XT
    502: 14.00, # Cadena Reforzada
    503: 7.50,  # Filtro Aire Premium
    504: 16.50, # KIT DE ARRASTRE
}

CONFIG_PAGO_DEFAULT = {
    "banco": "0102 - Banco de Venezuela",
    "rif_negocio": "J-50123456-0",
    "telefono_pm": "0412-5551234",
    "titular": "MOTOCONTROL PRO C.A.",
    "tasa_bcv": 45.50
}

def cargar_meta_catalogo():
    if ES_POSTGRES:
        try:
            df_kv = consultar("SELECT valor FROM dbo.kv_store WHERE clave = 'catalogo_meta'")
            if not df_kv.empty and df_kv['valor'].iloc[0]:
                return json.loads(df_kv['valor'].iloc[0])
        except Exception:
            pass
    if os.path.exists(CATALOGO_JSON):
        try:
            with open(CATALOGO_JSON, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def guardar_meta_catalogo(meta):
    texto_json = json.dumps(meta, ensure_ascii=False, indent=2)
    try:
        with open(CATALOGO_JSON, 'w', encoding='utf-8') as f:
            f.write(texto_json)
    except Exception as e:
        print(f"Error guardando meta de catálogo: {e}")
    if ES_POSTGRES:
        try:
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO dbo.kv_store (clave, valor) VALUES ('catalogo_meta', :v)
                    ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor
                """), {"v": texto_json})
        except Exception as e:
            print(f"Aviso kv_store meta: {e}")

def obtener_config_pago():
    meta = cargar_meta_catalogo()
    cfg = dict(CONFIG_PAGO_DEFAULT)
    if "_config_pago" in meta and isinstance(meta["_config_pago"], dict):
        cfg.update(meta["_config_pago"])
    return cfg

def cargar_pedidos_extra():
    if ES_POSTGRES:
        try:
            df_kv = consultar("SELECT valor FROM dbo.kv_store WHERE clave = 'pedidos_extra'")
            if not df_kv.empty and df_kv['valor'].iloc[0]:
                return json.loads(df_kv['valor'].iloc[0])
        except Exception:
            pass
    if os.path.exists(PEDIDOS_EXTRA_JSON):
        try:
            with open(PEDIDOS_EXTRA_JSON, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def guardar_pedidos_extra(datos):
    texto_json = json.dumps(datos, ensure_ascii=False, indent=2)
    try:
        with open(PEDIDOS_EXTRA_JSON, 'w', encoding='utf-8') as f:
            f.write(texto_json)
    except Exception as e:
        print(f"Error guardando pedidos extra: {e}")
    if ES_POSTGRES:
        try:
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO dbo.kv_store (clave, valor) VALUES ('pedidos_extra', :v)
                    ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor
                """), {"v": texto_json})
        except Exception as e:
            print(f"Aviso kv_store pedidos: {e}")

def guardar_imagen_subida(archivo, prefijo="repuesto"):
    if archivo and archivo.filename:
        ext = os.path.splitext(secure_filename(archivo.filename))[1].lower()
        if ext in ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp']:
            nombre_archivo = f"{prefijo}_{int(datetime.now().timestamp())}{ext}"
            ruta_destino = os.path.join(app.config['UPLOAD_FOLDER'], nombre_archivo)
            archivo.save(ruta_destino)
            return f"/static/uploads/{nombre_archivo}"
    return None

def calcular_precios_venezuela(costo_base, aplica_iva=True, tarifa_activa=3):
    costo = float(costo_base or 0)
    factor_iva = (1.0 + IVA_VENEZUELA) if aplica_iva else 1.0
    costo_full = round(costo * factor_iva, 2)

    precio1 = round(costo_full * 1.20, 2)
    precio2 = round(costo_full * 1.25, 2)
    precio3 = round(costo_full * 1.30, 2)

    mapa_tarifas = {1: precio1, 2: precio2, 3: precio3}
    tarifa_num = int(tarifa_activa) if int(tarifa_activa) in (1, 2, 3) else 3
    precio_venta = mapa_tarifas[tarifa_num]

    return {
        "costo_base": round(costo, 2),
        "aplica_iva": bool(aplica_iva),
        "costo_full": costo_full,
        "precio1": precio1,
        "precio2": precio2,
        "precio3": precio3,
        "tarifa_activa": tarifa_num,
        "precio_venta": precio_venta
    }

def obtener_ultimos_costos():
    df_c = consultar("""
        SELECT id_repuesto, precio_compra 
        FROM (
            SELECT id_repuesto, precio_compra,
                   ROW_NUMBER() OVER (PARTITION BY id_repuesto ORDER BY fecha DESC) as rn
            FROM dbo.compras
        ) t
        WHERE rn = 1
    """)
    costos = {}
    if df_c is not None and not df_c.empty:
        for r in df_c.to_dict(orient='records'):
            try:
                costos[int(r['id_repuesto'])] = float(r['precio_compra'] or 0)
            except Exception:
                pass
    return costos

def normalizar_productos(df):
    if df is None or df.empty:
        return []
    meta = cargar_meta_catalogo()
    cfg_pago = obtener_config_pago()
    tasa_bcv = float(cfg_pago.get("tasa_bcv") or 45.50)
    ultimos_costos = obtener_ultimos_costos()
    meta_modificada = False
    productos = []

    for row in df.to_dict(orient='records'):
        id_r = int(row.get('id_repuesto', 0))
        key = str(id_r)
        info_extra = meta.get(key, {}) if isinstance(meta.get(key), dict) else {}

        raw_cat = str(row.get('categoria') or '').strip().upper()
        if not raw_cat or raw_cat in ('NONE', 'NULL', 'NAN'):
            raw_cat = info_extra.get('categoria') or 'SIN CATEGORIA'

        raw_uni = str(row.get('unidad') or '').strip().upper()
        if not raw_uni or raw_uni in ('NONE', 'NULL', 'NAN'):
            raw_uni = 'UND'

        raw_marca = str(row.get('marca') or '').strip().upper()
        if not raw_marca or raw_marca in ('NONE', 'NULL', 'NAN'):
            raw_marca = 'GENÉRICO'

        stock = int(row.get('stock') or 0)
        reservado = int(row.get('reservado') or 0)
        disponible = stock - reservado

        costo_guardado = float(info_extra.get('costo_base') or 0)
        costo_compra_bd = ultimos_costos.get(id_r, 0.0)
        if costo_guardado > 0:
            costo_base = costo_guardado
        elif costo_compra_bd > 0:
            costo_base = costo_compra_bd
        else:
            costo_base = COSTOS_REFERENCIA_DEFAULT.get(id_r, 10.00)

        aplica_iva = info_extra.get('aplica_iva', True)
        tarifa_activa = int(info_extra.get('tarifa_activa', 3))

        precios = calcular_precios_venezuela(costo_base, aplica_iva=aplica_iva, tarifa_activa=tarifa_activa)

        if 'precio1' not in info_extra or float(info_extra.get('precio_venta') or 0) <= 0:
            info_extra.update({
                'costo_base': precios['costo_base'],
                'aplica_iva': precios['aplica_iva'],
                'costo_full': precios['costo_full'],
                'precio1': precios['precio1'],
                'precio2': precios['precio2'],
                'precio3': precios['precio3'],
                'tarifa_activa': precios['tarifa_activa'],
                'precio_venta': precios['precio_venta'],
                'categoria': raw_cat
            })
            meta[key] = info_extra
            meta_modificada = True

        imagen_url = str(info_extra.get('imagen_url') or '').strip()
        precio_bs = round(precios['precio_venta'] * tasa_bcv, 2)

        productos.append({
            'id_repuesto': id_r,
            'descripcion': str(row.get('descripcion') or '').strip(),
            'marca': raw_marca,
            'categoria': raw_cat,
            'unidad': raw_uni,
            'stock': stock,
            'reservado': reservado,
            'disponible': disponible,
            'costo_base': precios['costo_base'],
            'aplica_iva': precios['aplica_iva'],
            'costo_full': precios['costo_full'],
            'precio1': precios['precio1'],
            'precio2': precios['precio2'],
            'precio3': precios['precio3'],
            'tarifa_activa': precios['tarifa_activa'],
            'precio_venta': precios['precio_venta'],
            'precio_bs': precio_bs,
            'imagen_url': imagen_url
        })

    if meta_modificada:
        guardar_meta_catalogo(meta)

    return productos

@app.context_processor
def inyectar_config_global():
    return {"config_pago_global": obtener_config_pago()}

# --- SEGURIDAD ---
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- ACCESO (LOGIN / LOGOUT) ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form['username'].strip()
        pwd = request.form['password'].strip()
        sql = text("SELECT id_usuario, username, rol FROM dbo.Usuarios WHERE username = :u AND password = :p")
        res = consultar(sql, {"u": user, "p": pwd})
        if not res.empty:
            session['user_id'] = int(res['id_usuario'].iloc[0])
            session['username'] = res['username'].iloc[0]
            rol_db = str(res['rol'].iloc[0]).strip().lower()
            if rol_db == 'vendedor':
                rol_db = 'usuario_pedidos'
            session['rol'] = rol_db
            if rol_db == 'cliente':
                return redirect(url_for('tienda'))
            return redirect(url_for('index'))
        return render_template('login.html', error="Credenciales inválidas")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- 1. INVENTARIO ---
@app.route('/')
@login_required
def index():
    if session.get('rol') == 'cliente':
        return redirect(url_for('tienda'))
    df = consultar("SELECT * FROM dbo.repuestos ORDER BY id_repuesto ASC")
    productos = normalizar_productos(df)
    kpis = {
        "total": len(productos),
        "disponibles": sum(1 for p in productos if p['disponible'] > 5),
        "bajo_stock": sum(1 for p in productos if 0 < p['disponible'] <= 5),
        "agotados": sum(1 for p in productos if p['disponible'] <= 0),
        "unidades_totales": sum(int(p['disponible']) for p in productos if p['disponible'] > 0)
    }
    return render_template('inventario.html', productos=productos, kpis=kpis)

# --- 1.5 CATÁLOGO DE PRODUCTOS Y PORTAL CLIENTE (/tienda) ---
@app.route('/catalogo')
@login_required
def catalogo():
    df = consultar("SELECT * FROM dbo.repuestos ORDER BY id_repuesto ASC")
    productos = normalizar_productos(df)
    productos.sort(key=lambda x: (x['disponible'] <= 0, x['id_repuesto']))
    marcas = sorted(list({p['marca'] for p in productos if p['marca']}))
    categorias = sorted(list({p['categoria'] for p in productos if p['categoria']}))
    config_pago = obtener_config_pago()
    return render_template('catalogo.html', productos=productos, marcas=marcas, categorias=categorias, config_pago=config_pago)

@app.route('/tienda')
def tienda():
    """Portal público o vista exclusiva para el Cliente en la calle."""
    df = consultar("SELECT * FROM dbo.repuestos ORDER BY id_repuesto ASC")
    productos = normalizar_productos(df)
    productos.sort(key=lambda x: (x['disponible'] <= 0, x['id_repuesto']))
    marcas = sorted(list({p['marca'] for p in productos if p['marca']}))
    categorias = sorted(list({p['categoria'] for p in productos if p['categoria']}))
    config_pago = obtener_config_pago()
    return render_template('tienda.html', productos=productos, marcas=marcas, categorias=categorias, config_pago=config_pago)

@app.route('/tasa_pago', methods=['GET', 'POST'])
@login_required
def modulo_tasa_pago():
    """Módulo exclusivo del Administrador para fijar la Tasa BCV y los datos de Pago Móvil."""
    if session.get('rol') != 'admin':
        return redirect(url_for('index'))

    if request.method == 'POST':
        try:
            meta = cargar_meta_catalogo()
            nueva_tasa = float(request.form.get('tasa_bcv') or CONFIG_PAGO_DEFAULT['tasa_bcv'])
            if nueva_tasa <= 0:
                return jsonify({"exito": False, "mensaje": "La tasa debe ser mayor a 0."})

            anterior_cfg = obtener_config_pago()
            historial = anterior_cfg.get("historial_tasas", [])
            historial.insert(0, {
                "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "tasa_bcv": nueva_tasa,
                "usuario": session.get('username', 'admin')
            })

            meta["_config_pago"] = {
                "banco": request.form.get('banco', anterior_cfg['banco']).strip(),
                "rif_negocio": request.form.get('rif_negocio', anterior_cfg['rif_negocio']).strip().upper(),
                "telefono_pm": request.form.get('telefono_pm', anterior_cfg['telefono_pm']).strip(),
                "titular": request.form.get('titular', anterior_cfg['titular']).strip().upper(),
                "tasa_bcv": nueva_tasa,
                "ultima_actualizacion": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "actualizado_por": session.get('username', 'admin'),
                "historial_tasas": historial[:15]
            }
            guardar_meta_catalogo(meta)
            return jsonify({
                "exito": True,
                "mensaje": f"✅ Tasa BCV actualizada a Bs. {nueva_tasa:.2f} por $1 y datos de Pago Móvil guardados."
            })
        except Exception as e:
            return jsonify({"exito": False, "mensaje": f"Error: {str(e)}"})

    config_pago = obtener_config_pago()
    df = consultar("SELECT * FROM dbo.repuestos ORDER BY id_repuesto ASC")
    productos = normalizar_productos(df)
    return render_template('tasa_pago.html', config_pago=config_pago, productos=productos)

@app.route('/api/configurar_pago_movil', methods=['POST'])
@login_required
def configurar_pago_movil():
    if session.get('rol') != 'admin':
        return jsonify({"exito": False, "mensaje": "Solo el Administrador puede modificar la Tasa y el Pago Móvil."})
    try:
        meta = cargar_meta_catalogo()
        anterior_cfg = obtener_config_pago()
        nueva_tasa = float(request.form.get('tasa_bcv') or anterior_cfg['tasa_bcv'])
        historial = anterior_cfg.get("historial_tasas", [])
        historial.insert(0, {
            "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "tasa_bcv": nueva_tasa,
            "usuario": session.get('username', 'admin')
        })
        meta["_config_pago"] = {
            "banco": request.form.get('banco', anterior_cfg['banco']).strip(),
            "rif_negocio": request.form.get('rif_negocio', anterior_cfg['rif_negocio']).strip().upper(),
            "telefono_pm": request.form.get('telefono_pm', anterior_cfg['telefono_pm']).strip(),
            "titular": request.form.get('titular', anterior_cfg['titular']).strip().upper(),
            "tasa_bcv": nueva_tasa,
            "ultima_actualizacion": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "actualizado_por": session.get('username', 'admin'),
            "historial_tasas": historial[:15]
        }
        guardar_meta_catalogo(meta)
        return jsonify({"exito": True, "mensaje": "✅ Datos de Pago Móvil y Tasa BCV actualizados por el Administrador."})
    except Exception as e:
        return jsonify({"exito": False, "mensaje": str(e)})

@app.route('/api/actualizar_catalogo', methods=['POST'])
@login_required
def actualizar_catalogo():
    if session.get('rol') not in ROLES_COMPRAS:
        return jsonify({"exito": False, "mensaje": "No tienes permisos para editar el catálogo."})
    try:
        id_r = int(request.form['id_repuesto'])
        costo_base = float(request.form.get('costo_base') or 0)
        aplica_iva = request.form.get('condicion_iva', 'iva') == 'iva'
        tarifa_activa = int(request.form.get('tarifa_activa') or 3)
        cat = request.form.get('categoria', '').upper().strip()
        imagen_url = request.form.get('imagen_url', '').strip()

        archivo = request.files.get('imagen_file')
        nueva_ruta = guardar_imagen_subida(archivo, f"repuesto_{id_r}")
        if nueva_ruta:
            imagen_url = nueva_ruta

        precios = calcular_precios_venezuela(costo_base, aplica_iva=aplica_iva, tarifa_activa=tarifa_activa)

        meta = cargar_meta_catalogo()
        key = str(id_r)
        actual = meta.get(key, {}) if isinstance(meta.get(key), dict) else {}
        actual.update(precios)
        if imagen_url:
            actual['imagen_url'] = imagen_url
        if cat:
            actual['categoria'] = cat
        meta[key] = actual
        guardar_meta_catalogo(meta)

        if cat and cat not in ('SIN CATEGORIA', 'GENERAL'):
            with engine.begin() as conn:
                conn.execute(
                    text("UPDATE dbo.repuestos SET categoria = :c WHERE id_repuesto = :id"),
                    {"c": cat, "id": id_r}
                )

        return jsonify({
            "exito": True,
            "mensaje": f"✅ Catálogo actualizado. Precio anclado (Precio {tarifa_activa}): ${precios['precio_venta']:.2f}"
        })
    except Exception as e:
        return jsonify({"exito": False, "mensaje": f"Error: {str(e)}"})

# --- 2. GESTIÓN DE PRODUCTOS ---
@app.route('/nuevo_producto', methods=['GET', 'POST'])
@login_required
def nuevo_producto():
    if session.get('rol') not in ROLES_COMPRAS:
        return redirect(url_for('index'))

    if request.method == 'POST':
        try:
            id_n = int(request.form['id_n'])
            desc = request.form['desc'].upper().strip()
            marc = request.form['marc'].upper().strip()
            cat  = request.form['cat'].upper().strip()
            uni  = request.form['uni'].upper().strip()
            costo_base = float(request.form.get('costo_base') or 0)
            aplica_iva = request.form.get('condicion_iva', 'iva') == 'iva'
            tarifa_activa = int(request.form.get('tarifa_activa') or 3)
            
            with engine.begin() as conn:
                check = conn.execute(text("SELECT COUNT(*) FROM dbo.repuestos WHERE id_repuesto = :id"), {"id": id_n}).scalar()
                if check > 0:
                    conn.execute(text("""
                        UPDATE dbo.repuestos 
                        SET descripcion=:d, marca=:m, categoria=:c, unidad=:u
                        WHERE id_repuesto=:id
                    """), {"d":desc, "m":marc, "c":cat, "u":uni, "id":id_n})
                    msg = "✅ Producto y precios de venta actualizados correctamente."
                else:
                    pd.DataFrame({
                        'id_repuesto':[id_n],'descripcion':[desc],'marca':[marc],
                        'categoria':[cat],'unidad':[uni],'stock':[0],'reservado':[0]
                    }).to_sql('repuestos', conn, if_exists='append', index=False, schema='dbo')
                    msg = "✅ Producto registrado con sus 3 precios de venta."

            archivo = request.files.get('imagen_file')
            nueva_ruta = guardar_imagen_subida(archivo, f"repuesto_{id_n}")
            precios = calcular_precios_venezuela(costo_base, aplica_iva=aplica_iva, tarifa_activa=tarifa_activa)

            meta = cargar_meta_catalogo()
            key = str(id_n)
            actual = meta.get(key, {}) if isinstance(meta.get(key), dict) else {}
            actual.update(precios)
            actual['categoria'] = cat
            if nueva_ruta:
                actual['imagen_url'] = nueva_ruta
            meta[key] = actual
            guardar_meta_catalogo(meta)

            return jsonify({"exito": True, "mensaje": msg})
        except Exception as e: 
            return jsonify({"exito": False, "mensaje": str(e)})
    
    marcas = consultar("SELECT nombre_marca FROM dbo.marcas ORDER BY nombre_marca").to_dict(orient='records')
    categorias = consultar("SELECT nombre_categoria FROM dbo.categorias ORDER BY nombre_categoria").to_dict(orient='records')
    unidades = consultar("SELECT nombre_unidad FROM dbo.unidades ORDER BY nombre_unidad").to_dict(orient='records')
    df_prod = consultar("SELECT * FROM dbo.repuestos ORDER BY id_repuesto DESC")
    productos = normalizar_productos(df_prod)
    
    return render_template('nuevo_prod.html', productos=productos, marcas=marcas, categorias=categorias, unidades=unidades)

# --- 3. SOCIOS ---
@app.route('/socios', methods=['GET', 'POST'])
@login_required
def socios():
    if session.get('rol') not in ROLES_COMPRAS:
        return redirect(url_for('index'))

    if request.method == 'POST':
        try:
            rif = request.form['rif'].upper().strip()
            nom = request.form['nom'].upper().strip()
            tlf = request.form['tlf'].strip()
            dire = request.form['dir'].upper().strip()
            es_p = 1 if 'es_proveedor' in request.form else 0
            es_c = 1 if 'es_cliente' in request.form else 0
            with engine.begin() as conn:
                check = conn.execute(text("SELECT COUNT(*) FROM dbo.socios WHERE id_proveedor = :r"), {"r": rif}).scalar()
                if check > 0:
                    conn.execute(text("UPDATE dbo.socios SET nombre_empresa=:n, telefono=:t, ubicacion=:d, es_proveedor=:p, es_cliente=:c WHERE id_proveedor=:r"), 
                                 {"n":nom, "t":tlf, "d":dire, "p":es_p, "c":es_c, "r":rif})
                else:
                    pd.DataFrame({'id_proveedor':[rif],'nombre_empresa':[nom],'ubicacion':[dire],'telefono':[tlf],'es_cliente':[es_c],'es_proveedor':[es_p]}).to_sql('socios', conn, if_exists='append', index=False, schema='dbo')
            return jsonify({"exito": True, "mensaje": "✅ Socio guardado correctamente."})
        except Exception as e:
            return jsonify({"exito": False, "mensaje": str(e)})
    return render_template('socios.html', socios=consultar("SELECT * FROM dbo.socios ORDER BY nombre_empresa").to_dict(orient='records'))

# --- 4. COMPRAS ---
@app.route('/compras', methods=['GET', 'POST'])
@login_required
def compras():
    if session.get('rol') not in ROLES_COMPRAS:
        return redirect(url_for('index'))

    if request.method == 'POST':
        try:
            id_p = int(request.form['id_p'])
            rif = request.form['rif'].upper().strip()
            fact = request.form['factura'].upper().strip()
            cant = int(request.form['cant'])
            prec = float(request.form['prec'])
            aplica_iva = request.form.get('condicion_iva', 'iva') == 'iva'
            tarifa_activa = int(request.form.get('tarifa_activa') or 3)

            if cant <= 0:
                return jsonify({"exito": False, "mensaje": "La cantidad debe ser mayor a 0."})
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO dbo.compras (id_repuesto, id_proveedor, factura, cantidad_comprada, precio_compra, fecha) VALUES (:id,:rif,:f,:c,:p,CURRENT_TIMESTAMP)"),
                             {"id":id_p,"rif":rif,"f":fact,"c":cant,"p":prec})
                conn.execute(text("UPDATE dbo.repuestos SET stock = COALESCE(stock, 0) + :c WHERE id_repuesto = :id"), {"c":cant, "id":id_p})

            precios = calcular_precios_venezuela(prec, aplica_iva=aplica_iva, tarifa_activa=tarifa_activa)
            meta = cargar_meta_catalogo()
            key = str(id_p)
            actual = meta.get(key, {}) if isinstance(meta.get(key), dict) else {}
            actual.update(precios)
            meta[key] = actual
            guardar_meta_catalogo(meta)

            return jsonify({
                "exito": True,
                "mensaje": f"✅ Compra registrada. Precios actualizados (P1: ${precios['precio1']:.2f} | P2: ${precios['precio2']:.2f} | P3: ${precios['precio3']:.2f})."
            })
        except Exception as e:
            return jsonify({"exito": False, "mensaje": str(e)})

    historial_sql = """
        SELECT TOP 15 c.factura, c.id_repuesto, COALESCE(r.descripcion, 'Repuesto #' + CAST(c.id_repuesto AS VARCHAR)) as descripcion,
               c.id_proveedor, COALESCE(s.nombre_empresa, c.id_proveedor) as proveedor,
               c.cantidad_comprada, c.precio_compra, c.fecha
        FROM dbo.compras c
        LEFT JOIN dbo.repuestos r ON c.id_repuesto = r.id_repuesto
        LEFT JOIN dbo.socios s ON c.id_proveedor = s.id_proveedor
        ORDER BY c.fecha DESC
    """
    compras_recientes = consultar(historial_sql).to_dict(orient='records')
    return render_template('compras.html', compras_recientes=compras_recientes)

# --- 5. PEDIDOS Y ÓRDENES CON PAGO MÓVIL ---
def procesar_orden_pedido(req):
    id_p = int(req.form['id_p'])
    cant = int(req.form['cant'])
    c_rif = req.form['cliente_rif'].upper().strip()
    c_nom = req.form['cliente'].upper().strip()
    tlf_cli = req.form.get('telefono', '').strip()
    metodo_pago = req.form.get('metodo_pago', 'Pago Móvil').strip()
    referencia_pm = req.form.get('referencia_pm', '').strip()
    banco_origen = req.form.get('banco_origen', '').strip()

    if cant <= 0:
        return {"exito": False, "mensaje": "❌ La cantidad debe ser mayor a cero."}

    df_prod = consultar(text("SELECT * FROM dbo.repuestos WHERE id_repuesto = :id"), {"id": id_p})
    if df_prod.empty:
        return {"exito": False, "mensaje": "❌ El repuesto seleccionado no existe."}

    prod_info = normalizar_productos(df_prod)[0]
    disponible = prod_info['disponible']
    if cant > disponible:
        return {
            "exito": False,
            "mensaje": f"❌ Stock insuficiente para '{prod_info['descripcion']}'. Disponible actual: {disponible} und(s)."
        }

    with engine.begin() as conn:
        # Registrar o actualizar al cliente en dbo.socios para tener su teléfono
        if c_rif:
            check_s = conn.execute(text("SELECT COUNT(*) FROM dbo.socios WHERE id_proveedor = :r"), {"r": c_rif}).scalar()
            if check_s == 0:
                conn.execute(text("""
                    INSERT INTO dbo.socios (id_proveedor, nombre_empresa, ubicacion, telefono, es_cliente, es_proveedor)
                    VALUES (:r, :n, 'CLIENTE TIENDA', :t, 1, 0)
                """), {"r": c_rif, "n": c_nom, "t": tlf_cli or 'S/N'})
            elif tlf_cli:
                conn.execute(text("UPDATE dbo.socios SET telefono = :t, es_cliente = 1 WHERE id_proveedor = :r"), {"t": tlf_cli, "r": c_rif})

        if ES_POSTGRES:
            res_id = conn.execute(text("""
                INSERT INTO dbo.pedidos_clientes (id_repuesto, cliente, cliente_rif, cantidad, estado, fecha_pedido) 
                VALUES (:id, :n, :r, :c, 'BORRADOR', CURRENT_TIMESTAMP)
                RETURNING id_pedido
            """), {"id": id_p, "n": c_nom, "r": c_rif, "c": cant}).scalar()
        else:
            res_id = conn.execute(text("""
                INSERT INTO dbo.pedidos_clientes (id_repuesto, cliente, cliente_rif, cantidad, estado, fecha_pedido) 
                OUTPUT INSERTED.id_pedido
                VALUES (:id, :n, :r, :c, 'BORRADOR', CURRENT_TIMESTAMP)
            """), {"id": id_p, "n": c_nom, "r": c_rif, "c": cant}).scalar()

        conn.execute(text("UPDATE dbo.repuestos SET reservado = COALESCE(reservado, 0) + :c WHERE id_repuesto = :id"), 
                     {"c": cant, "id": id_p})

    cfg = obtener_config_pago()
    tasa = float(cfg.get('tasa_bcv') or 45.50)
    total_usd = round(cant * prod_info['precio_venta'], 2)
    total_bs = round(total_usd * tasa, 2)

    if res_id is not None:
        extras = cargar_pedidos_extra()
        extras[str(int(res_id))] = {
            "telefono": tlf_cli,
            "metodo_pago": metodo_pago,
            "referencia_pm": referencia_pm,
            "banco_origen": banco_origen,
            "precio_unitario_usd": prod_info['precio_venta'],
            "total_usd": total_usd,
            "total_bs": total_bs,
            "tasa_bcv": tasa
        }
        guardar_pedidos_extra(extras)

    return {
        "exito": True,
        "id_pedido": int(res_id) if res_id else 0,
        "total_usd": total_usd,
        "total_bs": total_bs,
        "mensaje": f"✅ Orden #{res_id} registrada exitosamente. Total: ${total_usd:.2f} (Bs. {total_bs:.2f}). Nuestro vendedor verificará tu Pago Móvil y te contactará."
    }

@app.route('/pedido_cliente', methods=['GET', 'POST'])
@login_required
def pedido_cliente():
    if session.get('rol') not in ROLES_VENTAS and session.get('rol') != 'cliente':
        return redirect(url_for('index'))

    if request.method == 'POST':
        try:
            return jsonify(procesar_orden_pedido(request))
        except Exception as e: 
            return jsonify({"exito": False, "mensaje": f"Error en BD: {str(e)}"})
            
    return render_template('pedido_cliente.html')

@app.route('/api/solicitar_compra_cliente', methods=['POST'])
def solicitar_compra_cliente():
    """Endpoint para que el cliente en la calle solicite su compra y registre su Pago Móvil."""
    try:
        return jsonify(procesar_orden_pedido(request))
    except Exception as e:
        return jsonify({"exito": False, "mensaje": f"Error al procesar orden: {str(e)}"})

@app.route('/api/mis_pedidos/<rif>')
def mis_pedidos_cliente(rif):
    """Permite al cliente consultar el estado de sus pedidos con su RIF/Cédula."""
    r_clean = rif.strip().upper()
    sql = text("""
        SELECT TOP 15 p.id_pedido, p.id_repuesto, p.cliente, p.cliente_rif, p.cantidad, p.estado, p.fecha_pedido,
               r.descripcion, r.marca
        FROM dbo.pedidos_clientes p
        JOIN dbo.repuestos r ON p.id_repuesto = r.id_repuesto
        WHERE UPPER(p.cliente_rif) = :r
        ORDER BY p.fecha_pedido DESC
    """)
    df = consultar(sql, {"r": r_clean})
    extras = cargar_pedidos_extra()
    lista = []
    for row in df.to_dict(orient='records'):
        idp = str(int(row['id_pedido']))
        ex = extras.get(idp, {})
        lista.append({
            "id_pedido": int(row['id_pedido']),
            "descripcion": row['descripcion'],
            "marca": row['marca'],
            "cantidad": int(row['cantidad']),
            "estado": row['estado'],
            "fecha": row['fecha_pedido'].strftime('%d/%m/%Y %H:%M') if row.get('fecha_pedido') else '-',
            "metodo_pago": ex.get("metodo_pago", "Pago Móvil"),
            "referencia_pm": ex.get("referencia_pm", "-"),
            "total_usd": ex.get("total_usd", 0),
            "total_bs": ex.get("total_bs", 0)
        })
    return jsonify({"encontrado": len(lista) > 0, "pedidos": lista})

@app.route('/lista_pedidos')
@login_required
def lista_pedidos():
    if session.get('rol') not in ROLES_VENTAS:
        return redirect(url_for('index'))

    query_borrador = """
        SELECT p.*, r.descripcion, r.marca, s.telefono as telefono_socio
        FROM dbo.pedidos_clientes p 
        JOIN dbo.repuestos r ON p.id_repuesto = r.id_repuesto 
        LEFT JOIN dbo.socios s ON p.cliente_rif = s.id_proveedor
        WHERE p.estado = 'BORRADOR' 
        ORDER BY p.fecha_pedido DESC
    """
    query_completados = """
        SELECT TOP 20 p.*, r.descripcion, r.marca, s.telefono as telefono_socio
        FROM dbo.pedidos_clientes p 
        JOIN dbo.repuestos r ON p.id_repuesto = r.id_repuesto 
        LEFT JOIN dbo.socios s ON p.cliente_rif = s.id_proveedor
        WHERE p.estado = 'COMPLETADO' 
        ORDER BY p.fecha_pedido DESC
    """
    df_b = consultar(query_borrador)
    df_c = consultar(query_completados)

    df_rep = consultar("SELECT * FROM dbo.repuestos")
    mapa_precios = {p['id_repuesto']: p['precio_venta'] for p in normalizar_productos(df_rep)}
    cfg = obtener_config_pago()
    tasa = float(cfg.get('tasa_bcv') or 45.50)
    extras = cargar_pedidos_extra()

    def limpiar_valor(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ''
        s = str(v).strip()
        return '' if s.lower() in ('nan', 'none', 'null') else s

    def enriquecer(filas):
        salida = []
        for f in filas:
            idp = str(int(f['id_pedido']))
            ex = extras.get(idp, {})
            p_unit = float(ex.get('precio_unitario_usd') or mapa_precios.get(int(f['id_repuesto']), 0))
            tot_usd = float(ex.get('total_usd') or round(p_unit * int(f['cantidad']), 2))
            tot_bs = float(ex.get('total_bs') or round(tot_usd * tasa, 2))
            f['cliente_rif'] = limpiar_valor(f.get('cliente_rif'))
            tlf = limpiar_valor(ex.get('telefono')) or limpiar_valor(f.get('telefono_socio'))
            tlf_limpio = ''.join(ch for ch in str(tlf) if ch.isdigit())
            if tlf_limpio.startswith('0'):
                tlf_wa = '58' + tlf_limpio[1:]
            elif tlf_limpio.startswith('58'):
                tlf_wa = tlf_limpio
            else:
                tlf_wa = ('58' + tlf_limpio) if tlf_limpio else ''

            f['telefono_contacto'] = tlf
            f['telefono_wa'] = tlf_wa
            f['metodo_pago'] = ex.get('metodo_pago', 'Por confirmar')
            f['referencia_pm'] = ex.get('referencia_pm', '')
            f['banco_origen'] = ex.get('banco_origen', '')
            f['total_usd'] = tot_usd
            f['total_bs'] = tot_bs
            salida.append(f)
        return salida

    return render_template(
        'lista_pedidos.html',
        pedidos=enriquecer(df_b.to_dict(orient='records')),
        completados=enriquecer(df_c.to_dict(orient='records')),
        config_pago=cfg
    )

@app.route('/confirmar_pedido/<int:id_pedido>', methods=['POST'])
@login_required
def confirmar_pedido(id_pedido):
    if session.get('rol') not in ROLES_VENTAS:
        return jsonify({"exito": False, "mensaje": "No tienes permisos"})

    try:
        with engine.begin() as conn:
            pedido = conn.execute(text("SELECT id_repuesto, cantidad FROM dbo.pedidos_clientes WHERE id_pedido = :id AND estado = 'BORRADOR'"), {"id": id_pedido}).fetchone()
            
            if pedido:
                id_r = pedido.id_repuesto
                cant = pedido.cantidad

                conn.execute(text("UPDATE dbo.pedidos_clientes SET estado = 'COMPLETADO' WHERE id_pedido = :id"), {"id": id_pedido})

                conn.execute(text("""
                    UPDATE dbo.repuestos 
                    SET stock = stock - :c, 
                        reservado = reservado - :c 
                    WHERE id_repuesto = :ir
                """), {"c": cant, "ir": id_r})

                return jsonify({"exito": True, "mensaje": "✅ Pago verificado, venta confirmada y stock actualizado."})
            else:
                return jsonify({"exito": False, "mensaje": "Pedido no encontrado o ya procesado."})
    except Exception as e:
        return jsonify({"exito": False, "mensaje": f"Error: {str(e)}"})

@app.route('/eliminar_pedido/<int:id_pedido>', methods=['POST'])
@login_required
def eliminar_pedido(id_pedido):
    if session.get('rol') not in ROLES_VENTAS:
        return jsonify({"exito": False, "mensaje": "No tienes permisos"})

    try:
        with engine.begin() as conn:
            pedido = conn.execute(text("SELECT id_repuesto, cantidad FROM dbo.pedidos_clientes WHERE id_pedido = :id AND estado = 'BORRADOR'"), {"id": id_pedido}).fetchone()
            
            if pedido:
                id_r = pedido.id_repuesto
                cant = pedido.cantidad

                conn.execute(text("UPDATE dbo.repuestos SET reservado = reservado - :c WHERE id_repuesto = :ir"), 
                             {"c": cant, "ir": id_r})

                conn.execute(text("DELETE FROM dbo.pedidos_clientes WHERE id_pedido = :id"), {"id": id_pedido})

                return jsonify({"exito": True, "mensaje": "✅ Pedido anulado y stock liberado correctamente."})
            else:
                return jsonify({"exito": False, "mensaje": "El pedido no existe o ya no está en borrador."})
    except Exception as e:
        return jsonify({"exito": False, "mensaje": f"Error: {str(e)}"})

# --- 6. REPORTES ---
@app.route('/reportes')
@login_required
def reportes():
    if session.get('rol') not in ROLES_COMPRAS:
        return redirect(url_for('index'))

    criticos = consultar("""
        SELECT id_repuesto, descripcion, marca, COALESCE(stock, 0) as stock, 
               COALESCE(reservado, 0) as reservado,
               (COALESCE(stock, 0) - COALESCE(reservado, 0)) as disponible
        FROM dbo.repuestos 
        WHERE (COALESCE(stock, 0) - COALESCE(reservado, 0)) <= 5 
        ORDER BY disponible ASC
    """)
    ventas = consultar("""
        SELECT r.descripcion, SUM(p.cantidad) as total_vendido 
        FROM dbo.pedidos_clientes p 
        JOIN dbo.repuestos r ON p.id_repuesto = r.id_repuesto 
        WHERE p.estado = 'COMPLETADO' 
        GROUP BY r.descripcion 
        ORDER BY total_vendido DESC
    """)
    recientes = consultar("""
        SELECT TOP 10 p.cliente, p.cliente_rif, r.descripcion, p.fecha_pedido, p.cantidad 
        FROM dbo.pedidos_clientes p
        LEFT JOIN dbo.repuestos r ON p.id_repuesto = r.id_repuesto
        WHERE p.estado = 'COMPLETADO' 
        ORDER BY p.fecha_pedido DESC
    """)
    
    return render_template('reportes.html', 
                           criticos=criticos.to_dict(orient='records'), 
                           ventas=ventas.to_dict(orient='records'), 
                           recientes=recientes.to_dict(orient='records'))

# --- 7. GESTIÓN DE USUARIOS ---
@app.route('/usuarios', methods=['GET', 'POST'])
@login_required
def gestion_usuarios():
    if session.get('rol') != 'admin':
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        try:
            u = request.form['username'].strip()
            p = request.form['password'].strip()
            r = request.form['rol'].strip()
            if r == 'vendedor':
                r = 'usuario_pedidos'
            with engine.begin() as conn:
                existe = conn.execute(text("SELECT COUNT(*) FROM dbo.Usuarios WHERE username = :u"), {"u": u}).scalar()
                if existe > 0:
                    conn.execute(text("UPDATE dbo.Usuarios SET password = :p, rol = :r WHERE username = :u"), {"u": u, "p": p, "r": r})
                    return jsonify({"exito": True, "mensaje": "Usuario actualizado correctamente."})
                conn.execute(text("INSERT INTO dbo.Usuarios (username, password, rol) VALUES (:u, :p, :r)"), 
                             {"u": u, "p": p, "r": r})
            return jsonify({"exito": True, "mensaje": "Usuario creado correctamente."})
        except Exception as e: 
            return jsonify({"exito": False, "mensaje": str(e)})
            
    usuarios_db = consultar("SELECT id_usuario, username, rol FROM dbo.Usuarios ORDER BY id_usuario")
    return render_template('admin_usuarios.html', usuarios=usuarios_db.to_dict(orient='records'))

@app.route('/api/eliminar_usuario/<int:id_u>', methods=['POST'])
@login_required
def eliminar_usuario(id_u):
    if session.get('rol') != 'admin':
        return jsonify({"exito": False, "mensaje": "No autorizado"})
    if session.get('user_id') == id_u:
        return jsonify({"exito": False, "mensaje": "No puedes eliminar tu propio usuario activo."})
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM dbo.Usuarios WHERE id_usuario = :id"), {"id": id_u})
        return jsonify({"exito": True, "mensaje": "✅ Usuario eliminado."})
    except Exception as e:
        return jsonify({"exito": False, "mensaje": str(e)})

# --- APIs DE APOYO ---
@app.route('/api/obtener_producto/<int:id_prod>')
@login_required
def obtener_producto(id_prod):
    res = consultar(text("SELECT * FROM dbo.repuestos WHERE id_repuesto = :id"), {"id": id_prod})
    if not res.empty:
        return jsonify({"encontrado": True, "datos": normalizar_productos(res)[0]})
    return jsonify({"encontrado": False})

@app.route('/api/buscar_producto_smart/<query>')
def api_prod_smart(query):
    q = f"%{query.strip().upper()}%"
    sql = text("""
        SELECT TOP 8 *
        FROM dbo.repuestos 
        WHERE CAST(id_repuesto AS VARCHAR) LIKE :q OR descripcion LIKE :q OR marca LIKE :q
    """)
    res = consultar(sql, {"q": q})
    productos = normalizar_productos(res)
    return jsonify({"encontrado": len(productos) > 0, "resultados": productos})

@app.route('/api/buscar_cliente_smart/<query>')
def buscar_cliente_smart(query):
    q = f"%{query.strip().upper()}%"
    sql = text("""
        SELECT TOP 8 id_proveedor, nombre_empresa, telefono 
        FROM dbo.socios 
        WHERE (id_proveedor LIKE :q OR nombre_empresa LIKE :q) 
        AND es_cliente = 1
    """)
    res = consultar(sql, {"q": q})
    return jsonify({"encontrado": len(res) > 0, "resultados": res.to_dict(orient='records')})

@app.route('/api/buscar_proveedor_smart/<query>')
@login_required
def buscar_proveedor_smart(query):
    q = f"%{query.strip().upper()}%"
    sql = text("""
        SELECT TOP 8 id_proveedor, nombre_empresa 
        FROM dbo.socios 
        WHERE (id_proveedor LIKE :q OR nombre_empresa LIKE :q) 
        AND es_proveedor = 1
    """)
    res = consultar(sql, {"q": q})
    return jsonify({"encontrado": len(res) > 0, "resultados": res.to_dict(orient='records')})

@app.route('/api/obtener_cliente/<rif>')
def obtener_cliente(rif):
    sql = text("SELECT nombre_empresa, telefono FROM dbo.socios WHERE id_proveedor = :r AND es_cliente = 1")
    res = consultar(sql, {"r": rif.upper().strip()})
    if not res.empty:
        return jsonify({
            "encontrado": True,
            "nombre": res['nombre_empresa'].iloc[0],
            "telefono": res['telefono'].iloc[0] if 'telefono' in res.columns else ''
        })
    return jsonify({"encontrado": False})

@app.route('/api/obtener_proveedor/<rif>')
@login_required
def obtener_proveedor(rif):
    sql = text("SELECT nombre_empresa FROM dbo.socios WHERE id_proveedor = :r AND es_proveedor = 1")
    res = consultar(sql, {"r": rif.upper().strip()})
    if not res.empty:
        return jsonify({"encontrado": True, "nombre": res['nombre_empresa'].iloc[0]})
    return jsonify({"encontrado": False})

@app.route('/api/buscar_socio/<rif>')
@login_required
def buscar_socio(rif):
    sql = text("SELECT * FROM dbo.socios WHERE id_proveedor = :r")
    res = consultar(sql, {"r": rif.upper().strip()})
    if not res.empty:
        row = res.iloc[0]
        return jsonify({
            "encontrado": True,
            "nom": row.get('nombre_empresa', ''),
            "tlf": row.get('telefono', ''),
            "dir": row.get('ubicacion', ''),
            "cli": int(row.get('es_cliente', 0) or 0),
            "prov": int(row.get('es_proveedor', 0) or 0)
        })
    return jsonify({"encontrado": False})

@app.route('/api/nueva_marca', methods=['POST'])
@login_required
def api_marca():
    try:
        nombre = request.form['nombre'].upper().strip()
        with engine.begin() as conn: 
            conn.execute(text("INSERT INTO dbo.marcas (nombre_marca) VALUES (:n)"), {"n": nombre})
        return jsonify({"exito": True})
    except Exception as e:
        return jsonify({"exito": False, "mensaje": str(e)})

@app.route('/api/nueva_categoria', methods=['POST'])
@login_required
def api_categoria():
    try:
        nombre = request.form['nombre'].upper().strip()
        with engine.begin() as conn: 
            conn.execute(text("INSERT INTO dbo.categorias (nombre_categoria) VALUES (:n)"), {"n": nombre})
        return jsonify({"exito": True})
    except Exception as e:
        return jsonify({"exito": False, "mensaje": str(e)})

@app.route('/api/nueva_unidad', methods=['POST'])
@login_required
def api_unidad():
    try:
        nombre = request.form['nombre'].upper().strip()
        with engine.begin() as conn: 
            conn.execute(text("INSERT INTO dbo.unidades (nombre_unidad) VALUES (:n)"), {"n": nombre})
        return jsonify({"exito": True})
    except Exception as e:
        return jsonify({"exito": False, "mensaje": str(e)})

@app.route('/ping')
def ping_keepalive():
    return "ok", 200

def _iniciar_keepalive():
    """Mantiene despierto el servidor en Render 24/7 para evitar la pantalla de espera de Render."""
    import threading
    import urllib.request
    def _loop():
        while True:
            time.sleep(600)  # cada 10 minutos
            for url in ["https://controlmotos.cibershieldac.com/ping", "https://motocontrol-pro.onrender.com/ping"]:
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "MotoControl-KeepAlive/1.0"})
                    urllib.request.urlopen(req, timeout=15).read()
                except Exception:
                    pass
    if os.environ.get("RENDER") or os.environ.get("DATABASE_URL"):
        hilo = threading.Thread(target=_loop, daemon=True)
        hilo.start()

_iniciar_keepalive()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5050)
