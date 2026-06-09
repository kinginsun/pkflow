# Pyrana

**A composable command-line workflow tool for pharmacometric modeling.**

Pyrana turns the run → diagnose → compare → report loop of population PK/PD
modeling into a handful of scriptable commands. Fit a NONMEM model, collect its
results into a tidy, file-based format, and generate goodness-of-fit plots,
VPCs, bootstrap confidence intervals, shrinkage tables, η–covariate plots, and a
shareable report — all from the terminal or as a Python library.

It is a clean-room Python rewrite of the ideas behind the classic *Pirana*
workbench, with three deliberate design choices:

- **File-based, not a database.** Every run is a self-contained directory
  (`results.yaml` + parquet sidecars) — diffable, reproducible, and git-friendly.
- **A thin backend protocol.** Modeling-engine specifics live behind a small
  `parse / run / collect` interface. Today that backend is **NONMEM** (via
  [pharmpy](https://pharmpy.github.io/)); the diagnostics, workflows, and report
  layers are engine-agnostic.
- **Pure functions you can test.** The statistics (VPC binning, bootstrap CIs,
  shrinkage, comparison tables) are pure and unit-tested without needing NONMEM.

> **Status:** early alpha (`2.0.0a0`). The NONMEM workflow below works
> end-to-end against a real `nmfe` binary. APIs may still change.

---

## Table of contents

- [Install](#install)
- [Quickstart](#quickstart)
- [Configuration](#configuration)
- [Examples](#examples) — one per feature
  - [1. Run a model](#1-run-a-model)
  - [2. Inspect saved results](#2-inspect-saved-results)
  - [3. Compare runs](#3-compare-runs)
  - [4. Bootstrap confidence intervals](#4-bootstrap-confidence-intervals)
  - [5. Goodness-of-fit plots](#5-goodness-of-fit-plots)
  - [6. Visual Predictive Check (VPC)](#6-visual-predictive-check-vpc)
  - [7. η / ε shrinkage](#7-η--ε-shrinkage)
  - [8. η–covariate plots](#8-ηcovariate-plots)
  - [9. Reports (md / html / docx)](#9-reports-md--html--docx)
  - [10. Use it as a Python library](#10-use-it-as-a-python-library)
- [Run directory layout](#run-directory-layout)
- [Architecture](#architecture)
- [Development](#development)
- [Contributing](#contributing)
- [Roadmap](#roadmap)
- [Citation](#citation)
- [Acknowledgements](#acknowledgements)
- [Author](#author)
- [License](#license)

---

## Install

Requires **Python ≥ 3.10**.

```bash
pip install -e .
```

To actually *run* models you also need:

- A **NONMEM** installation with an `nmfe` script on `PATH` (or point at it in
  `pyrana.toml` — see [Configuration](#configuration)).
- **pandoc** (system package) — only for `report --format html|docx`. Markdown
  reports and everything else need no extra tooling.

Python dependencies (installed automatically): `pharmpy-core`, `pandas`,
`pyarrow`, `plotnine`, `scikit-misc`, `jinja2`, `pyyaml`, `typer`.

---

## Quickstart

```bash
# 1. Fit a model — creates runs/<name>_<timestamp>/
pyrana run model.ctl

# 2. Look at the estimates
pyrana show runs/model_20260609_120000/

# 3. Diagnostics: GOF + VPC + shrinkage
pyrana diagnose  runs/model_20260609_120000/
pyrana vpc       runs/model_20260609_120000/
pyrana shrinkage runs/model_20260609_120000/

# 4. One report tying it all together
pyrana report runs/model_20260609_120000/ --format docx --gof
```

Every command is independent and operates on a saved run directory, so you can
re-run, re-collect, and re-diagnose without re-fitting.

---

## Configuration

Optional `pyrana.toml` in the working directory:

```toml
backend  = "nonmem"            # only backend today
executor = "local"            # local subprocess runner
nmfe     = "/opt/nm760/run/nmfe76"   # path to your NONMEM nmfe script
runs_dir = "runs"             # where run directories are created
```

All keys are optional; defaults are shown above (`nmfe` defaults to `nmfe75` on
`PATH`). Override per-invocation with flags like `--backend` / `--runs-dir`.

---

## Examples

The examples below use a 2-compartment IV model `warfarin.ctl`. Replace it with
your own control stream — Pyrana reads `$INPUT`, `$DATA`, parameter blocks, and
result files (`.lst`, `.ext`, `.phi`) through pharmpy.

### 1. Run a model

```bash
pyrana run warfarin.ctl
```

```
→ runs/warfarin_20260609_120000
status: ok  ofv: 1234.56  (21.9s)
```

`run` creates an isolated run directory, **copies the dataset in and rewrites
`$DATA`** so models with relative data paths just work, executes NONMEM, then
collects everything into `results.yaml` + parquet sidecars (parameters,
predictions, η estimates, covariates).

### 2. Inspect saved results

```bash
pyrana show runs/warfarin_20260609_120000/
```

```
run      : warfarin_20260609_120000
backend  : nonmem
status   : ok
ofv      : 1234.56
aic/bic  : 1250.56 / 1278.10
cond #   : 18.3

parameters:
     name   type  estimate      se  rse_pct
       CL  theta     0.134  0.0042      3.1
       V1  theta     8.110  0.2100      2.6
        Q  theta     0.220  0.0180      8.2
 OMEGA_1_1  omega     0.091  0.0150     16.4
```

`show` reads only the saved files — no NONMEM needed. Use `pyrana collect
<run_dir>` to re-parse the NONMEM output of an existing run without re-fitting.

### 3. Compare runs

Rank competing models side by side. ΔOFV is relative to the best (lowest) run;
failed runs are excluded from the "best" calculation.

```bash
pyrana compare runs/base_*/ runs/covCL_*/ runs/covCL_V_*/ --sort ofv --gof
```

```
          run_id status     ofv  delta_ofv  n_params     aic     bic  condition_number
covCL_V_20260609     ok  1208.9        0.0         9  1226.9  1236.9              18.3
  covCL_20260609     ok  1210.2        1.3         7  1224.2  1234.2              18.3
   base_20260609     ok  1234.5       25.6         5  1244.5  1254.5              18.3

→ compare/comparison.csv
→ compare/compare_gof.png      # overlaid DV-vs-PRED, colored by run
```

### 4. Bootstrap confidence intervals

Nonparametric case-resampling bootstrap: subjects are resampled with replacement
(and relabeled to keep duplicates distinct), the model is refit on each
replicate, and percentile CIs are reported. Non-converged replicates are
excluded and counted.

```bash
pyrana bootstrap warfarin.ctl --n 200 --ci 0.95
```

```
→ runs/warfarin_20260609_121500  (200 replicates)
converged: 196/200

     name  original_est  boot_median   boot_se   ci_lo   ci_hi  n_success
       CL         0.134        0.135    0.0051   0.125   0.145        196
       V1         8.110        8.090    0.2400   7.640   8.580        196
 OMEGA_1_1         0.091        0.087    0.0190   0.052   0.128        196

→ runs/.../bootstrap/bootstrap_summary.csv
```

Per-replicate run directories are cleaned up automatically; the summary and the
raw per-replicate estimates (`replicate_params.parquet`) are kept.

### 5. Goodness-of-fit plots

The standard 4-panel GOF (DV-vs-PRED, DV-vs-IPRED, CWRES-vs-PRED, CWRES-vs-TIME),
rendered with [plotnine](https://plotnine.org/):

```bash
pyrana diagnose runs/warfarin_20260609_120000/
```

```
  runs/.../diagnostics/dv_vs_pred.png
  runs/.../diagnostics/dv_vs_ipred.png
  runs/.../diagnostics/cwres_vs_pred.png
  runs/.../diagnostics/cwres_vs_time.png
→ 4 plot(s) in runs/.../diagnostics
```

> GOF needs a `$TABLE` with `DV PRED IPRED CWRES TIME` written to an
> `sdtab`-style file so Pyrana can find it.

### 6. Visual Predictive Check (VPC)

Pyrana converts the fitted model to a simulation (`$SIMULATION` with N
subproblems), runs it, bins observations by time, and overlays the observed
5/50/95 percentiles on the simulated prediction intervals.

```bash
pyrana vpc runs/warfarin_20260609_120000/ --n-sim 500 --n-bins 10
```

```
→ runs/.../diagnostics/vpc.png    (+ vpc.csv with the binned percentiles)
```

### 7. η / ε shrinkage

A shrinkage table (flagging values above a threshold, default 30%) plus a
faceted histogram of the individual η estimates.

```bash
pyrana shrinkage runs/warfarin_20260609_120000/ --threshold 0.30
```

```
parameter kind  shrinkage  shrinkage_pct   high
    ETA_1  eta     0.0868          8.68   False
    ETA_2  eta     0.4171         41.71    True
    ETA_3  eta     0.6388         63.88    True

→ runs/.../diagnostics/shrinkage_table.csv
→ runs/.../diagnostics/eta_distributions.png
```

### 8. η–covariate plots

Scatter of each η against each subject-level covariate, with a linear trend.
Covariates are **auto-detected** (constant-within-subject, varying across
subjects); override with `--cov`.

```bash
# auto-detect covariates
pyrana etacov runs/warfarin_20260609_120000/

# or name them explicitly
pyrana etacov runs/warfarin_20260609_120000/ --cov WT --cov SEX --cov AGE
```

```
→ runs/.../diagnostics/eta_covariates.png   (facet grid: η rows × covariate cols)
→ runs/.../diagnostics/eta_covariates.csv
```

### 9. Reports (md / html / docx)

Assemble fit summary, parameter table, shrinkage, any bootstrap result, and the
diagnostic plots into one document. Markdown is the canonical render; HTML and
Word are produced via `pandoc`.

```bash
# Markdown (no extra dependencies)
pyrana report runs/warfarin_20260609_120000/ --format md

# Word document, generating GOF plots first and embedding them
pyrana report runs/warfarin_20260609_120000/ --format docx --gof
```

```
→ runs/.../report/report.docx
```

### 10. Use it as a Python library

Everything the CLI does is available as importable functions. The statistics are
pure — feed them a `Results` object (from a saved run or constructed in memory):

```python
from pathlib import Path
from pyrana import backends
from pyrana.executors import LocalExecutor
from pyrana.model import Results
from pyrana.compare import build_table
from pyrana.diagnostics import save_gof, shrinkage_table
from pyrana.workflows import bootstrap

be = backends.get("nonmem")
ex = LocalExecutor({"nmfe": "/opt/nm760/run/nmfe76"})

# parse → run → collect
model  = be.parse(Path("warfarin.ctl"))
handle = be.run(model, Path("runs/wf"), ex)
res    = be.collect(model, Path("runs/wf"), handle)
res.save(Path("runs/wf"))

# load a saved run later
res = Results.load(Path("runs/wf"))

# pure analytics
table = build_table([Results.load(p) for p in Path("runs").glob("*/")])
shr   = shrinkage_table(res, threshold=0.3)
save_gof(res, Path("runs/wf/diagnostics"))

# a full bootstrap workflow
boot = bootstrap(model, res, be, ex, Path("runs/wf"), n=200, seed=1234)
print(boot.summary)
```

---

## Run directory layout

A run directory is the unit of reproducibility:

```
runs/warfarin_20260609_120000/
├── results.yaml            # fit metadata: status, ofv, aic/bic, cond#, shrinkage
├── parameters.parquet      # estimates + SE + RSE%
├── predictions.parquet     # $TABLE output (DV/PRED/IPRED/CWRES/...)
├── etas.parquet            # individual η estimates
├── covariates.parquet      # per-subject covariates
├── warfarin.ctl            # the control stream that was run
├── diagnostics/            # GOF, VPC, shrinkage, η-covariate PNGs + CSVs
├── bootstrap/              # bootstrap_summary.csv + replicate_params.parquet
└── report/                 # report.md / .html / .docx
```

---

## Architecture

```
pyrana/
├── cli.py              # typer entrypoint — every command is a thin wrapper
├── config.py           # pyrana.toml loader
├── compare.py          # cross-run table + overlaid GOF (pure functions)
├── model/
│   ├── base.py         # backend-agnostic Model
│   └── results.py      # unified Results + save/load (yaml + parquet)
├── backends/
│   ├── base.py         # Backend protocol: parse / run / collect / simulate
│   └── nonmem.py       # pharmpy-backed NONMEM implementation
├── executors/
│   └── local.py        # local subprocess runner
├── diagnostics/
│   ├── gof.py          # 4-panel goodness-of-fit
│   ├── vpc.py          # backend-agnostic VPC (compute + plot)
│   └── shrinkage.py    # shrinkage table, η distributions, η-covariate plots
├── workflows/
│   └── bootstrap.py    # case-resampling bootstrap (pure stats + orchestrator)
└── report/
    ├── render.py       # context builder + Jinja2 markdown + pandoc convert
    └── templates/      # run_report.md.j2
```

**Extending it** is meant to be small:

- A new **backend** (e.g. another estimation engine) = one file implementing
  `parse / run / collect`.
- A new **executor** (e.g. Slurm/SGE) = one file implementing `submit / wait`.

The diagnostics, comparison, bootstrap, and report layers consume the unified
`Results` object and don't care which engine produced it.

---

## Development

```bash
pip install -e ".[dev]"
python -m pytest          # full suite
```

The test suite covers every module. Pure-function tests (config, results,
compare, bootstrap, VPC math, shrinkage, report rendering) run **without
NONMEM** using in-memory `Results`; NONMEM-dependent paths are exercised with a
real `.mod` template and stubbed/faked boundaries. Pandoc-dependent report tests
skip automatically when pandoc is absent.

---

## Contributing

Contributions are welcome! Please see [`CONTRIBUTING.md`](CONTRIBUTING.md) for
details. In short:

1. Open an issue to discuss bugs or feature ideas before large changes.
2. Follow test-driven development — **add a failing test first**, then the
   implementation. Keep statistics as pure functions where possible.
3. Run `python -m pytest` and make sure the suite is green before opening a PR.

---

## Roadmap

- Categorical-covariate boxplots in η–covariate plots
- Cluster executors (`slurm`, `sge`)
- Additional report sections and templating hooks

The backend protocol is intentionally general, but the project is **focused on
NONMEM** for now.

---

## Citation

If you use Pyrana in your research, please cite it:

```bibtex
@software{zhang_pyrana,
  author  = {Zhang, Yufeng},
  title   = {Pyrana: A composable command-line workflow tool for pharmacometric modeling},
  year    = {2026},
  url      = {https://github.com/kinginsun/pyrana}
}
```

## Acknowledgements

Pyrana stands on the shoulders of excellent open-source work:

- **[pharmpy](https://pharmpy.github.io/)** — NONMEM control-stream parsing and
  result handling.
- **[plotnine](https://plotnine.org/)** — grammar-of-graphics plotting for all
  diagnostics.
- **[pandas](https://pandas.pydata.org/)**, **[Typer](https://typer.tiangolo.com/)**,
  **[Jinja2](https://jinja.palletsprojects.com/)**, and **[pandoc](https://pandoc.org/)**.
- The original **Pirana** workbench, whose workflow inspired this rewrite.

## Author

**Yufeng Zhang**
School of Pharmacy, The Chinese University of Hong Kong (CUHK)
Contact: [zhangyf@cuhk.edu.hk](mailto:zhangyf@cuhk.edu.hk)

## License

Released under the **MIT License** — see [`LICENSE`](LICENSE).

```
MIT License

Copyright (c) 2026 Yufeng Zhang
```

Pyrana is an independent Python project and is not affiliated with the original
Pirana software.
