-- =====================================================================
-- 01_esquema.sql  ·  Reto FEMSA: base para las 80 corridas + CONTROL
-- MySQL 8.0. Lo ejecuta cargar_mysql.py automáticamente; también se puede
-- correr a mano en Workbench (Ctrl+Shift+Enter).
-- Todas las tablas llevan la columna `corrida` (CONTROL, T01_R01 ... T16_R05).
-- Las columnas llave (IDs, cuentas, UUID) usan utf8mb4_bin: comparación
-- exacta, sensible a mayúsculas y sin convertir '000000…' a número.
-- =====================================================================
CREATE DATABASE IF NOT EXISTS femsa_fraude
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE femsa_fraude;

-- Una fila por corrida (sale de resumen.json; CONTROL no tiene niveles)
CREATE TABLE IF NOT EXISTS corridas (
    corrida       VARCHAR(20) NOT NULL PRIMARY KEY,
    tratamiento   TINYINT  NULL,
    replica       TINYINT  NULL,
    semilla       BIGINT   NULL,
    nivel_a_pct   DECIMAL(5,2) NULL,   -- Factor A: pagos con proveedor fuera del maestro
    nivel_b_pct   DECIMAL(5,2) NULL,   -- Factor B: pagos a cuenta no autorizada
    nivel_c_pct   DECIMAL(5,2) NULL,   -- Factor C: proveedores con cuenta compartida
    nivel_d_pct   DECIMAL(5,2) NULL    -- Factor D: pagos con UUID duplicado
);

-- Maestro de proveedores (columnas originales, nombres en snake_case)
CREATE TABLE IF NOT EXISTS maestro (
    corrida                        VARCHAR(20) NOT NULL,
    fila                           INT NOT NULL,
    unidad_operativa               VARCHAR(255) NULL,
    id_proveedor                   VARCHAR(40) COLLATE utf8mb4_bin NULL,
    tipo_proveedor                 VARCHAR(255) NULL,
    nombre_proveedor               VARCHAR(255) NULL,
    rfc                            VARCHAR(40) COLLATE utf8mb4_bin NULL,
    registro_impositivo            VARCHAR(255) NULL,
    fecha_creacion_prov            VARCHAR(255) NULL,
    actualizacion_provedor         VARCHAR(255) NULL,
    cabecera_actualizada_por       VARCHAR(255) NULL,
    fecha_proveedor_inactivo       VARCHAR(255) NULL,
    parent_vendor_id               VARCHAR(255) NULL,
    fuente_abasto_padre            VARCHAR(255) NULL,
    site_id_proveedor              VARCHAR(255) NULL,
    site                           VARCHAR(255) NULL,
    fa                             VARCHAR(255) NULL,
    fuente_abasto                  VARCHAR(255) NULL,
    fecha_site_inactivo            VARCHAR(255) NULL,
    actualizacion_site             VARCHAR(255) NULL,
    sucrusales_actualizadas_por    VARCHAR(255) NULL,
    metodo_de_pago                 VARCHAR(255) NULL,
    terminos_pago                  VARCHAR(255) NULL,
    grupo_pago                     VARCHAR(255) NULL,
    calculo_impuesto               VARCHAR(255) NULL,
    impuesto                       VARCHAR(255) NULL,
    impuesto_incluidos             VARCHAR(255) NULL,
    aplica_grupo_retencion         VARCHAR(255) NULL,
    grupo_retencion                VARCHAR(255) NULL,
    correo                         VARCHAR(255) NULL,
    direccion                      VARCHAR(255) NULL,
    pais                           VARCHAR(255) NULL,
    telefono                       VARCHAR(255) NULL,
    banco                          VARCHAR(255) NULL,
    prioridad_cuenta               VARCHAR(255) NULL,
    cuenta                         VARCHAR(40) COLLATE utf8mb4_bin NULL,
    inactivacion_cuenta            VARCHAR(255) NULL,
    actualizacion_cuenta           VARCHAR(255) NULL,
    referencia_bancaria            VARCHAR(255) NULL,
    referencia_adicional           VARCHAR(255) NULL,
    cuenta_pasivo                  VARCHAR(255) NULL,
    cuenta_anticipo                VARCHAR(255) NULL,
    estatus_fe                     VARCHAR(255) NULL,
    pago_independiente             VARCHAR(255) NULL,
    resico                         VARCHAR(255) NULL,
    sucursal_compra                VARCHAR(255) NULL,
    sucursal_pago                  VARCHAR(255) NULL,
    PRIMARY KEY (corrida, fila),
    KEY ix_maestro_id     (corrida, id_proveedor),
    KEY ix_maestro_cuenta (corrida, cuenta)
);

-- Pagos (fila = posición original en Pagos.csv, empieza en 0)
CREATE TABLE IF NOT EXISTS pagos (
    corrida                        VARCHAR(20) NOT NULL,
    fila                           INT NOT NULL,
    tipo                           VARCHAR(255) NULL,
    fecha_d_pago                   DATE NULL,
    vendor_id                      VARCHAR(40) COLLATE utf8mb4_bin NULL,
    invoice_id                     VARCHAR(255) NULL,
    site                           VARCHAR(255) NULL,
    segment4                       VARCHAR(255) NULL,
    vendor_name                    VARCHAR(255) NULL,
    segment1                       VARCHAR(255) NULL,
    attribute1                     VARCHAR(255) NULL,
    referencia                     VARCHAR(255) NULL,
    fecha_factura                  DATE NULL,
    fecha_vencimiento              DATE NULL,
    num_factura                    VARCHAR(255) NULL,
    importe_ap                     DECIMAL(18,2) NULL,
    pagado                         VARCHAR(255) NULL,
    pago_mx                        VARCHAR(255) NULL,
    tipo_cambio                    VARCHAR(255) NULL,
    total_tax_amount               DECIMAL(18,2) NULL,
    description                    VARCHAR(255) NULL,
    payment_reason_comments        VARCHAR(255) NULL,
    tipo_1                         VARCHAR(255) NULL,
    gpo_pago                       VARCHAR(255) NULL,
    plz                            VARCHAR(255) NULL,
    no_doc                         VARCHAR(255) NULL,
    importe_doc                    DECIMAL(18,2) NULL,
    bank_account_num               VARCHAR(40) COLLATE utf8mb4_bin NULL,
    bank_account_name              VARCHAR(255) NULL,
    check_id                       VARCHAR(255) NULL,
    bank_num                       VARCHAR(255) NULL,
    invoice_id_1                   VARCHAR(255) NULL,
    approval_description           VARCHAR(255) NULL,
    source                         VARCHAR(255) NULL,
    uuid                           VARCHAR(40) COLLATE utf8mb4_bin NULL,
    PRIMARY KEY (corrida, fila),
    KEY ix_pagos_vendor (corrida, vendor_id),
    KEY ix_pagos_cuenta (corrida, bank_account_num),
    KEY ix_pagos_uuid   (corrida, uuid)
);

-- Verdad del generador: SOLO para validar, las consultas de detección no la usan
CREATE TABLE IF NOT EXISTS etiquetas_pagos (
    corrida  VARCHAR(20) NOT NULL,
    fila     INT NOT NULL,
    a TINYINT NOT NULL, b TINYINT NOT NULL, c TINYINT NOT NULL, d TINYINT NOT NULL,
    PRIMARY KEY (corrida, fila)
);

CREATE TABLE IF NOT EXISTS etiquetas_maestro (
    corrida       VARCHAR(20) NOT NULL,
    fila          INT NOT NULL,
    id_proveedor  VARCHAR(40) COLLATE utf8mb4_bin NULL,
    c             TINYINT NOT NULL,
    PRIMARY KEY (corrida, fila)
);
