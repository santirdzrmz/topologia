"""
simulate_experiment.py

Leak-free version of the factorial experiment, generated in the style of
`simulate_topodata.py`:

  * CONTROL comes from `simulate_topodata.py --sin-atipicos`: the same 400
    vendors and ~5,390 payments, with no anomalies at all (the sporadic
    x6-25 amounts of section 4 are not applied).
  * 80 runs (2^4 treatments x 5 replicates) inject the same four anomaly
    types as `inject_anomalies.py`, with the same levels, order (C, A, B, D)
    and rules, but every draw comes from `r_rng.RRandom`, the port of R's
    generator. In R the same procedure is `set.seed(seed)` and
    `sample.int(n, size) - 1` for each draw.

Run (t, r) uses seed SEED_BASE + 100 * (t - 1) + (r - 1). The output layout
is the one `tda_anomalies.py` and `tda_comportamiento.py` read:
CONTROL/, Ttt_Rrr/{Maestro, Pagos, etiquetas_maestro, etiquetas_pagos,
registro_cambios}.csv + resumen.json, matriz_experimental.csv and
resumen_corridas.csv.

Usage:  python simulate_experiment.py [out_dir]     (default: corridas_simulador)
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from r_rng import RRandom
from inject_anomalies import (experimental_matrix, inject, read_table,
                              write_table)

SEED_BASE = 20261204
ROOT = Path(__file__).resolve().parent
OUT_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else "corridas_simulador")


class RChoice:
    """numpy-style `choice(n, size, replace=False)` backed by R's sample.int."""

    def __init__(self, seed):
        self.rng = RRandom(seed)

    def choice(self, n, size, replace=False):
        if replace:
            raise NotImplementedError("only sampling without replacement")
        idx = self.rng.sample_int(int(n), int(size)) if size else []
        return np.array([i - 1 for i in idx], dtype=np.int64)


def clean_control():
    """Maestro and Pagos from the simulator with section 4 switched off."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([sys.executable, str(ROOT / "simulate_topodata.py"),
                        tmp, "--sin-atipicos"], cwd=ROOT, check=True)
        maestro = read_table(Path(tmp) / "Maestro_simulado.csv")
        pagos = read_table(Path(tmp) / "Pagos_simulado.csv")
    return maestro, pagos


def main():
    maestro, pagos = clean_control()
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
            m, p, et_m, et_p, registro, resumen = inject(
                maestro, pagos, levels, seed, rng=RChoice(seed))
            resumen["generador"] = "r_rng.RRandom (R: set.seed + sample.int)"
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
