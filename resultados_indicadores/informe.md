# Vector de anomalías ponderadas por proveedor y homología persistente

Cada proveedor es un punto x_i = (A, B, C, D) con valores 0/1, colocado en w·x_i con w = (20, 30, 30, 25):

| Anomalía | Peso | Se activa cuando |
|---|---|---|
| A · proveedor no registrado | 20 | el VENDOR_ID del pago no tiene renglón en el Maestro |
| B · cuenta no autorizada | 30 | un pago va a una cuenta diferente a la del proveedor en el Maestro |
| C · cuenta compartida | 30 | una cuenta del proveedor está ligada a otro proveedor registrado |
| D · factura duplicada (UUID repetido) | 25 | un pago del proveedor usa un UUID que aparece en otro pago |

Los proveedores son los 400 del Maestro más cada `VENDOR_ID` de Pagos que no tiene renglón en el Maestro (los de A).

La puntuación S = w·x junta configuraciones distintas en un mismo número; el punto en 4-D no. La homología persistente describe cómo están acomodadas las configuraciones:

- **H0:** el árbol de expansión mínima de la nube. Cortado a ε = 10 (la mitad del peso más ligero) separa exactamente las configuraciones; la escala a la que cada una se une con otra da la jerarquía entre perfiles.
- **H1:** aparece un ciclo cuando los proveedores ocupan las cuatro esquinas de un rectángulo, es decir, dos anomalías ocurren solas y juntas.

## Antes de leer los resultados

- Los indicadores son las reglas que definen A–D, así que coinciden con las etiquetas por construcción (ver la última tabla). Esto **no mide detección**; describe el perfil de riesgo de cada proveedor para el desarrollo de proveedores: dos proveedores con la misma S y distinta configuración necesitan una corrección distinta.
- Los pesos de A (20) y D (25) son una elección: D conserva el peso de "factura duplicada" y A toma el de "RFC distinto". Se cambian en `WEIGHTS`.
- En CONTROL los 400 proveedores están en (0,0,0,0): una sola configuración y S = 0.

## Corrida extrema T16_R05 (A, B, C, D en nivel alto)

- Proveedores: 670 (400 registrados + 270 no registrados).
- Configuraciones distintas (grupos H0 a ε = 10): **8**; valores distintos de S: **6**.
- Proveedores cuya S coincide con la de otra configuración: **156 de 670** (23 %), en 2 valores de S.
- Ciclos H1: **3**.

### Qué confunde S y qué separa la nube

| S | perfil 1 | perfil 2 | proveedores | distancia en la nube |
|---|---|---|---|---|
| 30 | C | B | 12 / 35 | 42.4 |
| 55 | C+D | B+D | 16 / 93 | 42.4 |

### Jerarquía H0 de las configuraciones

Muerte = escala a la que la configuración se une a otra; el perfil limpio (el estado de CONTROL) nunca muere. Las muertes son pesos: morir a 25 quiere decir que el perfil se distingue de su vecino solo por D; a 20, solo por A; a 30, por B o por C.

| perfil | (A,B,C,D) | proveedores | S | muerte_H0 | se une al bloque de |
|---|---|---|---|---|---|
| limpio | 0000 | 93 | 0 | inf |  |
| C+D | 0011 | 16 | 55 | 30 | limpio |
| B+D | 0101 | 93 | 55 | 30 | limpio |
| D | 0001 | 151 | 25 | 25 | limpio |
| C | 0010 | 12 | 30 | 25 | C+D |
| B | 0100 | 35 | 30 | 25 | B+D |
| A | 1000 | 247 | 20 | 20 | limpio |
| A+D | 1001 | 23 | 45 | 20 | D |

### Ciclos H1

Diagrama H1 (nacimiento, muerte): (30.0, 39.1), (30.0, 39.1), (25.0, 32.0).

- Planos con las cuatro esquinas ocupadas (dos anomalías solas y juntas): A–D, B–D, C–D.
- Combinaciones que no aparecen en ningún proveedor: A+B, A+C, B+C.
- Por qué faltan: A+B y A+C no pueden ocurrir porque un proveedor no registrado no tiene cuenta en el Maestro contra la cual comparar; B+C no ocurre porque el simulador sortea B fuera de los pagos de C. En esos planos falta una esquina y no hay ciclo.

Figuras: `s_vs_configuracion.png` (qué configuraciones esconde cada valor de S) y `jerarquia_h0.png` (código de barras H0 y diagrama H1).

## Por tratamiento (promedio de 5 réplicas)

Niveles en % (A, B, D de pagos; C de proveedores); n_X = proveedores con la anomalía X.

| tratamiento | A | B | C | D | proveedores | configuraciones | valores_S | proveedores_en_colision | ciclos_H1 | n_A | n_B | n_C | n_D |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2 | 1 | 2 | 5 | 508 | 8 | 6 | 56.4 | 3 | 108 | 48.4 | 8 | 192 |
| 2 | 5 | 1 | 2 | 5 | 670 | 8 | 6 | 57.4 | 3 | 270 | 49.4 | 8 | 189 |
| 3 | 2 | 3 | 2 | 5 | 508 | 8 | 6 | 135 | 3 | 108 | 127 | 8 | 191 |
| 4 | 5 | 3 | 2 | 5 | 670 | 8 | 6 | 134 | 3 | 270 | 126 | 8 | 189 |
| 5 | 2 | 1 | 7 | 5 | 508 | 8 | 6 | 77 | 3 | 108 | 49 | 28 | 187 |
| 6 | 5 | 1 | 7 | 5 | 670 | 8 | 6 | 77.6 | 3 | 270 | 49.6 | 28 | 194 |
| 7 | 2 | 3 | 7 | 5 | 508 | 8 | 6 | 156 | 3 | 108 | 128 | 28 | 182 |
| 8 | 5 | 3 | 7 | 5 | 670 | 8 | 6 | 160 | 3 | 270 | 132 | 28 | 189 |
| 9 | 2 | 1 | 2 | 10 | 508 | 8 | 6 | 58.2 | 3 | 108 | 50.2 | 8 | 284 |
| 10 | 5 | 1 | 2 | 10 | 670 | 8 | 6 | 58 | 3 | 270 | 50 | 8 | 287 |
| 11 | 2 | 3 | 2 | 10 | 508 | 7.8 | 6 | 128 | 2.8 | 108 | 124 | 8 | 285 |
| 12 | 5 | 3 | 2 | 10 | 670 | 7.8 | 6 | 130 | 2.8 | 270 | 127 | 8 | 297 |
| 13 | 2 | 1 | 7 | 10 | 508 | 8 | 6 | 75.2 | 3 | 108 | 47.2 | 28 | 280 |
| 14 | 5 | 1 | 7 | 10 | 670 | 8 | 6 | 77.6 | 3 | 270 | 49.6 | 28 | 291 |
| 15 | 2 | 3 | 7 | 10 | 508 | 8 | 6 | 151 | 3 | 108 | 123 | 28 | 277 |
| 16 | 5 | 3 | 7 | 10 | 670 | 8 | 6 | 152 | 3 | 270 | 124 | 28 | 291 |

Figura: `configuraciones_por_tratamiento.png`.

## Comprobación con etiquetas (después del modelo)

Coincidencia por proveedor entre cada indicador y su etiqueta, en las 80 corridas:

| anomalía | coincidencia media | mínima |
|---|---|---|
| A | 1 | 1 |
| B | 1 | 1 |
| C | 1 | 1 |
| D | 1 | 1 |
