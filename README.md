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
| `simulate_topodata.py` | Generador (semilla, número de proveedores y rango de fechas al inicio del archivo) |
| `simulate_topodata.R` | Generador original en R |
| `r_rng.py` | Port del generador aleatorio de R, para que la misma semilla dé los mismos datos |
| `simulated_data/Maestro_simulado.csv` | 400 proveedores |
| `simulated_data/Pagos_simulado.csv` | ~5,390 pagos |
| `simulated_data/Maestro_ground_truth_clusters.csv` | Etiquetas reales de cluster y factores latentes (solo para diagnóstico) |

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
