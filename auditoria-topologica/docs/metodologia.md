# Metodología y datos

## Estructura esperada

La carpeta configurada en `AUDITORIA_DATA_DIR` contiene `CONTROL/` y carpetas de escenario `T01_R01/` … `T16_R05/`. Cada carpeta contiene:

- `Pagos.csv`: `VENDOR_ID`, `VENDOR_NAME`, `BANK_ACCOUNT_NUM`, `UUID`, `FECHA_D_PAGO`, `FECHA_FACTURA`, `FECHA_VENCIMIENTO`, `IMPORTE_AP`.
- `Maestro.csv`: `Id Proveedor`, `Cuenta`.
- `etiquetas_pagos.csv`: índice `fila_pago_original` con base cero, una fila por pago, y columnas booleanas `A`, `B`, `C`, `D`. El control no lleva etiquetas.

Las fechas se interpretan como día/mes/año de dos dígitos. Identificadores y cuentas se leen como texto para conservar ceros iniciales. No reordenes los pagos independientemente de las etiquetas.

## Baseline

SQLite ejecuta las cuatro reglas en memoria. A comprueba existencia del proveedor; B verifica la cuenta de un proveedor registrado; C señala pagos de proveedores que comparten cuenta en el maestro; D señala todas las filas de cada UUID no vacío repetido. Una fila puede recibir varias alertas, pero se cuenta una sola vez en el total conjunto. El importe es una suma por fila, no una pérdida estimada.

## Aprendizaje no supervisado

Isolation Forest y LOF se ajustan y puntúan por escenario. El perfil de comportamiento usa importes, frecuencias de proveedor y fechas. El perfil ampliado añade indicadores SQL y frecuencias de relaciones. Se imputan faltantes con la mediana del escenario (cero si no hay datos en la columna) y se aplica escala robusta. Isolation Forest usa 150 árboles y semilla 42; LOF usa 35 vecinos por defecto.

Una puntuación más alta indica mayor rareza según el modelo. Para un presupuesto de p%, se priorizan las primeras ceil(n × p/100) filas, con desempate por posición original. Por eso los modelos también priorizan pagos en CONTROL. No se usan etiquetas ni prevalencias conocidas para elegir el corte.

La evaluación conjunta compara la alerta de cada método con la unión de A–D. Precisión, recall y F1 dependen del corte; average precision evalúa el ranking completo y no se calcula para SQL. El recall por factor de ML mide cobertura, no clasificación del tipo. Las reglas SQL tienen su propio criterio de alerta y pueden producir un volumen diferente.

## Alcance experimental

Las variantes comparten una base y las etiquetas identifican cambios sintéticos. El ajuste por escenario es transductivo; no valida generalización a otras bases o a pagos futuros. La demo pública usa una base generada de forma independiente: sus métricas no deben interpretarse como reproducción numérica de las corridas locales. Para evaluar decisiones sobre parámetros, fija la configuración antes de usar las réplicas reservadas.
