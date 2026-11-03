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
| `simulate_topodata.py` | Generador (semilla, número de proveedores y rango de fechas al inicio del archivo) |
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
