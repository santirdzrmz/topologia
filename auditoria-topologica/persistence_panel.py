"""Resultados de homología persistente para el escenario seleccionado."""
import pandas as pd
import plotly.express as px
import streamlit as st
from sklearn.metrics import average_precision_score, roc_auc_score

from ml import truth_for
from persistence import MAX_LANDMARKS, MASS_FRACTION, diagrams, fit_reference, mass_scores, point_cloud


@st.cache_data
def control_geometry(payments, flags):
    reference = fit_reference(payments)
    return reference, diagrams(point_cloud(payments, flags, reference))


@st.cache_data
def scenario_geometry(payments, flags, reference):
    points = point_cloud(payments, flags, reference)
    return mass_scores(points), diagrams(points)


def show_persistence(case, payments, flags, control_payments, control_flags):
    st.subheader(f'Homología persistente · {case}')
    st.write('H₀ mide a qué distancia cada pago pasa a formar parte de un grupo grande. '
             'Los diagramas H₀ y H₁ resumen componentes y ciclos del escenario frente a CONTROL.')
    st.caption(f'Comportamiento escalado con CONTROL y banderas SQL A–D con peso 4. '
               f'Masa mínima H₀: {MASS_FRACTION:.0%} de los pagos. '
               f'Diagramas de Vietoris–Rips con hasta {MAX_LANDMARKS} pagos por escenario.')
    if payments.empty or control_payments.empty:
        st.info('Se necesitan pagos en el escenario y en CONTROL para calcular la homología.')
        return

    requested = st.session_state.setdefault('persistence_cases', set())
    if st.button('Calcular homología persistente', key='calculate_persistence'):
        requested.add(case)
    if case not in requested:
        return

    from persim import wasserstein

    with st.spinner('Calculando homología persistente…'):
        reference, baseline = control_geometry(control_payments, control_flags)
        scores, current = scenario_geometry(payments, flags, reference)

    st.subheader('Forma de la corrida frente a CONTROL')
    for dim, col in enumerate(st.columns(2)):
        distance = wasserstein(current[dim], baseline[dim])
        col.metric(f'Distancia de Wasserstein H{dim}', f'{distance:.3f}')
    groups = [('CONTROL', baseline)]
    if case != 'CONTROL':
        groups.append((case, current))
    intervals = pd.DataFrame(
        [(name, f'H{dim}', birth, death) for name, dgms in groups
         for dim, dgm in enumerate(dgms) for birth, death in dgm],
        columns=['Escenario', 'Dimensión', 'Nacimiento', 'Muerte'],
    )
    if intervals.empty:
        st.caption('Los diagramas no tienen intervalos finitos.')
    else:
        limit = float(intervals['Muerte'].max())
        chart = px.scatter(intervals, x='Nacimiento', y='Muerte', color='Escenario',
                           symbol='Dimensión', opacity=0.6, title='Diagramas de persistencia')
        chart.add_shape(type='line', x0=0, y0=0, x1=limit, y1=limit, line_dash='dot')
        chart.update_yaxes(scaleanchor='x', scaleratio=1)
        st.plotly_chart(chart)

    st.subheader('Detección de anomalías etiquetadas')
    truth = truth_for(case, payments.index)
    if truth is None:
        st.info('Este escenario no tiene etiquetas. Se muestran la forma y el ranking.')
    else:
        target = truth.any(axis=1)
        if target.nunique() < 2:
            st.info('Se necesitan pagos etiquetados y no etiquetados para calcular AUC y AP.')
        else:
            metrics = pd.DataFrame([
                {'Método': name, 'AUC ROC': roc_auc_score(target, score),
                 'Average precision': average_precision_score(target, score)}
                for name, score in [('Puntaje H₀', scores), ('Cualquier regla SQL', flags.any(axis=1))]
            ])
            st.dataframe(metrics.style.format(precision=3), hide_index=True, width='stretch')
            st.caption('Evaluación sobre la unión de A–D. La comparación SQL muestra cuánto '
                       'distinguen por sí solas las reglas que también entran al puntaje H₀.')

    st.subheader('Ranking de pagos por puntaje H₀')
    ranking = payments[['VENDOR_ID', 'VENDOR_NAME', 'UUID', 'IMPORTE_AP']].copy()
    ranking.insert(0, 'Fila original (base 0)', ranking.index)
    ranking['Puntaje H₀'] = scores
    ranking['Alerta SQL'] = flags.any(axis=1)
    if truth is not None:
        ranking['Anomalía etiquetada'] = truth.any(axis=1)
    ranking = ranking.sort_values('Puntaje H₀', ascending=False, kind='stable')
    st.dataframe(ranking, hide_index=True, width='stretch')
    st.download_button('Descargar ranking H₀', ranking.to_csv(index=False).encode('utf-8-sig'),
                       f'ranking_h0_{case}.csv', 'text/csv')
