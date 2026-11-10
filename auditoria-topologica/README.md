# Auditoría topológica de pagos

Laboratorio reproducible para comparar reglas SQL, aprendizaje no supervisado y futuros métodos de análisis topológico en la auditoría de pagos a proveedores. El panel de Streamlit permite pasar de los indicadores a las filas que requieren revisión y consultar cómo se generó cada alerta.

| Enfoque | Estado | Propósito |
| --- | --- | --- |
| Reglas SQL en SQLite | Disponible | Identificar excepciones conocidas y establecer una referencia de auditoría. |
| Isolation Forest y Local Outlier Factor (LOF) | Disponible | Priorizar pagos inusuales con un presupuesto fijo de revisión. |
| Mapper | Planeado | Explorar grupos de pagos o proveedores y rastrear qué registros forman cada grupo. |
| Homología persistente | Planeado | Investigar si la estructura a distintas escalas aporta señales adicionales al ranking. |

## Ejecutar el panel

Desde la raíz de `topologia`, con Python 3.12:

```sh
cd auditoria-topologica
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python generate_demo.py
python -m streamlit run app.py
```

Abre [Streamlit en el puerto 8501](http://localhost:8501). En Windows, crea el entorno con `py -3.12 -m venv .venv` y actívalo con `.venv\Scripts\activate` antes de instalar las dependencias.

El generador crea `data/` una sola vez y conserva los datos existentes. Los identificadores, cuentas, fechas e importes de la demo se generan en código.

Si `Reto` y `topologia` están en la misma carpeta, puedes abrir las corridas
locales desde `auditoria-topologica/`:

```sh
AUDITORIA_DATA_DIR="../../Reto/Resultados_80_pruebas" python -m streamlit run app.py
```

Para usar otro conjunto compatible, asigna su ruta a `AUDITORIA_DATA_DIR`.

La [metodología y el esquema de datos](docs/metodologia.md) describen las columnas requeridas, el diseño experimental y los límites de las métricas.

## Qué se compara

Las 80 variantes de la demo cubren un diseño factorial completo: cuatro factores, dos intensidades por factor y cinco réplicas por combinación. Cada escenario tiene 400 registros maestros y 5,390 pagos. El control sirve como referencia y carece de etiquetas.

| Factor | Anomalía introducida | Niveles |
| --- | --- | --- |
| A | Proveedor no registrado | 2% o 5% de pagos |
| B | Cuenta fuera del maestro | 1% o 3% de pagos |
| C | Cuenta compartida | 2% o 7% de proveedores |
| D | UUID repetido | 5% o 10% de pagos, en pares |

SQL evalúa cada condición de forma directa. Los modelos de ML generan un ranking general, sin atribuir una causa A–D. Se pueden ejecutar con variables de comportamiento o añadir señales SQL explícitas para medir cómo priorizan hallazgos conocidos. Las etiquetas se reservan para evaluar. Las alertas señalan casos para revisión y no constituyen evidencia de fraude.

## Próximos pasos

- **Mapper:** construir un mapa de grupos con variables y parámetros documentados. Permitir navegar desde los nodos al detalle de los pagos y comprobar si los patrones se mantienen al cambiar la escala y el solapamiento.
- **Homología persistente:** empezar con componentes conexas de vecindarios locales y explorar ciclos donde la representación los justifique. Comparar las firmas topológicas con referencias, asignar puntuaciones por entidad y conservar el vínculo con el registro original.
- **Evaluación:** usar los mismos escenarios y presupuesto de revisión para métodos que generan rankings. Comparar contra SQL y contra modelos con las mismas variables de entrada, para distinguir el valor de la representación del valor del detector.

## Desarrollo

- `app.py`: panel, visualizaciones y exportación.
- `detectors.py`: carga de datos, reglas SQLite y evaluación por factor.
- `ml.py`: variables, detectores y métricas de ranking.
- `generate_demo.py`: generación de datos ficticios con semillas fijas.
- `tests/`: pruebas de SQL y ML. Ejecútalas desde `auditoria-topologica/`
  con los datos de demo y sin configurar `AUDITORIA_DATA_DIR`.

```sh
python -m unittest discover -s tests -v
```
