#!/usr/bin/env python3
"""make_report_data.py -- collect the main result tables into results/json/report_data.json for the report builder."""
import json
import pandas as pd
from paths import RESULTS, JSON

rec = lambda f: json.loads(pd.read_csv(RESULTS / f).to_json(orient="records"))
tw = pd.read_csv(RESULTS / "replication_twfe.csv").iloc[0]
out = dict(main=rec("results_main.csv"), rob=rec("results_robustness.csv"), bystate=rec("results_by_state.csv"),
           sc=rec("synthetic_control.csv"), nat=rec("national_totals_check.csv"),
           twfe=dict(coef=round(float(tw.coef), 4), se=round(float(tw.se), 4)))
json.dump(out, open(JSON / "report_data.json", "w"), indent=1)
print("wrote", JSON / "report_data.json")
