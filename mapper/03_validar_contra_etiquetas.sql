-- =====================================================================
-- 03_validar_contra_etiquetas.sql  ·  Reto FEMSA
-- Compara lo que encuentran las consultas de 02 (vista v_criterios_pago)
-- contra las etiquetas reales del generador. Correr 02 antes (crea la vista).
-- tp = detectado y etiquetado · fn = etiquetado pero no detectado
-- fp = detectado pero no etiquetado
-- =====================================================================
USE femsa_fraude;

-- 1. Matriz de confusión y recall/precisión por factor, para cada corrida
WITH cmp AS (
    SELECT v.corrida,
           v.a_sin_maestro AS pa, e.a AS ea,
           v.b_cuenta_no_autorizada AS pb, e.b AS eb,
           v.c_cuenta_compartida AS pc, e.c AS ec,
           v.d_uuid_duplicado AS pd, e.d AS ed
    FROM v_criterios_pago v
    JOIN etiquetas_pagos e ON e.corrida = v.corrida AND e.fila = v.fila
),
conteos AS (
    SELECT corrida,
           SUM(pa AND ea) AS tp_a, SUM(ea AND NOT pa) AS fn_a, SUM(pa AND NOT ea) AS fp_a,
           SUM(pb AND eb) AS tp_b, SUM(eb AND NOT pb) AS fn_b, SUM(pb AND NOT eb) AS fp_b,
           SUM(pc AND ec) AS tp_c, SUM(ec AND NOT pc) AS fn_c, SUM(pc AND NOT ec) AS fp_c,
           SUM(pd AND ed) AS tp_d, SUM(ed AND NOT pd) AS fn_d, SUM(pd AND NOT ed) AS fp_d
    FROM cmp
    GROUP BY corrida
)
SELECT c.corrida, c.tratamiento, c.replica,
       c.nivel_a_pct, c.nivel_b_pct, c.nivel_c_pct, c.nivel_d_pct,
       k.tp_a, k.fn_a, k.fp_a, ROUND(k.tp_a / NULLIF(k.tp_a + k.fn_a, 0), 4) AS recall_a,
       k.tp_b, k.fn_b, k.fp_b, ROUND(k.tp_b / NULLIF(k.tp_b + k.fn_b, 0), 4) AS recall_b,
       k.tp_c, k.fn_c, k.fp_c, ROUND(k.tp_c / NULLIF(k.tp_c + k.fn_c, 0), 4) AS recall_c,
       k.tp_d, k.fn_d, k.fp_d, ROUND(k.tp_d / NULLIF(k.tp_d + k.fn_d, 0), 4) AS recall_d,
       ROUND((k.tp_a + k.tp_b + k.tp_c + k.tp_d) /
             NULLIF(k.tp_a + k.tp_b + k.tp_c + k.tp_d + k.fp_a + k.fp_b + k.fp_c + k.fp_d, 0), 4)
                                                                                AS precision_global
FROM corridas c
JOIN conteos k ON k.corrida = c.corrida
ORDER BY c.tratamiento, c.replica;


-- 2. Prueba rápida: corridas donde SQL y etiquetas NO coinciden.
--    Si regresa 0 filas, SQL encontró exactamente las anomalías inducidas.
SELECT v.corrida,
       SUM(v.a_sin_maestro          <> e.a) AS dif_a,
       SUM(v.b_cuenta_no_autorizada <> e.b) AS dif_b,
       SUM(v.c_cuenta_compartida    <> e.c) AS dif_c,
       SUM(v.d_uuid_duplicado       <> e.d) AS dif_d
FROM v_criterios_pago v
JOIN etiquetas_pagos e ON e.corrida = v.corrida AND e.fila = v.fila
GROUP BY v.corrida
HAVING dif_a + dif_b + dif_c + dif_d > 0;


-- 3. CONTROL (sin anomalías inducidas): debe dar 0 en todo
SELECT SUM(a_sin_maestro) AS a, SUM(b_cuenta_no_autorizada) AS b,
       SUM(c_cuenta_compartida) AS c, SUM(d_uuid_duplicado) AS d
FROM v_criterios_pago
WHERE corrida = 'CONTROL';


-- 4. Factor C a nivel proveedor, contra etiquetas_maestro
WITH cc AS (
    SELECT corrida, cuenta
    FROM maestro
    GROUP BY corrida, cuenta
    HAVING COUNT(DISTINCT id_proveedor) > 1
),
pred AS (
    SELECT m.corrida, m.fila, (cc.cuenta IS NOT NULL) AS c_pred
    FROM maestro m
    LEFT JOIN cc ON cc.corrida = m.corrida AND cc.cuenta = m.cuenta
)
SELECT p.corrida,
       SUM(p.c_pred AND e.c)     AS tp,
       SUM(e.c AND NOT p.c_pred) AS fn,
       SUM(p.c_pred AND NOT e.c) AS fp
FROM pred p
JOIN etiquetas_maestro e ON e.corrida = p.corrida AND e.fila = p.fila
GROUP BY p.corrida
ORDER BY p.corrida;
