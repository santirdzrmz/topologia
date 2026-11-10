"""
tda_indicadores.py

Vendor risk profile as a weighted indicator vector over the four anomaly
types A-D, and its persistent homology, on the runs built by
`simulate_experiment.py`.

Each vendor i (a row of Maestro, plus every VENDOR_ID in Pagos that has no
Maestro row) becomes a point

    x_i = (A_i, B_i, C_i, D_i)  in {0, 1}^4

  A  proveedor no registrado    VENDOR_ID has no row in Maestro
  B  cuenta no autorizada       a payment of i goes to an account other than
                                i's account in Maestro
  C  cuenta compartida          an account of i (Maestro or payments) is linked
                                to another registered vendor
  D  factura duplicada (UUID)   a payment of i has a UUID used by another payment

and is placed at w * x_i with weights WEIGHTS (A 20, B 30, C 30, D 25). The
weighted score S_i = w . x_i collapses different configurations onto one
number (B and C both give 30; B+D and C+D both give 55). The point cloud keeps
them apart, and persistent homology describes how the configurations are
arranged:

  * H0: the minimum spanning tree of the cloud. Cutting it below the lightest
    weight separates exactly the configurations; the merge scales give the
    hierarchy between them (which profiles are closest).
  * H1: a loop appears when vendors fill the four corners of a rectangle,
    i.e. two anomaly types occur both alone and together.

The indicators are the cross-table rules that define A-D, so they coincide
with the labels by construction (checked at the end). The point is not
detection, which the rules already give, but keeping the shape of each
vendor's risk profile for vendor development: vendors with the same S but a
different configuration need a different fix.

Usage:  python tda_indicadores.py [runs_dir] [out_dir]
        defaults: corridas_simulador  resultados_indicadores
"""
import sys
import warnings
from itertools import combinations
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=SyntaxWarning)  # persim on py>=3.12

_argv, sys.argv = sys.argv, sys.argv[:1]   # tda_anomalies reads argv on import
try:
    from tda_anomalies import mst_edges, read_table
finally:
    sys.argv = _argv

try:
    from ripser import ripser
    HAVE_RIPSER = True
except ImportError:
    HAVE_RIPSER = False

RUNS_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else "corridas_simulador")
OUT_DIR = Path(sys.argv[2] if len(sys.argv) > 2 else "resultados_indicadores")
EXAMPLE_RUN = "T16_R05"

INDICATORS = ["A", "B", "C", "D"]
NAMES = {"A": "proveedor no registrado", "B": "cuenta no autorizada",
         "C": "cuenta compartida", "D": "factura duplicada (UUID repetido)"}
RULES = {"A": "el VENDOR_ID del pago no tiene renglón en el Maestro",
         "B": "un pago va a una cuenta diferente a la del proveedor en el Maestro",
         "C": "una cuenta del proveedor está ligada a otro proveedor registrado",
         "D": "un pago del proveedor usa un UUID que aparece en otro pago"}
WEIGHTS = np.array([20.0, 30.0, 30.0, 25.0])
# below the lightest weight, the MST cut separates exactly the configurations
CUT = WEIGHTS.min() / 2
CLEAN = "0" * len(INDICATORS)


# --------------------------------------------------------------------------
# Indicator vector per vendor
# --------------------------------------------------------------------------
def vendor_indicators(maestro, pagos):
    registered = list(maestro["Id Proveedor"])
    vendor = pagos["VENDOR_ID"]
    known = vendor.isin(set(registered))
    master_acc = dict(zip(maestro["Id Proveedor"], maestro["Cuenta"]))

    A = set(vendor[~known])
    B = set(vendor[known & (pagos["BANK_ACCOUNT_NUM"] != vendor.map(master_acc))])
    links = pd.concat([
        maestro[["Id Proveedor", "Cuenta"]].set_axis(["v", "acc"], axis=1),
        pagos.loc[known, ["VENDOR_ID", "BANK_ACCOUNT_NUM"]].set_axis(["v", "acc"], axis=1),
    ]).drop_duplicates()
    n_vendors = links.groupby("acc")["v"].nunique()
    C = set(links.loc[links["acc"].isin(set(n_vendors[n_vendors > 1].index)), "v"])
    dup_uuid = pagos.groupby("UUID")["UUID"].transform("size") > 1
    D = set(vendor[dup_uuid])

    ids = registered + sorted(A)
    x = pd.DataFrame({"Id Proveedor": ids,
                      "registrado": [1] * len(registered) + [0] * len(A)})
    for name, s in zip(INDICATORS, (A, B, C, D)):
        x[name] = x["Id Proveedor"].isin(s).astype(int)
    x["S"] = x[INDICATORS].to_numpy() @ WEIGHTS
    x["configuracion"] = x[INDICATORS].astype(str).agg("".join, axis=1)
    return x


def config_label(code):
    on = [i for i, c in zip(INDICATORS, code) if c == "1"]
    return "+".join(on) if on else "limpio"


def config_point(code):
    return np.array([int(c) for c in code]) * WEIGHTS


# --------------------------------------------------------------------------
# Persistent homology of the vendor cloud
# --------------------------------------------------------------------------
def h0_groups(n, edges, cut):
    root = np.arange(n)

    def find(a):
        while root[a] != a:
            root[a] = root[root[a]]
            a = root[a]
        return a

    for u, v, w in edges:
        if w <= cut:
            root[find(u)] = find(v)
    return np.array([find(i) for i in range(n)])


def config_hierarchy(x):
    """H0 barcode of the distinct configurations (each born at 0)."""
    conf = x.groupby("configuracion").size().rename("proveedores").reset_index()
    P = np.array([config_point(c) for c in conf["configuracion"]])
    death = np.full(len(conf), np.inf)
    joins = [""] * len(conf)
    if len(conf) > 1:
        # elder rule: the component holding the clean profile (the CONTROL
        # state) survives a merge; otherwise the more populous one does
        size = conf["proveedores"].to_numpy().astype(float)
        size[(conf["configuracion"] == CLEAN).to_numpy()] = np.inf
        root = np.arange(len(conf))
        members = {i: [i] for i in range(len(conf))}
        for u, v, w in mst_edges(P):
            ru, rv = root[u], root[v]
            if size[ru] < size[rv]:
                ru, rv = rv, ru
            death[rv] = w
            joins[rv] = config_label(conf["configuracion"].iat[ru])
            size[ru] += size[rv]
            root[members[rv]] = ru
            members[ru].extend(members.pop(rv))
    conf["muerte_H0"] = death
    conf["se_une_a"] = joins
    conf["S"] = P.sum(axis=1)
    conf["perfil"] = conf["configuracion"].map(config_label)
    order = np.lexsort((conf["S"].to_numpy(), -conf["muerte_H0"].to_numpy()))
    return conf.iloc[order].reset_index(drop=True), P


def h1_loops(P):
    if not HAVE_RIPSER or len(P) < 4:
        return np.zeros((0, 2))
    return ripser(P, maxdim=1)["dgms"][1]


def rectangles(codes):
    """Pairs of types (i, j) whose four corners c, c+i, c+j, c+i+j are all present."""
    present = set(codes)
    out = set()
    for i, j in combinations(range(len(INDICATORS)), 2):
        for c in present:
            if c[i] == "0" and c[j] == "0":
                flip = lambda s, k: s[:k] + "1" + s[k + 1:]
                if {flip(c, i), flip(c, j), flip(flip(c, i), j)} <= present:
                    out.add(INDICATORS[i] + "–" + INDICATORS[j])
    return sorted(out)


def never_together(codes):
    """Pairs of types that never occur in the same vendor."""
    return [INDICATORS[i] + "+" + INDICATORS[j]
            for i, j in combinations(range(len(INDICATORS)), 2)
            if not any(c[i] == "1" and c[j] == "1" for c in codes)]


def collisions(x):
    """Vendors whose S is shared with a vendor of a different configuration."""
    k = x.groupby("S")["configuracion"].nunique()
    mixed = k[k > 1].index
    return int(x["S"].isin(mixed).sum()), len(mixed)


def collision_pairs(x):
    rows = []
    for s, g in x.groupby("S"):
        codes = sorted(g["configuracion"].unique())
        for a, b in combinations(codes, 2):
            rows.append({"S": s, "perfil 1": config_label(a), "perfil 2": config_label(b),
                         "proveedores": "%d / %d" % ((g["configuracion"] == a).sum(),
                                                     (g["configuracion"] == b).sum()),
                         "distancia en la nube":
                             float(np.linalg.norm(config_point(a) - config_point(b)))})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Evaluation, after the model: vendor-level labels
# --------------------------------------------------------------------------
def vendor_labels(run_dir, pagos, ids):
    lab = pd.read_csv(run_dir / "etiquetas_pagos.csv", encoding="utf-8-sig")
    lab_m = pd.read_csv(run_dir / "etiquetas_maestro.csv", encoding="utf-8-sig",
                        dtype={"Id Proveedor": str})
    vendor = pagos["VENDOR_ID"].to_numpy()
    out = pd.DataFrame({"Id Proveedor": ids})
    for f in "ABD":
        out[f] = out["Id Proveedor"].isin(set(vendor[lab[f].to_numpy(bool)]))
    out["C"] = out["Id Proveedor"].isin(set(lab_m.loc[lab_m["C"], "Id Proveedor"]))
    return out


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------
PALETTE = ["#2a6f97", "#e07a5f", "#81b29a", "#f2cc8f", "#6d597a",
           "#3d405b", "#b56576", "#468faf", "#e9c46a", "#bc6c25",
           "#52796f", "#9c6644", "#7d8597", "#c9ada7", "#355070"]
ALL_CODES = sorted((format(k, "0%db" % len(INDICATORS)) for k in range(1, 2 ** len(INDICATORS))),
                   key=lambda c: (c.count("1"), c))


def config_color(code):
    return "#9aa5b1" if code == CLEAN else PALETTE[ALL_CODES.index(code) % len(PALETTE)]


def text_color(hex_color):
    r, g, b = (int(hex_color[k:k + 2], 16) / 255 for k in (1, 3, 5))
    return "black" if 0.299 * r + 0.587 * g + 0.114 * b > 0.6 else "white"


def plot_s_vs_config(x, path, run):
    tab = x.pivot_table(index="S", columns="configuracion", values="Id Proveedor",
                        aggfunc="count", fill_value=0)
    tab = tab[[c for c in sorted(tab.columns, key=lambda c: (c.count("1"), c))]]
    fig, ax = plt.subplots(figsize=(11, 4.8))
    bottom = np.zeros(len(tab))
    pos = np.arange(len(tab))
    for c in tab.columns:
        v = tab[c].to_numpy()
        col = config_color(c)
        ax.bar(pos, v, bottom=bottom, color=col, label="%s  %s" % (c, config_label(c)),
               edgecolor="white", linewidth=0.6)
        for p, b, h in zip(pos, bottom, v):
            if h > 0:
                ax.text(p, b + h / 2, "%s (%d)" % (config_label(c), h), ha="center",
                        va="center", fontsize=8, color=text_color(col))
        bottom += v
    ax.set_xticks(pos, ["S = %g" % s for s in tab.index])
    ax.set_yscale("symlog", linthresh=10)
    ax.set_ylabel("proveedores (escala log)")
    ax.set_title("%s: misma S, distinta configuración\n"
                 "cada barra es un valor de S; los colores son configuraciones (A,B,C,D)" % run)
    ax.legend(fontsize=8, frameon=False, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_hierarchy(conf, h1, path, run):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.8),
                                 gridspec_kw={"width_ratios": [1.6, 1]})
    top = max(conf["muerte_H0"].replace(np.inf, np.nan).max(), 1) * 1.25
    for k, r in conf.iterrows():
        d = r["muerte_H0"] if np.isfinite(r["muerte_H0"]) else top
        a1.barh(k, d, color=config_color(r["configuracion"]), height=0.6)
        tail = "  ∞" if not np.isfinite(r["muerte_H0"]) else "  → %s" % r["se_une_a"]
        a1.text(d + top * 0.01, k, "%s  (%d prov., S=%g)%s" % (
            r["perfil"], r["proveedores"], r["S"], tail), va="center", fontsize=8)
    a1.set_yticks([])
    a1.invert_yaxis()
    a1.set_xlim(0, top * 1.7)
    a1.set_xlabel("escala ε (distancia en puntos de riesgo ponderados)")
    a1.set_title("H0: cada configuración nace en 0 y muere\n"
                 "cuando se une a otra (limpio nunca muere)")
    a1.spines[["top", "right", "left"]].set_visible(False)

    lim = max(top, h1[:, 1].max() * 1.15 if len(h1) else 0)
    a2.plot([0, lim], [0, lim], color="#999", lw=0.8)
    if len(h1):
        a2.scatter(h1[:, 0], h1[:, 1], color="#e07a5f", s=40, zorder=3, alpha=0.8,
                   label="H1 (%d ciclo%s)" % (len(h1), "" if len(h1) == 1 else "s"))
        a2.legend(fontsize=8, frameon=False, loc="lower right")
    a2.set_xlim(0, lim)
    a2.set_ylim(0, lim)
    a2.set_xlabel("nacimiento")
    a2.set_ylabel("muerte")
    a2.set_title("H1: ciclos entre configuraciones")
    a2.spines[["top", "right"]].set_visible(False)
    fig.suptitle(run, fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_configs_by_treatment(counts, path):
    cols = sorted(counts.columns, key=lambda c: (c.count("1"), c))
    data = counts[cols]
    fig, ax = plt.subplots(figsize=(11, 5.4))
    im = ax.imshow(data.to_numpy(), aspect="auto", cmap="Blues",
                   norm=matplotlib.colors.SymLogNorm(linthresh=5, vmin=0,
                                                     vmax=data.to_numpy().max()))
    ax.set_xticks(range(len(cols)), [config_label(c) for c in cols], rotation=35, ha="right")
    ax.set_yticks(range(len(data)), data.index)
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            v = data.iat[i, j]
            ax.text(j, i, "%.1f" % v if v else "·", ha="center", va="center", fontsize=7,
                    color="white" if v > 100 else "black")
    ax.set_title("Proveedores por configuración (promedio de 5 réplicas)")
    fig.colorbar(im, ax=ax, fraction=0.03)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------
def md_table(df):
    cell = lambda v: ("%.3g" % v) if isinstance(v, float) else str(v)
    lines = ["| " + " | ".join(map(str, df.columns)) + " |",
             "|" + "---|" * len(df.columns)]
    lines += ["| " + " | ".join(cell(v) for v in r) + " |"
              for r in df.itertuples(index=False)]
    return "\n".join(lines)


def write_report(metrics, by_treat, ex_info, agreement, n_ctrl, path):
    w = dict(zip(INDICATORS, WEIGHTS))
    L = ["# Vector de anomalías ponderadas por proveedor y homología persistente", "",
         "Cada proveedor es un punto x_i = (A, B, C, D) con valores 0/1, colocado en w·x_i con "
         "w = (%s):" % ", ".join("%g" % v for v in WEIGHTS), ""]
    L += ["| Anomalía | Peso | Se activa cuando |", "|---|---|---|"]
    L += ["| %s · %s | %g | %s |" % (i, NAMES[i], w[i], RULES[i]) for i in INDICATORS]
    L += ["", "Los proveedores son los %d del Maestro más cada `VENDOR_ID` de Pagos que no tiene "
          "renglón en el Maestro (los de A)." % n_ctrl, ""]
    L += ["La puntuación S = w·x junta configuraciones distintas en un mismo número; el punto en 4-D "
          "no. La homología persistente describe cómo están acomodadas las configuraciones:", "",
          "- **H0:** el árbol de expansión mínima de la nube. Cortado a ε = %g (la mitad del peso "
          "más ligero) separa exactamente las configuraciones; la escala a la que cada una se une "
          "con otra da la jerarquía entre perfiles." % CUT,
          "- **H1:** aparece un ciclo cuando los proveedores ocupan las cuatro esquinas de un "
          "rectángulo, es decir, dos anomalías ocurren solas y juntas.", ""]
    L += ["## Antes de leer los resultados", "",
          "- Los indicadores son las reglas que definen A–D, así que coinciden con las etiquetas "
          "por construcción (ver la última tabla). Esto **no mide detección**; describe el perfil "
          "de riesgo de cada proveedor para el desarrollo de proveedores: dos proveedores con la "
          "misma S y distinta configuración necesitan una corrección distinta.",
          "- Los pesos de A (20) y D (25) son una elección: D conserva el peso de \"factura "
          "duplicada\" y A toma el de \"RFC distinto\". Se cambian en `WEIGHTS`.",
          "- En CONTROL los %d proveedores están en (0,0,0,0): una sola configuración y S = 0."
          % n_ctrl, ""]

    ex, conf, h1, pairs, rects, apart = ex_info
    L += ["## Corrida extrema %s (A, B, C, D en nivel alto)" % EXAMPLE_RUN, "",
          "- Proveedores: %d (%d registrados + %d no registrados)." % (
              ex["proveedores"], ex["proveedores"] - ex["n_A"], ex["n_A"]),
          "- Configuraciones distintas (grupos H0 a ε = %g): **%d**; valores distintos de S: **%d**."
          % (CUT, ex["configuraciones"], ex["valores_S"]),
          "- Proveedores cuya S coincide con la de otra configuración: **%d de %d** (%.0f %%), "
          "en %d valores de S." % (ex["proveedores_en_colision"], ex["proveedores"],
                                    100 * ex["proveedores_en_colision"] / ex["proveedores"],
                                    ex["valores_S_en_colision"]),
          "- Ciclos H1: **%d**." % ex["ciclos_H1"], ""]
    L += ["### Qué confunde S y qué separa la nube", "", md_table(pairs), ""]
    L += ["### Jerarquía H0 de las configuraciones", "",
          "Muerte = escala a la que la configuración se une a otra; el perfil limpio (el estado "
          "de CONTROL) nunca muere. Las muertes son pesos: morir a 25 quiere decir que el perfil "
          "se distingue de su vecino solo por D; a 20, solo por A; a 30, por B o por C.", "",
          md_table(conf[["perfil", "configuracion", "proveedores", "S", "muerte_H0", "se_une_a"]]
                   .rename(columns={"configuracion": "(A,B,C,D)",
                                    "se_une_a": "se une al bloque de"})), ""]
    L += ["### Ciclos H1", ""]
    if len(h1):
        L += ["Diagrama H1 (nacimiento, muerte): " + ", ".join(
            "(%.1f, %.1f)" % tuple(p) for p in h1) + ".", ""]
    L += ["- Planos con las cuatro esquinas ocupadas (dos anomalías solas y juntas): %s."
          % (", ".join(rects) if rects else "ninguno"),
          "- Combinaciones que no aparecen en ningún proveedor: %s." % (
              ", ".join(apart) if apart else "ninguna"),
          "- Por qué faltan: A+B y A+C no pueden ocurrir porque un proveedor no registrado no "
          "tiene cuenta en el Maestro contra la cual comparar; B+C no ocurre porque el simulador "
          "sortea B fuera de los pagos de C. En esos planos falta una esquina y no hay ciclo.", ""]
    L += ["Figuras: `s_vs_configuracion.png` (qué configuraciones esconde cada valor de S) y "
          "`jerarquia_h0.png` (código de barras H0 y diagrama H1).", ""]

    L += ["## Por tratamiento (promedio de 5 réplicas)", "",
          "Niveles en % (A, B, D de pagos; C de proveedores); n_X = proveedores con la anomalía X.",
          "", md_table(by_treat), "",
          "Figura: `configuraciones_por_tratamiento.png`.", ""]

    L += ["## Comprobación con etiquetas (después del modelo)", "",
          "Coincidencia por proveedor entre cada indicador y su etiqueta, en las 80 corridas:", "",
          md_table(agreement), ""]
    path.write_text("\n".join(L), encoding="utf-8")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ctrl_m = read_table(RUNS_DIR / "CONTROL" / "Maestro.csv")
    ctrl_p = read_table(RUNS_DIR / "CONTROL" / "Pagos.csv")
    x_ctrl = vendor_indicators(ctrl_m, ctrl_p)
    assert x_ctrl["S"].eq(0).all(), "CONTROL should have no active indicator"

    design = pd.read_csv(RUNS_DIR / "matriz_experimental.csv")
    levels = lambda t: design.loc[design["tratamiento"] == t, list("ABCD")].iloc[0]
    rows, counts, agree = [], [], []
    ex_info = None
    for run_dir in sorted(RUNS_DIR.glob("T*_R*")):
        run = run_dir.name
        t = int(run[1:3])
        maestro = read_table(run_dir / "Maestro.csv")
        pagos = read_table(run_dir / "Pagos.csv")

        # model: indicator vectors -> weighted cloud -> persistent homology
        x = vendor_indicators(maestro, pagos)
        X = x[INDICATORS].to_numpy() * WEIGHTS
        groups = h0_groups(len(X), mst_edges(X), CUT)
        # the H0 groups at the cut are exactly the configurations
        assert pd.crosstab(groups, x["configuracion"]).gt(0).sum(axis=1).eq(1).all()
        conf, P = config_hierarchy(x)
        h1 = h1_loops(P)
        n_coll, s_coll = collisions(x)
        rows.append({"corrida": run, "tratamiento": t,
                     **{"nivel_" + f: v for f, v in levels(t).items()},
                     "proveedores": len(x),
                     "configuraciones": len(np.unique(groups)),
                     "valores_S": x["S"].nunique(),
                     "proveedores_en_colision": n_coll,
                     "valores_S_en_colision": s_coll,
                     "ciclos_H1": len(h1),
                     **{"n_" + i: int(x[i].sum()) for i in INDICATORS}})
        counts.append(x["configuracion"].value_counts().rename(run))

        # evaluation, after the model
        lab = vendor_labels(run_dir, pagos, x["Id Proveedor"])
        agree.append({i: (x[i].astype(bool) == lab[i]).mean() for i in INDICATORS})

        if run == EXAMPLE_RUN:
            codes = list(conf["configuracion"])
            ex_info = [rows[-1], conf, h1, collision_pairs(x), rectangles(codes),
                       never_together(codes)]
            plot_s_vs_config(x, OUT_DIR / "s_vs_configuracion.png", run)
            plot_hierarchy(conf, h1, OUT_DIR / "jerarquia_h0.png", run)
            x.to_csv(OUT_DIR / ("vectores_%s.csv" % run), index=False, encoding="utf-8-sig")
        print(run, "configuraciones", rows[-1]["configuraciones"],
              "colisiones", n_coll, "H1", len(h1), flush=True)

    metrics = pd.DataFrame(rows)
    metrics.to_csv(OUT_DIR / "metricas_por_corrida.csv", index=False, encoding="utf-8-sig")

    counts = pd.concat(counts, axis=1).fillna(0).T
    counts["tratamiento"] = metrics.set_index("corrida")["tratamiento"]
    by_conf = counts.groupby("tratamiento").mean()
    by_conf.index = ["T%02d A%s B%s C%s D%s" % (t, *levels(t)) for t in by_conf.index]
    plot_configs_by_treatment(by_conf, OUT_DIR / "configuraciones_por_tratamiento.png")

    cols = ["proveedores", "configuraciones", "valores_S", "proveedores_en_colision",
            "ciclos_H1"] + ["n_" + i for i in INDICATORS]
    by_treat = (metrics.groupby(["tratamiento"] + ["nivel_" + f for f in "ABCD"])[cols]
                .mean().round(1).reset_index()
                .rename(columns=lambda c: c.replace("nivel_", "")))
    agreement = pd.DataFrame(agree).agg(["mean", "min"]).T.reset_index()
    agreement.columns = ["anomalía", "coincidencia media", "mínima"]
    write_report(metrics, by_treat, ex_info, agreement, len(x_ctrl), OUT_DIR / "informe.md")
    print("listo:", OUT_DIR)


if __name__ == "__main__":
    main()
