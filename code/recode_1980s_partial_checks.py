#!/usr/bin/env python3
"""recode_1980s_partial_checks.py -- scrutinise the one significant result from recode_1980s.py:
the nine partial restrictions (PA, CT, VA, ME, TX, WA, MI, OH, RI) and the impaired share / log odds."""
from paths import RESULTS, FIGURES, INPUTS, JSON, RAW as RAW_DIR, AGG as AGG_DIR, TMP as TMP_DIR, CODE  # noqa: E402
import sys, json, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
OUT = str(RESULTS)
import estimator  # noqa: E402
estimator.configure(B=5000, seed=131)
ns = vars(estimator)
analyze = ns["analyze"]
P = pd.read_csv(f"{OUT}/hh_state_year_panel_full.csv")
L = pd.read_csv(INPUTS / "happy_hour_law_changes_1980_1995.csv")
aer = sorted(pd.read_csv(INPUTS / "fatalities.csv").state.str.upper().unique())
CLEAN = [s for s in sorted(L[L.change_type == "none found"].state.unique()) if s in aer]
PART = {"PA": (1986, None), "CT": (1986, None), "VA": (1986, 1985), "ME": (1986, 1985), "TX": (1986, 1985),
        "WA": (1984, None), "MI": (1984, 1983), "OH": (1989, 1988), "RI": (1986, 1985)}
TRAFFIC = ("mlda", "belt_primary", "belt_secondary", "speed65", "bac08", "log_income", "unemp")
def go(treat, yrs=(1982, 1995), cov=("mlda",), y="ai_share"):
    r = analyze(P, y, treat, yrs, list(treat) + CLEAN, CLEAN, covars=cov, E=(-1, 1))
    s = r["summary"]
    return dict(att=100 * s["att"], ci_lo=100 * s["ci_lo"], ci_hi=100 * s["ci_hi"], p=s["p"]), {k: 100 * v["att"] for k, v in r["by_state"].items()}
out = {}
for y in ["ai_share", "log_odds"]:
    base, bys = go(PART, y=y)
    out[y] = {"main": base, "by_state": bys,
              "+ traffic-safety controls and unemployment (1983-95; WA, MI lack pre-years)": go({k: v for k, v in PART.items() if k not in ("WA", "MI")}, (1983, 1995), TRAFFIC, y)[0],
              "without WA and MI (1984 starts)": go({k: v for k, v in PART.items() if k not in ("WA", "MI")}, y=y)[0],
              "without OH (date conflict)": go({k: v for k, v in PART.items() if k != "OH"}, y=y)[0],
              "without RI (ambiguous)": go({k: v for k, v in PART.items() if k != "RI"}, y=y)[0],
              "only the 1985-86 adopters (PA, CT, VA, ME, TX, RI)": go({k: v for k, v in PART.items() if k in ("PA", "CT", "VA", "ME", "TX", "RI")}, y=y)[0]}
    print(y, json.dumps(out[y], indent=1, default=float), flush=True)
R = json.load(open(str(JSON / "recode_data.json"))); R["partial_checks"] = out
json.dump(R, open(str(JSON / "recode_data.json"), "w"), indent=1, default=float)
