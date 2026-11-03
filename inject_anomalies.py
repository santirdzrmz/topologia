"""
inject_anomalies.py

Builds the 2^4 factorial experiment stored in
`Archivos_modificados_80_corridas/Resultados_80_pruebas`: starting from the
clean simulated tables (CONTROL), each run injects four kinds of labelled
anomalies at a low or high level and writes the modified tables, row labels,
a change log and a summary.

Factors (percent of rows affected, low / high):
    A  2 / 5   payments whose VENDOR_ID is not registered in Maestro
    B  1 / 3   payments sent to a bank account not authorised for the vendor
    C  2 / 7   vendors grouped in pairs that end up sharing one bank account
               (Maestro and their payments are synchronised to the donor's)
    D  5 / 10  payments grouped in pairs that share the same UUID

16 treatments (Yates order, A varies fastest) x 5 replicates = 80 runs.
Run (t, r) uses seed SEED_BASE + 100 * (t - 1) + (r - 1) with
`numpy.random.default_rng`; with the same inputs the output matches the
original folder byte for byte. The order of random draws (C, A, B, D) is
part of that contract; do not reorder.

Usage:  python inject_anomalies.py [base_dir] [out_dir]
        defaults: simulated_data  Archivos_modificados_80_corridas/Resultados_80_pruebas
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SEED_BASE = 20261204
N_REPLICAS = 5
LEVELS = {"A": (2, 5), "B": (1, 3), "C": (2, 7), "D": (5, 10)}
ID_OFFSET = 1_000_000  # new ids / accounts = max existing value + offset + k

BASE_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else "simulated_data")
OUT_DIR = Path(sys.argv[2] if len(sys.argv) > 2
               else "Archivos_modificados_80_corridas/Resultados_80_pruebas")


def read_table(path):
    # everything as text so the tables round-trip unchanged
    return pd.read_csv(path, dtype=str, keep_default_na=False,
                       encoding="utf-8-sig")


def write_table(df, path, bom=True):
    df.to_csv(path, index=False, encoding="utf-8-sig" if bom else "utf-8",
              lineterminator="\n")


def experimental_matrix():
    rows = []
    for t in range(16):
        row = {"tratamiento": t + 1}
        for bit, f in enumerate("ABCD"):
            row[f] = LEVELS[f][(t >> bit) & 1]
        row["replicas"] = N_REPLICAS
        rows.append(row)
    return pd.DataFrame(rows, columns=["tratamiento", "A", "B", "C", "D",
                                       "replicas"])


def inject(maestro, pagos, levels, seed):
    """Apply factors C, A, B, D (in that order) to copies of the tables.

    Returns (maestro, pagos, etiquetas_maestro, etiquetas_pagos, registro,
    resumen). Log values always refer to the CONTROL tables.
    """
    rng = np.random.default_rng(seed)
    n_m, n_p = len(maestro), len(pagos)
    m, p = maestro.copy(), pagos.copy()
    lab_p = {f: np.zeros(n_p, dtype=bool) for f in "ABCD"}
    lab_m = np.zeros(n_m, dtype=bool)
    log = []

    # -- C: pairs of vendors sharing the donor's bank account ----------------
    n_c = int(round(n_m * levels["C"] / 100)) // 2 * 2
    picked = rng.choice(n_m, n_c, replace=False)
    n_c_pagos = 0
    for k in range(n_c // 2):
        donor, recv = picked[2 * k], picked[2 * k + 1]
        v_d, v_r = maestro["Id Proveedor"].iat[donor], maestro["Id Proveedor"].iat[recv]
        acc_d, acc_r = maestro["Cuenta"].iat[donor], maestro["Cuenta"].iat[recv]
        m.iat[recv, m.columns.get_loc("Cuenta")] = acc_d
        rows_r = (pagos["VENDOR_ID"] == v_r).to_numpy()
        p.loc[rows_r, "BANK_ACCOUNT_NUM"] = acc_d
        both = pagos["VENDOR_ID"].isin([v_d, v_r]).to_numpy()
        lab_p["C"] |= both
        lab_m[[donor, recv]] = True
        n_c_pagos += int(both.sum())
        log.append(["C", "pareja_proveedores", "", "%s|%s" % (v_d, v_r),
                    "%s|%s" % (acc_d, acc_r), acc_d,
                    "par_%d; maestro receptor fila %d; %d pagos sincronizados"
                    % (k + 1, recv, rows_r.sum())])

    # -- A: payments to unregistered vendor ids (outside C) ------------------
    n_a = int(round(n_p * levels["A"] / 100))
    pool = np.flatnonzero(~lab_p["C"])
    rows_a = pool[rng.choice(len(pool), n_a, replace=False)]
    new_id = maestro["Id Proveedor"].astype(int).max() + ID_OFFSET
    for k, r in enumerate(rows_a):
        old = pagos["VENDOR_ID"].iat[r]
        p.iat[r, p.columns.get_loc("VENDOR_ID")] = str(new_id + k)
        log.append(["A", "pago", r, old, old, str(new_id + k),
                    "VENDOR_ID no registrado"])
    lab_p["A"][rows_a] = True

    # -- B: payments to unauthorised accounts (outside C and A) --------------
    n_b = int(round(n_p * levels["B"] / 100))
    pool = np.flatnonzero(~lab_p["C"] & ~lab_p["A"])
    rows_b = pool[rng.choice(len(pool), n_b, replace=False)]
    # base taken after C: a receptor may have held the largest account
    new_acc = m["Cuenta"].astype(np.int64).max() + ID_OFFSET
    for k, r in enumerate(rows_b):
        p.iat[r, p.columns.get_loc("BANK_ACCOUNT_NUM")] = str(new_acc + k)
        log.append(["B", "pago", r, pagos["VENDOR_ID"].iat[r],
                    pagos["BANK_ACCOUNT_NUM"].iat[r], str(new_acc + k),
                    "cuenta no autorizada"])
    lab_p["B"][rows_b] = True

    # -- D: pairs of payments sharing a UUID (any rows) -----------------------
    n_d = int(round(int(round(n_p * levels["D"] / 100)) / 2))
    pairs = rng.choice(n_p, 2 * n_d, replace=False)
    for k in range(n_d):
        src, dst = pairs[2 * k], pairs[2 * k + 1]
        p.iat[dst, p.columns.get_loc("UUID")] = pagos["UUID"].iat[src]
        log.append(["D", "par_uuid", dst, pagos["VENDOR_ID"].iat[dst],
                    pagos["UUID"].iat[dst], pagos["UUID"].iat[src],
                    "par_%d; origen fila %d; ambas filas etiquetadas D"
                    % (k + 1, src)])
    lab_p["D"][pairs] = True

    et_m = pd.DataFrame({"fila_maestro_original": np.arange(n_m),
                         "Id Proveedor": maestro["Id Proveedor"], "C": lab_m})
    et_p = pd.DataFrame({"fila_pago_original": np.arange(n_p), **lab_p})
    registro = pd.DataFrame(log, columns=["factor", "unidad", "fila",
                                          "proveedor", "valor_antes",
                                          "valor_despues", "detalle"])
    resumen = {
        "semilla": seed,
        "niveles_porcentaje": dict(levels),
        "filas_maestro": n_m,
        "filas_pagos": n_p,
        "A_pagos": int(lab_p["A"].sum()),
        "B_pagos": int(lab_p["B"].sum()),
        "C_proveedores": int(lab_m.sum()),
        "C_pagos_proveedores_afectados": n_c_pagos,
        "C_parejas": n_c // 2,
        "D_pagos_con_uuid_duplicado": int(lab_p["D"].sum()),
        "D_parejas": n_d,
    }
    resumen["validacion"] = validate(maestro, pagos, m, p, lab_m, lab_p)
    return m, p, et_m, et_p, registro, resumen


def validate(maestro, pagos, m, p, lab_m, lab_p):
    """Check that every changed cell is explained by its factor's labels."""
    problems = []
    if not (m.columns.equals(maestro.columns) and len(m) == len(maestro)):
        problems.append("estructura Maestro")
    if not (p.columns.equals(pagos.columns) and len(p) == len(pagos)):
        problems.append("estructura Pagos")
    diff_m = (m != maestro).to_numpy()
    if set(maestro.columns[diff_m.any(axis=0)]) - {"Cuenta"}:
        problems.append("columnas inesperadas en Maestro")
    if (diff_m.any(axis=1) & ~lab_m).any():
        problems.append("cambios en Maestro sin etiqueta C")
    diff_p = p != pagos
    expected = {"VENDOR_ID": lab_p["A"],
                "BANK_ACCOUNT_NUM": lab_p["B"] | lab_p["C"],
                "UUID": lab_p["D"]}
    for col in pagos.columns:
        changed = diff_p[col].to_numpy()
        allowed = expected.get(col, np.zeros(len(p), dtype=bool))
        if (changed & ~allowed).any():
            problems.append("cambios sin etiqueta en %s" % col)
    if (p["VENDOR_ID"][lab_p["A"]].isin(maestro["Id Proveedor"])).any():
        problems.append("A con proveedor registrado")
    return "OK" if not problems else "ERROR: " + "; ".join(problems)


def main():
    maestro = read_table(BASE_DIR / "Maestro_simulado.csv")
    pagos = read_table(BASE_DIR / "Pagos_simulado.csv")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "CONTROL").mkdir(exist_ok=True)
    write_table(maestro, OUT_DIR / "CONTROL" / "Maestro.csv")
    write_table(pagos, OUT_DIR / "CONTROL" / "Pagos.csv")

    matriz = experimental_matrix()
    write_table(matriz, OUT_DIR / "matriz_experimental.csv", bom=False)

    resumenes = []
    for _, tr in matriz.iterrows():
        t = int(tr["tratamiento"])
        levels = {f: int(tr[f]) for f in "ABCD"}
        for r in range(1, int(tr["replicas"]) + 1):
            seed = SEED_BASE + 100 * (t - 1) + (r - 1)
            m, p, et_m, et_p, registro, resumen = inject(maestro, pagos,
                                                         levels, seed)
            run_dir = OUT_DIR / ("T%02d_R%02d" % (t, r))
            run_dir.mkdir(exist_ok=True)
            write_table(m, run_dir / "Maestro.csv")
            write_table(p, run_dir / "Pagos.csv")
            write_table(et_m, run_dir / "etiquetas_maestro.csv")
            write_table(et_p, run_dir / "etiquetas_pagos.csv")
            write_table(registro, run_dir / "registro_cambios.csv")
            resumen.update(tratamiento=t, replica=r)
            with open(run_dir / "resumen.json", "w", encoding="utf-8",
                      newline="\n") as f:
                json.dump(resumen, f, indent=2, ensure_ascii=False)
            resumenes.append(resumen)
            print("%s  %s" % (run_dir.name, resumen["validacion"]))

    write_table(pd.DataFrame(resumenes), OUT_DIR / "resumen_corridas.csv",
                bom=False)


if __name__ == "__main__":
    main()
