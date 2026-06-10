---
name: pkflow
description: Run and diagnose population PK/PD (NONMEM) models from the command line with pkflow. Use when the user wants to fit a NONMEM control stream, generate goodness-of-fit (GOF) plots, a VPC, bootstrap confidence intervals, shrinkage / η-covariate diagnostics, compare candidate models, or build a model report (md/html/docx/pdf). Triggers on: NONMEM, .ctl/.mod/.mod control stream, pharmacometrics, popPK, OFV, GOF, VPC, shrinkage, bootstrap CI, model run/diagnose/compare/report, nmfe, pkflow.
---

# pkflow

`pkflow` is a composable command-line tool for pharmacometric (population PK/PD)
modeling. It wraps the **run → diagnose → compare → report** loop around a NONMEM
backend (via pharmpy). Each run is a self-contained directory
(`results.yaml` + parquet sidecars) — file-based, diffable, reproducible.

## When to use this skill

Use it whenever the task involves a NONMEM model and any of: fitting/estimation,
GOF plots, VPC, bootstrap CIs, shrinkage, η–covariate plots, model comparison,
or generating a report. If the user just wants to *read* an existing `.ctl`, that
doesn't need pkflow — but anything that runs NONMEM or post-processes its output
does.

## Prerequisites (check first)

1. **pkflow installed**: `pkflow --version`. If missing: `pip install pkflow`.
2. **NONMEM `nmfe` path configured** (needed for `run`, `vpc`, `bootstrap`):
   ```bash
   pkflow config show                 # is `nmfe` set and valid?
   pkflow config set nmfe /path/to/nmfe76
   ```
   `show`/`diagnose`/`compare`/`report` work on *saved* runs and do NOT need NONMEM.
3. **pandoc** for `report --format html|docx|pdf`; a **PDF engine**
   (weasyprint / wkhtmltopdf / a LaTeX engine) additionally for `pdf`.

## Core workflow

```bash
# 1. Fit — creates runs/<name>_<timestamp>/ and records it as the "last run"
pkflow run model.ctl

# 2. Downstream commands DEFAULT to the last successful run — omit <run_dir>:
pkflow show           # estimates, OFV, AIC/BIC, condition number
pkflow diagnose       # 4-panel GOF (DV~PRED, DV~IPRED, CWRES~PRED, CWRES~TIME)
pkflow vpc            # visual predictive check (simulates from the fit)
pkflow shrinkage      # η/ε shrinkage table + η distribution plot
pkflow etacov         # η vs covariate scatter plots
pkflow report --format pdf --gof   # one document tying it together
```

Pass an explicit `<run_dir>` to act on a specific (non-latest) run:
`pkflow show runs/model_20260101_120000/`.

## Command reference

| Command | Purpose | Needs NONMEM? |
|---|---|---|
| `pkflow run <model.ctl>` | Fit: copy → execute → collect → save | yes |
| `pkflow parse <model.ctl>` | Print parsed model summary | no |
| `pkflow show [run_dir]` | Estimates + fit stats from `results.yaml` | no |
| `pkflow collect [run_dir]` | Re-parse raw NONMEM output → `results.yaml` | no |
| `pkflow diagnose [run_dir]` | 4-panel GOF PNGs | no |
| `pkflow vpc [run_dir] --n-sim 500 --n-bins 10` | Visual predictive check | yes (simulates) |
| `pkflow shrinkage [run_dir] --threshold 0.30` | Shrinkage table + η dist | no |
| `pkflow etacov [run_dir] --cov WT --cov SEX` | η–covariate plots (auto-detects if omitted) | no |
| `pkflow compare <runA> <runB> ... --sort ofv --gof` | Rank models, ΔOFV, overlaid GOF | no |
| `pkflow bootstrap <model.ctl> --n 200 --ci 0.95` | Case-resampling bootstrap CIs | yes |
| `pkflow report [run_dir] --format md\|html\|docx\|pdf --gof` | Assemble a report | no (pandoc for non-md) |
| `pkflow config show\|get\|set\|unset\|path` | View/edit configuration | no |

Outputs land under the run dir: `diagnostics/` (GOF/VPC/shrinkage/etacov PNGs +
CSVs), `bootstrap/`, `report/`.

## Requirements for full diagnostics

GOF and VPC need the model's `$TABLE` to export the right columns. If
`pkflow diagnose` reports *"predictions empty / missing columns"*, the control
stream needs:

```
$TABLE ID TIME DV PRED IPRED CWRES MDV EVID
       NOAPPEND NOPRINT ONEHEADER FILE=sdtab1
```

For SE / RSE% / AIC / BIC / condition number, the model needs a covariance step:
`$COVARIANCE`. Suggest adding these and re-running if the user's results are
sparse.

## Handling failures

- `pkflow run` on a broken model prints the **tail of the NONMEM `.lst`** (the
  actual error: bad `$DATA` path, syntax error, boundary problem) and exits
  non-zero — read that output to diagnose; don't just re-run.
- "no previous successful run recorded" → either `run` hasn't succeeded yet, or
  you're in the wrong directory (the last-run marker lives in `<runs_dir>/.last`).
- A `status: minimization_terminated` or `boundary` in `pkflow show` means the
  fit ran but didn't converge cleanly — inspect parameters for values pinned at
  bounds.

## Python library use

Everything is importable; the statistics are pure functions of a `Results`:

```python
from pkflow import backends
from pkflow.executors import LocalExecutor
from pkflow.model import Results
from pkflow.diagnostics import save_gof, shrinkage_table
from pkflow.compare import build_table

r = Results.load("runs/model_20260101_120000")
save_gof(r, "runs/.../diagnostics")
print(shrinkage_table(r, threshold=0.3))
```

## Tips

- Commands are independent and idempotent on a saved run — re-diagnose / re-report
  without re-fitting.
- Use `pkflow compare runs/base_*/ runs/cov_*/ --sort ofv` to rank a model-building
  sequence; ΔOFV is relative to the best (lowest) run.
- VPC and bootstrap are the slow ones (they invoke NONMEM N times); GOF/shrinkage/
  report are instant (read saved files).
