# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository. The README (in Spanish)
is the user-facing documentation; this file is the working context.

## Handoff

Written 2026-11-05 when the project moved to another computer. The chat history did not
move, so everything needed to continue is here.

### What the project does

Topological data analysis (TDA) of synthetic accounts-payable data:

1. `simulate_topodata.py` is a Python port of an R simulator (`simulate_topodata.R`,
   not in this repo). It generates a vendor master table (Maestro, 400 vendors) and
   payments (Pagos, ~5,390 rows), with clusters, periodic cycles, outliers and
   structured missing values. With seed 8347 the output matches the R script byte
   for byte, thanks to `r_rng.py` (a port of R's RNG).
2. `inject_anomalies.py` builds a 2^4 factorial experiment: 16 treatments × 5
   replicates = 80 runs. Each run starts from the clean data (CONTROL) and injects four
   labelled anomaly types at a low or high level:
   - A: unregistered `VENDOR_ID` (2/5 % of payments)
   - B: unauthorised bank account (1/3 % of payments)
   - C: vendor pairs sharing the donor's account (2/7 % of vendors)
   - D: payment pairs sharing a UUID (5/10 % of payments)
3. `tda_anomalies.py` detects the anomalies with persistent homology:
   - a per-payment H0 "mass" score;
   - run-level Rips diagrams compared to CONTROL with the Wasserstein distance;
   - Betti numbers of the vendor–account–UUID graph;
   - a factorial OLS model explaining the run-level responses.

### Structure

| Path | Role |
|---|---|
| `run_workflow.py` | Orchestrator: `simulate` → `inject` → `analyze`, plus `--verify` |
| `simulate_topodata.py`, `r_rng.py` | Step 1, the simulator (pre-existing; do not reorder random calls) |
| `inject_anomalies.py` | Step 2: writes `Archivos_modificados_80_corridas/Resultados_80_pruebas/` |
| `tda_anomalies.py` | Step 3: writes `resultados_tda/` |
| `simulated_data/` | Committed output of step 1 (CONTROL data) |
| `resultados_tda/` | Committed output of step 3: `informe.md` (summary), metric CSVs, figures |
| `presentacion/` | Source of the results slide deck (see "Most recent work") |
| `topologia.Rproj` | Leftover RStudio project file; there is no R code here |

Each run folder `Txx_Ryy/` contains:
- `Maestro.csv` and `Pagos.csv`: the modified tables;
- `etiquetas_maestro.csv` and `etiquetas_pagos.csv`: row labels;
- `registro_cambios.csv`: the change log;
- `resumen.json`: the run summary, including its validation result.

The run folder's root also holds `matriz_experimental.csv` and `resumen_corridas.csv`.

### Install, run, test

Requires Python ≥ 3.9. It was developed with Python 3.14.8 in a uv-managed venv, because
the old machine had no system Python.

```bash
uv venv .venv && uv pip install -r requirements.txt   # or: python -m venv .venv && pip install -r requirements.txt
.venv/Scripts/python run_workflow.py            # all three steps (Windows path; use .venv/bin/python elsewhere)
.venv/Scripts/python run_workflow.py inject     # only regenerate the 80 runs (~15 s)
.venv/Scripts/python run_workflow.py analyze    # only the TDA analysis (~10 min)
.venv/Scripts/python run_workflow.py --verify   # rebuild steps 1-2 in a temp dir and compare with disk
```

Versions the results were produced with:
- numpy 2.5.4
- pandas 3.1.0
- scipy 1.18.1
- scikit-learn 1.9.1
- statsmodels 0.15.0
- patsy 1.0.3
- matplotlib 3.11.2
- ripser 0.6.15
- persim 0.4.1

There is no unit-test suite. The checks are:
- `--verify`, which proves byte-for-byte reproducibility of steps 1–2, ignoring line endings;
- `inject_anomalies.py` itself, which prints `OK` for every run after `validate()` checks that every changed cell is explained by its label;
- `tda_anomalies.py`, which should reproduce `resultados_tda/metricas_por_corrida.csv` exactly.

### Current status

- All three steps work end to end.
- The original 80-run folder (484 files) is reproduced byte for byte, every run validates `OK`, and `--verify` passes.
- The work is on branch `anomalias-homologia-persistente`, pushed to `origin`. It is **not merged into `main`** and no pull request has been opened yet.

Results, from `resultados_tda/informe.md`:
- **Payment-level H0 score:** AUC 1.000 on A–D in all 80 runs. Isolation Forest on the same features gets 0.977, and the same score on behaviour features alone gets 0.502 (chance).
- **Simulator outliers (N):** 0.998.
- **Vendor-level C detection:** 0.886 ± 0.122.
- **τ sensitivity:** AUC is 0.930 at τ = 0.01 and 1.000 from τ = 0.10 up. At τ = 0.01 the A factor costs 0.079, because similar anomalies mask each other.
- **Wasserstein distance to CONTROL:** grows with C (the largest effect, +28.6 for H0), then D and B.
- **Relational graph:** β0 drops by 112 when D is high.

### Most recent work

1. Committed and pushed the workflow (commit `e16a14e`).
2. Built a 10-slide results presentation as a claude.ai Slides artifact:
   https://claude.ai/artifact/WrjKy5cTjaVVZ3eYsbntPf
   - It is private to the user's claude.ai account and opens from any machine logged into that account.
   - It was then translated to Spanish; that is the current version.
   - It exports to .pptx or PDF from Share › Export.
   - `presentacion/` holds a copy of its source files (`project/deck.json` and one HTML file per slide). The two images there point to `/_blob/...` assets that only resolve inside the artifact; the originals are `resultados_tda/puntajes_por_etiqueta.png` and `resultados_tda/diagramas_persistencia.png`.

### Key decisions and why

- **Random draw order C → A → B → D**
  - **What:** each run uses seed `20261204 + 100·(t−1) + (r−1)` with `numpy.random.default_rng`.
  - **Why:** this reproduces the original folder exactly.
  - **Pools:** A draws only from payments outside C, and B from payments outside C and A.
  - **Rule:** do not reorder.
- **B's new account base is taken from Maestro after C is applied.** A C receptor can hold the largest account (it happened in T01_R05, T05_R05 and T08_R03), and using the pre-C Maestro broke reproduction.
- **CSV format**
  - **Reading:** everything is read as text (`dtype=str`, `keep_default_na=False`, `utf-8-sig`) so the tables round-trip unchanged.
  - **Writing:** files are written with LF line endings.
  - **BOM:** per-run CSVs have a BOM; the two root CSVs do not.
  - **`resumen.json`:** indent 2, no trailing newline.
- **`--verify` ignores line endings**, because git here has `core.autocrlf=true` and checks the CSVs out as CRLF.
- **Mass-based H0 score (τ = 0.25), not nearest-neighbour distance.** Groups of similar anomalies would otherwise mask each other.
- **Feature space**
  - **Behaviour:** 4 features (log amount, within-vendor z, days to pay, days to due date), robust-scaled on CONTROL and clipped at ±8, so all runs share one geometry.
  - **Relational:** 4 binary flags weighted 4.0.
- **H0 barcode via a numpy Prim minimum spanning tree.** For run-level diagrams, ripser runs on a 600-point greedy max-min subsample (`n_perm=600`) to keep runtime reasonable.
- **Factorial model:** main effects plus two-way interactions.
  - Responses that are constant across runs (for example AUC = 1.0) are skipped, because they produced spurious "significant" effects from float noise.
  - Column names are quoted with `Q('...')` in formulas, because names like `ph_auc_ABCD_tau_0.01` break patsy.
- **The 194 MB run folder is gitignored, not committed.** `run_workflow.py inject` rebuilds it exactly in about 15 seconds.
- **Commits and PRs carry no "Co-Authored-By: Claude" or "Generated with Claude Code" lines.** The user's explicit preference.

### Known bugs and open issues

- **AUC 1.000 is partly by construction.** Each injected type sets a binary relational flag, so a hand-written rule would also catch it. The behaviour-only N outliers are the more meaningful test.
- **Simulator quirk:** `IMPORTE_AP` of outlier rows keeps the unrounded multiplied value. It is kept on purpose for parity with R.
- **`persim` warnings:** it emits SyntaxWarnings on Python 3.14; `tda_anomalies.py` suppresses them.
- **Spanish labels:** the figures in `resultados_tda/` have Spanish axis labels.
- **No automated tests.**
- **R source not in the repo:** the README refers to `simulate_topodata.R` in a `Reto` folder that is not part of this repo.

### Next steps

1. Open a PR from `anomalias-homologia-persistente` into `main`, or merge it. Remember: no Claude attribution lines.
2. Test anomalies that do not break a join, such as unusual amounts or timing within a valid vendor, where topology has to earn its result.
3. Improve vendor-level detection of C (AUC 0.886).
4. Run the pipeline on real payment data.
5. Optionally add a small pytest suite: `validate()` on one run, `--verify`, and the MST/H0 score on a toy cloud.

### What lives outside the repo

There are **no environment variables, API keys, credentials or databases**. Nothing reads
`os.environ` or any `.env` file. The things not in git are:

| Item | Where it comes from |
|---|---|
| `Archivos_modificados_80_corridas/Resultados_80_pruebas/` (194 MB, gitignored) | Regenerate with `run_workflow.py inject`; it is byte-identical to the original folder (verified) |
| `.venv/` (gitignored) | Recreate with the install command above |
| Python ≥ 3.9 and optionally `uv` | python.org / astral.sh; on the old machine uv was at `~/.local/bin/uv` |
| `simulate_topodata.R` (folder `Reto`) | The original R simulator, kept outside this repo; only needed to re-check R parity |
| GitHub access to `origin` (`https://github.com/santirdzrmz/topologia.git`) | The user's own GitHub login on the new machine |
| Results deck (claude.ai artifact, link above) | The user's claude.ai account; source copy in `presentacion/` |
