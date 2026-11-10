import pandas as pd
import plotly.express as px
import streamlit as st
from detectors import DATA, RULES, load_case, evaluate

st.set_page_config(page_title='Auditoría de pagos', page_icon='◈', layout='wide')
st.markdown('''<style>
.stApp {background:#f5f7fa} h1,h2,h3 {color:#16324f}
[data-testid="stMetric"] {background:white;border:1px solid #e3e8ee;border-radius:12px;padding:18px}
[data-testid="stSidebar"] {background:#eaf0f6}
</style>''', unsafe_allow_html=True)

if not all((DATA / 'CONTROL' / filename).is_file() for filename in ('Pagos.csv', 'Maestro.csv')):
    st.title('Auditoría de pagos')
    st.info('Genera los datos de demostración con python generate_demo.py, o configura AUDITORIA_DATA_DIR para usar otro conjunto compatible.')
    st.stop()


@st.cache_data
def case_data(case):
    return load_case(case)

@st.cache_data
def comparison():
    rows = []
    for folder in sorted(DATA.glob('T*_R*')):
        _, _, flags = load_case(folder.name)
        metrics = evaluate(folder.name, flags)
        metrics['Escenario'] = folder.name
        metrics['Tratamiento'] = folder.name.split('_')[0]
        rows.append(metrics)
    return pd.concat(rows, ignore_index=True)

with st.sidebar:
    st.title('◈ Auditoría')
    st.caption('Laboratorio de detección · v2')
    case = st.selectbox('Escenario', ['CONTROL'] + sorted(p.name for p in DATA.glob('T*_R*') if p.is_dir()))
    st.caption('Baseline SQL + laboratorio de ML clásico')
    st.divider()
    st.markdown('**Alcance**\n\nConciliación con maestro, cuentas compartidas y UUID repetidos.')
    st.caption('Una alerta requiere revisión. No constituye evidencia de fraude.')

st.caption('CONTROL INTERNO / CUENTAS POR PAGAR')
st.title('Auditoría de pagos')
st.write('De la señal al registro: explora las excepciones y consulta la regla que las originó.')
payments, master, flags = case_data(case)
any_flag = flags.any(axis=1)
amount = pd.to_numeric(payments['IMPORTE_AP'].str.replace(',', '', regex=False), errors='coerce')
cols = st.columns(4)
for col, title, value in zip(cols, ['Pagos revisados', 'Registros del maestro', 'Pagos con alertas', 'Tasa de alerta'],
                            [f'{len(payments):,}', f'{len(master):,}', f'{any_flag.sum():,}', f'{any_flag.mean():.1%}']):
    col.metric(title, value)
st.caption(f'Escenario {case} · Las alertas pueden coincidir en un mismo pago; no se suman para calcular el total.')

overview, detail, validation, methodology, ml_tab = st.tabs(['Resumen ejecutivo', 'Explorar alertas', 'Evaluación experimental', 'Reglas y metodología', 'ML clásico'])
with overview:
    left, right = st.columns([3, 2])
    counts = pd.DataFrame({'Regla': [f'{k} · {v[0]}' for k,v in RULES.items()], 'Pagos señalados': flags.sum().values})
    with left:
        st.subheader('Distribución de hallazgos')
        chart = px.bar(counts, x='Pagos señalados', y='Regla', orientation='h', text='Pagos señalados', color_discrete_sequence=['#24788c'])
        chart.update_layout(yaxis={'autorange':'reversed'}, height=340, paper_bgcolor='rgba(0,0,0,0)', margin=dict(l=0,r=20,t=15,b=0))
        st.plotly_chart(chart)
    with right:
        st.subheader('Importes asociados')
        st.metric('Importe de facturas con alerta', f'{amount[any_flag].sum():,.2f}')
        st.caption('Suma de IMPORTE_AP por fila señalada, una sola vez por fila. No representa pérdida, importe único por factura ni moneda consolidada verificada.')
        st.write('**Lectura del panel**')
        st.write('A y B revisan la relación con el maestro. C busca proveedores vinculados por cuenta. D identifica UUID repetidos.')
    st.info('El control es una referencia, no una garantía de ausencia de excepciones. Las mismas reglas se aplican a todos los escenarios.')

with detail:
    selected = st.multiselect('Tipos de alerta', list(RULES), default=list(RULES), format_func=lambda k: f'{k} · {RULES[k][0]}')
    query = st.text_input('Buscar proveedor, nombre, cuenta o UUID')
    mask = flags[selected].any(axis=1) if selected else pd.Series(False, index=flags.index)
    columns = ['VENDOR_ID','VENDOR_NAME','BANK_ACCOUNT_NUM','UUID','FECHA_D_PAGO','IMPORTE_AP']
    table = payments[columns].copy()
    table.insert(0, 'Fila original (base 0)', table.index)
    table['Alertas'] = flags.apply(lambda row: ', '.join(k for k in RULES if row[k]), axis=1)
    if query:
        mask &= table.astype(str).apply(lambda col: col.str.contains(query, case=False, regex=False)).any(axis=1)
    shown = table.loc[mask]
    st.caption(f'{len(shown):,} pagos cumplen los filtros. Los identificadores se conservan como texto.')
    st.dataframe(shown, hide_index=True, width="stretch")
    st.download_button('Descargar selección CSV', shown.to_csv(index=False).encode('utf-8-sig'), f'alertas_{case}.csv', 'text/csv')

with validation:
    st.subheader('Reglas frente a anomalías introducidas')
    st.caption('Las etiquetas se consultan únicamente después de ejecutar SQL. Evaluación por pago, incluida C: pagos de proveedores afectados.')
    metrics = evaluate(case, flags)
    if metrics.empty:
        st.info('CONTROL no incluye etiquetas: se muestran alertas, pero no se calculan precisión ni recall.')
    else:
        st.dataframe(metrics.style.format({'Precisión':'{:.1%}', 'Recall':'{:.1%}'}, na_rep='No definido'), hide_index=True, width="stretch")
        st.caption('Precisión: aciertos entre alertas. Recall: anomalías etiquetadas encontradas. No definido indica denominador cero. Las etiquetas de inyección no certifican que toda alerta adicional sea inválida en términos de negocio.')
    if st.button('Comparar los 80 escenarios'):
        with st.spinner('Ejecutando reglas SQL en los 80 escenarios…'):
            results = comparison()
        st.session_state['comparison'] = results
    if 'comparison' in st.session_state:
        results = st.session_state['comparison']
        average = results.groupby(['Tratamiento','Factor'])['Recall'].mean().reset_index()
        heatmap = average.pivot(index='Tratamiento', columns='Factor', values='Recall')
        st.plotly_chart(px.imshow(heatmap, zmin=0, zmax=1, text_auto='.0%', color_continuous_scale='Teal', title='Recall medio de las 5 réplicas'))
        st.dataframe(results, hide_index=True, width="stretch")
        st.download_button('Descargar evaluación completa', results.to_csv(index=False).encode('utf-8-sig'), 'evaluacion_sql.csv', 'text/csv')

with methodology:
    st.write('Motor: SQLite en memoria. Se eliminan espacios exteriores; los UUID se comparan en mayúsculas. No se convierten cuentas ni identificadores a números.')
    for factor, (name, sql) in RULES.items():
        with st.expander(f'{factor} · {name}'):
            st.code(sql, language='sql')
    st.write('B se aplica a proveedores existentes con cuenta informada. C señala todos los pagos de proveedores que comparten una cuenta no vacía en el maestro, incluso si otro cambio alteró la cuenta del pago. D señala todas las filas del UUID repetido.')
    st.write('Campos vacíos quedan fuera de sus respectivas reglas; requieren controles de calidad separados. La referencia de autorización es el maestro del escenario, no el CONTROL original.')
    st.write('Isolation Forest y LOF están disponibles en ML clásico. Próximos detectores: grafos y homología persistente. Deberán devolver una predicción por fila y mantener las etiquetas separadas de sus entradas.')

with ml_tab:
    st.subheader('Priorizar pagos con aprendizaje no supervisado')
    st.write('Isolation Forest busca registros fáciles de aislar; LOF busca registros menos densos que sus vecinos. Ambos generan alertas generales, sin atribuir una causa A–D.')
    st.caption('Los indicadores superiores y las primeras cuatro pestañas corresponden a SQL. Los resultados de ML se muestran aquí.')
    from ml import MODELS, PROFILES, run_ml, compare

    @st.cache_data
    def ml_case(case, model, profile, budget, neighbors):
        p, m, _ = case_data(case)
        return run_ml(p, m, model, profile, budget, neighbors)

    @st.cache_data
    def ml_batch(profile, budget, neighbors):
        parts = []
        for folder in sorted(DATA.glob('T*_R*')):
            _, _, sql = case_data(folder.name)
            predictions = {model: ml_case(folder.name, model, profile, budget, neighbors)[0] for model in MODELS}
            scores, _, _ = compare(folder.name, sql, predictions)
            scores['Perfil'] = profile
            scores['Presupuesto (%)'] = budget
            scores['Vecinos LOF'] = neighbors
            scores['Escenario'] = folder.name
            scores['Tratamiento'] = folder.name.split('_')[0]
            parts.append(scores)
        return pd.concat(parts, ignore_index=True)

    with st.form('ml_settings'):
        profile = st.selectbox('Variables disponibles', PROFILES)
        a, b = st.columns(2)
        budget = a.slider('Porcentaje de pagos a revisar', 1, 30, 10)
        neighbors = b.slider('Vecinos de LOF', 5, 100, 35, step=5)
        st.form_submit_button('Ejecutar / actualizar detectores')
    st.caption('Se ajustan ambos modelos en el escenario seleccionado (análisis transductivo). No hay entrenamiento supervisado ni prueba de generalización. Semilla de Isolation Forest: 42; 150 árboles. LOF usa escala robusta y vecindad configurable.')
    if profile == PROFILES[1]:
        st.warning('Este perfil incluye explícitamente las reglas SQL A–D y frecuencias de relaciones. Evalúa la priorización de señales conocidas; no demuestra descubrimiento independiente de esas reglas.')
    else:
        st.info('Este perfil usa importes, frecuencia de pagos por proveedor y fechas. No incluye conciliación con maestro, cuentas compartidas ni frecuencia de UUID. Algunas anomalías pueden ser invisibles en estas variables.')
    st.caption('El presupuesto elige exactamente los primeros k = techo(n × porcentaje / 100). No estima la prevalencia real. Empates: orden original de fila. Incluso CONTROL tendrá alertas con este criterio. La puntuación no es una probabilidad y sus escalas no son comparables entre modelos.')
    with st.spinner('Calculando puntuaciones…'):
        runs = {model: ml_case(case, model, profile, budget, neighbors) for model in MODELS}
    predictions = {model: run[0] for model, run in runs.items()}
    summary, coverage, curves = compare(case, flags, predictions)
    cols = st.columns(2)
    for col, (model, (result, _, seconds)) in zip(cols, runs.items()):
        col.metric(model, f"{result['Alerta ML'].sum():,} alertas")
        col.caption(f'Cálculo: {seconds:.2f} s · incluye variables, escalado y modelo; caché en consultas posteriores.')
    if summary.empty:
        st.info('CONTROL no tiene etiquetas; no se calculan métricas de acierto.')
    else:
        st.subheader('Comparación sobre cualquier anomalía A ∪ B ∪ C ∪ D')
        st.dataframe(summary.style.format({k:'{:.1%}' for k in ['Precisión','Recall','F1','Average precision']}, na_rep='No aplica'), hide_index=True, width='stretch')
        st.caption('SQL alerta por reglas; ML usa un presupuesto de revisión. Por ello, los volúmenes de alertas difieren. Average precision evalúa el ranking completo; se omite para SQL, que no genera ranking. No se ajustan parámetros con las etiquetas automáticamente.')
        st.plotly_chart(px.line(curves, x='Recall', y='Precisión', color='Detector', title='Calidad del ranking · curva precisión–recall'))
        st.plotly_chart(px.bar(coverage, x='Factor', y='Recall de cobertura', color='Detector', barmode='group', range_y=[0,1], title='Cobertura de cada anomalía por alertas generales'))
        st.caption('Cobertura por factor: fracción de sus pagos etiquetados que recibe una alerta general. No equivale a clasificar correctamente el tipo de anomalía.')
        st.download_button('Descargar métricas ML', summary.assign(Escenario=case, Perfil=profile, Presupuesto=budget, Vecinos_LOF=neighbors).to_csv(index=False).encode('utf-8-sig'), f'metricas_ml_{case}.csv', 'text/csv')
    st.subheader('Bandeja de revisión ML')
    model = st.selectbox('Ranking a inspeccionar', MODELS)
    result, x, _ = runs[model]
    only_alerts = st.checkbox('Mostrar únicamente pagos priorizados', value=True)
    ranking = payments[['VENDOR_ID','VENDOR_NAME','BANK_ACCOUNT_NUM','UUID','IMPORTE_AP']].copy()
    ranking.insert(0, 'Fila original (base 0)', ranking.index)
    ranking = ranking.join(result)
    ranking['Alerta SQL'] = flags.any(axis=1)
    if only_alerts:
        ranking = ranking.loc[result['Alerta ML']]
    ranking = ranking.sort_values('Puntuación', ascending=False, kind='stable')
    st.dataframe(ranking, hide_index=True, width='stretch')
    st.download_button('Descargar ranking ML', ranking.assign(Detector=model, Escenario=case, Perfil=profile, Presupuesto=budget, Vecinos_LOF=neighbors).to_csv(index=False).encode('utf-8-sig'), f'ranking_{model}_{case}.csv', 'text/csv')
    with st.expander('Variables utilizadas · sin etiquetas'):
        st.dataframe(x, width='stretch')
        st.caption('Faltantes: mediana del escenario; columnas totalmente vacías: cero. RobustScaler estima mediana y rango intercuartílico en este escenario. Identificadores usados solo para agrupar, nunca como magnitudes numéricas.')
    st.subheader('Experimento completo')
    st.caption('Ejecuta ambos modelos y SQL en las 80 variantes con la configuración actual. Puede tardar varios minutos. No compara escenarios como muestras independientes de empresas diferentes.')
    if st.button('Comparar SQL y ML en los 80 escenarios'):
        with st.spinner('Comparando los 80 escenarios…'):
            batch = ml_batch(profile, budget, neighbors)
        st.session_state['ml_batch'] = ((profile, budget, neighbors), batch)
    stored = st.session_state.get('ml_batch')
    if stored and stored[0] == (profile, budget, neighbors):
        batch = stored[1]
        means = batch.groupby(['Tratamiento','Detector'])['Recall'].mean().unstack()
        st.plotly_chart(px.imshow(means, zmin=0, zmax=1, text_auto='.0%', color_continuous_scale='Teal', title='Recall medio · 5 réplicas por tratamiento'))
        st.dataframe(batch, hide_index=True, width='stretch')
        st.download_button('Descargar experimento SQL y ML', batch.to_csv(index=False).encode('utf-8-sig'), 'comparacion_sql_ml.csv', 'text/csv')
