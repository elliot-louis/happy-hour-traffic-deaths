#!/usr/bin/env python3
"""
more_tests.py -- further checks with data already in hand (report section 8.7).

  weekend    weekday vs. weekend evenings (4-10 pm): happy hours are mostly a weekday practice, so a ban
             should lower alcohol involvement on weekday evenings relative to weekend evenings.
  timing     is the 1980s evening-vs-night shift in sober deaths real? The same contrast for ALL deaths (no
             BAC data involved), and weekday-evening and night deaths per vehicle-mile separately.
  neighbors  drop states bordering a treated state from the comparison group (cross-border drinking).
  jackknife  drop one treated state at a time.
  pooled     all nine law changes combined as the effect of having a ban (repeal estimates sign-flipped).
  midrvacc   cross-check the driver-BAC construction against NHTSA's own highest-driver-BAC file, 2013-2015.
  curve      specification curve of every impaired-share estimate produced so far.
"""
from paths import RESULTS, FIGURES, INPUTS, JSON, RAW as RAW_DIR, AGG as AGG_DIR, TMP as TMP_DIR, CODE  # noqa: E402
import os, re, sys, json, zipfile, importlib.util, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")
OUT = str(RESULTS)
from ri import joint_ri

import estimator  # noqa: E402
estimator.configure(B=5000, seed=77)
ns = vars(estimator)
run, make_pools, analyze = ns["run"], ns["make_pools"], ns["analyze"]
rng = np.random.default_rng(78)

sy = pd.read_csv(f"{OUT}/hh_state_year_panel.csv")
raw = pd.read_csv(f"{OUT}/hh_state_year_dow_hour_counts.csv")
vm = pd.read_csv(f"{OUT}/fhwa_vm2_state_year.csv")[["st", "year", "vmt"]]
aer = pd.read_csv(INPUTS / "fatalities.csv")
ALL = sorted(sy.st.unique())
MOD_TREAT = {"KS": (2013, 2012), "IL": (2016, 2015), "OK": (2019, 2018)}
from designs import AD_TREAT, AD_STATES as VERIFIED_STATES  # noqa: E402
EXCL80 = ["NE", "NJ", "MI", "OH", "TX", "DE", "ME", "WA", "OK", "UT"]
AD_STATES = list(VERIFIED_STATES)
MOD = dict(treat=MOD_TREAT, yrs=(1994, 2024), states=ALL, controls=[s for s in ALL if s not in MOD_TREAT],
           extra_drop=[("IN", 2024)], pool_excl=["IN"], E=(-1, 1))
ADO = dict(treat=AD_TREAT, yrs=(1982, 1995), states=AD_STATES, controls=[s for s in AD_STATES if s not in AD_TREAT],
           covars=("mlda",), E=(-1, 1))
DES = {"modern_repeals": MOD, "adoption_1980s": ADO}

# ---------------------------------------------------------------- new state-year outcomes
eve, wk, wkend = raw.hbin.isin(["16-18", "19-21"]), raw.dow.between(2, 6), raw.dow.isin([1, 7])
night = raw.hbin.isin(["22-23", "00-05"])
agg = lambda m: raw[m].groupby(["st", "year"])[["fat", "ai08", "sober"]].sum()
W, E_, N_ = agg(wk & eve), agg(wkend & eve), agg(night)
X = sy.set_index(["st", "year"]).join(vm.set_index(["st", "year"]))
X["we_ai"] = np.log(W.ai08 / E_.ai08)            # weekday vs weekend evenings, impaired deaths
X["we_sober"] = np.log(W.sober / E_.sober)       # same for sober deaths (placebo)
X["we_net"] = X.we_ai - X.we_sober               # log odds ratio of alcohol involvement, weekday vs weekend evenings
X["tod_all"] = np.log(W.fat / N_.fat)            # weekday evening vs night, ALL deaths (no BAC data)
X["eve_per_vmt"] = np.log(W.fat / (X.vmt / 1e8))
X["night_per_vmt"] = np.log(N_.fat / (X.vmt / 1e8))
X = X.replace([np.inf, -np.inf], np.nan).reset_index()
LAB = {"we_ai": "Weekday vs weekend evenings, impaired (x100)", "we_sober": "Weekday vs weekend evenings, sober: placebo (x100)",
       "we_net": "Weekday vs weekend evenings, net (x100)", "tod_all": "Evening vs night, ALL deaths (x100)",
       "eve_per_vmt": "Weekday-evening deaths per mile (log x100)", "night_per_vmt": "Night deaths per mile (log x100)",
       "ai_share": "Impaired share (pp)", "log_odds": "Log odds, impaired vs sober (x100)", "svn_share": "Single-vehicle-night share (pp)"}
rows = []


def rec(section, design, spec, y, s):
    rows.append(dict(section=section, design=design, spec=spec, outcome=y, label=LAB[y], att=100 * s["att"],
                     ci_lo=100 * s["ci_lo"], ci_hi=100 * s["ci_hi"], p=s["p"]))


for g, cfg in DES.items():
    for y in ["we_ai", "we_sober", "we_net"]:
        rec("weekend", g, "main", y, analyze(X, y, **cfg)["summary"])
    for y in (["tod_all", "eve_per_vmt", "night_per_vmt"] if g == "adoption_1980s" else ["tod_all"]):
        rec("timing", g, "main", y, analyze(X, y, **cfg)["summary"])
print("weekend/timing done", flush=True)

NB = {"modern_repeals": {"NE", "MO", "CO", "WI", "IA", "KY", "IN", "AR", "TX", "NM"},
      "adoption_1980s": {"NH", "NY", "CT", "NE", "MO", "CO", "KY", "VA", "TN", "GA", "SC", "WI", "IA", "MI", "OH", "OK"}}
for g, cfg in DES.items():
    c = dict(cfg, states=[s for s in cfg["states"] if s not in NB[g]], controls=[s for s in cfg["controls"] if s not in NB[g]],
             extra_drop=[], pool_excl=[])
    for y in ["ai_share", "log_odds"]:
        rec("neighbors", g, f"drop {len(set(cfg['controls']) & NB[g])} bordering states", y, analyze(sy, y, **c)["summary"])
    for k in cfg["treat"]:
        c = dict(cfg, treat={s: v for s, v in cfg["treat"].items() if s != k}, states=[s for s in cfg["states"] if s != k])
        for y in (["ai_share"] if g == "modern_repeals" else ["ai_share", "svn_share"]):
            rec("jackknife", g, f"without {k}", y, analyze(sy, y, **c)["summary"])
print("neighbors/jackknife done", flush=True)

# ---------------------------------------------------------------- pooled effect of having a ban
pooled = []
for y in ["log_odds", "ai_share"]:
    est, dist = {}, {}
    for g, cfg in DES.items():
        d = run(sy, y, cfg["treat"], cfg["yrs"], cfg["states"], cfg.get("covars", ()), cfg.get("extra_drop", ()))
        est[g] = float(np.mean([d[(d.st == k) & d.e.between(0, 5)].gap.mean() for k in cfg["treat"]]))
        pools = make_pools(sy, cfg["treat"], cfg["controls"], cfg["yrs"], exclude=cfg.get("pool_excl", ()))
        dd, _ = joint_ri(sy, y, cfg["treat"], cfg["yrs"], cfg["controls"], pools, rng, B=5000,
                         covars=cfg.get("covars", ()), extra_drop=cfg.get("extra_drop", ()))
        dist[g] = dd[~np.isnan(dd)]
    n = min(len(dist["modern_repeals"]), len(dist["adoption_1980s"]))
    vm_, va_ = dist["modern_repeals"].var(), dist["adoption_1980s"].var()
    for wl, wm in [(f"equal weight per law change ({len(MOD_TREAT)} repeals, {len(AD_TREAT)} bans)", len(MOD_TREAT) / (len(MOD_TREAT) + len(AD_TREAT))), ("inverse-variance weights", (1 / vm_) / (1 / vm_ + 1 / va_))]:
        e = wm * (-est["modern_repeals"]) + (1 - wm) * est["adoption_1980s"]      # repeals sign-flipped: effect of HAVING a ban
        null = wm * (-dist["modern_repeals"][:n]) + (1 - wm) * dist["adoption_1980s"][:n]
        q_lo, q_hi = np.quantile(null, [0.025, 0.975])
        p = min(1.0, 2 * min((1 + np.sum(null >= e)) / (1 + n), (1 + np.sum(null <= e)) / (1 + n)))
        pooled.append(dict(outcome=y, weighting=wl, weight_on_repeals=wm, att=100 * e, ci_lo=100 * (e - q_hi), ci_hi=100 * (e - q_lo), p=p))
print("pooled done", flush=True)

# ---------------------------------------------------------------- NHTSA MIDRVACC cross-check
spec = importlib.util.spec_from_file_location("bf", f"{CODE}/build_fars.py")
bf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bf)
os.makedirs(bf.TMP, exist_ok=True)
from dbfread import DBF
mid = []
for yr in [2013, 2014, 2015]:
    z = bf.fetch(f"fars/{yr}/National/FARS{yr}NationalDBF.zip")
    zf = zipfile.ZipFile(z)
    nm = [n for n in zf.namelist() if re.fullmatch(r"midrvacc\.dbf", os.path.basename(n), re.I)][0]
    local = os.path.join(bf.TMP, "midrv.dbf")
    open(local, "wb").write(zf.read(nm))
    df = pd.DataFrame(iter(DBF(local, load=False, char_decode_errors="ignore")))
    df.columns = [c.upper() for c in df.columns]
    ac = [c for c in df.columns if re.fullmatch(r"[AP]\d+", c)]
    v = df[ac].apply(pd.to_numeric, errors="coerce").to_numpy()
    scale = 1000.0 if np.nanpercentile(v[v > 0], 90) > 60 else 100.0
    p_nh = pd.Series(((v / scale) >= 0.08).mean(axis=1), index=pd.to_numeric(df.ST_CASE).astype("int64"))
    acc = bf.dbf_from_zip(z, r"(acc\d{2,4}|accident)\.dbf", bf.ACC_KEEP)
    mi = bf.dbf_from_zip(z, r"miper\d*\.dbf", bf.MI_KEEP)
    mi = mi[["ST_CASE", "VEH_NO", "PER_NO"] + bf.PCOLS].apply(pd.to_numeric, errors="coerce")
    drv = mi[mi.VEH_NO > 0].sort_values("PER_NO").drop_duplicates(["ST_CASE", "VEH_NO"])
    sc2 = 1000.0 if np.nanpercentile(drv[bf.PCOLS].values[drv[bf.PCOLS].values > 0], 90) > 60 else 100.0
    p_me = ((drv.groupby("ST_CASE")[bf.PCOLS].max() / sc2) >= 0.08).mean(axis=1)
    p_me.index = p_me.index.astype("int64")
    acc["ST_CASE"] = pd.to_numeric(acc.ST_CASE).astype("int64")
    acc["FATALS"] = pd.to_numeric(acc.FATALS)
    a = acc.set_index("ST_CASE")
    pm_, pn_ = p_me.reindex(a.index).fillna(0), p_nh.reindex(a.index).fillna(0)
    mid.append(dict(year=yr, crashes=len(a), identical_share=float((np.abs(pm_ - pn_) < 1e-9).mean()),
                    impaired_deaths_mine=float((a.FATALS * pm_).sum()), impaired_deaths_nhtsa_file=float((a.FATALS * pn_).sum()),
                    max_abs_diff=float(np.abs(pm_ - pn_).max())))
    for f in os.listdir(bf.TMP):
        os.remove(os.path.join(bf.TMP, f))
print("midrvacc", mid, flush=True)

R = pd.DataFrame(rows)
R.round(3).to_csv(f"{OUT}/more_tests_results.csv", index=False)
P = pd.DataFrame(pooled)
P.round(4).to_csv(f"{OUT}/more_tests_pooled.csv", index=False)

# ---------------------------------------------------------------- specification curve (impaired share, pp)
cur = []
m0 = pd.read_csv(f"{OUT}/results_main.csv")
for g in DES:
    r = m0[(m0.design == g) & (m0.outcome == "ai_share")].iloc[0]
    cur.append((g, "Main", r.att, r.ci_lo, r.ci_hi))
rb = pd.read_csv(f"{OUT}/results_robustness.csv")
for r in rb[(rb.outcome == "ai_share") & ~rb.spec.str.startswith("timing")].itertuples():
    cur.append((r.design, "Robustness checks", r.att, r.ci_lo, r.ci_hi))
for r in pd.read_csv(f"{OUT}/followup_1980s_controls.csv").query("outcome == 'ai_share'").itertuples():
    cur.append(("adoption_1980s", "Traffic-safety controls", r.att, r.ci_lo, r.ci_hi))
for r in pd.read_csv(f"{OUT}/vmt_results.csv").query("outcome == 'ai_share'").itertuples():
    cur.append((r.design, "Vehicle-miles controls", r.att, r.ci_lo, r.ci_hi))
r = pd.read_csv(f"{OUT}/followup_sdid.csv").query("outcome == 'ai_share' and unit == 'Pooled (mean of 3)'").iloc[0]
cur.append(("modern_repeals", "Synthetic DiD", r.tau, r.ci_lo, r.ci_hi))
for r in pd.read_csv(f"{OUT}/fred_results.csv").query("outcome == 'ai_share'").itertuples():
    cur.append((r.design, "Unemployment and population", r.att, r.ci_lo, r.ci_hi))
ALT = ["Four strict bans (MA, NC, VT, IL)", "Original seven, clean comparison group", "Six bans, Vermont dated 1986",
       "Six bans plus Alaska (1983-95)"]
for r in pd.read_csv(f"{OUT}/recode_1980s_results.csv").query("outcome == 'ai_share' and design in @ALT").itertuples():
    cur.append(("adoption_1980s", "Alternative 1980s coding", r.att, r.ci_lo, r.ci_hi))
for r in pd.read_csv(f"{OUT}/tests_now_dates.csv").query("outcome == 'ai_share' and state != 'none'").itertuples():
    cur.append(("adoption_1980s", "Date shifted +/-1 year", r.att, r.ci_lo, r.ci_hi))
for r in R[R.outcome == "ai_share"].itertuples():
    cur.append((r.design, "Neighbors dropped" if r.section == "neighbors" else "Jackknife", r.att, r.ci_lo, r.ci_hi))
C = pd.DataFrame(cur, columns=["design", "family", "att", "ci_lo", "ci_hi"])
C.round(3).to_csv(f"{OUT}/spec_curve_ai_share.csv", index=False)
fams = list(dict.fromkeys(C.family))
PALETTE = {"Main": "black", "Robustness checks": "tab:blue", "Traffic-safety controls": "tab:green",
           "Vehicle-miles controls": "tab:orange", "Unemployment and population": "tab:cyan", "Synthetic DiD": "tab:purple",
           "Alternative 1980s coding": "tab:pink", "Date shifted +/-1 year": "tab:brown", "Neighbors dropped": "tab:red",
           "Jackknife": "tab:olive"}
col = {f: PALETTE.get(f, "tab:gray") for f in fams}
fig, axes = plt.subplots(1, 2, figsize=(15, 6.0), sharey=True)
for ax, (g, title) in zip(axes, [("modern_repeals", "Modern repeals: effect of LIFTING a ban"), ("adoption_1980s", "1980s: effect of IMPOSING a ban")]):
    c = C[C.design == g].sort_values("att").reset_index(drop=True)
    for i, r in c.iterrows():
        ax.plot([i, i], [r.ci_lo, r.ci_hi], color=col[r.family], lw=1.2, alpha=0.7)
        ax.plot(i, r.att, "o", color=col[r.family], ms=5 if r.family != "Main" else 8)
    ax.axhline(0, color="tab:red", ls="--", lw=0.9)
    ax.set_title(f"{title}: {len(c)} specifications", fontsize=10)
    ax.set_xlabel("Specifications, sorted by estimate", fontsize=9)
from matplotlib.lines import Line2D  # noqa: E402
handles = [Line2D([0], [0], marker="o", ls="", color=col[f], ms=8 if f == "Main" else 6, label=f) for f in fams]
fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.0), ncol=5, fontsize=8.5, frameon=False)
fig.subplots_adjust(left=0.06, right=0.99, top=0.93, bottom=0.25, wspace=0.05)
axes[0].set_ylabel("Impaired share of deaths (pp), 95% interval")
fig.savefig(f"{FIGURES}/fig9_specification_curve.png", dpi=150)
plt.close(fig)

json.dump(dict(rows=json.loads(R.to_json(orient="records")), pooled=json.loads(P.to_json(orient="records")), midrvacc=mid,
               curve=dict(n_modern=int((C.design == "modern_repeals").sum()), n_1980s=int((C.design == "adoption_1980s").sum()),
                          sig_modern=int(((C.design == "modern_repeals") & ((C.ci_lo > 0) | (C.ci_hi < 0))).sum()),
                          sig_1980s=int(((C.design == "adoption_1980s") & ((C.ci_lo > 0) | (C.ci_hi < 0))).sum()),
                          range_modern=[float(C[C.design == "modern_repeals"].att.min()), float(C[C.design == "modern_repeals"].att.max())],
                          range_1980s=[float(C[C.design == "adoption_1980s"].att.min()), float(C[C.design == "adoption_1980s"].att.max())])),
          open(f"{OUT}/more_tests_results.json", "w"), indent=1, default=float)
pd.set_option("display.width", 220)
print(R[["section", "design", "spec", "outcome", "att", "ci_lo", "ci_hi", "p"]].round(2).to_string(index=False))
print(P.round(3).to_string(index=False))
print(json.load(open(f"{OUT}/more_tests_results.json"))["curve"])
