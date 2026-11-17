"""
tda_comportamiento.py

Leak-free persistent-homology analysis of the runs built by
`simulate_experiment.py`.

Ingestion: the model only sees behaviour. From each run's Maestro.csv and
Pagos.csv it builds two feature sets, scaled on CONTROL:

  * C4: log amount, amount z within the vendor, days invoice->payment and
    invoice->due date (the `CONTINUOUS` columns of tda_anomalies.py).
  * C6: C4 + payment cadence computed inside Pagos only: log of
    (days since the vendor's previous payment + 1) / (vendor median + 1),
    and log of the vendor's number of payments.
  * C6M: C6 + the vendor's attributes from Maestro, joined by VENDOR_ID:
    deviation of days invoice->payment from the Maestro terms, vendor age
    and days since its last Maestro update at the payment date, and
    indicators of vendor type, payment method, tax rate, Resico and site.
    A payment whose VENDOR_ID has no Maestro row gets the CONTROL median for
    the numeric attributes and zeros for the indicators. Maestro columns the
    simulator fills at random (FA, Calculo/Impuesto Incluidos, Aplica Grupo
    Retencion) are left out because they carry no structure.

No variable states that a row is A, B, C or D: the four cross-table flags
(unregistered vendor, account different from Maestro, shared account,
repeated UUID) never enter the model.

Model (persistent homology only):
  * H0 score per payment: scale at which its component in the Rips
    filtration (= minimum spanning tree) reaches tau * n points.
  * H0 groups: the MST is cut at the largest H0 death of CONTROL (a
    threshold taken from clean data, no labels); the largest component is
    the bulk, the rest are "separate groups".
  * Run shape: Rips diagrams (H0, H1) on a max-min subsample and their
    Wasserstein distance to CONTROL.

Only after the model has produced scores and groups are the labels and the
cross-table flags read, to describe what each group contains (A-D share,
flags, hypergeometric enrichment) and to score detection (AUC). Isolation
Forest on the same features is reported as a reference, not as part of the
model.

Usage:  python tda_comportamiento.py [runs_dir] [out_dir]
        defaults: corridas_simulador  resultados_comportamiento
"""
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.stats import hypergeom
from sklearn.ensemble import IsolationForest
from sklearn.metrics import adjusted_rand_score, roc_auc_score

warnings.filterwarnings("ignore", category=SyntaxWarning)  # persim on py>=3.12

_argv, sys.argv = sys.argv, sys.argv[:1]   # tda_anomalies reads argv on import
try:
    from tda_anomalies import (CLIP, CONTINUOUS, N_PERM, RELATIONAL, TAU,
                               finite, h0_mass_scores, mst_edges,
                               payment_features, read_table)
finally:
    sys.argv = _argv

try:
    from persim import wasserstein
    from ripser import ripser
    HAVE_RIPSER = True
except ImportError:  # H0 score and groups do not need ripser
    HAVE_RIPSER = False

RUNS_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else "corridas_simulador")
OUT_DIR = Path(sys.argv[2] if len(sys.argv) > 2 else "resultados_comportamiento")
FACTORS = "ABCD"
EXAMPLE_RUN = "T16_R05"
CADENCE = ["log_brecha_relativa", "log_n_pagos_proveedor"]
MAESTRO_NUM = ["desvio_terminos", "antiguedad_proveedor", "dias_desde_actualizacion"]
MAESTRO_CATS = {"Tipo Proveedor": "tipo", "Metodo de Pago": "metodo",
                "Impuesto": "impuesto", "Resico": "resico", "Site": "site"}
# name -> (numeric columns, 0/1 indicator columns); C6M indicators are added
# in main() from the categories present in CONTROL's Maestro
RED = ["log_proveedores_componente", "log_ciclos_componente",
       "log_persistencia_fusion", "ciclos_cerrados"]
FEATURE_SETS = {"C4": (CONTINUOUS, []),
                "C6": (CONTINUOUS + CADENCE, []),
                "C6M": (CONTINUOUS + CADENCE + MAESTRO_NUM, []),
                "R": (RED, []),
                "C6M+R": (CONTINUOUS + CADENCE + MAESTRO_NUM + RED, [])}
MODEL_SET_FOR_EXAMPLE = "C6M+R"
COLORS = {"limpio": "#b4b0a7", "A": "#c24e26", "B": "#5e55c4",
          "C": "#147a5a", "D": "#2668b3", "varias": "#1f2a37"}


# --------------------------------------------------------------------------
# Ingestion: behaviour only
# --------------------------------------------------------------------------
def cadence_features(pagos):
    """Payment cadence per VENDOR_ID, from Pagos alone."""
    fecha = pd.to_datetime(pagos["FECHA_D_PAGO"], format="%d/%m/%y")
    vendor = pagos["VENDOR_ID"]
    order = np.lexsort((np.arange(len(pagos)), fecha.to_numpy(), vendor.to_numpy()))
    f_sorted, v_sorted = fecha.iloc[order], vendor.iloc[order]
    gap = f_sorted.groupby(v_sorted.to_numpy()).diff().dt.days
    gap = pd.Series(gap.to_numpy(), index=order).sort_index()
    med = gap.groupby(vendor.to_numpy()).transform("median")
    rel = np.log((gap + 1) / (med + 1)).fillna(0.0)   # first payment: neutral
    n = vendor.map(vendor.value_counts())
    return pd.DataFrame({"log_brecha_relativa": rel.to_numpy(),
                         "log_n_pagos_proveedor": np.log(n.to_numpy())},
                        index=pagos.index)


def maestro_categories(maestro):
    """Indicator columns, from the categories present in CONTROL's Maestro."""
    return {col: sorted(maestro[col].unique()) for col in MAESTRO_CATS}


def indicator_columns(categories):
    return ["%s_%s" % (MAESTRO_CATS[col], v) for col, vals in categories.items()
            for v in vals]


def maestro_features(maestro, pagos, dias_factura_pago, categories):
    """Vendor attributes from Maestro joined by VENDOR_ID (NaN / 0 if absent)."""
    m = maestro.drop_duplicates("Id Proveedor").set_index("Id Proveedor")
    vendor = pagos["VENDOR_ID"]
    pago = pd.to_datetime(pagos["FECHA_D_PAGO"], format="%d/%m/%y")
    terms = m["Terminos Pago"].str.extract(r"(\d+)")[0].astype(float)
    creado = pd.to_datetime(m["Fecha Creacion Prov"], format="%d-%b-%y")
    actual = pd.to_datetime(m["Actualizacion Provedor"], format="%d-%b-%y")
    f = pd.DataFrame(index=pagos.index)
    f["desvio_terminos"] = dias_factura_pago.to_numpy() - vendor.map(terms).to_numpy()
    f["antiguedad_proveedor"] = (pago - vendor.map(creado)).dt.days.to_numpy()
    f["dias_desde_actualizacion"] = (pago - vendor.map(actual)).dt.days.to_numpy()
    for col, vals in categories.items():
        attr = vendor.map(m[col])
        for v in vals:
            f["%s_%s" % (MAESTRO_CATS[col], v)] = (attr == v).astype(float).to_numpy()
    return f


def entity_graph_features(maestro, pagos):
    """Topology of the vendor-account-UUID network, per payment.

    Nodes are vendors, bank accounts and UUIDs; edges are the vendor-account
    pairs of Maestro (dated at the vendor's creation) and the vendor-account
    and vendor-UUID pairs of each payment (dated at the payment). The same
    generic quantities are computed for every payment; none of them encodes
    a rule about what an anomaly is:

      * log_proveedores_componente: log of the number of distinct vendors in
        the connected component of the payment's vendor (final graph).
      * log_ciclos_componente: log(1 + beta_1) of that component
        (beta_1 = edges - nodes + 1, independent cycles).
      * log_persistencia_fusion / ciclos_cerrados: persistent homology of the
        graph filtered by date. Edges are added in time order with a
        union-find; when a payment's edge joins two components, the younger
        one dies (elder rule) and its H0 persistence is the days since it was
        born; when it joins a component to itself, it closes a cycle (an H1
        birth). Per payment: log(1 + largest H0 persistence it causes) and
        the number of H1 births it causes. Attaching a brand-new node (a new
        UUID) has persistence 0.
    """
    vendor_m = maestro["Id Proveedor"].to_numpy()
    acc_m = maestro["Cuenta"].to_numpy()
    t_m = pd.to_datetime(maestro["Fecha Creacion Prov"], format="%d-%b-%y")
    vendor_p = pagos["VENDOR_ID"].to_numpy()
    acc_p = pagos["BANK_ACCOUNT_NUM"].to_numpy()
    uuid_p = pagos["UUID"].to_numpy()
    t_p = pd.to_datetime(pagos["FECHA_D_PAGO"], format="%d/%m/%y")

    # (time, order, payment row or -1, (kind, key), (kind, key))
    events = [(t, 0, -1, ("v", v), ("a", a))
              for t, v, a in zip(t_m, vendor_m, acc_m)]
    for i, (t, v, a, u) in enumerate(zip(t_p, vendor_p, acc_p, uuid_p)):
        events.append((t, 1, i, ("v", v), ("a", a)))
        events.append((t, 1, i, ("v", v), ("u", u)))
    events.sort(key=lambda e: (e[0], e[1], e[2]))

    node_id, parent, birth = {}, [], []

    def node(key, t):
        if key not in node_id:
            node_id[key] = len(parent)
            parent.append(len(parent))
            birth.append(t)
        return node_id[key]

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    n = len(pagos)
    persistence = np.zeros(n)
    closed = np.zeros(n)
    seen_edges = set()
    for t, _, row, k1, k2 in events:
        if (k1, k2) in seen_edges:
            continue                      # the same relation again: no event
        seen_edges.add((k1, k2))
        r1, r2 = find(node(k1, t)), find(node(k2, t))
        if r1 == r2:
            if row >= 0:
                closed[row] += 1          # H1 birth
            continue
        old, young = (r1, r2) if birth[r1] <= birth[r2] else (r2, r1)
        if row >= 0:
            persistence[row] = max(persistence[row], (t - birth[young]).days)
        parent[young] = old               # elder rule: the younger dies

    # final components: vendors and cycles per component
    roots = np.array([find(i) for i in range(len(parent))])
    n_nodes = np.bincount(roots, minlength=len(parent))
    edge_root = np.array([roots[node_id[k1]] for k1, _ in seen_edges])
    n_edges = np.bincount(edge_root, minlength=len(parent))
    is_vendor = np.zeros(len(parent), dtype=bool)
    for (kind, _), i in node_id.items():
        is_vendor[i] = kind == "v"
    n_vendors = np.bincount(roots[is_vendor], minlength=len(parent))
    vroot = roots[[node_id[("v", v)] for v in vendor_p]]
    beta1 = n_edges[vroot] - n_nodes[vroot] + 1
    return pd.DataFrame({
        "log_proveedores_componente": np.log(n_vendors[vroot]),
        "log_ciclos_componente": np.log1p(beta1),
        "log_persistencia_fusion": np.log1p(persistence),
        "ciclos_cerrados": closed}, index=pagos.index)


def behaviour(maestro, pagos, categories):
    """All candidate columns. The model only ever takes FEATURE_SETS columns."""
    f = payment_features(maestro, pagos)
    return pd.concat([f, cadence_features(pagos),
                      maestro_features(maestro, pagos, f["dias_factura_pago"],
                                       categories),
                      entity_graph_features(maestro, pagos)], axis=1)


def fit_scaler(df, spec):
    num, _ = spec
    med = df[num].median()
    q = df[num].quantile([0.25, 0.75])
    iqr = (q.loc[0.75] - q.loc[0.25]) / 1.349
    sd = df[num].std()
    return med, iqr.where(iqr > 0, sd).where(lambda s: s > 0, 1.0)


def model_matrix(df, spec, scaler):
    """Numeric columns: robust z on CONTROL, clipped; indicators: 0/1."""
    num, ind = spec
    assert not set(num + ind) & set(RELATIONAL), "flags must not enter the model"
    med, scale = scaler
    z = ((df[num].fillna(med) - med) / scale).clip(-CLIP, CLIP)
    return np.hstack([z.to_numpy(), df[ind].fillna(0.0).to_numpy()])


# --------------------------------------------------------------------------
# Model: persistent homology
# --------------------------------------------------------------------------
def h0_groups(n, edges, threshold):
    """Components after removing MST edges longer than `threshold`."""
    keep = [(u, v) for u, v, w in edges if w <= threshold]
    if keep:
        e = np.array(keep)
        g = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n))
    else:
        g = coo_matrix((n, n))
    _, comp = connected_components(g, directed=False)
    sizes = np.bincount(comp)
    bulk = int(np.argmax(sizes))
    # relabel: 0 = bulk, then separate groups by decreasing size
    order = [bulk] + [c for c in np.argsort(-sizes, kind="stable") if c != bulk]
    remap = np.empty(len(sizes), dtype=int)
    remap[order] = np.arange(len(order))
    return remap[comp]


def rips(X):
    if not HAVE_RIPSER:
        return None
    return ripser(X, maxdim=1, n_perm=min(N_PERM, len(X)))["dgms"]


def run_model(X, threshold, dgms_ctrl):
    edges = mst_edges(X)
    out = {"score": h0_mass_scores(len(X), edges, [TAU])[TAU],
           "edges": edges,
           "groups": h0_groups(len(X), edges, threshold),
           "if_score": -IsolationForest(n_estimators=200, random_state=0)
                        .fit(X).score_samples(X),
           "dgms": rips(X)}
    if out["dgms"] is not None and dgms_ctrl is not None:
        out["wasserstein_H0"] = wasserstein(finite(out["dgms"][0]),
                                            finite(dgms_ctrl[0]))
        out["wasserstein_H1"] = wasserstein(out["dgms"][1], dgms_ctrl[1])
    return out


# --------------------------------------------------------------------------
# Evaluation: labels and flags are read only here, after the model
# --------------------------------------------------------------------------
def read_labels(run_dir, n):
    path = run_dir / "etiquetas_pagos.csv"
    if not path.exists():
        return np.zeros((n, 4), dtype=bool)
    lab = pd.read_csv(path, encoding="utf-8-sig")
    return lab[list(FACTORS)].to_numpy(dtype=bool)


def label_class(labels):
    out = np.array(["limpio"] * len(labels), dtype=object)
    k = labels.sum(axis=1)
    for j, f in enumerate(FACTORS):
        out[(k == 1) & labels[:, j]] = f
    out[k > 1] = "varias"
    return out


def describe_groups(groups, labels, flags):
    n, any_lab = len(groups), labels.any(axis=1)
    rows = []
    for g in np.unique(groups):
        m = groups == g
        k = int(any_lab[m].sum())
        row = {"grupo": int(g), "tipo": "grueso" if g == 0 else "aparte",
               "pagos": int(m.sum()), "etiquetados": k,
               "pct_etiquetados": 100 * k / m.sum(),
               "p_enriquecimiento": float(hypergeom.sf(k - 1, n, int(any_lab.sum()), int(m.sum())))}
        for j, f in enumerate(FACTORS):
            row["pct_" + f] = 100 * labels[m, j].mean()
        for col in RELATIONAL:
            row["bandera_" + col] = int((flags[col].to_numpy()[m] > 0).sum())
        rows.append(row)
    return pd.DataFrame(rows)


def evaluate(out, labels, flags, prefix):
    any_lab = labels.any(axis=1)
    clean = ~any_lab
    row = {}
    if any_lab.any():
        for name, s in (("h0", out["score"]), ("if", out["if_score"])):
            row["%s_%s_auc_ABCD" % (prefix, name)] = roc_auc_score(any_lab, s)
            for j, f in enumerate(FACTORS):
                sel = labels[:, j] | clean
                row["%s_%s_auc_%s" % (prefix, name, f)] = roc_auc_score(labels[sel, j], s[sel])
    apart = out["groups"] > 0
    row[prefix + "_grupos_aparte"] = int(out["groups"].max())
    row[prefix + "_pagos_aparte"] = int(apart.sum())
    row[prefix + "_pureza_aparte"] = float(any_lab[apart].mean()) if apart.any() else np.nan
    row[prefix + "_cobertura_aparte"] = float(apart[any_lab].mean()) if any_lab.any() else np.nan
    row[prefix + "_ari"] = adjusted_rand_score(label_class(labels), out["groups"])
    for k in ("wasserstein_H0", "wasserstein_H1"):
        if k in out:
            row["%s_%s" % (prefix, k)] = float(out[k])
    return row


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------
def plot_barcode(results, labels, path, n_bars=60):
    cls = label_class(labels)
    fig, axes = plt.subplots(1, len(results), figsize=(6 * len(results), 6))
    for ax, (fs, (out, thr)) in zip(np.atleast_1d(axes), results.items()):
        n = len(cls)
        root = np.arange(n)
        members = {i: [i] for i in range(n)}
        bars = []
        for u, v, w in out["edges"]:   # sorted: each merge is an H0 death
            ru, rv = root[u], root[v]
            if len(members[ru]) < len(members[rv]):
                ru, rv = rv, ru
            small = cls[members[rv]]
            vals, cnt = np.unique(small, return_counts=True)
            bars.append((w, vals[np.argmax(cnt)], len(small)))
            root[members[rv]] = ru
            members[ru].extend(members.pop(rv))
        bars = sorted(bars, key=lambda b: -b[0])[:n_bars]
        for i, (w, c, size) in enumerate(bars):
            ax.plot([0, w], [i, i], color=COLORS[c], lw=3, solid_capstyle="butt")
        ax.axvline(thr, color="k", ls="--", lw=1)
        ax.text(thr, -1.5, " umbral CONTROL", fontsize=8, va="bottom")
        ax.invert_yaxis()
        ax.set(title="%s: las %d barras H0 más largas" % (fs, n_bars),
               xlabel="escala de muerte (distancia)", yticks=[])
    handles = [plt.Line2D([], [], color=c, lw=3, label=k) for k, c in COLORS.items()]
    fig.legend(handles=handles, loc="lower center", ncol=6, frameon=False)
    fig.suptitle("Código de barras H0 (%s). Color = etiqueta mayoritaria del grupo absorbido,"
                 " asignada después del modelo" % EXAMPLE_RUN)
    fig.tight_layout(rect=(0, 0.05, 1, 0.95))
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_scores(results, labels, path):
    cls = label_class(labels)
    cats = ["limpio", "A", "B", "C", "D", "varias"]
    rng = np.random.default_rng(1)
    fig, axes = plt.subplots(1, len(results), figsize=(6 * len(results), 4.5))
    for ax, (fs, (out, thr)) in zip(np.atleast_1d(axes), results.items()):
        for i, c in enumerate(cats):
            y = out["score"][cls == c]
            ax.scatter(i + rng.uniform(-0.3, 0.3, len(y)), y, s=6, alpha=0.5,
                       color=COLORS[c], lw=0)
        ax.set_xticks(range(len(cats)), cats)
        ax.set(title=fs, ylabel="puntaje H0")
    fig.suptitle("Puntaje H0 por etiqueta (asignada después), %s" % EXAMPLE_RUN)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_diagrams(ctrl, run, path):
    sets = [fs for fs in ctrl if ctrl[fs] is not None]
    if not sets:
        return
    fig, axes = plt.subplots(len(sets), 2, figsize=(10, 4.5 * len(sets)), squeeze=False)
    for r, fs in enumerate(sets):
        for c, (dgms, title) in enumerate([(ctrl[fs], "CONTROL"), (run[fs], EXAMPLE_RUN)]):
            ax = axes[r, c]
            top = max(np.nanmax(finite(d)[:, 1]) if len(finite(d)) else 1
                      for d in ctrl[fs] + run[fs])
            for dim, (d, col) in enumerate(zip(dgms, ["#1f77b4", "#d62728"])):
                d = finite(d)
                ax.scatter(d[:, 0], d[:, 1], s=10, c=col, alpha=0.6, label="H%d" % dim)
            ax.plot([0, top], [0, top], "k--", lw=0.8)
            ax.set(title="%s · %s" % (fs, title), xlabel="nacimiento", ylabel="muerte")
            ax.legend(loc="lower right")
    fig.suptitle("Diagramas de persistencia (Rips, submuestra max-min de %d pagos)" % N_PERM)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_auc(metrics, path):
    runs = metrics[metrics.corrida != "CONTROL"]
    fig, axes = plt.subplots(1, len(FEATURE_SETS), figsize=(6 * len(FEATURE_SETS), 4.5),
                             sharey=True)
    for ax, fs in zip(np.atleast_1d(axes), FEATURE_SETS):
        data, pos, cols = [], [], []
        for i, f in enumerate(FACTORS):
            for j, (m, c) in enumerate((("h0", "#1f2a37"), ("if", "#e39b3a"))):
                data.append(runs["%s_%s_auc_%s" % (fs, m, f)].dropna())
                pos.append(i + (j - 0.5) * 0.35)
                cols.append(c)
        bp = ax.boxplot(data, positions=pos, widths=0.3, patch_artist=True)
        for patch, c in zip(bp["boxes"], cols):
            patch.set_facecolor(c)
            patch.set_alpha(0.6)
        ax.axhline(0.5, color="grey", ls=":")
        ax.set_xticks(range(4), list(FACTORS))
        ax.set(title="%s  (negro: H0, naranja: Isolation Forest)" % fs, ylim=(0, 1.02),
               ylabel="AUC (80 corridas)")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------
def fmt(s):
    s = s.dropna()
    return "%.3f ± %.3f" % (s.mean(), s.std()) if len(s) else "—"


def write_report(metrics, ctrl_info, agreement, groups_example, path):
    runs = metrics[metrics.corrida != "CONTROL"]
    L = ["# Homología persistente solo con comportamiento",
         "",
         "Generado por `tda_comportamiento.py` sobre las corridas de `simulate_experiment.py`"
         " (CONTROL sin anomalías + 80 corridas).",
         "",
         "El modelo solo recibe variables de comportamiento. Las banderas de cruce con el maestro"
         " y las etiquetas se leen después de calcular puntajes y grupos.",
         "",
         "- **C4:** %s" % ", ".join(FEATURE_SETS["C4"][0]),
         "- **C6:** C4 + %s" % ", ".join(CADENCE),
         "- **C6M:** C6 + atributos del proveedor en el Maestro: %s, e indicadores de %s"
         % (", ".join(MAESTRO_NUM), ", ".join(MAESTRO_CATS)),
         "- **R:** topología de la red proveedor–cuenta–UUID para cada pago: %s. Son"
         " cantidades genéricas (tamaño y ciclos de la componente, persistencia H0 y ciclos H1"
         " de la red filtrada por fecha); ninguna codifica una regla de anomalía." % ", ".join(RED),
         "- **C6M+R:** C6M + R.",
         "",
         "Ninguna variable dice que un renglón es A, B, C o D: las 4 banderas de cruce no entran"
         " al modelo. En C6M, un pago cuyo proveedor no aparece en el Maestro recibe la mediana de"
         " CONTROL en los atributos numéricos y ceros en los indicadores.",
         "",
         "Puntaje H0 con masa mínima τ = %.2f. Grupos: el árbol de expansión mínima se corta en la"
         " mayor muerte H0 de CONTROL (%s); el grupo más grande es el grueso."
         % (TAU, ", ".join("%s: %.3f" % (fs, ctrl_info[fs]["umbral"]) for fs in FEATURE_SETS)),
         "",
         "## Detección por pago (AUC contra pagos limpios, media ± de en 80 corridas)",
         "",
         "| Tipo | " + " | ".join("H0 · %s | Isolation Forest · %s" % (fs, fs)
                                  for fs in FEATURE_SETS) + " |",
         "|---|" + "---|" * (2 * len(FEATURE_SETS))]
    for f in ["ABCD"] + list(FACTORS):
        L.append("| %s | %s |" % (f, " | ".join(fmt(runs["%s_%s_auc_%s" % (fs, m, f)])
                                             for fs in FEATURE_SETS for m in ("h0", "if"))))
    L += ["",
          "## Grupos que forma H0 (sin etiquetas) y qué contienen (marcado posterior)",
          "",
          "| Medida | " + " | ".join(FEATURE_SETS) + " |",
          "|---|" + "---|" * len(FEATURE_SETS)]
    names = {"grupos_aparte": "Grupos aparte por corrida",
             "pagos_aparte": "Pagos en grupos aparte",
             "pureza_aparte": "Pureza: fracción etiquetada dentro de los grupos aparte",
             "cobertura_aparte": "Cobertura: fracción de etiquetados que cae en grupos aparte",
             "ari": "Índice de Rand ajustado (grupos vs. etiquetas)"}
    for k, label in names.items():
        L.append("| %s | %s |" % (label, " | ".join(fmt(runs["%s_%s" % (fs, k)])
                                                   for fs in FEATURE_SETS)))
    L.append("| En CONTROL: grupos aparte | %s |"
             % " | ".join(str(ctrl_info[fs]["grupos"]) for fs in FEATURE_SETS))
    if "C4_wasserstein_H0" in runs:
        L += ["",
              "## Forma de la corrida (distancia de Wasserstein a CONTROL)",
              "",
              "| Medida | " + " | ".join(FEATURE_SETS) + " |",
              "|---|" + "---|" * len(FEATURE_SETS)]
        for k in ("wasserstein_H0", "wasserstein_H1"):
            L.append("| %s | %s |" % (k, " | ".join(fmt(runs["%s_%s" % (fs, k)])
                                                   for fs in FEATURE_SETS)))
    else:
        L += ["", "ripser no está disponible: se omiten diagramas y Wasserstein."]
    L += ["",
          "## Control: banderas calculadas después vs. etiquetas",
          "",
          "Coincidencia por pago en las 80 corridas (las banderas no entran al modelo; solo"
          " describen los grupos).",
          "",
          "| Bandera | Etiqueta | Coincidencia |",
          "|---|---|---|"]
    for (col, f), v in agreement.items():
        L.append("| %s | %s | %.4f |" % (col, f, v))
    L += ["",
          "## Grupos de la corrida %s (%s), marcados después del modelo"
          % (EXAMPLE_RUN, MODEL_SET_FOR_EXAMPLE),
          "",
          md_table(groups_example.head(15)),
          ""]
    path.write_text("\n".join(L), encoding="utf-8")


def md_table(df):
    if df.empty:
        return "(sin datos)"
    cell = lambda x: ("%.3g" % x) if isinstance(x, float) else str(x)
    lines = ["| " + " | ".join(df.columns) + " |",
             "|" + "---|" * len(df.columns)]
    lines += ["| " + " | ".join(cell(x) for x in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def load_tables(run_dir):
    return read_table(run_dir / "Maestro.csv"), read_table(run_dir / "Pagos.csv")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ctrl_dir = RUNS_DIR / "CONTROL"
    ctrl_m, ctrl_p = load_tables(ctrl_dir)
    categories = maestro_categories(ctrl_m)
    for fs in ("C6M", "C6M+R"):
        FEATURE_SETS[fs] = (FEATURE_SETS[fs][0], indicator_columns(categories))
    ctrl_df = behaviour(ctrl_m, ctrl_p, categories)
    scalers = {fs: fit_scaler(ctrl_df, cols) for fs, cols in FEATURE_SETS.items()}

    # CONTROL: threshold for the groups = largest H0 death of clean data
    ctrl_info, dgms_ctrl, ctrl_out = {}, {}, {}
    for fs, cols in FEATURE_SETS.items():
        X = model_matrix(ctrl_df, cols, scalers[fs])
        edges = mst_edges(X)
        thr = max(w for _, _, w in edges)
        out = run_model(X, thr, None)
        dgms_ctrl[fs] = out["dgms"]
        ctrl_out[fs] = out
        ctrl_info[fs] = {"umbral": thr, "grupos": int(out["groups"].max())}

    rows = [{"corrida": "CONTROL",
             **{"%s_grupos_aparte" % fs: ctrl_info[fs]["grupos"] for fs in FEATURE_SETS}}]
    agree_hits = {(c, f): 0 for c, f in zip(RELATIONAL, "ABCD")}
    agree_n = 0
    example = {}
    run_dirs = sorted(p for p in RUNS_DIR.iterdir() if p.is_dir() and p.name.startswith("T"))
    for run_dir in run_dirs:
        maestro, pagos = load_tables(run_dir)
        df = behaviour(maestro, pagos, categories)
        # 1) model: behaviour only, no labels, no flags
        outs = {fs: run_model(model_matrix(df, cols, scalers[fs]),
                              ctrl_info[fs]["umbral"], dgms_ctrl[fs])
                for fs, cols in FEATURE_SETS.items()}
        # 2) evaluation: labels and flags are read only now
        labels = read_labels(run_dir, len(pagos))
        flags = df[RELATIONAL]
        row = {"corrida": run_dir.name}
        for fs, out in outs.items():
            row.update(evaluate(out, labels, flags, fs))
        rows.append(row)
        # flags (column order A, B, C, D) vs labels
        for j, (col, f) in enumerate(zip(RELATIONAL, "ABCD")):
            agree_hits[(col, f)] += int(((flags[col].to_numpy() > 0) == labels[:, j]).sum())
        agree_n += len(pagos)
        if run_dir.name == EXAMPLE_RUN:
            example = {"outs": outs, "labels": labels, "flags": flags, "pagos": pagos}
        print("%s  H0 AUC A-D %s | grupos aparte %s" % (
            run_dir.name,
            " ".join("%s %.3f" % (fs, row["%s_h0_auc_ABCD" % fs]) for fs in FEATURE_SETS),
            " ".join("%s %d" % (fs, row["%s_grupos_aparte" % fs]) for fs in FEATURE_SETS)),
            flush=True)

    metrics = pd.DataFrame(rows)
    metrics.to_csv(OUT_DIR / "metricas_por_corrida.csv", index=False)
    agreement = {k: v / agree_n for k, v in agree_hits.items()}

    groups_example = pd.DataFrame()
    if example:
        lab, fl = example["labels"], example["flags"]
        tables = []
        for fs, out in example["outs"].items():
            g = describe_groups(out["groups"], lab, fl)
            g.insert(0, "variables", fs)
            tables.append(g)
        groups_example = pd.concat(tables, ignore_index=True)
        groups_example.to_csv(OUT_DIR / ("grupos_%s.csv" % EXAMPLE_RUN), index=False)
        res = {fs: (out, ctrl_info[fs]["umbral"]) for fs, out in example["outs"].items()}
        plot_barcode(res, lab, OUT_DIR / "codigo_barras_h0.png")
        plot_scores(res, lab, OUT_DIR / "puntajes_por_etiqueta.png")
        plot_diagrams(dgms_ctrl, {fs: o["dgms"] for fs, o in example["outs"].items()},
                      OUT_DIR / "diagramas_persistencia.png")
    plot_auc(metrics, OUT_DIR / "auc_por_tipo.png")
    write_report(metrics, ctrl_info, agreement,
                 groups_example[groups_example.variables == MODEL_SET_FOR_EXAMPLE]
                 if len(groups_example) else groups_example,
                 OUT_DIR / "informe.md")
    print("Listo: %s" % OUT_DIR)


if __name__ == "__main__":
    main()
