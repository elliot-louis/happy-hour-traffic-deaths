#!/usr/bin/env python3
"""
fred_extension.py -- validate the FRED file and add unemployment and population to both designs.

Upload: fred_state_unemployment_population_1982_2024.csv
        state, year, unemployment_rate_pct (annual average of monthly {ST}UR), population_thousands ({ST}POP)
Validation (logged to audit_log.csv): completeness; FRED's annual-average signature; agreement with Ruhm's
  independently sourced 1982-88 unemployment and population; national totals; spot checks; smoothness.
Analyses (imputation DiD + joint randomization inference, as in analysis.py):
  unemployment as a control; per-capita outcomes (impaired / sober / all deaths per 100,000 residents);
  population-weighted pooled estimates; synthetic DiD per capita for the modern repeals.
"""
from paths import RESULTS, FIGURES, INPUTS, JSON, RAW as RAW_DIR, AGG as AGG_DIR, TMP as TMP_DIR, CODE  # noqa: E402
import sys, json, warnings
import os
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
OUT = str(RESULTS)
UP = str(INPUTS / "fred_state_unemployment_population_1982_2024.csv")
from ri import joint_ri

import estimator  # noqa: E402
estimator.configure(B=5000, seed=111)
ns = vars(estimator)
run, make_pools, analyze, pre_size = ns["run"], ns["make_pools"], ns["analyze"], ns["pre_size"]
from sdid import sdid  # noqa: E402
rng = np.random.default_rng(112)

# ====================================================================== 1. validation
F = pd.read_csv(UP)
F.columns = [c.strip().lower() for c in F.columns]
F = F.rename(columns={"state": "st", "unemployment_rate_pct": "unemp", "population_thousands": "pop"})
F["st"] = F.st.str.strip().str.upper()
checks = []


def log(check, result, status):
    checks.append(dict(area="data (FRED upload)", check=check, result=result, status=status))
    print(f"[{status}] {check} | {result}", flush=True)


ok = lambda c: "PASS" if c else "FAIL"
dups, miss = int(F.duplicated(["st", "year"]).sum()), int(F[["unemp", "pop"]].isna().sum().sum())
log("51 jurisdictions x 1982-2024, no duplicates or gaps", f"{F.st.nunique()} x {F.year.nunique()} = {len(F)} rows; {dups} duplicates; {miss} missing",
    ok(F.st.nunique() == 51 and F.year.nunique() == 43 and len(F) == 2193 and dups == 0 and miss == 0))
frac = (F.unemp * 120 - (F.unemp * 120).round()).abs()
log("unemployment values are averages of twelve one-decimal monthly rates (FRED's annual-average signature)",
    f"{100 * (frac < 0.07).mean():.1f}% of values fit (random 3-decimal numbers would fit ~12% of the time)", ok((frac < 0.07).mean() > 0.98))
aer = pd.read_csv(INPUTS / "fatalities.csv")
aer["st"] = aer.state.str.upper()
m = F.merge(aer[["st", "year", "unemp", "pop"]], on=["st", "year"], suffixes=("", "_ruhm"))
du, rp = m.unemp - m.unemp_ruhm, m["pop"] * 1000 / m.pop_ruhm
log("unemployment agrees with Ruhm's independently compiled 1982-88 panel (48 states)",
    f"correlation {np.corrcoef(m.unemp, m.unemp_ruhm)[0, 1]:.3f}; mean abs diff {du.abs().mean():.2f} pp; largest {du.abs().max():.2f} pp ({m.loc[du.abs().idxmax(), 'st']} {int(m.loc[du.abs().idxmax(), 'year'])})",
    ok(np.corrcoef(m.unemp, m.unemp_ruhm)[0, 1] > 0.95 and du.abs().mean() < 0.5))
log("population agrees with Ruhm's 1982-88 panel", f"median ratio {rp.median():.4f}; range {rp.min():.3f}-{rp.max():.3f}", ok(abs(rp.median() - 1) < 0.01 and rp.min() > 0.95 and rp.max() < 1.05))
US = F.groupby("year").apply(lambda g: pd.Series(dict(pop=g["pop"].sum() / 1000, ur=np.average(g.unemp, weights=g["pop"]))))
kp = {1982: 231.7, 1990: 249.6, 2000: 282.2, 2010: 309.3, 2020: 331.5, 2024: 340.1}
ku = {1982: 9.7, 1983: 9.6, 1990: 5.6, 2000: 4.0, 2009: 9.3, 2010: 9.6, 2019: 3.7, 2020: 8.1, 2023: 3.6, 2024: 4.0}
dpop = {y: round(100 * (US.loc[y, "pop"] / v - 1), 2) for y, v in kp.items()}
log("state populations sum to the published US totals", f"% deviation by year {dpop}", ok(max(abs(x) for x in dpop.values()) < 1))
dur = {y: round(US.loc[y, "ur"] - v, 2) for y, v in ku.items()}
log("population-weighted state unemployment tracks the published national rate", f"pp deviation by year {dur}",
    "PASS" if max(abs(x) for x in dur.values()) < 0.5 else "FLAG")
g = lambda s, y, c: float(F[(F.st == s) & (F.year == y)][c].iloc[0])
spots = [("NV 2020 unemployment >= 12 (pandemic)", g("NV", 2020, "unemp") >= 12), ("MI 2009 unemployment >= 12.5", g("MI", 2009, "unemp") >= 12.5),
         ("ND 2015 unemployment <= 3.5", g("ND", 2015, "unemp") <= 3.5), ("CA 2010 unemployment >= 11.5", g("CA", 2010, "unemp") >= 11.5),
         ("CA 2020 population 39.3-39.7M", 39300 <= g("CA", 2020, "pop") <= 39700), ("TX 2024 population 30.5-31.8M", 30500 <= g("TX", 2024, "pop") <= 31800),
         ("DC 2024 population 0.66-0.72M", 660 <= g("DC", 2024, "pop") <= 720), ("WY 2024 population 0.57-0.60M", 570 <= g("WY", 2024, "pop") <= 600)]
log("spot checks against well-known values", "; ".join(f"{k}: {'ok' if v else 'NO'}" for k, v in spots), ok(all(v for _, v in spots)))
top = F.nlargest(3, "unemp")[["st", "year", "unemp"]].values.tolist()
F = F.sort_values(["st", "year"])
F["gpop"] = F.groupby("st")["pop"].pct_change() * 100
F["dur"] = F.groupby("st").unemp.diff()
odd = F[(F.gpop < -7) | (F.gpop > 8) | (F.dur.abs() > 12)][["st", "year", "gpop", "dur"]].round(2).values.tolist()
rep = int(F.groupby("st")["pop"].apply(lambda s: (s.diff() == 0).sum()).sum())
log("no implausible jumps or repeated values", f"population growth range {F.gpop.min():.1f}% to {F.gpop.max():.1f}%; flagged {odd}; repeated population values {rep}; highest unemployment {top}",
    "PASS" if not odd and rep == 0 else "FLAG")

# ====================================================================== 2. panel
P = pd.read_csv(f"{OUT}/hh_state_year_panel_vmt.csv").merge(F[["st", "year", "unemp", "pop"]], on=["st", "year"], how="left")
P["ai_per_cap"] = np.log(P.ai08 / (P["pop"] / 100))          # per 100,000 residents
P["sober_per_cap"] = np.log(P.sober / (P["pop"] / 100))
P["fat_per_cap"] = np.log(P.fat / (P["pop"] / 100))
P["log_pop"] = np.log(P["pop"])
P = P.replace([np.inf, -np.inf], np.nan)
rate = 100 * P.fat.sum() / P["pop"].sum() * 1e-3 * 1000
dpc = (P.fat / (P["pop"] / 100))
vpc = P.vmt / (P["pop"] * 1000)
log("merged panel is complete and per-capita rates are plausible",
    f"{int(P['pop'].isna().sum())} state-years missing; deaths per 100k {dpc.min():.1f}-{dpc.max():.1f}; vehicle-miles per resident {vpc.min():,.0f}-{vpc.max():,.0f}",
    ok(P["pop"].notna().all() and dpc.between(2, 60).all() and vpc.between(3000, 30000).all()))
P.round(6).to_csv(f"{OUT}/hh_state_year_panel_full.csv", index=False)

# ====================================================================== 3. estimates
aer_st = sorted(aer.st.unique())
EXCL80 = ["NE", "NJ", "MI", "OH", "TX", "DE", "ME", "WA", "OK", "UT"]
from designs import AD_TREAT, AD_STATES as VERIFIED_STATES  # noqa: E402
AD_STATES = list(VERIFIED_STATES)
ALL = sorted(P.st.unique())
MOD_TREAT = {"KS": (2013, 2012), "IL": (2016, 2015), "OK": (2019, 2018)}
MOD = dict(treat=MOD_TREAT, yrs=(1994, 2024), states=ALL, controls=[s for s in ALL if s not in MOD_TREAT],
           extra_drop=[("IN", 2024)], pool_excl=["IN"], E=(-1, 1))
ADO = dict(treat=AD_TREAT, yrs=(1982, 1995), states=AD_STATES, controls=[s for s in AD_STATES if s not in AD_TREAT],
           covars=("mlda",), E=(-1, 1))
TRAFFIC = ("mlda", "belt_primary", "belt_secondary", "speed65", "bac08", "log_income", "rural_share")
LAB = {"ai_share": "Impaired share (pp)", "log_odds": "Log odds, impaired vs sober (x100)", "ddd_net": "Net evening test (x100)",
       "ai_per_cap": "Impaired deaths per 100k residents (log x100)", "sober_per_cap": "Sober deaths per 100k: placebo (log x100)",
       "fat_per_cap": "All deaths per 100k residents (log x100)"}
RUNS = [("modern_repeals", "+ unemployment", dict(MOD, covars=("unemp",)), ["ai_share", "log_odds", "ddd_net"]),
        ("modern_repeals", "+ unemployment, vehicle-miles, rural share", dict(MOD, covars=("unemp", "log_vmt", "rural_share")), ["ai_share", "log_odds"]),
        ("modern_repeals", "per capita", MOD, ["ai_per_cap", "sober_per_cap", "fat_per_cap"]),
        ("modern_repeals", "per capita + unemployment", dict(MOD, covars=("unemp",)), ["ai_per_cap"]),
        ("adoption_1980s", "+ unemployment", dict(ADO, covars=("mlda", "unemp")), ["ai_share", "log_odds"]),
        ("adoption_1980s", "per capita", ADO, ["ai_per_cap", "sober_per_cap", "fat_per_cap"]),
        ("adoption_1980s", "per capita + unemployment", dict(ADO, covars=("mlda", "unemp")), ["ai_per_cap"]),
        ("adoption_1980s", "1983-95, all traffic-safety controls + unemployment", dict(ADO, yrs=(1983, 1995), covars=TRAFFIC + ("unemp",)), ["ai_share", "ai_per_cap"])]
rows = []
for g_, spec, cfg, outs in RUNS:
    for y in outs:
        s = analyze(P, y, **cfg)["summary"]
        rows.append(dict(design=g_, spec=spec, outcome=y, label=LAB[y], att=100 * s["att"], ci_lo=100 * s["ci_lo"],
                         ci_hi=100 * s["ci_hi"], p=s["p"], mde80=100 * s["mde80"]))
    print("done:", g_, spec, flush=True)
for g_, cfg in [("modern_repeals", MOD), ("adoption_1980s", ADO)]:        # population-weighted pooled estimates
    for y in ["ai_share", "ai_per_cap"]:
        d = run(P, y, cfg["treat"], cfg["yrs"], cfg["states"], cfg.get("covars", ()), cfg.get("extra_drop", ()))
        popw = {k: P[(P.st == k) & P.year.between(cfg["yrs"][0], (T if T else F_) - 1)]["pop"].mean() for k, (F_, T) in cfg["treat"].items()}
        w = np.array([popw[k] for k in cfg["treat"]]) / sum(popw.values())
        att = float(np.dot(w, [d[(d.st == k) & d.e.between(0, 5)].gap.mean() for k in cfg["treat"]]))
        dist, _ = joint_ri(P, y, cfg["treat"], cfg["yrs"], cfg["controls"], make_pools(P, cfg["treat"], cfg["controls"], cfg["yrs"], exclude=cfg.get("pool_excl", ())),
                           rng, B=5000, covars=cfg.get("covars", ()), extra_drop=cfg.get("extra_drop", ()), weights=dict(zip(cfg["treat"], w)))
        dist = dist[~np.isnan(dist)]
        n = len(dist)
        q_lo, q_hi = np.quantile(dist, [0.025, 0.975])
        rows.append(dict(design=g_, spec="population-weighted", outcome=y, label=LAB[y], att=100 * att, ci_lo=100 * (att - q_hi), ci_hi=100 * (att - q_lo),
                         p=min(1.0, 2 * min((1 + np.sum(dist >= att)) / (1 + n), (1 + np.sum(dist <= att)) / (1 + n))), mde80=100 * 2.8 * dist.std()))
R = pd.DataFrame(rows)
R.round(3).to_csv(f"{OUT}/fred_results.csv", index=False)

size = P[P.year.between(1994, 2011)].groupby("st").fat.mean()
donors = [s for s in ALL if s not in MOD_TREAT and s != "IN" and size[s] >= 200]
S = []
for y in ["ai_per_cap", "sober_per_cap"]:
    taus, plac = {}, {}
    for k, (F_, T) in MOD_TREAT.items():
        w = P[P.year.between(1994, 2024)].pivot(index="year", columns="st", values=y).drop(index=[T])
        taus[k] = sdid(w, k, donors, T, F_)
        plac[k] = np.array([sdid(w, d, [x for x in donors if x != d], T, F_) for d in donors])
    est = float(np.mean(list(taus.values())))
    dist = np.array([np.mean([plac[k][rng.integers(len(donors))] for k in MOD_TREAT]) for _ in range(5000)])
    q_lo, q_hi = np.quantile(dist, [0.025, 0.975])
    S.append(dict(outcome=y, tau=100 * est, ci_lo=100 * (est - q_hi), ci_hi=100 * (est - q_lo),
                  p=min(1.0, 2 * min((1 + np.sum(dist >= est)) / 5001, (1 + np.sum(dist <= est)) / 5001)),
                  **{f"{k}": 100 * v for k, v in taus.items()}))
S = pd.DataFrame(S)
S.round(3).to_csv(f"{OUT}/fred_sdid.csv", index=False)
base = {g_: float(np.mean([P[(P.st == k) & P.year.between(((T if T else F_) - 3), (T if T else F_) - 1)].eval("ai08 / (pop / 100)").mean()
                           for k, (F_, T) in cfg["treat"].items()])) for g_, cfg in [("modern_repeals", MOD), ("adoption_1980s", ADO)]}
# Nevada and DC jump in 2000 where the population series switches to the census count: drop both as a check
nv = analyze(P, "ai_per_cap", **dict(MOD, states=[s for s in MOD["states"] if s not in ("NV", "DC")],
                                     controls=[s for s in MOD["controls"] if s not in ("NV", "DC")]))["summary"]
nvdc = dict(att=100 * nv["att"], ci_lo=100 * nv["ci_lo"], ci_hi=100 * nv["ci_hi"], p=nv["p"])
json.dump(dict(rows=json.loads(R.to_json(orient="records")), sdid=json.loads(S.to_json(orient="records")), checks=checks, base_per_100k=base,
               top_unemp=top, nvdc=nvdc), open(str(JSON / "fred_data.json"), "w"), indent=1, default=float)
lg = pd.read_csv(f"{OUT}/audit_log.csv") if os.path.exists(f"{OUT}/audit_log.csv") else pd.DataFrame(columns=["area", "check", "result", "status"])
lg = lg[lg.area != "data (FRED upload)"]
pd.concat([lg[lg.area != "data (FRED upload)"], pd.DataFrame(checks)]).to_csv(f"{OUT}/audit_log.csv", index=False)
pd.set_option("display.width", 220)
print(R[["design", "spec", "outcome", "att", "ci_lo", "ci_hi", "p"]].round(2).to_string(index=False))
print(S.round(2).to_string(index=False))
print("baseline impaired deaths per 100k:", {k: round(v, 2) for k, v in base.items()})
