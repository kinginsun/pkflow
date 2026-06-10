# Example 001 — 2-compartment IV, linear elimination

A small, self-contained PKflow example.

- `demo.csv` — 24 subjects, IV bolus, columns
  `ID TIME DV AMT CMT MDV EVID WT CRCL AGE SEX CENT`.
- `001.ctl` — ADVAN3/TRANS4 (2-comp IV) control stream; combined
  proportional + additive residual error; IIV on CL/V1/Q. Emits Xpose-style
  `sdtab1`/`patab1` tables for diagnostics.

## Run it

PKflow finds NONMEM via a `pkflow.toml` in the working directory. Point `nmfe`
at your install (the bundled value below is just an example):

```toml
# pkflow.toml
nmfe = "nmfe76"
runs_dir = "runs"
```

Then, from this directory:

```bash
pkflow run 001.ctl                 # estimate → collect → results.yaml
RUN=$(ls -d runs/001_* | tail -1)
pkflow show       $RUN
pkflow diagnose   $RUN             # GOF plots
pkflow shrinkage  $RUN             # eta/eps shrinkage
pkflow etacov     $RUN             # eta vs WT/CRCL/AGE/SEX
pkflow vpc        $RUN             # simulate + VPC
pkflow report     $RUN             # markdown report
```

A clean fit lands around OFV ≈ −1996 in a few seconds.
