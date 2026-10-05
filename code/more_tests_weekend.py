#!/usr/bin/env python3
"""more_tests_weekend.py -- robustness and simulated false-positive rate for the weekday-vs-weekend evening test
(modern repeals), the one new result from more_tests.py that reached conventional significance."""
from paths import RESULTS, FIGURES, INPUTS, JSON, RAW as RAW_DIR, AGG as AGG_DIR, TMP as TMP_DIR, CODE  # noqa: E402
import sys, json, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
OUT = str(RESULTS)
from ri import joint_ri
import estimator  # noqa: E402
estimator.configure(B=5000, seed=91)
ns = vars(estimator)
run, make_pools, analyze = ns["run"], ns["make_pools"], ns["analyze"]
sy = pd.read_csv(f"{OUT}/hh_state_year_panel.csv")
raw = pd.read_csv(f"{OUT}/hh_state_year_dow_hour_counts.csv")
eve = raw.hbin.isin(["16-18", "19-21"])
Wk = raw[raw.dow.between(2, 6) & eve].groupby(["st", "year"])[["ai08", "sober"]].sum()
We = raw[raw.dow.isin([1, 7]) & eve].groupby(["st", "year"])[["ai08", "sober"]].sum()
X = sy.set_index(["st", "year"])
X["we_net"] = np.log(Wk.ai08 / We.ai08) - np.log(Wk.sober / We.sober)
X = X.replace([np.inf, -np.inf], np.nan).reset_index()
ALL = sorted(sy.st.unique())
T3 = {"KS": (2013, 2012), "IL": (2016, 2015), "OK": (2019, 2018)}
MOD = dict(treat=T3, yrs=(1994, 2024), states=ALL, controls=[s for s in ALL if s not in T3],
           extra_drop=[("IN", 2024)], pool_excl=["IN"], E=(-1, 1))
out = {}
main = analyze(X, "we_net", **MOD)
out["main"] = dict(att=100 * main["summary"]["att"], p=main["summary"]["p"],
                   by_state={k: dict(att=100 * v["att"], p=v["p"]) for k, v in main["by_state"].items()})
pre = X.copy()
for k, (F, T) in T3.items():
    pre = pre[~((pre.st == k) & (pre.year >= T))]
specs = {"excl. 2020-21": (X[~X.year.isin([2020, 2021])], MOD),
         "state linear trends": (X, dict(MOD, trends=True)),
         "fatality-weighted": (X, dict(MOD, weighting="size")),
         "all post years": (X, dict(MOD, horizon=(0, 40))),
         "KS + OK only": (X, dict(MOD, treat={"KS": T3["KS"], "OK": T3["OK"]}, states=[s for s in ALL if s != "IL"])),
         "timing placebo (5 yrs early)": (pre, dict(MOD, treat={k: (F - 5, T - 5) for k, (F, T) in T3.items()}, horizon=(0, 3)))}
out["robustness"] = {}
for name, (pnl, cfg) in specs.items():
    s = analyze(pnl, "we_net", **cfg)["summary"]
    out["robustness"][name] = dict(att=100 * s["att"], ci_lo=100 * s["ci_lo"], ci_hi=100 * s["ci_hi"], p=s["p"])
print(json.dumps(out, indent=1, default=float), flush=True)
g = np.random.default_rng(92)                      # simulated false-positive rate for this outcome
pool0 = [s for s in ALL if s not in T3 and s != "IN"]
ps = []
for _ in range(200):
    fake = list(g.choice(pool0, 3, replace=False))
    treat, ctrls = dict(zip(fake, T3.values())), [s for s in pool0 if s not in fake]
    d = run(X, "we_net", treat, (1994, 2024), ctrls + fake)
    att = float(np.mean([d[(d.st == k) & d.e.between(0, 5)].gap.mean() for k in treat]))
    dist, _ = joint_ri(X, "we_net", treat, (1994, 2024), ctrls, make_pools(X, treat, ctrls, (1994, 2024)), g, B=500)
    dist = dist[~np.isnan(dist)]; n = len(dist)
    ps.append(min(1.0, 2 * min((1 + np.sum(dist >= att)) / (1 + n), (1 + np.sum(dist <= att)) / (1 + n))))
ps = np.array(ps)
out["size"] = dict(sims=200, reject_5pct=float(np.mean(ps < 0.05)), reject_1pct=float(np.mean(ps <= 0.011)),
                   share_p_at_or_below_actual=float(np.mean(ps <= out["main"]["p"])))
print(out["size"])
r = json.load(open(f"{OUT}/more_tests_results.json")); r["weekend_checks"] = out
json.dump(r, open(f"{OUT}/more_tests_results.json", "w"), indent=1, default=float)
