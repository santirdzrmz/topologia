# Datos simulados para análisis topológico

Versión en Python del simulador original en R. Genera tablas ficticias de
proveedores (Maestro) y pagos (Pagos) con estructura incrustada: clusters por tipo de
proveedor, un factor latente de tamaño, pagos con cadencia periódica (ciclos), outliers y
valores faltantes estructurados.

## Regenerar los datos

```bash
pip install -r requirements.txt
python simulate_topodata.py            # escribe en ./simulated_data
python simulate_topodata.py otra_ruta  # o en otra carpeta
```

La versión en Python requiere Python 3.9 o superior. También puedes ejecutar
`Rscript simulate_topodata.R` desde esta carpeta para regenerar los archivos
con R y los paquetes `dplyr`, `purrr`, `tidyr`, `stringr`, `lubridate` y `tibble`.

## Archivos

| Archivo | Contenido |
|---|---|
| `run_workflow.py` | Orquesta los tres pasos del flujo y la verificación |
| `simulate_topodata.py` | Generador (semilla, número de proveedores y rango de fechas al inicio del archivo) |
| `simulate_topodata.R` | Generador original en R |
| `inject_anomalies.py` | Diseño factorial: inyecta anomalías A–D en 80 corridas |
| `tda_anomalies.py` | Análisis de anomalías con homología persistente sobre las corridas |
| `simulate_experiment.py` | Experimento sin fuga: CONTROL sin anomalías + 80 corridas con el generador de R |
| `tda_comportamiento.py` | Homología persistente solo con comportamiento; banderas y etiquetas se usan después |
| `tda_indicadores.py` | Vector de anomalías ponderadas por proveedor (A, B, C, D) y su homología persistente |
| `r_rng.py` | Port del generador aleatorio de R, para que la misma semilla dé los mismos datos |
| `simulated_data/Maestro_simulado.csv` | 400 proveedores |
| `simulated_data/Pagos_simulado.csv` | ~5,390 pagos |
| `simulated_data/Maestro_ground_truth_clusters.csv` | Etiquetas reales de cluster y factores latentes (solo para diagnóstico) |

## Flujo completo: simulación → 80 corridas con anomalías → homología persistente

```bash
pip install -r requirements.txt
python run_workflow.py            # los tres pasos
python run_workflow.py --verify   # regenera pasos 1-2 en una carpeta temporal y compara
```

| Paso | Script | Salida |
|---|---|---|
| 1. simulate | `simulate_topodata.py` | `simulated_data/` |
| 2. inject | `inject_anomalies.py` | `Archivos_modificados_80_corridas/Resultados_80_pruebas/` |
| 3. analyze | `tda_anomalies.py` | `resultados_tda/` |

Se puede correr un subconjunto: `python run_workflow.py inject analyze`.

### Paso 2: diseño factorial 2^4 con 5 réplicas (80 corridas)

Cada corrida parte de CONTROL (los datos simulados) e inyecta cuatro tipos de anomalía
etiquetada, cada uno en nivel bajo o alto (porcentaje de filas):

| Factor | Bajo / Alto | Anomalía |
|---|---|---|
| A | 2 / 5 % de pagos | `VENDOR_ID` que no existe en Maestro (nuevo id = máximo + 1,000,000 + k) |
| B | 1 / 3 % de pagos | Pago a cuenta no autorizada (nueva cuenta = máxima + 1,000,000 + k) |
| C | 2 / 7 % de proveedores | Parejas de proveedores que comparten la cuenta del donante (Maestro y pagos del receptor) |
| D | 5 / 10 % de pagos | Parejas de pagos con el mismo `UUID` |

Los tratamientos siguen el orden de Yates (A cambia más rápido). La corrida `Ttt_Rrr` usa
la semilla `20261204 + 100·(t−1) + (r−1)` con `numpy.random.default_rng`, y los sorteos se hacen
en el orden C, A, B, D: C sobre proveedores, A sobre pagos fuera de C, B sobre pagos fuera de
C y A, y D sobre todos los pagos. Con esto la carpeta se reproduce byte por byte (484 archivos).
Por corrida se escriben `Maestro.csv`, `Pagos.csv`, `etiquetas_maestro.csv`,
`etiquetas_pagos.csv`, `registro_cambios.csv` y `resumen.json`, más `matriz_experimental.csv` y
`resumen_corridas.csv` en la raíz. Cada corrida se valida comprobando que todo cambio
respecto a CONTROL esté explicado por su etiqueta.

### Paso 3: detección de anomalías con homología persistente

Cada pago es un punto en un espacio que combina comportamiento (log del importe, z del importe
dentro del proveedor, días factura→pago y factura→vencimiento; escalado robusto ajustado en
CONTROL) y consistencia entre tablas (proveedor no registrado, cuenta distinta a la del Maestro,
cuenta compartida por varios proveedores, UUID repetido).

- **H0 por pago.** La filtración de Rips en dimensión 0 equivale al árbol de expansión mínima.
  El puntaje de un pago es la escala en la que su componente conexa alcanza `τ·n` puntos
  (τ = 0.25), es decir, cuándo lo absorbe el grueso de los datos. A diferencia de la distancia
  al vecino más cercano, los grupos de anomalías parecidas entre sí no se enmascaran mutuamente
  (ver la tabla de sensibilidad a τ).
- **H0/H1 por corrida.** Diagramas de Rips sobre una submuestra max-min de 600 pagos, y su
  distancia de Wasserstein al diagrama de CONTROL.
- **Complejo relacional.** Números de Betti del grafo proveedor–cuenta–UUID, cuya topología
  limpia es un árbol por proveedor registrado (β0 = 400, β1 = 0).

La detección se evalúa con AUC, AP y precisión@k contra las etiquetas A–D, y también contra los
pagos atípicos que el propio simulador introdujo (`outlier_rows`, "N"), que se reportan aparte y
no cuentan como falsos positivos. Se compara con el mismo puntaje usando solo comportamiento y con
Isolation Forest. Las respuestas por corrida se explican con un modelo factorial (efectos
principales e interacciones dobles).

Salidas en `resultados_tda/`: `informe.md` (resumen), `metricas_por_corrida.csv`,
`efectos_factoriales.csv`, `puntajes_T16_R05.csv` y figuras (`diagramas_persistencia.png`,
`auc_por_tipo.png`, `efectos_principales.png`, `puntajes_por_etiqueta.png`). Tarda unos
10 minutos.

## Experimento sin fuga: solo comportamiento

En el flujo anterior las cuatro banderas de cruce con el maestro entran al modelo, y cada
anomalía A–D se define justo por lo que revisa su bandera, así que bandera = etiqueta. Este
experimento separa las dos cosas:

```bash
python run_workflow.py simulate_exp analyze_beh
```

| Paso | Script | Salida |
|---|---|---|
| simulate_exp | `simulate_experiment.py` | `corridas_simulador/` (CONTROL + 80 corridas) |
| analyze_beh | `tda_comportamiento.py` | `resultados_comportamiento/` |

- **CONTROL sin anomalías:** `simulate_topodata.py --sin-atipicos` omite la sección 4 del
  simulador (montos ×6–25 y vencimientos invertidos). Sin la opción, la salida sigue igual a la de R.
- **80 corridas:** mismas anomalías A–D, niveles, orden y reglas que `inject_anomalies.py`, pero
  todos los sorteos salen de `r_rng.RRandom` (en R: `set.seed` + `sample.int`).
- **Qué entra al modelo:** solo comportamiento. C4 = log del importe, z del importe dentro del
  proveedor, días factura→pago y factura→vencimiento. C6 = C4 + cadencia calculada dentro de
  Pagos (brecha relativa con el pago anterior del mismo proveedor y log del número de pagos del
  proveedor). C6M = C6 + atributos del proveedor en el Maestro (tipo, términos, método,
  impuesto, Resico, sitio, antigüedad). Las banderas no entran.
- **R, topología de la red:** con proveedores, cuentas y UUID como nodos y los pagos y el
  Maestro como enlaces, cada pago recibe cantidades genéricas de la red: proveedores y ciclos
  (β1) de su componente, y la persistencia H0 y los ciclos H1 que provoca cuando la red se
  filtra por fecha. Ninguna codifica una regla de anomalía. Se reporta R sola y C6M + R.
- **Modelo:** solo homología persistente. Puntaje H0 por pago (τ = 0.25), grupos de H0 (el árbol
  de expansión mínima se corta en la mayor muerte H0 de CONTROL) y Wasserstein contra CONTROL.
- **Qué se marca después:** con las etiquetas y las banderas, ya calculados los grupos, se
  describe qué contiene cada grupo (porcentaje de A–D, banderas, enriquecimiento hipergeométrico)
  y se mide la detección (AUC; Isolation Forest solo como referencia).

Salidas en `resultados_comportamiento/`: `informe.md`, `metricas_por_corrida.csv`,
`grupos_T16_R05.csv` y figuras (`codigo_barras_h0.png`, `puntajes_por_etiqueta.png`,
`diagramas_persistencia.png`, `auc_por_tipo.png`).

## Vector de indicadores ponderados por proveedor

```bash
python run_workflow.py analyze_ind   # sobre corridas_simulador/
```

Cada proveedor es un punto x_i = (A, B, C, D) ∈ {0, 1}⁴, colocado en w·x_i con pesos
w = (20, 30, 30, 25): proveedor no registrado, cuenta no autorizada, cuenta compartida con
otro proveedor y factura duplicada (UUID repetido). Los proveedores son los del Maestro más
cada `VENDOR_ID` de Pagos sin renglón en el Maestro. La puntuación S = w·x junta
configuraciones distintas (B y C valen 30; B+D y C+D valen 55); la nube de puntos no.

- **H0:** el árbol de expansión mínima, cortado a ε = 10, separa exactamente las
  configuraciones, y sus escalas de unión dan la jerarquía entre perfiles.
- **H1:** un ciclo indica que dos anomalías ocurren solas y juntas (las cuatro esquinas
  de un rectángulo).

Los indicadores son las reglas que definen A–D, así que coinciden con las etiquetas por
construcción: esto describe el perfil de riesgo para el desarrollo de proveedores, no mide
detección. Los pesos de A y D son una elección y se cambian en `WEIGHTS`.

Salidas en `resultados_indicadores/`: `informe.md`, `metricas_por_corrida.csv`,
`vectores_T16_R05.csv` y figuras (`s_vs_configuracion.png`, `jerarquia_h0.png`,
`configuraciones_por_tratamiento.png`).

## Reproducibilidad

Con `SEED = 8347`, `Maestro_simulado.csv` y `Pagos_simulado.csv` coinciden byte a byte con
los del script de R. En `Maestro_ground_truth_clusters.csv` unas pocas filas difieren en el
último dígito de `size_factor` y `risk_score` (redondeo de punto flotante).

El orden de las llamadas aleatorias replica el script de R línea por línea; reordenarlas
cambia los datos.

## Panel de auditoría de pagos

La carpeta [auditoria-topologica](auditoria-topologica/) contiene el panel de
Streamlit, las reglas SQL, los modelos Isolation Forest y LOF, y el generador
de 80 escenarios de demostración. El panel usa un conjunto organizado por
escenario, separado de las tablas base de `simulated_data/`. Su
[guía de ejecución](auditoria-topologica/README.md) explica cómo generar la
demo o abrir las corridas de `Reto`.
