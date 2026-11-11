-- =====================================================================
-- 02_detectar_anomalias.sql  ·  Reto FEMSA
-- Detección de los 4 tipos de anomalía con SQL puro (MySQL 8.0).
-- NO usa las tablas de etiquetas: solo cruza Pagos con Maestro.
--
-- En Workbench: pon el cursor en una consulta y presiona Ctrl+Enter
-- para correr solo esa. Cambia @corrida para ver otra réplica.
-- =====================================================================
USE femsa_fraude;
SET @corrida = 'T16_R01';


-- ---------------------------------------------------------------------
-- A. Integridad del maestro: pagos cuyo proveedor NO existe en el maestro
--    Un LEFT JOIN deja NULL del lado del maestro cuando no hay match.
-- ---------------------------------------------------------------------
SELECT p.fila, p.vendor_id, p.vendor_name, p.fecha_d_pago, p.importe_ap,
       p.bank_account_num, p.uuid
FROM pagos p
LEFT JOIN maestro m
       ON m.corrida = p.corrida AND m.id_proveedor = p.vendor_id
WHERE p.corrida = @corrida
  AND m.id_proveedor IS NULL
ORDER BY p.fila;


-- ---------------------------------------------------------------------
-- B. Consistencia bancaria: pagos a una cuenta distinta de la autorizada
--    Solo aplica a proveedores que sí existen en el maestro (INNER JOIN).
--    <=> es la igualdad que trata NULL = NULL como verdadero.
-- ---------------------------------------------------------------------
SELECT p.fila, p.vendor_id, p.vendor_name, p.fecha_d_pago, p.importe_ap,
       m.cuenta            AS cuenta_autorizada,
       p.bank_account_num  AS cuenta_pagada
FROM pagos p
JOIN maestro m
  ON m.corrida = p.corrida AND m.id_proveedor = p.vendor_id
WHERE p.corrida = @corrida
  AND NOT (p.bank_account_num <=> m.cuenta)
ORDER BY p.fila;


-- ---------------------------------------------------------------------
-- C. Cuentas compartidas: una misma cuenta registrada a 2+ proveedores
-- C.1  Las cuentas y quiénes las comparten (nivel proveedor)
-- ---------------------------------------------------------------------
SELECT cuenta,
       COUNT(DISTINCT id_proveedor)                               AS proveedores,
       GROUP_CONCAT(DISTINCT id_proveedor ORDER BY id_proveedor)  AS ids_proveedor,
       GROUP_CONCAT(DISTINCT nombre_proveedor SEPARATOR ' | ')    AS nombres
FROM maestro
WHERE corrida = @corrida
GROUP BY cuenta
HAVING COUNT(DISTINCT id_proveedor) > 1
ORDER BY proveedores DESC, cuenta;

-- C.2  Pagos hechos a esas cuentas (nivel pago)
SELECT p.fila, p.vendor_id, p.vendor_name, p.fecha_d_pago, p.importe_ap, p.bank_account_num
FROM pagos p
JOIN (SELECT cuenta
      FROM maestro
      WHERE corrida = @corrida
      GROUP BY cuenta
      HAVING COUNT(DISTINCT id_proveedor) > 1) cc
  ON cc.cuenta = p.bank_account_num
WHERE p.corrida = @corrida
ORDER BY p.bank_account_num, p.vendor_id, p.fila;


-- ---------------------------------------------------------------------
-- D. Duplicidad fiscal: UUID (CFDI) que aparece en más de un pago
--    Se listan todos los pagos involucrados, agrupados por UUID.
-- ---------------------------------------------------------------------
SELECT p.uuid, du.veces, p.fila, p.vendor_id, p.vendor_name,
       p.fecha_d_pago, p.importe_ap, p.num_factura
FROM pagos p
JOIN (SELECT uuid, COUNT(*) AS veces
      FROM pagos
      WHERE corrida = @corrida
      GROUP BY uuid
      HAVING COUNT(*) > 1) du
  ON du.uuid = p.uuid
WHERE p.corrida = @corrida
ORDER BY p.uuid, p.fila;


-- =====================================================================
-- Vista con los 4 criterios para TODAS las corridas (un renglón por pago)
-- 1 = el pago cumple el criterio. `patron` junta los criterios, p. ej. 'A+D'.
-- =====================================================================
CREATE OR REPLACE VIEW v_criterios_pago AS
WITH cuentas_compartidas AS (
    SELECT corrida, cuenta
    FROM maestro
    GROUP BY corrida, cuenta
    HAVING COUNT(DISTINCT id_proveedor) > 1
),
uuid_duplicados AS (
    SELECT corrida, uuid
    FROM pagos
    GROUP BY corrida, uuid
    HAVING COUNT(*) > 1
),
base AS (
    SELECT p.corrida, p.fila, p.vendor_id, p.vendor_name, p.fecha_d_pago,
           p.importe_ap, p.bank_account_num, p.uuid,
           (m.id_proveedor IS NULL)                                          AS a_sin_maestro,
           (m.id_proveedor IS NOT NULL
            AND NOT (p.bank_account_num <=> m.cuenta))                       AS b_cuenta_no_autorizada,
           (cc.cuenta IS NOT NULL)                                           AS c_cuenta_compartida,
           (ud.uuid IS NOT NULL)                                             AS d_uuid_duplicado
    FROM pagos p
    LEFT JOIN maestro m
           ON m.corrida = p.corrida AND m.id_proveedor = p.vendor_id
    LEFT JOIN cuentas_compartidas cc
           ON cc.corrida = p.corrida AND cc.cuenta = p.bank_account_num
    LEFT JOIN uuid_duplicados ud
           ON ud.corrida = p.corrida AND ud.uuid = p.uuid
)
SELECT base.*,
       a_sin_maestro + b_cuenta_no_autorizada + c_cuenta_compartida + d_uuid_duplicado AS n_criterios,
       CONCAT_WS('+', IF(a_sin_maestro, 'A', NULL), IF(b_cuenta_no_autorizada, 'B', NULL),
                      IF(c_cuenta_compartida, 'C', NULL), IF(d_uuid_duplicado, 'D', NULL))  AS patron
FROM base;


-- Pagos sospechosos de una corrida, los de más criterios primero
SELECT *
FROM v_criterios_pago
WHERE corrida = @corrida AND n_criterios > 0
ORDER BY n_criterios DESC, patron, fila;

-- Conteo por patrón en una corrida (equivale a las "islas" del grafo Mapper)
SELECT IF(patron = '', 'Sin anomalía', patron) AS patron, COUNT(*) AS pagos
FROM v_criterios_pago
WHERE corrida = @corrida
GROUP BY patron
ORDER BY pagos DESC;

-- Resumen de las 81 corridas: cuántos pagos cumple cada criterio
SELECT c.corrida, c.tratamiento, c.replica,
       c.nivel_a_pct, c.nivel_b_pct, c.nivel_c_pct, c.nivel_d_pct,
       SUM(v.a_sin_maestro)          AS pagos_a,
       SUM(v.b_cuenta_no_autorizada) AS pagos_b,
       SUM(v.c_cuenta_compartida)    AS pagos_c,
       SUM(v.d_uuid_duplicado)       AS pagos_d,
       SUM(v.n_criterios > 0)        AS pagos_sospechosos
FROM corridas c
JOIN v_criterios_pago v ON v.corrida = c.corrida
GROUP BY c.corrida, c.tratamiento, c.replica,
         c.nivel_a_pct, c.nivel_b_pct, c.nivel_c_pct, c.nivel_d_pct
ORDER BY c.tratamiento IS NULL DESC, c.tratamiento, c.replica;
