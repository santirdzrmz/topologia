import sys
from pathlib import Path

import numpy as np
import pandas as pd
import networkx as nx
import plotly.graph_objects as go

import kmapper as km

from mapper_fraude import correr_mapper, leer, buscar, FLAGS

COLORES = {
    "Cuerpo principal": "#B4B2A9", "A": "#D85A30", "B": "#7F77DD", "C": "#1D9E75", "D": "#378ADD",
    "A+D": "#8E3A1B", "B+D": "#3C3489", "C+D": "#0F5E49", "Importe atipico": "#EF9F27",
}
EXTRA = ["#C2185B", "#5D4037", "#00838F", "#9E9D24", "#6A1B9A", "#AD1457", "#455A64"]
NOMBRES = {
    "Cuerpo principal": "Pagos normales", "A": "A · proveedor no existe", "B": "B · cuenta no autorizada",
    "C": "C · cuenta compartida", "D": "D · factura duplicada", "Importe atipico": "Monto fuera de lo normal",
    "Normal": "Normales aislados",
}
FONDO = "#F6F4EF"
TEXTO = "#1F2A37"


def _color(perfil, usados):
    if perfil in COLORES:
        return COLORES[perfil]
    usados.setdefault(perfil, EXTRA[len(usados) % len(EXTRA)])
    return usados[perfil]


def _perfiles(f):
    """Nombre de cada pago según su isla: criterio (A, B+D, ...), cuerpo principal o monto atípico."""
    def sin_criterio(sub, k):
        if k == 0:
            return "Cuerpo principal"
        return "Importe atipico" if sub["desv_importe_prov"].mean() > 0.5 else "Normal"
    f = f.copy()
    perfil = pd.Series("", index=f.index)
    for k, sub in f.groupby("componente"):
        if k >= 0:
            crit = sub["criterio_mapper"].mode()[0]
            perfil[sub.index] = crit if crit else sin_criterio(sub, k)
    ais = f["componente"] == -1
    for i in f.index[ais]:
        crit = f.at[i, "criterio_mapper"]
        perfil[i] = (crit if crit else sin_criterio(f.loc[[i]], -1)) + " (aislado)"
    f["perfil_componente"] = perfil
    return f


def _layout(g, G, f):
    """Posiciones: cuerpo principal a la izquierda, las demás islas en una cuadrícula a la derecha."""
    perfil_agrupado = f["perfil_componente"].str.replace(" (aislado)", "", regex=False)
    comps = sorted(nx.connected_components(g), key=lambda c: -len({i for n in c for i in G["nodes"][n]}))

    por_perfil = {}
    for comp in comps:
        idx = sorted({i for n in comp for i in G["nodes"][n]})
        perfil = f.loc[idx, "perfil_componente"].mode()[0]
        por_perfil.setdefault(perfil, []).append(comp)

    otros = sorted([p for p in por_perfil if p != "Cuerpo principal"],
                   key=lambda p: -(perfil_agrupado == p).sum())
    orden = (["Cuerpo principal"] if "Cuerpo principal" in por_perfil else []) + otros

    cols = 3
    pos, islas = {}, []
    for j, perfil in enumerate(orden):
        if perfil == "Cuerpo principal":
            centro, escala = (0.0, -0.3), 2.0
        else:
            k = j - 1 if "Cuerpo principal" in por_perfil else j
            centro, escala = (3.4 + 1.9 * (k % cols), 2.0 - 2.3 * (k // cols)), 0.5
        grupo = por_perfil[perfil]
        for m, comp in enumerate(grupo):
            sp = nx.spring_layout(g.subgraph(comp), seed=3) if len(comp) > 1 else {next(iter(comp)): np.zeros(2)}
            dx = (m - (len(grupo) - 1) / 2) * 0.6
            s = escala if len(grupo) == 1 else escala * 0.55
            for n, (x, y) in sp.items():
                pos[n] = (centro[0] + dx + s * x, centro[1] + s * y)
        islas.append({"perfil": perfil, "centro": centro, "escala": escala,
                      "pagos": int((perfil_agrupado == perfil).sum()), "nodos": sum(len(c) for c in grupo)})
    return pos, islas


def figura_islas(carpeta, titulo=None):
    """Corre Mapper sobre una corrida y regresa (figura Plotly, tabla resumen por isla)."""
    carpeta = Path(carpeta)
    maestro = leer(buscar(carpeta, "Maestro"))
    pagos = leer(buscar(carpeta, "Pagos"))
    f, G, _ = correr_mapper(maestro, pagos)
    f = _perfiles(f)
    g = km.adapter.to_nx(G)
    pos, islas = _layout(g, G, f)
    usados = {}

    # aristas
    ex, ey = [], []
    for a, b in g.edges:
        ex += [pos[a][0], pos[b][0], None]
        ey += [pos[a][1], pos[b][1], None]
    trazas = [go.Scatter(x=ex, y=ey, mode="lines", line=dict(color="#8A8780", width=2),
                           hoverinfo="skip", showlegend=False)]

    # nodos, una traza por perfil para que la leyenda permita prender y apagar islas
    filas = []
    for n in g.nodes:
        idx = G["nodes"][n]
        sub = f.loc[idx]
        perfil = sub["perfil_componente"].mode()[0]
        filas.append({
            "nodo": n, "perfil": perfil, "x": pos[n][0], "y": pos[n][1], "pagos": len(idx),
            "rareza": sub["score_iforest"].mean(),
            "importe_mediano": float(10 ** sub["log_importe"].median()),
            "dias": sub["dias_factura_pago"].mean(),
            **{c[0]: sub[c].mean() for c in FLAGS},
        })
    nodos = pd.DataFrame(filas)
    for perfil, d in nodos.groupby("perfil", sort=False):
        hover = [
            f"<b>{NOMBRES.get(perfil, perfil)}</b><br>"
            f"Pagos en el nodo: {r.pagos:,}<br>"
            f"Rareza promedio: {r.rareza:.3f}<br>"
            f"Importe mediano: ${r.importe_mediano:,.0f}<br>"
            f"Días factura→pago: {r.dias:.0f}<br>"
            f"A {r.A:.0%} · B {r.B:.0%} · C {r.C:.0%} · D {r.D:.0%}"
            for r in d.itertuples()
        ]
        trazas.append(go.Scatter(
            x=d["x"], y=d["y"], mode="markers", name=NOMBRES.get(perfil, perfil),
            marker=dict(size=np.minimum(60, 9 + 0.9 * np.sqrt(d["pagos"])), color=_color(perfil, usados),
                        line=dict(color="#2B2B2B", width=1)),
            text=hover, hovertemplate="%{text}<extra></extra>"))

    fig = go.Figure(trazas)
    for isla in islas:
        cx, cy = isla["centro"]
        principal = isla["perfil"] == "Cuerpo principal"
        fig.add_annotation(
            x=cx, y=(cy - 2.45) if principal else (cy - isla["escala"] - 0.2), showarrow=False,
            text=(f"<b>{NOMBRES.get(isla['perfil'], isla['perfil'])}</b><br>{isla['pagos']:,} pagos"
                  if principal else f"{NOMBRES.get(isla['perfil'], isla['perfil'])}<br>{isla['pagos']:,} pagos"),
            font=dict(size=15 if principal else 13, color=TEXTO), yanchor="top")

    n_aislados = int((f["componente"] == -1).sum())
    if n_aislados:
        fig.add_annotation(xref="paper", yref="paper", x=1, y=1.02, showarrow=False, xanchor="right",
                           text=f"{n_aislados} pagos quedaron aislados (sin nodo); se cuentan en su patrón",
                           font=dict(size=12, color="#4A5563"))
    n_filas = max(1, int(np.ceil((len(islas) - 1) / 3)))
    fig.update_layout(
        title=dict(text=titulo or f"Islas de Mapper · {carpeta.name}", font=dict(size=20, color=TEXTO)),
        plot_bgcolor=FONDO, paper_bgcolor=FONDO, height=680,
        xaxis=dict(visible=False, range=[-2.4, 8.2]),
        yaxis=dict(visible=False, range=[min(-3.3, 2.0 - 2.3 * (n_filas - 1) - 1.4), 2.7],
                   scaleanchor="x", scaleratio=1),
        legend=dict(title="Clic para ocultar o mostrar", orientation="h", y=-0.02, font=dict(color=TEXTO)),
        margin=dict(l=20, r=20, t=60, b=20), hoverlabel=dict(bgcolor="white", font_size=13),
    )

    resumen = pd.DataFrame([{"isla": NOMBRES.get(i["perfil"], i["perfil"]), "patron": i["perfil"],
                             "pagos": i["pagos"], "nodos": i["nodos"]} for i in islas])
    # patrones que solo tienen pagos aislados (muy pocos pagos para formar un nodo)
    agrupado = f["perfil_componente"].str.replace(" (aislado)", "", regex=False)
    for p in agrupado.unique():
        if p not in set(resumen["patron"]):
            resumen.loc[len(resumen)] = [NOMBRES.get(p, p) + " (solo aislados)", p, int((agrupado == p).sum()), 0]
    return fig, resumen


def guardar_html(carpeta, destino):
    fig, resumen = figura_islas(carpeta)
    fig.write_html(destino, include_plotlyjs="cdn", full_html=True,
                   config={"displaylogo": False, "scrollZoom": True})
    return resumen


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ruta = Path(args[0] if args else ".")
    if "--todas" in sys.argv:
        salida = ruta / "salida_mapper" / "islas"
        salida.mkdir(parents=True, exist_ok=True)
        carpetas = sorted(p for p in ruta.iterdir()
                          if p.is_dir() and any(x.name.lower().startswith("pagos") for x in p.glob("*.csv")))
        for i, c in enumerate(carpetas, 1):
            try:
                guardar_html(c, salida / f"{c.name}.html")
                print(f"[{i:>2}/{len(carpetas)}] {c.name}")
            except Exception as e:
                print(f"[{i:>2}/{len(carpetas)}] {c.name} ERROR: {e}")
        print(f"Listo: {salida}")
    else:
        destino = Path(f"{ruta.name}_islas.html")
        print(guardar_html(ruta, destino).to_string(index=False))
        print(f"-> {destino.resolve()}")


if __name__ == "__main__":
    main()