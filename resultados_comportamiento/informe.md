# Homología persistente solo con comportamiento

Generado por `tda_comportamiento.py` sobre las corridas de `simulate_experiment.py` (CONTROL sin anomalías + 80 corridas).

El modelo solo recibe variables de comportamiento. Las banderas de cruce con el maestro y las etiquetas se leen después de calcular puntajes y grupos.

- **C4:** log_importe, z_importe_proveedor, dias_factura_pago, dias_factura_vencimiento
- **C6:** C4 + log_brecha_relativa, log_n_pagos_proveedor
- **C6M:** C6 + atributos del proveedor en el Maestro: desvio_terminos, antiguedad_proveedor, dias_desde_actualizacion, e indicadores de Tipo Proveedor, Metodo de Pago, Impuesto, Resico, Site
- **R:** topología de la red proveedor–cuenta–UUID para cada pago: log_proveedores_componente, log_ciclos_componente, log_persistencia_fusion, ciclos_cerrados. Son cantidades genéricas (tamaño y ciclos de la componente, persistencia H0 y ciclos H1 de la red filtrada por fecha); ninguna codifica una regla de anomalía.
- **C6M+R:** C6M + R.

Ninguna variable dice que un renglón es A, B, C o D: las 4 banderas de cruce no entran al modelo. En C6M, un pago cuyo proveedor no aparece en el Maestro recibe la mediana de CONTROL en los atributos numéricos y ceros en los indicadores.

Puntaje H0 con masa mínima τ = 0.25. Grupos: el árbol de expansión mínima se corta en la mayor muerte H0 de CONTROL (C4: 1.773, C6: 3.229, C6M: 3.723, R: 0.000, C6M+R: 3.723); el grupo más grande es el grueso.

## Detección por pago (AUC contra pagos limpios, media ± de en 80 corridas)

| Tipo | H0 · C4 | Isolation Forest · C4 | H0 · C6 | Isolation Forest · C6 | H0 · C6M | Isolation Forest · C6M | H0 · R | Isolation Forest · R | H0 · C6M+R | Isolation Forest · C6M+R |
|---|---|---|---|---|---|---|---|---|---|---|
| ABCD | 0.491 ± 0.020 | 0.468 ± 0.022 | 0.585 ± 0.037 | 0.584 ± 0.036 | 0.595 ± 0.041 | 0.573 ± 0.028 | 0.597 ± 0.077 | 0.596 ± 0.048 | 0.670 ± 0.047 | 0.636 ± 0.036 |
| A | 0.463 ± 0.025 | 0.355 ± 0.021 | 0.913 ± 0.003 | 0.914 ± 0.017 | 0.954 ± 0.003 | 0.871 ± 0.046 | 0.533 ± 0.102 | 0.507 ± 0.054 | 0.949 ± 0.043 | 0.860 ± 0.058 |
| B | 0.502 ± 0.029 | 0.498 ± 0.033 | 0.499 ± 0.032 | 0.497 ± 0.033 | 0.499 ± 0.030 | 0.497 ± 0.034 | 0.518 ± 0.029 | 0.516 ± 0.035 | 0.511 ± 0.029 | 0.508 ± 0.035 |
| C | 0.508 ± 0.088 | 0.498 ± 0.062 | 0.496 ± 0.081 | 0.498 ± 0.062 | 0.496 ± 0.076 | 0.491 ± 0.066 | 0.500 ± 0.136 | 0.482 ± 0.125 | 0.485 ± 0.085 | 0.483 ± 0.071 |
| D | 0.496 ± 0.016 | 0.493 ± 0.016 | 0.512 ± 0.016 | 0.511 ± 0.018 | 0.516 ± 0.018 | 0.511 ± 0.019 | 0.731 ± 0.062 | 0.755 ± 0.065 | 0.711 ± 0.034 | 0.678 ± 0.037 |

## Grupos que forma H0 (sin etiquetas) y qué contienen (marcado posterior)

| Medida | C4 | C6 | C6M | R | C6M+R |
|---|---|---|---|---|---|
| Grupos aparte por corrida | 0.613 ± 0.490 | 0.125 ± 0.369 | 1.125 ± 0.933 | 196.688 ± 50.133 | 10.887 ± 4.444 |
| Pagos en grupos aparte | 258.475 ± 206.887 | 0.412 ± 1.270 | 2.337 ± 2.181 | 3072.625 ± 983.968 | 1095.362 ± 989.180 |
| Pureza: fracción etiquetada dentro de los grupos aparte | 0.159 ± 0.042 | 0.100 ± 0.120 | 0.078 ± 0.154 | 0.197 ± 0.032 | 0.590 ± 0.382 |
| Cobertura: fracción de etiquetados que cae en grupos aparte | 0.046 ± 0.038 | 0.000 ± 0.000 | 0.000 ± 0.001 | 0.691 ± 0.260 | 0.294 ± 0.126 |
| Índice de Rand ajustado (grupos vs. etiquetas) | -0.003 ± 0.013 | -0.000 ± 0.000 | -0.000 ± 0.001 | 0.044 ± 0.019 | 0.172 ± 0.093 |
| En CONTROL: grupos aparte | 0 | 0 | 0 | 0 | 0 |

## Forma de la corrida (distancia de Wasserstein a CONTROL)

| Medida | C4 | C6 | C6M | R | C6M+R |
|---|---|---|---|---|---|
| wasserstein_H0 | 3.301 ± 0.759 | 33.555 ± 8.071 | 29.502 ± 8.949 | 20.404 ± 1.299 | 276.001 ± 30.103 |
| wasserstein_H1 | 4.776 ± 0.392 | 23.918 ± 4.851 | 32.456 ± 6.386 | 1.113 ± 0.294 | 149.087 ± 10.087 |

## Control: banderas calculadas después vs. etiquetas

Coincidencia por pago en las 80 corridas (las banderas no entran al modelo; solo describen los grupos).

| Bandera | Etiqueta | Coincidencia |
|---|---|---|
| proveedor_no_registrado | A | 1.0000 |
| cuenta_distinta_maestro | B | 1.0000 |
| cuenta_compartida | C | 1.0000 |
| uuid_repetido | D | 1.0000 |

## Grupos de la corrida T16_R05 (C6M+R), marcados después del modelo

| variables | grupo | tipo | pagos | etiquetados | pct_etiquetados | p_enriquecimiento | pct_A | pct_B | pct_C | pct_D | bandera_proveedor_no_registrado | bandera_cuenta_distinta_maestro | bandera_cuenta_compartida | bandera_uuid_repetido |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C6M+R | 0 | grueso | 3425 | 738 | 21.5 | 1 | 4.93 | 2.8 | 6.69 | 8.18 | 169 | 96 | 229 | 280 |
| C6M+R | 1 | aparte | 1721 | 279 | 16.2 | 1 | 5.23 | 3.54 | 6.28 | 1.34 | 90 | 61 | 108 | 23 |
| C6M+R | 2 | aparte | 213 | 213 | 100 | 5.38e-142 | 5.16 | 1.88 | 6.1 | 100 | 11 | 4 | 13 | 213 |
| C6M+R | 3 | aparte | 21 | 21 | 100 | 4.49e-14 | 0 | 0 | 0 | 100 | 0 | 0 | 0 | 21 |
| C6M+R | 4 | aparte | 2 | 1 | 50 | 0.411 | 0 | 0 | 50 | 0 | 0 | 0 | 1 | 0 |
| C6M+R | 5 | aparte | 2 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C6M+R | 6 | aparte | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C6M+R | 7 | aparte | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C6M+R | 8 | aparte | 1 | 1 | 100 | 0.233 | 0 | 0 | 0 | 100 | 0 | 0 | 0 | 1 |
| C6M+R | 9 | aparte | 1 | 1 | 100 | 0.233 | 0 | 100 | 0 | 100 | 0 | 1 | 0 | 1 |
| C6M+R | 10 | aparte | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C6M+R | 11 | aparte | 1 | 1 | 100 | 0.233 | 0 | 0 | 100 | 100 | 0 | 0 | 1 | 1 |
