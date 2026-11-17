# Deteccion de anomalias con homologia persistente

Generado por `tda_anomalies.py` sobre 80 corridas (+ CONTROL).
Puntaje: escala de absorcion H0 con masa minima tau = 0.25.

## Deteccion por pago (AUC ROC contra pagos limpios, media ± de)

| Tipo | H0, comportamiento + relaciones | H0, solo comportamiento | Isolation Forest |
|---|---|---|---|
| A | 1.000 ± 0.000 | 0.471 ± 0.023 | 0.988 ± 0.010 |
| B | 1.000 ± 0.000 | 0.507 ± 0.031 | 0.996 ± 0.002 |
| C | 1.000 ± 0.000 | 0.520 ± 0.099 | 0.984 ± 0.015 |
| D | 1.000 ± 0.000 | 0.510 ± 0.019 | 0.973 ± 0.018 |
| ABCD | 1.000 ± 0.000 | 0.502 ± 0.024 | 0.977 ± 0.011 |
| N | 0.998 ± 0.001 | 0.992 ± 0.005 | 0.997 ± 0.001 |

Precision@k (k = pagos etiquetados): 1.000 ± 0.000. AP (A-D): 1.000 ± 0.000.
AUC de C a nivel proveedor (maximo por proveedor): 0.886 ± 0.122.
N son los pagos que el simulador ya altero (x6-25); se reportan aparte.

## Sensibilidad a tau (AUC A-D)

| tau | AUC |
|---|---|
| 0.01 | 0.930 ± 0.043 |
| 0.05 | 0.998 ± 0.002 |
| 0.1 | 1.000 ± 0.000 |
| 0.25 | 1.000 ± 0.000 |
| 0.5 | 1.000 ± 0.000 |

## Forma de los datos

| Medida | CONTROL | Corridas (media ± de) |
|---|---|---|
| pers_total_H0 | 247.657 | 429.931 ± 21.009 |
| pers_total_H1 | 22.270 | 44.050 ± 3.765 |
| n_H1 | 284.000 | 506.238 ± 36.244 |
| wasserstein_H0 | 0.000 | 172.193 ± 20.423 |
| wasserstein_H1 | 0.000 | 33.103 ± 3.569 |
| betti0_relacional | 400.000 | 200.662 ± 56.813 |
| betti1_relacional | 0.000 | 11.512 ± 11.747 |
| componentes_multiproveedor | 0.000 | 37.562 ± 15.314 |

## Efectos factoriales significativos (p < 0.01)

Efecto = cambio medio al pasar del nivel bajo al alto. Las respuestas constantes
(p. ej. AUC = 1 en todas las corridas) no se modelan.

| Respuesta | Termino | Efecto | p |
|---|---|---|---|
| betti0_relacional | D | -112.3750 | 7.5e-87 |
| betti0_relacional | C | -8.3750 | 4.4e-16 |
| betti1_relacional | D | 22.1750 | 1.2e-39 |
| componentes_multiproveedor | D | -28.4250 | 3.0e-33 |
| if_auc_ABCD | D | -0.0183 | 2.6e-27 |
| if_auc_ABCD | C | -0.0058 | 4.3e-07 |
| if_auc_ABCD | C:D | 0.0036 | 8.2e-04 |
| pers_total_H1 | C | 4.4890 | 2.7e-15 |
| pers_total_H1 | D | 3.5234 | 2.5e-11 |
| pers_total_H1 | B | 2.8354 | 1.6e-08 |
| ph_auc_ABCD_tau_0.01 | A | -0.0785 | 2.7e-39 |
| ph_auc_ABCD_tau_0.01 | A:D | 0.0207 | 2.9e-10 |
| wasserstein_H0 | C | 28.5745 | 4.5e-30 |
| wasserstein_H0 | D | 19.1675 | 1.3e-20 |
| wasserstein_H0 | B | 16.9663 | 4.7e-18 |
| wasserstein_H0 | A | 4.2908 | 4.2e-03 |
| wasserstein_H1 | C | 4.6478 | 3.3e-22 |
| wasserstein_H1 | D | 3.4833 | 3.1e-16 |
| wasserstein_H1 | B | 2.8866 | 5.9e-13 |
