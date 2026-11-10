"""
run_workflow.py

End-to-end workflow:

  1. simulate  simulate_topodata.py  -> simulated_data/
  2. inject    inject_anomalies.py   -> Archivos_modificados_80_corridas/Resultados_80_pruebas/
  3. analyze   tda_anomalies.py      -> resultados_tda/

Leak-free experiment (behaviour-only model, CONTROL with no anomalies):

  simulate_exp  simulate_experiment.py  -> corridas_simulador/
  analyze_beh   tda_comportamiento.py   -> resultados_comportamiento/
  analyze_ind   tda_indicadores.py      -> resultados_indicadores/
                (weighted A-D vector per vendor, on the same runs)

Usage:
  python run_workflow.py                      # the three original steps
  python run_workflow.py inject analyze       # only some steps, in order
  python run_workflow.py simulate_exp analyze_beh   # the leak-free experiment
  python run_workflow.py --verify             # regenerate the data steps in a temp
                                              # folder and compare (line endings ignored)
"""
import filecmp
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SIM_DIR = ROOT / "simulated_data"
RUNS_DIR = ROOT / "Archivos_modificados_80_corridas" / "Resultados_80_pruebas"
TDA_DIR = ROOT / "resultados_tda"
EXP_DIR = ROOT / "corridas_simulador"
BEH_DIR = ROOT / "resultados_comportamiento"
IND_DIR = ROOT / "resultados_indicadores"

STEPS = {
    "simulate": lambda: ["simulate_topodata.py", SIM_DIR],
    "inject": lambda: ["inject_anomalies.py", SIM_DIR, RUNS_DIR],
    "analyze": lambda: ["tda_anomalies.py", RUNS_DIR, TDA_DIR],
    "simulate_exp": lambda: ["simulate_experiment.py", EXP_DIR],
    "analyze_beh": lambda: ["tda_comportamiento.py", EXP_DIR, BEH_DIR],
    "analyze_ind": lambda: ["tda_indicadores.py", EXP_DIR, IND_DIR],
}
DEFAULT_STEPS = ["simulate", "inject", "analyze"]


def run(script, *args):
    cmd = [sys.executable, str(ROOT / script)] + [str(a) for a in args]
    print(">>", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def same_content(a, b):
    # line endings ignored: git with core.autocrlf checks CSVs out as CRLF
    return (a.read_bytes().replace(b"\r\n", b"\n")
            == b.read_bytes().replace(b"\r\n", b"\n"))


def differing_files(a, b):
    cmp = filecmp.dircmp(a, b)
    out = [str(Path(a) / f) for f in cmp.left_only + cmp.right_only]
    out += [str(Path(a) / f) for f in cmp.common_files
            if not same_content(Path(a) / f, Path(b) / f)]
    for sub in cmp.common_dirs:
        out += differing_files(Path(a) / sub, Path(b) / sub)
    return out


def verify():
    with tempfile.TemporaryDirectory() as tmp:
        sim, runs, exp = Path(tmp) / "sim", Path(tmp) / "runs", Path(tmp) / "exp"
        run("simulate_topodata.py", sim)
        bad = (differing_files(sim, SIM_DIR) if SIM_DIR.exists() else [str(SIM_DIR)])
        checked = ["simulated_data"]
        # the generated run folders are gitignored: compare them only if present
        if RUNS_DIR.exists():
            run("inject_anomalies.py", sim, runs)
            bad += differing_files(runs, RUNS_DIR)
            checked.append("Resultados_80_pruebas")
        if EXP_DIR.exists():
            run("simulate_experiment.py", exp)
            bad += differing_files(exp, EXP_DIR)
            checked.append("corridas_simulador")
    if bad:
        print("Differences (%d):" % len(bad))
        print("\n".join("  " + b for b in bad[:20]))
        sys.exit(1)
    print("OK: %s reproduced exactly (line endings ignored)" % ", ".join(checked))


def main(argv):
    if "--verify" in argv:
        verify()
        return
    steps = argv or DEFAULT_STEPS
    unknown = [s for s in steps if s not in STEPS]
    if unknown:
        sys.exit("unknown step(s): %s (choose from %s)" % (unknown, list(STEPS)))
    for s in steps:
        run(*STEPS[s]())


if __name__ == "__main__":
    main(sys.argv[1:])
