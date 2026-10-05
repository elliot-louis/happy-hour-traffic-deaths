#!/usr/bin/env python3
"""
recode_1980s.py -- check the verified 1980-1995 law file (the law-by-law check) and re-run the 1980s design.

Law file: happy_hour_law_changes_1980_1995.csv (one row per statewide change, with citations and sources).
Coding used here
  Ban on time-limited price cuts (the defining happy-hour practice), applied to all on-premise licensees
  then licensed: MA 12/1984, KS 1985, IN 1985, NC 8/1985, VT ~1985/86 (date unverified), IL 1989; AK 1986.
  The law file labels KS and IN "partial"; by the standard the file applies to NC (time-limited cuts banned, full-day
  specials allowed) Indiana qualifies, and Kansas's 1985 law covered every on-premise licensee then existing.
  RI 1985 is ambiguous (original text unavailable), so it is analysed with the partial restrictions.
  Clean comparison group: states where the law file shows no statewide change 1980-1995 (adds DE and UT; drops PA,
  CT, VA, which restricted in 1985-86, and GA, with local bans).
Designs (1982-1995, drinking-age covariate): six bans; Four strict bans; the original seven with the
  clean comparison group; six bans with Vermont moved to 1986; six bans plus Alaska (1983-1995, binary
  drinking-age covariate from Cohen-Einav); nine partial restrictions. Plus a pooled estimate over all
  strict-ban law changes (three repeals sign-flipped).
"""
from paths import RESULTS, FIGURES, INPUTS, JSON, RAW as RAW_DIR, AGG as AGG_DIR, TMP as TMP_DIR, CODE  # noqa: E402
import sys, json, warnings
import os
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
OUT = str(RESULTS)
LAW = INPUTS / "happy_hour_law_changes_1980_1995.csv"
from ri import joint_ri

import estimator  # noqa: E402
estimator.configure(B=5000, seed=121)
ns = vars(estimator)
run, make_pools, analyze = ns["run"], ns["make_pools"], ns["analyze"]
rng = np.random.default_rng(122)

L = pd.read_csv(LAW)
P = pd.read_csv(f"{OUT}/hh_state_year_panel_full.csv")
u = pd.read_csv(INPUTS / "usseatbelts.csv").rename(columns={"state": "st"})
u["mlda21"] = (u.drinkage == "yes").astype(float)
P = P.merge(u[["st", "year", "mlda21"]], on=["st", "year"], how="left")
aer = sorted(pd.read_csv(INPUTS / "fatalities.csv").state.str.upper().unique())

# ---------------------------------------------------------------- checks on the law file
checks = []
def log(check, result, status):
    checks.append(dict(area="data (1980s law file)", check=check, result=result, status=status))
    print(f"[{status}] {check} | {result}", flush=True)
need = ["state", "change_type", "provisions", "date_enacted", "date_effective", "citation", "source", "source_type", "notes"]
log("requested columns present; every jurisdiction covered; every row marked primary or secondary",
    f"{len(L)} rows; {L.state.nunique()} jurisdictions; missing columns {[c for c in need if c not in L.columns] or 'none'}; source_type {L.source_type.value_counts().to_dict()}",
    "PASS" if L.state.nunique() == 51 and all(c in L.columns for c in need) and L.source_type.isin(["primary", "secondary"]).all() else "FAIL")
indep = {"MA": "Dec 1984 (Patch: Dec 10, 1984)", "KS": "1985 (Kansas liquor-law timeline)", "IN": "1985 (NWI Times)", "NC": "1985",
         "RI": "1985 (Rhode Island Monthly)", "IL": "1989 (26-year ban ended 2015)", "AK": "1986 (Money: on the books since 1986)", "UT": "2011 (Money)"}
got = {s: str(L[L.state == s].date_effective.dropna().astype(str).min()) for s in indep}
agree = all(got[s].startswith(indep[s][:4]) or (s == "MA" and got[s].startswith("1984")) for s in ["MA", "KS", "IN", "NC", "RI", "IL", "AK"])
log("adoption years agree with the independent sources found earlier", "; ".join(f"{s}: file {got[s]} vs {indep[s]}" for s in indep if s != "UT") +
    "; UT: file 'none found' before 1996, consistent with a 2011 ban", "PASS" if agree else "FLAG")
log("strict/partial labels applied consistently",
    "Indiana (time-of-day price cuts banned, all-day specials allowed) is labelled partial while North Carolina, under the same standard, is labelled strict; "
    "Kansas's 1985 law covered every on-premise licensee then existing (clubs and 3.2% beer bars). Recoded here: KS and IN as bans; RI ambiguous", "FLAG")
gaps = L[(L.date_effective.isna() & L.change_type.isin(["strict ban", "partial restriction"]))].state.tolist()
sec = L[(L.source_type == "secondary") & (L.change_type != "none found")].state.tolist()
log("remaining gaps", f"no effective date: {gaps}; year-only dates: {L[L.date_effective.astype(str).str.len() == 4].state.tolist()}; secondary-only restriction rows: {sec}", "FLAG")

# ---------------------------------------------------------------- designs
CLEAN = sorted(L[L.change_type == "none found"].state.unique())
CLEAN_AER = [s for s in CLEAN if s in aer]
BANS6 = {"MA": (1985, None), "KS": (1986, 1985), "IN": (1986, 1985), "NC": (1986, 1985), "VT": (1986, 1985), "IL": (1990, 1989)}
BANS4 = {k: BANS6[k] for k in ["MA", "NC", "VT", "IL"]}
ORIG7 = dict(BANS6, RI=(1986, 1985))
VT86 = dict(BANS6, VT=(1987, 1986))
PARTIAL = {"PA": (1986, None), "CT": (1986, None), "VA": (1986, 1985), "ME": (1986, 1985), "TX": (1986, 1985),
           "WA": (1984, None), "MI": (1984, 1983), "OH": (1989, 1988), "RI": (1986, 1985)}
DESIGNS = [("Six bans (MA, KS, IN, NC, VT, IL)", BANS6, (1982, 1995), ("mlda",), CLEAN_AER),
           ("Four strict bans (MA, NC, VT, IL)", BANS4, (1982, 1995), ("mlda",), CLEAN_AER),
           ("Original seven, clean comparison group", ORIG7, (1982, 1995), ("mlda",), CLEAN_AER),
           ("Six bans, Vermont dated 1986", VT86, (1982, 1995), ("mlda",), CLEAN_AER),
           ("Six bans plus Alaska (1983-95)", dict(BANS6, AK=(1987, 1986)), (1983, 1995), ("mlda21",), [s for s in CLEAN if s != "DC"]),
           ("Nine partial restrictions", PARTIAL, (1982, 1995), ("mlda",), CLEAN_AER)]
OUTS = ["ai_share", "log_odds", "ai_per_cap", "svn_share", "ddd_net"]
LAB = {"ai_share": "Impaired share (pp)", "log_odds": "Log odds, impaired vs sober (x100)", "ai_per_cap": "Impaired deaths per 100k (log x100)",
       "svn_share": "Single-vehicle-night share (pp)", "ddd_net": "Net evening test (x100)"}
rows = []
for name, treat, yrs, cov, ctrls in DESIGNS:
    for y in OUTS:
        s = analyze(P, y, treat, yrs, list(treat) + ctrls, ctrls, covars=cov, E=(-1, 1))["summary"]
        rows.append(dict(design=name, treated=", ".join(treat), n_treated=len(treat), n_controls=len(ctrls), outcome=y, label=LAB[y],
                         att=100 * s["att"], ci_lo=100 * s["ci_lo"], ci_hi=100 * s["ci_hi"], p=s["p"]))
    print("done:", name, flush=True)
R = pd.DataFrame(rows)
R.round(3).to_csv(f"{OUT}/recode_1980s_results.csv", index=False)

# ---------------------------------------------------------------- pooled over strict-ban law changes
ALL = sorted(P.st.unique())
MOD_TREAT = {"KS": (2013, 2012), "IL": (2016, 2015), "OK": (2019, 2018)}
MODc = dict(treat=MOD_TREAT, yrs=(1994, 2024), states=ALL, controls=[s for s in ALL if s not in MOD_TREAT], extra_drop=[("IN", 2024)], pool_excl=["IN"])
def att_dist(y, treat, yrs, states, ctrls, cov=(), extra=(), excl=()):
    d = run(P, y, treat, yrs, states, cov, extra)
    a = float(np.mean([d[(d.st == k) & d.e.between(0, 5)].gap.mean() for k in treat]))
    dd, _ = joint_ri(P, y, treat, yrs, ctrls, make_pools(P, treat, ctrls, yrs, exclude=excl), rng, B=5000, covars=cov, extra_drop=extra)
    return a, dd[~np.isnan(dd)]
pooled = []
for y in ["log_odds", "ai_share"]:
    am, dm = att_dist(y, MOD_TREAT, (1994, 2024), ALL, MODc["controls"], extra=[("IN", 2024)], excl=["IN"])
    for lab, bans in [("3 repeals + 6 bans", BANS6), ("3 repeals + 4 strict bans", BANS4)]:
        ab, db = att_dist(y, bans, (1982, 1995), list(bans) + CLEAN_AER, CLEAN_AER, cov=("mlda",))
        wm = 3 / (3 + len(bans))
        n = min(len(dm), len(db))
        e, null = wm * (-am) + (1 - wm) * ab, wm * (-dm[:n]) + (1 - wm) * db[:n]
        q_lo, q_hi = np.quantile(null, [0.025, 0.975])
        pooled.append(dict(outcome=y, changes=lab, att=100 * e, ci_lo=100 * (e - q_hi), ci_hi=100 * (e - q_lo),
                           p=min(1.0, 2 * min((1 + np.sum(null >= e)) / (1 + n), (1 + np.sum(null <= e)) / (1 + n)))))
Pq = pd.DataFrame(pooled)
Pq.round(3).to_csv(f"{OUT}/recode_1980s_pooled.csv", index=False)
coding = [dict(state=s, used_as="ban", first_full_year=F, transition_year=T) for s, (F, T) in BANS6.items()] + \
         [dict(state="AK", used_as="ban (1983-95 variant)", first_full_year=1987, transition_year=1986)] + \
         [dict(state=s, used_as="partial restriction", first_full_year=F, transition_year=T) for s, (F, T) in PARTIAL.items()] + \
         [dict(state=s, used_as="comparison", first_full_year=None, transition_year=None) for s in CLEAN]
pd.DataFrame(coding).to_csv(f"{OUT}/coding_1980s_verified.csv", index=False)
json.dump(dict(rows=json.loads(R.to_json(orient="records")), pooled=json.loads(Pq.to_json(orient="records")), checks=checks,
               clean=CLEAN, n_clean_aer=len(CLEAN_AER)), open(str(JSON / "recode_data.json"), "w"), indent=1, default=float)
lg = pd.read_csv(f"{OUT}/audit_log.csv") if os.path.exists(f"{OUT}/audit_log.csv") else pd.DataFrame(columns=["area", "check", "result", "status"])
pd.concat([lg[lg.area != "data (1980s law file)"], pd.DataFrame(checks)]).to_csv(f"{OUT}/audit_log.csv", index=False)
pd.set_option("display.width", 220)
print(R.pivot_table(index="design", columns="outcome", values="att", sort=False).round(2).to_string())
print(R.pivot_table(index="design", columns="outcome", values="p", sort=False).round(2).to_string())
print(Pq.round(3).to_string(index=False))
print("clean comparison states:", CLEAN)
