#!/usr/bin/env python3
"""
followup.py -- follow-up checks for the happy hour project

A. 1980s adoption wave with traffic-safety controls from the Cohen & Einav (2003) state panel
   (AER::USSeatBelts, 1983-1997): seat-belt laws (primary / secondary), 65-mph limits, .08 BAC laws,
   per-capita income, and vehicle-miles for per-mile death rates. A further spec drops Georgia,
   where metro-Atlanta counties and cities banned happy hours locally in 1985.
B. Illinois synthetic-control stress tests: leave-one-out, alternative donor pools, in-time placebo.
C. Synthetic difference-in-differences (Arkhangelsky, Athey, Hirshberg, Imbens & Wager 2021) for
   Kansas, Illinois and Oklahoma, with in-space placebo inference and a pooled average.

Inputs: hh_state_year_panel.csv (analysis.py), Fatalities.csv and USSeatBelts.csv (Rdatasets, AER).
"""
from paths import RESULTS, FIGURES, INPUTS, JSON, RAW as RAW_DIR, AGG as AGG_DIR, TMP as TMP_DIR, CODE  # noqa: E402
import json, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.optimize import nnls

warnings.filterwarnings("ignore")
OUT = str(RESULTS)
FIG = str(FIGURES)
AER, SEAT = str(INPUTS / "fatalities.csv"), str(INPUTS / "usseatbelts.csv")
rng = np.random.default_rng(20260925)
B, H = 5000, (0, 5)
sy = pd.read_csv(f"{OUT}/hh_state_year_panel.csv")


# ---------------------------------------------------------------- estimator (as in analysis.py)
def fe_predict(d, y, covars=()):
    fit = d[d.untreated & d[y].notna()]
    for c in covars:
        fit = fit[fit[c].notna()]
    states, years = sorted(d.st.unique()), sorted(d.year.unique())
    si, ti = {s: i for i, s in enumerate(states)}, {t: i for i, t in enumerate(years)}
    ns, nt, nc = len(states), len(years), len(covars)

    def X(df):
        M = np.zeros((len(df), ns + nt - 1 + nc))
        r, s, t = np.arange(len(df)), df.st.map(si).to_numpy(), df.year.map(ti).to_numpy()
        M[r, s] = 1.0
        M[r[t > 0], ns + t[t > 0] - 1] = 1.0
        for k, c in enumerate(covars):
            M[:, ns + nt - 1 + k] = df[c].to_numpy()
        return M

    beta = np.linalg.lstsq(X(fit), fit[y].to_numpy(), rcond=None)[0]
    return X(d) @ beta


def run(panel, y, treat, yrs, states, covars=()):
    d = panel[panel.st.isin(states) & panel.year.between(*yrs)].copy()
    for s, (F, T) in treat.items():
        if T is not None:
            d = d[~((d.st == s) & (d.year == T))]
    d["e"] = d.year - d.st.map({s: F for s, (F, T) in treat.items()})
    d["untreated"] = ~(d.st.isin(list(treat)) & (d.e >= 0))
    d["gap"] = d[y] - fe_predict(d, y, covars)
    return d


def pre_size(panel, entry, y0):
    F, T = entry
    return panel[panel.year.between(y0, (T if T is not None else F) - 1)].groupby("st").fat.mean()


def make_pools(panel, treat, controls, yrs, lo=0.5, hi=2.0, min_n=8):
    pools = {}
    for k, entry in treat.items():
        sz = pre_size(panel, entry, yrs[0])
        r = sz[[c for c in controls if c in sz.index]] / sz[k]
        P = list(r[(r >= lo) & (r <= hi)].index)
        pools[k] = P if len(P) >= min_n else list(np.log(r).abs().sort_values().index[:min_n])
    return pools


def draw_sets(pools, keys):
    """Independent draws for each treated slot, with replacement across slots, for the synthetic-DiD placebos,
    which fit each slot separately. With separate fits, drawing without replacement shrinks the placebo variance
    when slots share a small pool. The main inference (ri.py) differs: it assigns distinct placebo states and
    re-fits the model jointly, which keeps the shared year-effect error inside the null."""
    return [[pools[k][rng.integers(len(pools[k]))] for k in keys] for _ in range(B)]


def ri_summary(att, dist):
    dist = dist[~np.isnan(dist)]
    n = len(dist)
    q_lo, q_hi = np.quantile(dist, [0.025, 0.975])
    p = min(1.0, 2 * min((1 + np.sum(dist >= att)) / (1 + n), (1 + np.sum(dist <= att)) / (1 + n)))
    return dict(att=att, ci_lo=att - q_hi, ci_hi=att - q_lo, p=p, mde80=2.8 * dist.std())


from ri import joint_ri


def analyze(panel, y, treat, yrs, states, controls, covars=()):
    d = run(panel, y, treat, yrs, states, covars)
    keys = list(treat)
    att = float(np.mean([d[(d.st == k) & d.e.between(*H)].gap.mean() for k in keys]))
    pools = make_pools(panel, treat, controls, yrs)
    dist, _ = joint_ri(panel, y, treat, yrs, controls, pools, rng, B=B, covars=covars, horizon=H)
    return ri_summary(att, dist)


# ---------------------------------------------------------------- A. 1980s wave + traffic-safety controls
u = pd.read_csv(SEAT).rename(columns={"state": "st"})
u["belt_primary"] = (u.enforce == "primary").astype(float)
u["belt_secondary"] = (u.enforce == "secondary").astype(float)
u["speed65"] = (u.speed65 == "yes").astype(float)
u["bac08"] = (u.alcohol == "yes").astype(float)
u["log_income"] = np.log(u.income)
u["vmt"] = u.miles.astype(float)                        # millions of vehicle-miles
p80 = sy.merge(u[["st", "year", "belt_primary", "belt_secondary", "speed65", "bac08", "log_income", "vmt"]],
               on=["st", "year"], how="left")
p80["ai_per_vmt"] = np.log(p80.ai08 / p80.vmt)
p80["sober_per_vmt"] = np.log(p80.sober / p80.vmt)

aer = pd.read_csv(AER)
AER_ST = sorted(aer.state.str.upper().unique())
EXCL = ["NE", "NJ", "MI", "OH", "TX", "DE", "ME", "WA", "OK", "UT"]
from designs import AD_TREAT, AD_STATES as VERIFIED_STATES  # noqa: E402
AD_STATES = list(VERIFIED_STATES)
AD_CONTROLS = [s for s in AD_STATES if s not in AD_TREAT]
COV = ("mlda", "belt_primary", "belt_secondary", "speed65", "bac08", "log_income")
SPECS_A = [("1983-95, drinking age only", AD_STATES, ("mlda",)),
           ("+ seat belt, 65 mph, .08 BAC, income", AD_STATES, COV),
           ("+ same controls, drop Georgia", [s for s in AD_STATES if s != "GA"], COV)]
OUTS_A = [("ai_share", "Impaired share (pp)"),
          ("log_odds", "Log odds, impaired vs. sober (x100)"),
          ("ai_per_vmt", "Log impaired deaths per mile (x100)"),
          ("sober_per_vmt", "Log sober deaths per mile: placebo (x100)"),
          ("svn_share", "Single-vehicle-night share (pp)"),
          ("ddd_sober", "Evening-vs-night, sober deaths: placebo (x100)"),
          ("ddd_net", "Net evening test (x100)")]
rowsA = []
for spec, states, cov in SPECS_A:
    ctrls = [s for s in states if s not in AD_TREAT]
    for y, lab in OUTS_A:
        r = analyze(p80, y, AD_TREAT, (1983, 1995), states, ctrls, cov)
        rowsA.append(dict(spec=spec, outcome=y, label=lab, **{k: 100 * v if k != "p" else v for k, v in r.items()}))
A = pd.DataFrame(rowsA)
A.round(3).to_csv(f"{OUT}/followup_1980s_controls.csv", index=False)
belt_first = {s: int(u[(u.st == s) & (u.enforce != "no")].year.min()) for s in AD_TREAT}


# ---------------------------------------------------------------- B. Illinois synthetic-control stress tests
def synth_weights(y1, Y0, M=1000.0):
    w, _ = nnls(np.vstack([Y0, M * np.ones((1, Y0.shape[1]))]), np.concatenate([y1, [M]]))
    return w


def wide(y, yrs, drop):
    w = sy[sy.year.between(*yrs)].pivot(index="year", columns="st", values=y)
    return w.drop(index=[drop]) if drop in w.index else w


def sc(w, unit, pool, T, F):
    yr = w.index.to_numpy()
    pre, post = yr < T, yr >= F
    Y0, y1 = w[pool].to_numpy(), w[unit].to_numpy()
    ok = pre & ~np.isnan(Y0).any(axis=1) & ~np.isnan(y1)
    wt = synth_weights(y1[ok], Y0[ok])
    gap = pd.Series(y1 - Y0 @ wt, index=yr)
    return dict(w=pd.Series(wt, index=pool), gap=gap, pre=float(np.sqrt(np.nanmean(gap[pre] ** 2))),
                post_rmspe=float(np.sqrt(np.nanmean(gap[post] ** 2))), post_mean=float(np.nanmean(gap[post])),
                first6=float(np.nanmean(gap.loc[F:F + 5])))


def sc_p(w, unit, pool, T, F):
    r = sc(w, unit, pool, T, F)
    ratios = []
    for d in pool:
        q = sc(w, d, [x for x in pool if x != d], T, F)
        ratios.append(q["post_rmspe"] / q["pre"])
    r["p"] = (1 + sum(x >= r["post_rmspe"] / r["pre"] for x in ratios)) / (1 + len(ratios))
    return r


MOD_TREAT = {"KS": (2013, 2012), "IL": (2016, 2015), "OK": (2019, 2018)}
never = [s for s in sorted(sy.st.unique()) if s not in MOD_TREAT and s != "IN"]
size = sy[sy.year.between(1994, 2011)].groupby("st").fat.mean()
base_donors = [s for s in never if size[s] >= 200]
SOUTH = {"AL", "AR", "DE", "DC", "FL", "GA", "KY", "LA", "MD", "MS", "NC", "OK", "SC", "TN", "TX", "VA", "WV"}
MW_NE = {"IA", "KS", "MI", "MN", "MO", "NE", "ND", "OH", "SD", "WI", "CT", "ME", "MA", "NH", "NJ", "NY", "PA", "RI", "VT"}
ALWAYS_BANNED = {"AK", "MA", "NC", "RI", "UT", "VT"}

W = wide("ai_share", (1994, 2024), 2015)
base = sc_p(W, "IL", base_donors, 2015, 2016)
top = lambda r: ", ".join(f"{s} {v:.2f}" for s, v in r["w"].sort_values(ascending=False).items() if v > 0.05)
rowsB, paths = [], {"Base": base["gap"]}
rowsB.append(dict(test=f"Base: {len(base_donors)} donors with 200+ deaths a year", pre=base["pre"], post=base["post_mean"],
                  first6=base["first6"], p=base["p"], donors=top(base)))
for name, pool in [("All never-treated states, no size filter", never),
                   ("Large states only (500+ deaths a year)", [s for s in never if size[s] >= 500]),
                   ("No Southern states", [s for s in base_donors if s not in SOUTH]),
                   ("Midwest and Northeast only", [s for s in never if s in MW_NE]),
                   ("No always-banned states", [s for s in base_donors if s not in ALWAYS_BANNED])]:
    r = sc_p(W, "IL", pool, 2015, 2016)
    paths[name] = r["gap"]
    rowsB.append(dict(test=f"{name} ({len(pool)} donors)", pre=r["pre"], post=r["post_mean"], first6=r["first6"],
                      p=r["p"], donors=top(r)))
loo = {}
for dnr in base["w"][base["w"] > 0.02].sort_values(ascending=False).index:
    r = sc(W, "IL", [x for x in base_donors if x != dnr], 2015, 2016)
    loo[dnr] = r["gap"]
    rowsB.append(dict(test=f"Leave out {dnr} (base weight {base['w'][dnr]:.2f})", pre=r["pre"], post=r["post_mean"],
                      first6=r["first6"], p=np.nan, donors=top(r)))
Wpre = wide("ai_share", (1994, 2014), 2008)
fake = sc_p(Wpre, "IL", base_donors, 2008, 2009)
rowsB.append(dict(test="In-time placebo: pretend Illinois repealed in 2008 (data through 2014)", pre=fake["pre"],
                  post=fake["post_mean"], first6=fake["first6"], p=fake["p"], donors=top(fake)))
Bt = pd.DataFrame(rowsB)
for c in ["pre", "post", "first6"]:
    Bt[c] = 100 * Bt[c]
Bt.round(3).to_csv(f"{OUT}/followup_illinois_sc_tests.csv", index=False)
loo_range = (100 * min(g.loc[2016:].mean() for g in loo.values()), 100 * max(g.loc[2016:].mean() for g in loo.values()))


# ---------------------------------------------------------------- C. synthetic difference-in-differences
from sdid import sdid  # noqa: E402


rowsC = []
for y in ["ai_share", "log_odds"]:
    taus, plac = {}, {}
    for k, (F, T) in MOD_TREAT.items():
        w = wide(y, (1994, 2024), T)
        taus[k] = sdid(w, k, base_donors, T, F)
        plac[k] = {dn: sdid(w, dn, [x for x in base_donors if x != dn], T, F) for dn in base_donors}
        pv = np.array(list(plac[k].values()))
        se = pv.std(ddof=1)
        pr = min(1.0, 2 * min((1 + np.sum(pv >= taus[k])) / (1 + len(pv)), (1 + np.sum(pv <= taus[k])) / (1 + len(pv))))
        rowsC.append(dict(outcome=y, unit=k, tau=100 * taus[k], ci_lo=100 * (taus[k] - 1.96 * se),
                          ci_hi=100 * (taus[k] + 1.96 * se), p=pr, placebos=len(pv)))
    keys = list(MOD_TREAT)
    sets = draw_sets({k: base_donors for k in keys}, keys)
    dist = np.array([np.mean([plac[k][row[i]] for i, k in enumerate(keys)]) for row in sets])
    r = ri_summary(float(np.mean([taus[k] for k in keys])), dist)
    rowsC.append(dict(outcome=y, unit="Pooled (mean of 3)", tau=100 * r["att"], ci_lo=100 * r["ci_lo"],
                      ci_hi=100 * r["ci_hi"], p=r["p"], placebos=B))
Ct = pd.DataFrame(rowsC)
Ct.round(3).to_csv(f"{OUT}/followup_sdid.csv", index=False)

# ---------------------------------------------------------------- figures
fig, axes = plt.subplots(1, 2, figsize=(15, 4.6), sharey=True)
cols = ["tab:blue", "tab:orange", "tab:green", "tab:purple", "tab:brown"]
for (name, g), c in zip([(n, g) for n, g in paths.items() if n != "Base"], cols):
    axes[0].plot(g.index, 100 * g.to_numpy(), color=c, lw=1.1, label=name)
for i, (dn, g) in enumerate(loo.items()):
    axes[1].plot(g.index, 100 * g.to_numpy(), color="0.6", lw=0.9, label="Leave one donor out" if i == 0 else None)
for ax in axes:
    ax.plot(base["gap"].index, 100 * base["gap"].to_numpy(), color="black", lw=2.2, label="Base synthetic control")
    ax.axvline(2015, color="tab:red", ls="--", lw=1)
    ax.axhline(0, color="0.4", lw=0.8)
    ax.set_xlabel("Year")
    ax.legend(fontsize=7.5, loc="upper left")
axes[0].set_ylabel("Illinois minus synthetic Illinois,\nimpaired share (pp)")
axes[0].set_title("Alternative donor pools", fontsize=10)
axes[1].set_title("Leave-one-out (each donor with weight > 0.02 dropped in turn)", fontsize=10)
fig.suptitle("Stress tests for the Illinois synthetic control (repeal effective July 2015)", fontsize=11.5)
fig.tight_layout()
fig.savefig(f"{FIG}/fig5_illinois_stress_tests.png", dpi=150)
plt.close(fig)

fig, ax = plt.subplots(figsize=(11, 5.2))
labs = [lab for _, lab in OUTS_A]
yy = np.arange(len(labs))[::-1]
for j, (spec, _, _) in enumerate(SPECS_A):
    sub = A[A.spec == spec].set_index("outcome").loc[[o for o, _ in OUTS_A]]
    off = (j - 1) * 0.22
    ax.errorbar(sub.att, yy + off, xerr=[sub.att - sub.ci_lo, sub.ci_hi - sub.att], fmt="o", ms=5, capsize=2,
                color=["0.55", "tab:blue", "tab:green"][j], label=spec)
ax.axvline(0, color="tab:red", ls="--", lw=0.9)
ax.set_yticks(yy)
ax.set_yticklabels(labs, fontsize=9)
ax.set_xlabel("Effect of imposing a strict ban, with 95% randomization interval (units in labels)", fontsize=9)
ax.set_title("1980s adoption wave, 1983-1995: adding seat-belt, speed-limit, BAC-law and income controls", fontsize=10.5)
ax.legend(fontsize=8.5, loc="upper left")
fig.tight_layout()
fig.savefig(f"{FIG}/fig6_1980s_with_traffic_controls.png", dpi=150)
plt.close(fig)

json.dump(dict(A=json.loads(A.to_json(orient="records")), B=json.loads(Bt.to_json(orient="records")),
               C=json.loads(Ct.to_json(orient="records")), belt_first=belt_first,
               loo_range=loo_range, base_w=base["w"].round(3).to_dict()),
          open(str(JSON / "followup_data.json"), "w"))

pd.set_option("display.width", 220)
pd.set_option("display.max_colwidth", 70)
print("A. 1980s with controls (x100)\n", A[["spec", "outcome", "att", "ci_lo", "ci_hi", "p"]].round(2).to_string(index=False))
print("\nFirst seat-belt-law year, treated states:", belt_first)
print("\nB. Illinois SC tests (pp)\n", Bt.round(2).to_string(index=False))
print("\nLOO post-gap range (pp): %.2f to %.2f" % loo_range)
print("\nC. SDID (x100)\n", Ct.round(2).to_string(index=False))
