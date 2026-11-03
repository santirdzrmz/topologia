"""
tda_anomalies.py

Persistent-homology anomaly analysis of the factorial experiment built by
`inject_anomalies.py`.

For every run (and CONTROL) each payment becomes a point in a feature space
that mixes intra-vendor behaviour (amount, terms) with cross-table
consistency (unregistered vendor, unauthorised account, account shared by
several vendors, duplicated UUID). On that point cloud:

  * H0 (payment level): the Vietoris-Rips H0 barcode is the single-linkage
    hierarchy, i.e. the minimum spanning tree. A payment's anomaly score is
    the filtration value at which its connected component first holds at
    least `tau * n` points (the scale at which it is absorbed by the bulk).
    Unlike a 1-NN distance, this does not reward small groups of
    near-identical anomalies for keeping each other company.
  * H0/H1 (run level): Rips diagrams on a greedy max-min subsample; their
    Wasserstein distance to CONTROL measures how much the injected
    anomalies change the shape of the data.
  * Relational complex: Betti numbers of the vendor-account-UUID graph,
    whose clean topology is one tree per registered vendor.

Detection is scored against the run labels (A-D) and against the outliers
the simulator injected on its own (`simulate_topodata.outlier_rows`, "N"),
which are reported separately and never counted as false positives. Run
level responses are then explained with the factorial design (OLS with
main effects and two-way interactions).

Feature scaling is fitted once on CONTROL so all runs share one geometry.

Usage:  python tda_anomalies.py [runs_dir] [out_dir]
        defaults: Archivos_modificados_80_corridas/Resultados_80_pruebas  resultados_tda
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
import warnings
warnings.filterwarnings("ignore", category=SyntaxWarning)  # persim on py>=3.12
from persim import wasserstein
from ripser import ripser
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, roc_auc_score

RUNS_DIR = Path(sys.argv[1] if len(sys.argv) > 1
                else "Archivos_modificados_80_corridas/Resultados_80_pruebas")
OUT_DIR = Path(sys.argv[2] if len(sys.argv) > 2 else "resultados_tda")

TAU = 0.25            # minimum mass (fraction of payments) of the "bulk"
TAU_GRID = (0.01, 0.05, 0.10, 0.25, 0.50)
RELATIONAL_WEIGHT = 4.0   # distance of a broken relation, in robust sd units
CLIP = 8.0
N_PERM = 600          # subsample size for the run-level Rips diagrams
EXAMPLE_RUN = "T16_R05"
FACTORS = "ABCD"

CONTINUOUS = ["log_importe", "z_importe_proveedor", "dias_factura_pago",
              "dias_factura_vencimiento"]
RELATIONAL = ["proveedor_no_registrado", "cuenta_distinta_maestro",
              "cuenta_compartida", "uuid_repetido"]


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------
def read_table(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False,
                       encoding="utf-8-sig")


def load_run(run_dir):
    maestro = read_table(run_dir / "Maestro.csv")
    pagos = read_table(run_dir / "Pagos.csv")
    lab_path = run_dir / "etiquetas_pagos.csv"
    if lab_path.exists():
        lab = pd.read_csv(lab_path, encoding="utf-8-sig")
        labels = lab[list(FACTORS)].to_numpy(dtype=bool)
        lab_m = pd.read_csv(run_dir / "etiquetas_maestro.csv",
                            encoding="utf-8-sig", dtype={"Id Proveedor": str})
    else:
        labels = np.zeros((len(pagos), 4), dtype=bool)
        lab_m = None
    return maestro, pagos, labels, lab_m


def natural_outliers(n_pagos):
    """Rows the simulator itself made anomalous (amount x6-25)."""
    argv, sys.argv = sys.argv, sys.argv[:1]
    try:
        import simulate_topodata as sim
    finally:
        sys.argv = argv
    mask = np.zeros(n_pagos, dtype=bool)
    mask[sim.outlier_rows] = True
    return mask


# --------------------------------------------------------------------------
# Features and point cloud
# --------------------------------------------------------------------------
def payment_features(maestro, pagos):
    f = pd.DataFrame(index=pagos.index)
    amount = pagos["IMPORTE_AP"].astype(float)
    log_amt = np.log(amount)
    f["log_importe"] = log_amt

    vendor = pagos["VENDOR_ID"]
    med = log_amt.groupby(vendor).transform("median")
    mad = (log_amt - med).abs().groupby(vendor).transform("median")
    floor = np.nanmedian(mad[mad > 0])
    f["z_importe_proveedor"] = (log_amt - med) / (1.4826 * np.maximum(mad, floor))

    fecha = lambda c: pd.to_datetime(pagos[c], format="%d/%m/%y")
    pago, fac, ven = fecha("FECHA_D_PAGO"), fecha("FECHA_FACTURA"), fecha("FECHA_VENCIMIENTO")
    f["dias_factura_pago"] = (pago - fac).dt.days
    f["dias_factura_vencimiento"] = (ven - fac).dt.days

    registered = set(maestro["Id Proveedor"])
    master_acc = dict(zip(maestro["Id Proveedor"], maestro["Cuenta"]))
    known = vendor.isin(registered)
    f["proveedor_no_registrado"] = (~known).astype(float)
    f["cuenta_distinta_maestro"] = (
        known & (pagos["BANK_ACCOUNT_NUM"] != vendor.map(master_acc))).astype(float)

    # registered vendors linked to each account, through Maestro or Pagos
    links = pd.concat([
        maestro[["Id Proveedor", "Cuenta"]].set_axis(["v", "acc"], axis=1),
        pagos.loc[known, ["VENDOR_ID", "BANK_ACCOUNT_NUM"]].set_axis(["v", "acc"], axis=1),
    ]).drop_duplicates()
    n_vendors = links.groupby("acc")["v"].nunique()
    f["cuenta_compartida"] = (pagos["BANK_ACCOUNT_NUM"].map(n_vendors)
                              .fillna(1).clip(lower=1) - 1).clip(upper=1)
    f["uuid_repetido"] = (pagos.groupby("UUID")["UUID"].transform("size") > 1).astype(float)
    return f


def fit_scaler(features):
    med = features[CONTINUOUS].median()
    q = features[CONTINUOUS].quantile([0.25, 0.75])
    iqr = (q.loc[0.75] - q.loc[0.25]) / 1.349
    sd = features[CONTINUOUS].std()
    return med, iqr.where(iqr > 0, sd).where(lambda s: s > 0, 1.0)


def point_cloud(features, scaler):
    med, scale = scaler
    cont = ((features[CONTINUOUS] - med) / scale).clip(-CLIP, CLIP)
    rel = features[RELATIONAL] * RELATIONAL_WEIGHT
    return np.hstack([cont.to_numpy(), rel.to_numpy()])


# --------------------------------------------------------------------------
# Persistent homology
# --------------------------------------------------------------------------
def mst_edges(X):
    """Prim's algorithm on the Euclidean distance; returns (u, v, w) sorted.

    The MST edge lengths are exactly the finite deaths of the Rips H0
    barcode.
    """
    n = len(X)
    in_tree = np.zeros(n, dtype=bool)
    best = np.full(n, np.inf)
    parent = np.full(n, -1)
    cur = 0
    edges = []
    for _ in range(n - 1):
        in_tree[cur] = True
        d = np.sqrt(((X - X[cur]) ** 2).sum(axis=1))
        upd = ~in_tree & (d < best)
        best[upd], parent[upd] = d[upd], cur
        best[in_tree] = np.inf
        cur = int(np.argmin(best))
        edges.append((parent[cur], cur, best[cur]))
    edges.sort(key=lambda e: e[2])
    return edges


def h0_mass_scores(n, edges, taus):
    """For each tau: scale at which each point's component reaches tau*n."""
    out = {}
    for tau in taus:
        m = max(2, int(np.ceil(tau * n)))
        root = np.arange(n)
        members = {i: [i] for i in range(n)}
        score = np.zeros(n)
        # MST edges arrive sorted, so each merge is an H0 death at scale w
        for u, v, w in edges:
            ru, rv = root[u], root[v]
            if len(members[ru]) < len(members[rv]):
                ru, rv = rv, ru
            size = len(members[ru]) + len(members[rv])
            if size >= m:
                for r in (ru, rv):
                    if len(members[r]) < m:
                        score[members[r]] = w
            root[members[rv]] = ru
            members[ru].extend(members.pop(rv))
        out[tau] = score
    return out


def rips_diagrams(X):
    res = ripser(X, maxdim=1, n_perm=min(N_PERM, len(X)))
    return res["dgms"]


def finite(dgm):
    return dgm[np.isfinite(dgm[:, 1])]


def total_persistence(dgm):
    d = finite(dgm)
    return float((d[:, 1] - d[:, 0]).sum())


def relational_betti(maestro, pagos):
    """Betti numbers of the vendor-account-UUID graph (1-dim complex)."""
    nodes = {}
    def node(kind, key):
        return nodes.setdefault((kind, key), len(nodes))
    edges = set()
    for v, a in zip(maestro["Id Proveedor"], maestro["Cuenta"]):
        edges.add((node("v", v), node("a", a)))
    for v, a, u in zip(pagos["VENDOR_ID"], pagos["BANK_ACCOUNT_NUM"], pagos["UUID"]):
        edges.add((node("v", v), node("a", a)))
        edges.add((node("v", v), node("u", u)))
    e = np.array(sorted(edges))
    n = len(nodes)
    g = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n))
    b0, comp = connected_components(g, directed=False)
    registered = set(maestro["Id Proveedor"])
    vend_nodes = [i for (k, key), i in nodes.items() if k == "v" and key in registered]
    per_comp = np.bincount(comp[vend_nodes], minlength=b0)
    return {"betti0_relacional": int(b0),
            "betti1_relacional": int(len(e) - n + b0),
            "componentes_multiproveedor": int((per_comp > 1).sum())}


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------
def detection_metrics(score, labels, natural, prefix):
    any_lab = labels.any(axis=1)
    clean = ~any_lab & ~natural
    out = {}
    if any_lab.any():
        sel = any_lab | clean
        out[prefix + "auc_ABCD"] = roc_auc_score(any_lab[sel], score[sel])
        out[prefix + "ap_ABCD"] = average_precision_score(any_lab[sel], score[sel])
        k = int(any_lab.sum())
        top = np.argsort(-score, kind="stable")[:k]
        out[prefix + "precision_k"] = float(any_lab[top].mean())
        for j, f in enumerate(FACTORS):
            pos = labels[:, j]
            sel = pos | clean
            out[prefix + "auc_" + f] = roc_auc_score(pos[sel], score[sel])
    sel = natural | clean
    out[prefix + "auc_N"] = roc_auc_score(natural[sel], score[sel])
    return out


def vendor_auc_c(score, pagos, lab_m):
    if lab_m is None or not lab_m["C"].any():
        return np.nan
    vs = pd.Series(score).groupby(pagos["VENDOR_ID"].to_numpy()).max()
    s = lab_m["Id Proveedor"].map(vs).fillna(0.0)
    return roc_auc_score(lab_m["C"], s)


# --------------------------------------------------------------------------
# Factorial analysis and figures
# --------------------------------------------------------------------------
def factorial_effects(metrics, responses):
    df = metrics.dropna(subset=["tratamiento"]).copy()
    lv = {f: sorted(df[f].unique()) for f in FACTORS}
    for f in FACTORS:
        df["x" + f] = np.where(df[f] == lv[f][1], 1.0, -1.0)
    rows = []
    for y in responses:
        if df[y].std() < 1e-9:
            continue  # constant response (e.g. AUC = 1): only float noise to fit
        model = smf.ols("Q('%s') ~ (xA + xB + xC + xD) ** 2" % y, data=df).fit()
        anova = sm.stats.anova_lm(model, typ=2)
        for term in model.params.index.drop("Intercept"):
            rows.append({"respuesta": y,
                         "termino": term.replace("x", ""),
                         "efecto": 2 * model.params[term],
                         "F": anova.loc[term, "F"],
                         "p_valor": anova.loc[term, "PR(>F)"],
                         "r2_modelo": model.rsquared})
    return pd.DataFrame(rows)


def plot_diagrams(dgms_ctrl, dgms_run, run_name, path):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    for ax, dgms, title in [(axes[0], dgms_ctrl, "CONTROL"),
                            (axes[1], dgms_run, run_name)]:
        top = max(np.nanmax(finite(d)[:, 1]) if len(finite(d)) else 1
                  for d in dgms + dgms_ctrl)
        for dim, (d, c) in enumerate(zip(dgms, ["#1f77b4", "#d62728"])):
            d = finite(d)
            ax.scatter(d[:, 0], d[:, 1], s=10, c=c, alpha=0.6, label="H%d" % dim)
        ax.plot([0, top], [0, top], "k--", lw=0.8)
        ax.set(title=title, xlabel="nacimiento", ylabel="muerte",
               xlim=(-0.02 * top, top * 1.05), ylim=(-0.02 * top, top * 1.05))
        ax.legend(loc="lower right")
    fig.suptitle("Diagramas de persistencia (Rips, submuestra max-min de %d pagos)" % N_PERM)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_auc(metrics, path):
    runs = metrics.dropna(subset=["tratamiento"])
    cols = ["ph_auc_" + f for f in FACTORS] + ["ph_auc_N"]
    base = ["if_auc_" + f for f in FACTORS] + ["if_auc_N"]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    pos = np.arange(len(cols))
    ax.boxplot([runs[c] for c in cols], positions=pos - 0.18, widths=0.3,
               patch_artist=True, boxprops=dict(facecolor="#9ecae1"))
    ax.boxplot([runs[c] for c in base], positions=pos + 0.18, widths=0.3,
               patch_artist=True, boxprops=dict(facecolor="#fdd0a2"))
    ax.set_xticks(pos, ["A", "B", "C", "D", "N (simulador)"])
    ax.set_ylabel("AUC ROC (vs pagos limpios)")
    ax.set_title("Deteccion por tipo de anomalia en 80 corridas\n"
                 "azul: puntaje H0 de persistencia   naranja: Isolation Forest")
    ax.axhline(0.5, color="grey", lw=0.8, ls=":")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_main_effects(metrics, responses, path):
    runs = metrics.dropna(subset=["tratamiento"])
    fig, axes = plt.subplots(len(responses), 4, figsize=(11, 2.4 * len(responses)),
                             sharey="row", squeeze=False)
    for i, y in enumerate(responses):
        for j, f in enumerate(FACTORS):
            m = runs.groupby(f)[y].mean()
            axes[i, j].plot(m.index.astype(str), m.values, "o-")
            if i == len(responses) - 1:
                axes[i, j].set_xlabel("%s (%%)" % f)
        axes[i, 0].set_ylabel(y, fontsize=8)
    fig.suptitle("Efectos principales")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_scores(score, labels, natural, run_name, path):
    groups = {"limpio": ~labels.any(axis=1) & ~natural, "N (simulador)": natural}
    groups.update({f: labels[:, j] for j, f in enumerate(FACTORS)})
    fig, ax = plt.subplots(figsize=(9, 4))
    data = [score[g] for g in groups.values()]
    ax.boxplot(data, showfliers=False)
    for k, d in enumerate(data):
        ax.scatter(np.random.default_rng(k).normal(k + 1, 0.06, len(d)), d,
                   s=3, alpha=0.3)
    ax.set_xticks(range(1, len(groups) + 1), list(groups))
    ax.set_ylabel("puntaje H0 (escala de absorcion)")
    ax.set_title("Puntaje de anomalia por etiqueta, %s" % run_name)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def analyse_run(name, run_dir, scaler, natural, dgms_ctrl):
    maestro, pagos, labels, lab_m = load_run(run_dir)
    X = point_cloud(payment_features(maestro, pagos), scaler)
    scores = h0_mass_scores(len(X), mst_edges(X), TAU_GRID)
    score = scores[TAU]
    iforest = IsolationForest(n_estimators=200, random_state=0).fit(X)
    if_score = -iforest.score_samples(X)

    dgms = rips_diagrams(X)
    # same score on behaviour alone: what geometry sees without the joins
    X_beh = X[:, :len(CONTINUOUS)]
    beh_score = h0_mass_scores(len(X), mst_edges(X_beh), [TAU])[TAU]

    row = {"corrida": name}
    row.update(detection_metrics(score, labels, natural, "ph_"))
    row.update(detection_metrics(beh_score, labels, natural, "phc_"))
    row.update(detection_metrics(if_score, labels, natural, "if_"))
    row["ph_auc_C_proveedor"] = vendor_auc_c(score, pagos, lab_m)
    for tau, s in scores.items():
        if labels.any():
            sel = labels.any(axis=1) | (~labels.any(axis=1) & ~natural)
            row["ph_auc_ABCD_tau_%g" % tau] = roc_auc_score(
                labels.any(axis=1)[sel], s[sel])
    row["pers_total_H0"] = total_persistence(dgms[0])
    row["pers_total_H1"] = total_persistence(dgms[1])
    row["n_H1"] = int(len(finite(dgms[1])))
    if dgms_ctrl is not None:
        row["wasserstein_H0"] = wasserstein(finite(dgms[0]), finite(dgms_ctrl[0]))
        row["wasserstein_H1"] = wasserstein(dgms[1], dgms_ctrl[1])
    row.update(relational_betti(maestro, pagos))
    return row, dgms, score, labels


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    matriz = pd.read_csv(RUNS_DIR / "matriz_experimental.csv")
    ctrl_m, ctrl_p, _, _ = load_run(RUNS_DIR / "CONTROL")
    scaler = fit_scaler(payment_features(ctrl_m, ctrl_p))
    natural = natural_outliers(len(ctrl_p))

    ctrl_row, dgms_ctrl, ctrl_score, ctrl_labels = analyse_run(
        "CONTROL", RUNS_DIR / "CONTROL", scaler, natural, None)
    ctrl_row["wasserstein_H0"] = ctrl_row["wasserstein_H1"] = 0.0
    rows = [ctrl_row]

    run_dirs = sorted(p for p in RUNS_DIR.iterdir()
                      if p.is_dir() and p.name.startswith("T"))
    for run_dir in run_dirs:
        row, dgms, score, labels = analyse_run(run_dir.name, run_dir, scaler,
                                               natural, dgms_ctrl)
        t, r = run_dir.name[1:].split("_R")
        row.update(tratamiento=int(t), replica=int(r))
        rows.append(row)
        if run_dir.name == EXAMPLE_RUN:
            plot_diagrams(dgms_ctrl, dgms, EXAMPLE_RUN,
                          OUT_DIR / "diagramas_persistencia.png")
            plot_scores(score, labels, natural, EXAMPLE_RUN,
                        OUT_DIR / "puntajes_por_etiqueta.png")
            ex = pd.DataFrame(labels, columns=list(FACTORS))
            ex.insert(0, "fila_pago_original", np.arange(len(score)))
            ex["N"] = natural
            ex["puntaje_h0"] = score
            ex.to_csv(OUT_DIR / ("puntajes_%s.csv" % EXAMPLE_RUN), index=False)
        print("%-8s auc_ABCD=%.3f  W_H0=%.2f  W_H1=%.2f" % (
            run_dir.name, row["ph_auc_ABCD"], row["wasserstein_H0"],
            row["wasserstein_H1"]))

    metrics = pd.DataFrame(rows)
    metrics = metrics.merge(matriz[["tratamiento"] + list(FACTORS)],
                            on="tratamiento", how="left")
    lead = ["corrida", "tratamiento", "replica"] + list(FACTORS)
    metrics = metrics[lead + [c for c in metrics.columns if c not in lead]]
    metrics.to_csv(OUT_DIR / "metricas_por_corrida.csv", index=False)
    summarise(metrics)


def summarise(metrics):
    responses = ["ph_auc_ABCD", "ph_ap_ABCD", "ph_auc_A", "ph_auc_B",
                 "ph_auc_C", "ph_auc_D", "ph_auc_C_proveedor",
                 "ph_auc_ABCD_tau_0.01", "if_auc_ABCD", "wasserstein_H0",
                 "wasserstein_H1", "pers_total_H1", "betti0_relacional",
                 "betti1_relacional", "componentes_multiproveedor"]
    effects = factorial_effects(metrics, responses)
    effects.to_csv(OUT_DIR / "efectos_factoriales.csv", index=False)

    plot_auc(metrics, OUT_DIR / "auc_por_tipo.png")
    plot_main_effects(metrics, ["wasserstein_H0", "wasserstein_H1",
                                "betti0_relacional"],
                      OUT_DIR / "efectos_principales.png")
    write_report(metrics, effects, OUT_DIR / "informe.md")


def write_report(metrics, effects, path):
    runs = metrics.dropna(subset=["tratamiento"])
    ctrl = metrics[metrics.corrida == "CONTROL"].iloc[0]
    fmt = lambda c: "%.3f ± %.3f" % (runs[c].mean(), runs[c].std())
    lines = [
        "# Deteccion de anomalias con homologia persistente",
        "",
        "Generado por `tda_anomalies.py` sobre %d corridas (+ CONTROL)." % len(runs),
        "Puntaje: escala de absorcion H0 con masa minima tau = %g." % TAU,
        "",
        "## Deteccion por pago (AUC ROC contra pagos limpios, media ± de)",
        "",
        "| Tipo | H0, comportamiento + relaciones | H0, solo comportamiento | Isolation Forest |",
        "|---|---|---|---|",
    ]
    for f in list(FACTORS) + ["ABCD", "N"]:
        lines.append("| %s | %s | %s | %s |" % (f, fmt("ph_auc_" + f),
                                               fmt("phc_auc_" + f),
                                               fmt("if_auc_" + f)))
    lines += [
        "",
        "Precision@k (k = pagos etiquetados): %s. AP (A-D): %s." % (
            fmt("ph_precision_k"), fmt("ph_ap_ABCD")),
        "AUC de C a nivel proveedor (maximo por proveedor): %s." % fmt("ph_auc_C_proveedor"),
        "N son los pagos que el simulador ya altero (x6-25); se reportan aparte.",
        "",
        "## Sensibilidad a tau (AUC A-D)",
        "",
        "| tau | AUC |",
        "|---|---|",
    ]
    for tau in TAU_GRID:
        lines.append("| %g | %s |" % (tau, fmt("ph_auc_ABCD_tau_%g" % tau)))
    lines += [
        "",
        "## Forma de los datos",
        "",
        "| Medida | CONTROL | Corridas (media ± de) |",
        "|---|---|---|",
    ]
    for c in ["pers_total_H0", "pers_total_H1", "n_H1", "wasserstein_H0",
              "wasserstein_H1", "betti0_relacional", "betti1_relacional",
              "componentes_multiproveedor"]:
        lines.append("| %s | %.3f | %s |" % (c, ctrl[c], fmt(c)))
    sig = effects[effects.p_valor < 0.01].sort_values(["respuesta", "p_valor"])
    lines += [
        "",
        "## Efectos factoriales significativos (p < 0.01)",
        "",
        "Efecto = cambio medio al pasar del nivel bajo al alto. Las respuestas constantes",
        "(p. ej. AUC = 1 en todas las corridas) no se modelan.",
        "",
        "| Respuesta | Termino | Efecto | p |",
        "|---|---|---|---|",
    ]
    for _, e in sig.iterrows():
        lines.append("| %s | %s | %.4f | %.1e |" % (e.respuesta, e.termino,
                                                   e.efecto, e.p_valor))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
