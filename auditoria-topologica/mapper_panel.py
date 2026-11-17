"""Vista de Mapper y trazabilidad de los pagos de cada nodo."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from mapper import build_mapper
from persistence import fit_reference, scaled_behavior


@st.cache_data(max_entries=16)
def case_mapper(payments, control_payments, lens, intervals, overlap, eps, min_samples):
    features = scaled_behavior(payments, fit_reference(control_payments))
    return build_mapper(features.to_numpy(), features[lens].to_numpy(),
                        intervals, overlap / 100, eps, min_samples)


def mapper_figure(summary, edges):
    x = summary['Intervalo'].to_numpy()
    groups = summary.groupby('Intervalo')['Nodo']
    y = (groups.cumcount() - (groups.transform('size') - 1) / 2).to_numpy()
    edge_x, edge_y = [], []
    for left, right in edges:
        edge_x.extend((x[left], x[right], None))
        edge_y.extend((y[left], y[right], None))
    fig = go.Figure()
    fig.add_scatter(x=edge_x, y=edge_y, mode='lines',
                    line=dict(color='#8294a7', width=1), hoverinfo='skip')
    counts = summary['Pagos']
    fig.add_scatter(
        x=x, y=y, mode='markers', text=summary['Nodo'],
        customdata=summary[['Pagos', 'Tasa de alerta SQL', 'Límite inferior', 'Límite superior']],
        hovertemplate=('<b>%{text}</b><br>Intervalo %{x}<br>Pagos: %{customdata[0]}'
                       '<br>Con alerta SQL: %{customdata[1]:.1%}'
                       '<br>Rango de la lente: [%{customdata[2]:.2f}, %{customdata[3]:.2f}]'
                       '<extra></extra>'),
        marker=dict(size=9 + 27 * np.sqrt(counts / counts.max()),
                    color=summary['Tasa de alerta SQL'], colorscale='Teal',
                    cmin=0, cmax=1, colorbar=dict(title='Alerta SQL', tickformat='.0%'),
                    line=dict(width=1, color='#16324f')),
    )
    fig.update_layout(showlegend=False, xaxis_title='Intervalo de la lente',
                      yaxis=dict(visible=False), margin=dict(l=20, r=20, t=20, b=35))
    fig.update_xaxes(dtick=1, range=[0.5, int(x.max()) + 0.5])
    return fig


def show_mapper(case, payments, flags, control_payments):
    st.subheader(f'Mapper · {case}')
    st.write('Cada nodo agrupa pagos de comportamiento similar dentro de un intervalo de la lente. '
             'Dos nodos se conectan si comparten al menos un pago.')
    st.caption('Las cuatro variables de comportamiento se escalan con CONTROL. '
               'Las alertas SQL colorean los nodos después de agrupar los pagos.')
    if payments.empty or control_payments.empty:
        st.info('Se necesitan pagos en el escenario y en CONTROL para construir el mapa.')
        return

    lenses = ['Importe log', 'Desviación de importe', 'Días factura a pago',
              'Días factura a vencimiento']
    settings = st.session_state.setdefault('mapper_settings_by_case', {})
    saved_lens, saved_intervals, saved_overlap, saved_eps, saved_min_samples = settings.get(
        case, (lenses[0], 8, 35, 0.8, 5)
    )
    with st.form(f'mapper_settings_{case}'):
        lens = st.selectbox('Lente de Mapper', lenses, index=lenses.index(saved_lens))
        a, b = st.columns(2)
        intervals = a.slider('Intervalos de la lente', 2, 20, saved_intervals)
        overlap = b.slider('Solapamiento (%)', 0, 70, saved_overlap, step=5)
        eps = a.slider('Radio de DBSCAN (ε)', 0.1, 4.0, saved_eps, step=0.1)
        min_samples = b.slider('Mínimo de pagos en la vecindad', 2, 30, saved_min_samples)
        submitted = st.form_submit_button('Construir mapa')
    node_key = f'mapper_node_{case}'
    if submitted:
        settings[case] = (lens, intervals, overlap, eps, min_samples)
        st.session_state.pop(node_key, None)
    if case not in settings:
        return

    with st.spinner('Construyendo el grafo de Mapper…'):
        nodes, edges, covered = case_mapper(payments, control_payments, *settings[case])

    metrics = st.columns(3)
    metrics[0].metric('Nodos', len(nodes))
    metrics[1].metric('Aristas', len(edges))
    metrics[2].metric('Pagos en algún nodo', f'{covered.sum():,} / {len(payments):,}')
    alert = flags.any(axis=1).to_numpy()
    node_ids = [f'N{i:02d}' for i in range(1, len(nodes) + 1)]
    if nodes:
        summary = pd.DataFrame(
            [(node_id, interval, len(rows), alert[rows].mean(), low, high)
             for node_id, (interval, low, high, rows) in zip(node_ids, nodes)],
            columns=['Nodo', 'Intervalo', 'Pagos', 'Tasa de alerta SQL',
                     'Límite inferior', 'Límite superior'],
        )
        st.plotly_chart(mapper_figure(summary, edges))
        st.caption('El tamaño indica cuántos pagos contiene el nodo. La posición vertical '
                   'separa visualmente los nodos del mismo intervalo.')
        st.dataframe(summary.style.format({'Tasa de alerta SQL': '{:.1%}',
                                           'Límite inferior': '{:.2f}', 'Límite superior': '{:.2f}'}),
                     hide_index=True, width='stretch')
    else:
        st.info('DBSCAN no formó grupos con estos parámetros.')

    st.subheader('Pagos por nodo')
    rows_by_node = dict(zip(node_ids, (node[3] for node in nodes)))
    if not covered.all():
        rows_by_node['Pagos sin nodo'] = np.flatnonzero(~covered)
    selected = st.selectbox('Grupo de pagos', rows_by_node, key=node_key)
    rows = rows_by_node[selected]
    detail = payments.iloc[rows][['VENDOR_ID', 'VENDOR_NAME', 'UUID', 'IMPORTE_AP']].copy()
    detail.insert(0, 'Fila original (base 0)', detail.index)
    detail['Alerta SQL'] = alert[rows]
    st.dataframe(detail, hide_index=True, width='stretch')
    st.download_button('Descargar pagos seleccionados', detail.to_csv(index=False).encode('utf-8-sig'),
                       f'mapper_{case}_{selected}.csv', 'text/csv')
