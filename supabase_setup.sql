-- ============================================================================
-- SCRIPT DE BASE DE DATOS PARA SUPABASE (PostgreSQL) - MOTOCONTROL PRO
-- Pega y ejecuta este script en el "SQL Editor" de tu proyecto en Supabase
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS dbo;

-- 1. Tabla de Usuarios
CREATE TABLE IF NOT EXISTS dbo.Usuarios (
    id_usuario SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(100) NOT NULL,
    rol VARCHAR(50) NOT NULL
);

-- 2. Catálogos Auxiliares (Marcas, Categorías, Unidades)
CREATE TABLE IF NOT EXISTS dbo.marcas (
    id_marca SERIAL PRIMARY KEY,
    nombre_marca VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS dbo.categorias (
    id_categoria SERIAL PRIMARY KEY,
    nombre_categoria VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS dbo.unidades (
    id_unidad SERIAL PRIMARY KEY,
    nombre_unidad VARCHAR(50) UNIQUE NOT NULL
);

-- 3. Tabla de Repuestos
CREATE TABLE IF NOT EXISTS dbo.repuestos (
    id_repuesto INT PRIMARY KEY,
    descripcion VARCHAR(255) NOT NULL,
    marca VARCHAR(100),
    categoria VARCHAR(100) DEFAULT 'SIN CATEGORIA',
    unidad VARCHAR(50) DEFAULT 'UND',
    stock INT DEFAULT 0,
    reservado INT DEFAULT 0,
    precio_unitario NUMERIC(12,2) DEFAULT 0,
    precio_venta NUMERIC(12,2) DEFAULT 0,
    imagen_url VARCHAR(500)
);

ALTER TABLE dbo.repuestos ADD COLUMN IF NOT EXISTS precio_unitario NUMERIC(12,2) DEFAULT 0;
ALTER TABLE dbo.repuestos ADD COLUMN IF NOT EXISTS precio_venta NUMERIC(12,2) DEFAULT 0;
ALTER TABLE dbo.repuestos ADD COLUMN IF NOT EXISTS imagen_url VARCHAR(500);

-- 4. Tabla de Socios (Clientes y Proveedores)
CREATE TABLE IF NOT EXISTS dbo.socios (
    id_proveedor VARCHAR(50) PRIMARY KEY,
    nombre_empresa VARCHAR(200) NOT NULL,
    contacto_nombre VARCHAR(200),
    contacto VARCHAR(200),
    direccion VARCHAR(255),
    ubicacion VARCHAR(255),
    telefono VARCHAR(50),
    es_cliente INT DEFAULT 1,
    es_proveedor INT DEFAULT 0
);

-- 5. Tabla de Compras
CREATE TABLE IF NOT EXISTS dbo.compras (
    id_compra SERIAL PRIMARY KEY,
    id_repuesto INT REFERENCES dbo.repuestos(id_repuesto),
    id_proveedor VARCHAR(50),
    proveedor VARCHAR(100),
    factura VARCHAR(100),
    num_factura VARCHAR(100),
    cantidad_comprada INT NOT NULL,
    precio_compra NUMERIC(12,2) DEFAULT 0,
    monto_total NUMERIC(12,2) DEFAULT 0,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_compra TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Tabla de Pedidos de Clientes
CREATE TABLE IF NOT EXISTS dbo.pedidos_clientes (
    id_pedido SERIAL PRIMARY KEY,
    id_repuesto INT REFERENCES dbo.repuestos(id_repuesto),
    cliente VARCHAR(200) NOT NULL,
    cliente_rif VARCHAR(50),
    cantidad INT NOT NULL,
    estado VARCHAR(50) DEFAULT 'BORRADOR',
    fecha_pedido TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. Tabla de Configuración Persistente (Tasa BCV, Pago Móvil, Precios y Fotos)
CREATE TABLE IF NOT EXISTS dbo.kv_store (
    clave VARCHAR(100) PRIMARY KEY,
    valor TEXT
);

-- ============================================================================
-- DATOS INICIALES (USUARIOS Y REPUESTOS ACTUALES)
-- ============================================================================

INSERT INTO dbo.Usuarios (username, password, rol) VALUES
('aida_admin', 'admin123', 'admin'),
('ventas_user', 'ventas123', 'usuario_pedidos'),
('Analista-compras', 'compras123', 'analista_compras')
ON CONFLICT (username) DO NOTHING;

INSERT INTO dbo.marcas (nombre_marca) VALUES
('MEGAZUKI'), ('BESTIA NEGRA'), ('BREMBO'), ('DID'), ('K&N'), ('GENERICO'), ('EMPIRE')
ON CONFLICT (nombre_marca) DO NOTHING;

INSERT INTO dbo.categorias (nombre_categoria) VALUES
('ELECTRICO'), ('FRENOS'), ('TRANSMISION'), ('CAUCHOS'), ('MOTOR'), ('FILTROS'), ('SIN CATEGORIA')
ON CONFLICT (nombre_categoria) DO NOTHING;

INSERT INTO dbo.unidades (nombre_unidad) VALUES
('UND'), ('PAR'), ('KIT'), ('JGO')
ON CONFLICT (nombre_unidad) DO NOTHING;

INSERT INTO dbo.repuestos (id_repuesto, descripcion, marca, categoria, unidad, stock, reservado) VALUES
(1, 'KIT DE ARRASTRE EMPIRE', 'MEGAZUKI', 'TRANSMISION', 'UND', 10, 0),
(2, 'BATERIA-SECA', 'BESTIA NEGRA', 'ELECTRICO', 'UND', 39, 0),
(3, 'KIT DE RODAJE', 'MEGAZUKI', 'TRANSMISION', 'UND', 20, 0),
(4, 'CAUCHO 18/90', 'MEGAZUKI', 'CAUCHOS', 'UND', 20, 0),
(5, 'CDI-ELECTRONICO', 'MEGAZUKI', 'ELECTRICO', 'UND', 20, 0),
(6, 'CAUCHO-110', 'MEGAZUKI', 'CAUCHOS', 'UND', 25, 5),
(7, 'PASTILLAS DE FRENO-150', 'MEGAZUKI', 'FRENOS', 'UND', 0, 0),
(8, 'CAUCHO-17', 'MEGAZUKI', 'CAUCHOS', 'UND', 0, 0),
(9, 'CDI-MECANICO', 'MEGAZUKI', 'ELECTRICO', 'UND', 0, 0),
(90, 'CDI-MECANICO', 'MEGAZUKI', 'ELECTRICO', 'UND', 0, 0),
(501, 'PASTILLAS FRENO XT', 'BREMBO', 'FRENOS', 'UND', 10, 0),
(502, 'CADENA REFORZADA', 'DID', 'TRANSMISION', 'UND', 5, 0),
(503, 'FILTRO AIRE PREMIUM', 'K&N', 'FILTROS', 'UND', 20, 0),
(504, 'KIT DE ARRASTRE', 'GENERICO', 'TRANSMISION', 'UND', 8, 0)
ON CONFLICT (id_repuesto) DO NOTHING;

-- Cargar todas tus fotos, precios P1/P2/P3, Tasa BCV (894.89) y Pago Móvil Mercantil
INSERT INTO dbo.kv_store (clave, valor) VALUES (
'catalogo_meta',
$json${
  "5": {"costo_base": 5.0, "aplica_iva": true, "costo_full": 5.8, "precio1": 6.96, "precio2": 7.25, "precio3": 7.54, "tarifa_activa": 3, "precio_venta": 7.54, "imagen_url": "/static/uploads/repuesto_5_1793367143.png", "categoria": "ELECTRICO"},
  "1": {"costo_base": 16.0, "aplica_iva": true, "costo_full": 18.56, "precio1": 22.27, "precio2": 23.2, "precio3": 24.13, "tarifa_activa": 3, "precio_venta": 24.13, "categoria": "KIT", "imagen_url": "/static/uploads/repuesto_1_1793378640.png"},
  "2": {"costo_base": 14.0, "aplica_iva": true, "costo_full": 16.24, "precio1": 19.49, "precio2": 20.3, "precio3": 21.11, "tarifa_activa": 3, "precio_venta": 21.11, "categoria": "BATERIA", "imagen_url": "/static/uploads/repuesto_2_1793378567.png"},
  "3": {"costo_base": 15.0, "aplica_iva": true, "costo_full": 17.4, "precio1": 20.88, "precio2": 21.75, "precio3": 22.62, "tarifa_activa": 3, "precio_venta": 22.62, "categoria": "KIT", "imagen_url": "/static/uploads/repuesto_3_1793378486.png"},
  "4": {"costo_base": 25.0, "aplica_iva": true, "costo_full": 29.0, "precio1": 34.8, "precio2": 36.25, "precio3": 37.7, "tarifa_activa": 3, "precio_venta": 37.7, "categoria": "CAUCHOS", "imagen_url": "/static/uploads/repuesto_4_1793378385.png"},
  "6": {"costo_base": 14.0, "aplica_iva": true, "costo_full": 16.24, "precio1": 19.49, "precio2": 20.3, "precio3": 21.11, "tarifa_activa": 3, "precio_venta": 21.11, "categoria": "CAUCHOS", "imagen_url": "/static/uploads/repuesto_6_1793378765.png"},
  "7": {"costo_base": 2.0, "aplica_iva": true, "costo_full": 2.32, "precio1": 2.78, "precio2": 2.9, "precio3": 3.02, "tarifa_activa": 3, "precio_venta": 3.02, "categoria": "FRENOS", "imagen_url": "/static/uploads/repuesto_7_1793378318.png"},
  "8": {"costo_base": 15.0, "aplica_iva": true, "costo_full": 17.4, "precio1": 20.88, "precio2": 21.75, "precio3": 22.62, "tarifa_activa": 3, "precio_venta": 22.62, "categoria": "CAUCHOS", "imagen_url": "/static/uploads/repuesto_8_1793378257.png"},
  "9": {"costo_base": 8.0, "aplica_iva": true, "costo_full": 9.28, "precio1": 11.14, "precio2": 11.6, "precio3": 12.06, "tarifa_activa": 3, "precio_venta": 12.06, "categoria": "ELÉCTRICO", "imagen_url": "/static/uploads/repuesto_9_1793378203.png"},
  "90": {"costo_base": 4.8, "aplica_iva": true, "costo_full": 5.57, "precio1": 6.68, "precio2": 6.96, "precio3": 7.24, "tarifa_activa": 3, "precio_venta": 7.24, "categoria": "ELÉCTRICO", "imagen_url": "/static/uploads/repuesto_90_1793378044.png"},
  "501": {"costo_base": 2.0, "aplica_iva": true, "costo_full": 2.32, "precio1": 2.78, "precio2": 2.9, "precio3": 3.02, "tarifa_activa": 3, "precio_venta": 3.02, "categoria": "FRENOS", "imagen_url": "/static/uploads/repuesto_501_1793377940.png"},
  "502": {"costo_base": 8.0, "aplica_iva": true, "costo_full": 9.28, "precio1": 11.14, "precio2": 11.6, "precio3": 12.06, "tarifa_activa": 3, "precio_venta": 12.06, "categoria": "CADENA", "imagen_url": "/static/uploads/repuesto_502_1793377866.png"},
  "503": {"costo_base": 7.5, "aplica_iva": true, "costo_full": 8.7, "precio1": 10.44, "precio2": 10.88, "precio3": 11.31, "tarifa_activa": 3, "precio_venta": 11.31, "categoria": "ACCESORIOS", "imagen_url": "/static/uploads/repuesto_503_1793378108.png"},
  "504": {"costo_base": 12.0, "aplica_iva": true, "costo_full": 13.92, "precio1": 16.7, "precio2": 17.4, "precio3": 18.1, "tarifa_activa": 3, "precio_venta": 18.1, "categoria": "ACCESORIOS", "imagen_url": "/static/uploads/repuesto_504_1793372758.png"},
  "_config_pago": {"banco": "0105- Mercantil", "rif_negocio": "V-18799049", "telefono_pm": "0412-5756301", "titular": "MOTOCONTROL PRO C.A.", "tasa_bcv": 894.89, "ultima_actualizacion": "05/11/2026 10:00", "actualizado_por": "aida_admin"}
}$json$
) ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor;

