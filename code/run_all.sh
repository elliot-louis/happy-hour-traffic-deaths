#!/usr/bin/env bash
# Reproduce every result, figure and the audit log from data/fars_agg and data/inputs.
# To rebuild data/fars_agg from raw FARS files first, run: python code/build_fars.py  (see README).
set -euo pipefail
cd "$(dirname "$0")"
python analysis.py            # main estimates, synthetic control, Figures 1-4
python followup.py            # Illinois stress tests, synthetic DiD, 1980s traffic-safety controls (Figures 5-6)
python vmt_extension.py       # deaths per vehicle-mile (Figure 7)
python fred_extension.py      # unemployment and population
python tests_now.py power_modern power_1980s dates monthly   # simulations, date sensitivity, Indiana (Figure 8)
python recode_1980s.py        # alternative 1980s codings
python recode_1980s_followup.py
python recode_1980s_partial_checks.py
python more_tests.py          # mechanism checks, pooled estimate, specification curve (Figure 9)
python more_tests_weekend.py
python final_specs.py         # poster figures
python make_report_data.py
python audit.py data estimators size repro report
(cd report && npm install --silent && node build_report.js)   # paper/happy_hour_report.docx
