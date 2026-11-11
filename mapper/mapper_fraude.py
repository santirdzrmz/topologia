
import json
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import networkx as nx
import kmapper as km
from sklearn.cluster import DBSCAN
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler

FACTORES = "ABCD"
FLAGS = ["A_sin_maestro", "B_cuenta_no_autorizada", "C_cuenta_compartida", "D_uuid_repetido"]
BEH = ["log_importe", "desv_importe_prov", "dias_factura_pago"]
W_FLAG = 3.0
N_CUBES, OVERLAP = 12, 0.40
EPS, MIN_SAMPLES = 1.2, 3
SEED = 0


def leer(f):
    # dtype=str conserva ceros a la izquierda de cuentas e IDs; utf-8-sig quita el BOM
    return pd.read_csv(f, dtype=str, encoding="utf-8-sig", keep_default_na=False)


def buscar(carpeta, prefijo):
    """Maestro.csv / Pagos.csv (acepta Maestro_1.csv, etc., pero no etiquetas_maestro.csv)."""
    c = sorted(p for p in carpeta.glob(prefijo + "*.csv") if p.name.lower().startswith(prefijo.lower()))
    if not c:
        raise FileNotFoundError(f"No hay {prefijo}*.csv en {carpeta}")
    return c[0]


def features(maestro, pagos):
    ids = set(maestro["Id Proveedor"].str.strip())
    cuenta_aut = dict(zip(maestro["Id Proveedor"].str.strip(), maestro["Cuenta"].str.strip()))
    prov_por_cuenta = maestro["Cuenta"].str.strip().value_counts()

    vid = pagos["VENDOR_ID"].str.strip()
    cta = pagos["BANK_ACCOUNT_NUM"].str.strip()
    uuid = pagos["UUID"].str.strip()

    imp = pd.to_numeric(pagos["IMPORTE_AP"], errors="coerce").clip(lower=0.01).fillna(1.0)
    li = np.log10(imp)
    f = pd.DataFrame(index=pagos.index)
    f["log_importe"] = li
    f["desv_importe_prov"] = (li - li.groupby(vid).transform("median")).abs()
    fp = pd.to_datetime(pagos["FECHA_D_PAGO"], format="%d/%m/%y", errors="coerce")
    ff = pd.to_datetime(pagos["FECHA_FACTURA"], format="%d/%m/%y", errors="coerce")
    f["dias_factura_pago"] = (fp - ff).dt.days.fillna(0)

    en_maestro = vid.isin(ids)
    f["A_sin_maestro"] = (~en_maestro).astype(int)
    f["B_cuenta_no_autorizada"] = (en_maestro & (cta != vid.map(cuenta_aut))).astype(int)
    f["C_cuenta_compartida"] = (cta.map(prov_por_cuenta).fillna(1) > 1).astype(int)
    f["D_uuid_repetido"] = ((uuid != "") & (uuid.map(uuid.value_counts()) > 1)).astype(int)
    return f


def criterios(sub):
    """Criterios que comparte la mayoría de los pagos de un grupo, p. ej. 'A+D'; '' si ninguno."""
    return "+".join(c[0] for c in FLAGS if sub[c].mean() > 0.5)


# ----------------------------------------------------------------------------- Mapper
def correr_mapper(maestro, pagos):
    f = features(maestro, pagos)
    X = np.hstack([RobustScaler().fit_transform(f[BEH]), W_FLAG * f[FLAGS].values])
    score = -IsolationForest(n_estimators=300, random_state=SEED).fit(X).score_samples(X)

    mapper = km.KeplerMapper(verbose=0)
    G = mapper.map(score.reshape(-1, 1), X,
                   cover=km.Cover(n_cubes=N_CUBES, perc_overlap=OVERLAP),
                   clusterer=DBSCAN(eps=EPS, min_samples=MIN_SAMPLES))
    g = km.adapter.to_nx(G)

    f["score_iforest"] = score
    f["componente"] = -1                       # -1 = DBSCAN no lo metió en ningún nodo
    comps = sorted(nx.connected_components(g),
                   key=lambda c: len({i for n in c for i in G["nodes"][n]}), reverse=True)
    for k, comp in enumerate(comps):
        f.loc[sorted({i for n in comp for i in G["nodes"][n]}), "componente"] = k

    # criterio detectado: por componente; los aislados, pago por pago
    crit = {k: criterios(f[f["componente"] == k]) for k in f["componente"].unique() if k >= 0}
    f["criterio_mapper"] = f["componente"].map(crit).fillna("")
    aisl = f["componente"] == -1
    f.loc[aisl, "criterio_mapper"] = [criterios(f.loc[[i]]) for i in f.index[aisl]]
    f["anomalia_mapper"] = (f["criterio_mapper"] != "").astype(int)
    return f, G, mapper


# ----------------------------------------------------------------------------- evaluación
def evaluar(f, etiquetas):
    lab = pd.DataFrame({c: (etiquetas[c].astype(str).str.strip().str.lower() == "true").values
                        for c in FACTORES}, index=f.index)
    detectado = f["anomalia_mapper"].astype(bool)
    limpio = ~lab.any(axis=1)
    res = {}
    for c in FACTORES:
        pred_c = f["criterio_mapper"].str.contains(c)
        n = int(lab[c].sum())
        res[f"n_{c}"] = n
        res[f"recall_{c}"] = float((pred_c & lab[c]).sum() / n) if n else np.nan
        res[f"precision_{c}"] = float((pred_c & lab[c]).sum() / pred_c.sum()) if pred_c.any() else np.nan
    res["recall_global"] = float((detectado & ~limpio).sum() / (~limpio).sum()) if (~limpio).any() else np.nan
    res["precision_global"] = float((detectado & ~limpio).sum() / detectado.sum()) if detectado.any() else np.nan
    res["falsos_positivos"] = int((detectado & limpio).sum())
    res["tasa_falsos_positivos"] = float((detectado & limpio).sum() / limpio.sum())
    verdad = lab.apply(lambda r: "+".join(c for c in FACTORES if r[c]), axis=1)
    res["patron_exacto"] = float((f["criterio_mapper"] == verdad)[~limpio].mean()) if (~limpio).any() else np.nan
    return res


def procesar_carpeta(carpeta, salida=None, guardar_html=False):
    carpeta = Path(carpeta)
    t0 = time.time()
    maestro = leer(buscar(carpeta, "Maestro"))
    pagos = leer(buscar(carpeta, "Pagos"))
    f, G, mapper = correr_mapper(maestro, pagos)

    res = {"corrida": carpeta.name, "filas_pagos": len(pagos), "nodos": len(G["nodes"]),
           "componentes": int(f.loc[f["componente"] >= 0, "componente"].nunique()),
           "anomalias_mapper": int(f["anomalia_mapper"].sum())}
    for c in FACTORES:
        res[f"mapper_{c}"] = int(f["criterio_mapper"].str.contains(c).sum())

    rj = carpeta / "resumen.json"
    if rj.exists():
        meta = json.loads(rj.read_text(encoding="utf-8-sig"))
        for k in ("tratamiento", "replica", "semilla"):
            res[k] = meta.get(k)
        for c in FACTORES:
            res[f"nivel_{c}"] = meta.get("niveles_porcentaje", {}).get(c)

    et = carpeta / "etiquetas_pagos.csv"
    if et.exists():
        etiq = leer(et)
        if len(etiq) != len(f):
            raise ValueError(f"etiquetas_pagos tiene {len(etiq)} filas y Pagos {len(f)}")
        res.update(evaluar(f, etiq))

    if salida is not None:
        det = pagos.loc[f["anomalia_mapper"] == 1, ["VENDOR_ID", "VENDOR_NAME", "FECHA_D_PAGO",
                                                     "IMPORTE_AP", "BANK_ACCOUNT_NUM", "UUID"]].copy()
        det.insert(0, "criterio_mapper", f.loc[det.index, "criterio_mapper"])
        det.insert(0, "fila_pago_original", det.index)
        (salida / "deteccion").mkdir(parents=True, exist_ok=True)
        det.to_csv(salida / "deteccion" / f"{carpeta.name}.csv", index=False, encoding="utf-8-sig")
        if guardar_html:
            (salida / "html").mkdir(parents=True, exist_ok=True)
            tips = (f["criterio_mapper"].replace("", "sin criterio")).values
            mapper.visualize(G, path_html=str(salida / "html" / f"{carpeta.name}.html"),
                             title=f"Mapper {carpeta.name}", color_values=f["score_iforest"].values,
                             color_function_name="score Isolation Forest", custom_tooltips=tips)
    res["segundos"] = round(time.time() - t0, 1)
    return res, f


def es_corrida(p):
    return p.is_dir() and any(x.name.lower().startswith("pagos") for x in p.glob("*.csv"))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    html = "--html" in sys.argv
    ruta = Path(args[0] if args else ".")

    if es_corrida(ruta):                                   # una sola corrida
        salida = ruta.parent / "salida_mapper"
        res, f = procesar_carpeta(ruta, salida, html)
        print(json.dumps(res, indent=2, ensure_ascii=False, default=str))
        return

    carpetas = sorted(p for p in ruta.iterdir() if es_corrida(p))
    if not carpetas:
        sys.exit(f"No encontré carpetas con Pagos*.csv dentro de {ruta}")
    salida = ruta / "salida_mapper"
    salida.mkdir(exist_ok=True)
    filas, errores = [], []
    for i, c in enumerate(carpetas, 1):
        try:
            res, _ = procesar_carpeta(c, salida, html)
            filas.append(res)
            rec = " ".join(f"{k[-1]}={res[k]:.0%}" for k in ("recall_A", "recall_B", "recall_C", "recall_D")
                           if k in res and pd.notna(res[k]))
            print(f"[{i:>2}/{len(carpetas)}] {c.name:<10} anomalías={res['anomalias_mapper']:>5}  {rec}"
                  f"  FP={res.get('falsos_positivos', '-')}  ({res['segundos']}s)")
        except Exception as e:                            # una corrida mala no detiene las demás
            errores.append({"corrida": c.name, "error": repr(e)})
            print(f"[{i:>2}/{len(carpetas)}] {c.name:<10} ERROR: {e}")
            traceback.print_exc()

    df = pd.DataFrame(filas)
    df.to_csv(salida / "resultados_corridas.csv", index=False, encoding="utf-8-sig")
    if errores:
        pd.DataFrame(errores).to_csv(salida / "errores.csv", index=False, encoding="utf-8-sig")

    print(f"\nListo: {len(filas)} corridas procesadas, {len(errores)} con error.")
    print(f"Resultados en {salida / 'resultados_corridas.csv'}")
    if "tratamiento" in df and df["tratamiento"].notna().any():
        cols = [c for c in ["recall_A", "recall_B", "recall_C", "recall_D",
                            "precision_global", "falsos_positivos"] if c in df]
        print("\nPromedio por tratamiento (5 réplicas):")
        print(df.dropna(subset=["tratamiento"]).groupby("tratamiento")[cols].mean().round(3).to_string())


if __name__ == "__main__":
    main()
