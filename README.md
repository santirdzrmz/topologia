# Datos simulados para análisis topológico

Versión en Python de `simulate_topodata.R` (carpeta `Reto`). Genera tablas ficticias de
proveedores (Maestro) y pagos (Pagos) con estructura incrustada: clusters por tipo de
proveedor, un factor latente de tamaño, pagos con cadencia periódica (ciclos), outliers y
valores faltantes estructurados.

## Regenerar los datos

```bash
pip install -r requirements.txt
python simulate_topodata.py            # escribe en ./simulated_data
python simulate_topodata.py otra_ruta  # o en otra carpeta
```

Requiere Python 3.9 o superior.

## Archivos

| Archivo | Contenido |
|---|---|
| `run_workflow.py` | Orquesta los tres pasos del flujo y la verificación |
| `simulate_topodata.py` | Generador (semilla, número de proveedores y rango de fechas al inicio del archivo) |
| `inject_anomalies.py` | Diseño factorial: inyecta anomalías A–D en 80 corridas |
| `tda_anomalies.py` | Análisis de anomalías con homología persistente sobre las corridas |
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

## Reproducibilidad

Con `SEED = 8347`, `Maestro_simulado.csv` y `Pagos_simulado.csv` coinciden byte a byte con
los del script de R. En `Maestro_ground_truth_clusters.csv` unas pocas filas difieren en el
último dígito de `size_factor` y `risk_score` (redondeo de punto flotante).

El orden de las llamadas aleatorias replica el script de R línea por línea; reordenarlas
cambia los datos.
