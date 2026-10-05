#!/usr/bin/env python3
"""recode_1980s_followup.py -- use the follow-up research memo (Sept 24, 2026) to stress-test the partial-restriction
result: Maine's 1984 immediate-suspension law and August 1988 BAC changes (.08; .05 for convicted offenders), Ohio's
disputed start date (April 1988 official; a 9/20/84 filing unverified) and its September 1993 license-suspension law."""
from paths import RESULTS, FIGURES, INPUTS, JSON, RAW as RAW_DIR, AGG as AGG_DIR, TMP as TMP_DIR, CODE  # noqa: E402
import sys, json, warnings
import os
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
OUT = str(RESULTS)
import estimator  # noqa: E402
estimator.configure(B=5000, seed=141)
ns = vars(estimator)
analyze = ns["analyze"]
P = pd.read_csv(f"{OUT}/hh_state_year_panel_full.csv")
L = pd.read_csv(INPUTS / "happy_hour_law_changes_1980_1995.csv")
aer = sorted(pd.read_csv(INPUTS / "fatalities.csv").state.str.upper().unique())
CLEAN = [s for s in sorted(L[L.change_type == "none found"].state.unique()) if s in aer]
PART = {"PA": (1986, None), "CT": (1986, None), "VA": (1986, 1985), "ME": (1986, 1985), "TX": (1986, 1985),
        "WA": (1984, None), "MI": (1984, 1983), "OH": (1989, 1988), "RI": (1986, 1985)}
def go(treat, panel=P, y="ai_share"):
    s = analyze(panel, y, treat, (1982, 1995), list(treat) + CLEAN, CLEAN, covars=("mlda",), E=(-1, 1))["summary"]
    return dict(att=100 * s["att"], ci_lo=100 * s["ci_lo"], ci_hi=100 * s["ci_hi"], p=s["p"])
trunc = P.copy()                        # end Maine's post-period before Aug 1988 and Ohio's before Sept 1993
trunc.loc[((trunc.st == "ME") & (trunc.year >= 1988)) | ((trunc.st == "OH") & (trunc.year >= 1993)), ["ai_share", "log_odds"]] = np.nan
res = {}
for y in ["ai_share", "log_odds"]:
    res[y] = {"main": go(PART, y=y),
              "without Maine and Ohio": go({k: v for k, v in PART.items() if k not in ("ME", "OH")}, y=y),
              "Maine and Ohio post-periods cut before their confounding laws": go(PART, trunc, y),
              "Ohio dated 1984 (unverified 9/20/84 filing)": go(dict(PART, OH=(1985, 1984)), y=y)}
u = pd.read_csv(INPUTS / "usseatbelts.csv")
me08 = int(u[(u.state == "ME") & (u.alcohol == "yes")].year.min())
res["maine_08_first_year_cohen_einav"] = me08
print(json.dumps(res, indent=1, default=float))
R = json.load(open(str(JSON / "recode_data.json"))); R["followup"] = res
json.dump(R, open(str(JSON / "recode_data.json"), "w"), indent=1, default=float)
checks = [dict(area="data (1980s law file)", check="follow-up memo: Rhode Island description matches the 1985 court opinion",
               result="S & S Liquor Mart v. Pastore (Aug 26, 1985) quotes P.L. 1985 ch. 345: no multi-drink price inducements; no advertising of happy hours, open bars, two-for-one nights or free-drink specials. Partial restriction confirmed",
               status="PASS"),
          dict(area="data (1980s law file)", check="follow-up memo: Maine's .08 BAC date agrees with Cohen-Einav's independent panel",
               result=f"memo: effective Aug 4, 1988; Cohen-Einav codes Maine .08 from {me08}", status="PASS" if me08 in (1988, 1989) else "FLAG"),
          dict(area="data (1980s law file)", check="follow-up memo: still unresolved",
               result="Vermont Regulation 49 adoption date; Rhode Island original chapter text; whether Ohio's 9/20/84 filing was substantive; Maine's 1984 suspension-law day",
               status="FLAG")]
lg = pd.read_csv(f"{OUT}/audit_log.csv") if os.path.exists(f"{OUT}/audit_log.csv") else pd.DataFrame(columns=["area", "check", "result", "status"])
lg = lg[~lg.check.str.startswith("follow-up memo")]
pd.concat([lg, pd.DataFrame(checks)]).to_csv(f"{OUT}/audit_log.csv", index=False)
