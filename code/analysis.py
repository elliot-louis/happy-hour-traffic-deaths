#!/usr/bin/env python3
"""
analysis.py -- Happy hour laws and alcohol-impaired traffic deaths: upgraded analysis

Two natural experiments
  A. Modern repeals, 1994-2024: Kansas (ban lifted 7/1/2012), Illinois (ban -> restricted, 7/15/2015),
     Oklahoma (10/1/2018). Indiana (7/1/2024) has no full post year yet: its 2024 is dropped and it is
     a control through 2023.
  B. 1980s adoption wave, 1982-1995: strict bans in Massachusetts (12/10/1984), Kansas, Indiana,
     North Carolina, Rhode Island, Vermont (1985) and Illinois (1989). States with partial or undated
     1980s restrictions (NE, NJ, MI, OH, TX; DE, ME, WA) and OK/UT are excluded from the controls;
     AK, HI and DC fall outside the drinking-age covariate data (Ruhm/AER 1982-88 panel).

Estimator
  Imputation DiD (Borusyak, Jaravel & Spiess 2024): fit state + year fixed effects (plus covariates)
  on untreated state-years only, impute each treated state's counterfactual, and average actual minus
  imputed over event years 0-5 (the first six full years under the new law). Mid-year transition
  years are dropped.

Inference
  Joint size-matched randomization inference (ri.py): each draw assigns every treated state's event dates
  to a distinct never-treated state with 0.5x-2x its pre-period deaths (nearest 8 if fewer qualify),
  re-fits the model with all placebo states treated at once, and recomputes the pooled estimate; 5,000 draws.
  Per-state p-values use single-state placebo fits. Two-sided p-values; 95% intervals invert the placebo
  distribution (constant-effect assumption); MDE80 = 2.8 x placebo SD.
  Plus synthetic control with in-space placebos for each modern repeal state.

Outcomes (state-year)
  ai_share   alcohol-impaired deaths / all deaths (continuity with the original analysis)
  log_odds   log(alcohol-impaired / sober deaths): sober deaths in the same state-year absorb exposure
  svn_share  single-vehicle-night deaths / all deaths (BAC-free proxy)
  ddd_ai     log(impaired deaths Mon-Fri 4-10pm / impaired deaths 10pm-6am): time-of-day triple difference
  ddd_sober  the same ratio for sober deaths (placebo: should not move)
  ddd_net    ddd_ai - ddd_sober = log odds ratio of alcohol involvement, weekday evening vs night:
             nets out anything that shifts ALL crashes between evening and night
"""
from paths import RESULTS, FIGURES, INPUTS, JSON, RAW as RAW_DIR, AGG as AGG_DIR, TMP as TMP_DIR, CODE  # noqa: E402
import glob, os, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.optimize import nnls
from linearmodels.panel import PanelOLS

warnings.filterwarnings("ignore")
AGG, AER = str(AGG_DIR), str(INPUTS / "fatalities.csv")
OUT = str(RESULTS)
FIG = str(FIGURES)
os.makedirs(FIG, exist_ok=True)
rng = np.random.default_rng(20260924)
B = 5000          # randomization-inference draws
H = (0, 5)        # event years averaged into the ATT

FIPS = {1: "AL", 2: "AK", 4: "AZ", 5: "AR", 6: "CA", 8: "CO", 9: "CT", 10: "DE", 11: "DC", 12: "FL", 13: "GA",
        15: "HI", 16: "ID", 17: "IL", 18: "IN", 19: "IA", 20: "KS", 21: "KY", 22: "LA", 23: "ME", 24: "MD",
        25: "MA", 26: "MI", 27: "MN", 28: "MS", 29: "MO", 30: "MT", 31: "NE", 32: "NV", 33: "NH", 34: "NJ",
        35: "NM", 36: "NY", 37: "NC", 38: "ND", 39: "OH", 40: "OK", 41: "OR", 42: "PA", 44: "RI", 45: "SC",
        46: "SD", 47: "TN", 48: "TX", 49: "UT", 50: "VT", 51: "VA", 53: "WA", 54: "WV", 55: "WI", 56: "WY"}

# ------------------------------------------------------------------ 1. panel
raw = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(f"{AGG}/fars_*.csv"))], ignore_index=True)
raw = raw[raw.state.isin(FIPS)].copy()
raw.insert(1, "st", raw.state.map(FIPS))
raw["sober"] = raw.fat - raw.ai08
weekday = raw.dow.between(2, 6)
raw["win"] = np.select([weekday & raw.hbin.isin(["16-18", "19-21"]), raw.hbin.isin(["22-23", "00-05"])],
                       ["hh", "night"], "other")
sy = raw.groupby(["st", "year"])[["fat", "ai08", "ai01", "svn", "sober"]].sum()
wv = raw.groupby(["st", "year", "win"])[["ai08", "sober"]].sum().unstack("win").fillna(0.0)
for v in ["ai08", "sober"]:
    for w in ["hh", "night"]:
        sy[f"{v}_{w}"] = wv[(v, w)]
sy = sy.reset_index()
sy["ai_share"] = sy.ai08 / sy.fat
sy["log_odds"] = np.log(sy.ai08 / sy.sober)
sy["svn_share"] = sy.svn / sy.fat
sy["ddd_ai"] = np.log(sy.ai08_hh / sy.ai08_night)
sy["ddd_sober"] = np.log(sy.sober_hh / sy.sober_night)
sy["ddd_net"] = sy.ddd_ai - sy.ddd_sober      # evening-vs-night odds ratio of alcohol involvement
sy = sy.replace([np.inf, -np.inf], np.nan)
aer = pd.read_csv(AER)
aer["st"] = aer.state.str.upper()
mlda = aer.set_index(["st", "year"]).drinkage.to_dict()
sy["mlda"] = [mlda.get((s, y), 21.0 if y > 1988 else np.nan) for s, y in zip(sy.st, sy.year)]
sy.round(6).to_csv(f"{OUT}/hh_state_year_panel.csv", index=False)
raw.drop(columns=["state"]).round(4).to_csv(f"{OUT}/hh_state_year_dow_hour_counts.csv", index=False)
nat = sy.groupby("year")[["fat", "ai08"]].sum()
nat["ai_share"] = nat.ai08 / nat.fat
nat.round(3).to_csv(f"{OUT}/national_totals_check.csv")
print(f"Panel: {sy.st.nunique()} jurisdictions x {sy.year.min()}-{sy.year.max()} ({len(sy)} state-years)")


# ------------------------------------------------------------------ 2. estimator (code/estimator.py)
import estimator
estimator.configure(B=B, seed=20260924)
from estimator import fe_predict, run, pre_size, make_pools, event_bands, analyze, cfg_with  # noqa: E402


# ------------------------------------------------------------------ 3. designs
ALL = sorted(FIPS.values())
MOD_TREAT = {"KS": (2013, 2012), "IL": (2016, 2015), "OK": (2019, 2018)}
MOD = dict(treat=MOD_TREAT, yrs=(1994, 2024), states=ALL, controls=[s for s in ALL if s not in MOD_TREAT],
           extra_drop=[("IN", 2024)], pool_excl=["IN"], E=(-10, 11))
AER_ST = sorted(aer.st.unique())
from designs import AD_PARTIAL as PARTIAL  # noqa: E402  (partial restrictions in the verified coding)
from designs import AD_TREAT, AD_STATES as VERIFIED_STATES  # noqa: E402
AD_STATES = list(VERIFIED_STATES)
ADO = dict(treat=AD_TREAT, yrs=(1982, 1995), states=AD_STATES, controls=[s for s in AD_STATES if s not in AD_TREAT],
           covars=("mlda",), E=(-8, 10))
OUTCOMES = [("ai_share", "Alcohol-impaired share of deaths (pp)"),
            ("log_odds", "Log odds, impaired vs. sober deaths (x100)"),
            ("svn_share", "Single-vehicle-night share, BAC-free (pp)"),
            ("ddd_ai", "Time-of-day DDD, impaired deaths (x100)"),
            ("ddd_sober", "Time-of-day DDD, sober deaths: placebo (x100)"),
            ("ddd_net", "Evening-vs-night alcohol odds ratio, net (x100)")]

main_rows, state_rows, rob_rows, ES = [], [], [], {}


def rec(rows, design, spec, y, label, res):
    rows.append(dict(design=design, spec=spec, outcome=y, label=label, **res["summary"]))


for design, cfg in [("modern_repeals", MOD), ("adoption_1980s", ADO)]:
    for y, label in OUTCOMES:
        res = analyze(sy, y, **cfg)
        rec(main_rows, design, "main", y, label, res)
        for k, v in res["by_state"].items():
            state_rows.append(dict(design=design, outcome=y, state=k, **v))
        ES[(design, y)] = res["es"]


def time_placebo(panel, y, cfg, shift=5):
    """Pretend each law changed `shift` years early, using only true pre-period data."""
    pre = panel.copy()
    for k, (F, T) in cfg["treat"].items():
        pre = pre[~((pre.st == k) & (pre.year >= (T if T is not None else F)))]
    fake = {k: (F - shift, (T - shift) if T is not None else None) for k, (F, T) in cfg["treat"].items()}
    return analyze(pre, y, **cfg_with(cfg, treat=fake, horizon=(0, shift - 2)))


ROB_OUT = OUTCOMES
no_covid = sy[~sy.year.isin([2020, 2021])]
ROB_MOD = [("excl. 2020-21", no_covid, MOD),
           ("fatality-weighted", sy, cfg_with(MOD, weighting="size")),
           ("all post years", sy, cfg_with(MOD, horizon=(0, 40))),
           ("state linear trends", sy, cfg_with(MOD, trends=True)),
           ("excl. 2024 (newest FARS year)", sy[sy.year <= 2023], MOD),
           ("KS + OK only (full repeals)", sy, cfg_with(MOD, treat={"KS": (2013, 2012), "OK": (2019, 2018)},
                                                         states=[s for s in ALL if s != "IL"]))]
for spec, pnl, cfg in ROB_MOD:
    for y, label in ROB_OUT:
        rec(rob_rows, "modern_repeals", spec, y, label, analyze(pnl, y, **cfg))
for y, label in ROB_OUT:
    rec(rob_rows, "modern_repeals", "timing placebo (5 yrs early)", y, label, time_placebo(sy, y, MOD))
ROB_ADO = [("incl. partial-restriction states as controls", sy,
            cfg_with(ADO, states=AD_STATES + PARTIAL, controls=ADO["controls"] + PARTIAL)),
           ("no MLDA covariate", sy, cfg_with(ADO, covars=())),
           ("fatality-weighted", sy, cfg_with(ADO, weighting="size"))]
for spec, pnl, cfg in ROB_ADO:
    for y, label in ROB_OUT:
        rec(rob_rows, "adoption_1980s", spec, y, label, analyze(pnl, y, **cfg))

# ------------------------------------------------------------------ 4. replication of the original TWFE
rep = sy[sy.year.between(1994, 2024)].copy()
rep["banned"] = rep.st.isin(["AK", "MA", "NC", "RI", "UT", "VT"]).astype(float)
for s, T in {"KS": 2012, "IL": 2015, "OK": 2018, "IN": 2024}.items():
    rep.loc[(rep.st == s) & (rep.year < T), "banned"] = 1.0
    rep = rep[~((rep.st == s) & (rep.year == T))]
twfe = PanelOLS.from_formula("ai_share ~ banned + EntityEffects + TimeEffects",
                             rep.set_index(["st", "year"])).fit(cov_type="clustered", cluster_entity=True)
pd.DataFrame([dict(spec="TWFE, ai_share on banned (0/1), state+year FE, clustered by state, 1994-2024",
                   coef=twfe.params["banned"], se=twfe.std_errors["banned"], p=twfe.pvalues["banned"],
                   original_coef=0.0155, original_se=0.0120)]).round(4).to_csv(f"{OUT}/replication_twfe.csv", index=False)


# ------------------------------------------------------------------ 5. synthetic control (modern repeals)
def synth_weights(y1, Y0, M=1000.0):
    w, _ = nnls(np.vstack([Y0, M * np.ones((1, Y0.shape[1]))]), np.concatenate([y1, [M]]))
    return w


def synth(panel, y, k, F, T, donors, yrs):
    wide = panel[panel.year.between(*yrs)].pivot(index="year", columns="st", values=y).drop(index=T)
    yr = wide.index.to_numpy()
    pre, post = yr < T, yr >= F

    def fit(unit, pool):
        Y0, y1 = wide[pool].to_numpy(), wide[unit].to_numpy()
        ok = pre & ~np.isnan(Y0).any(axis=1) & ~np.isnan(y1)
        w = synth_weights(y1[ok], Y0[ok])
        gap = y1 - Y0 @ w
        return w, pd.Series(gap, index=yr), np.sqrt(np.nanmean(gap[pre] ** 2)), np.sqrt(np.nanmean(gap[post] ** 2))

    w, gap, r0, r1 = fit(k, donors)
    plac = {dn: fit(dn, [x for x in donors if x != dn])[1:] for dn in donors}
    ratio = r1 / r0
    p = (1 + sum(v[2] / v[1] >= ratio for v in plac.values())) / (1 + len(plac))
    top = pd.Series(w, index=donors).sort_values(ascending=False)
    return dict(state=k, outcome=y, T=T, gap=gap, pre_rmspe=r0, post_gap=float(np.nanmean(gap.to_numpy()[post])),
                post_gap_first6=float(np.nanmean(gap.loc[F:F + 5].to_numpy())), ratio=ratio, p=p, plac=plac, weights=", ".join(f"{s} {v:.2f}" for s, v in top[top > 0.05].items()))


sz9411 = sy[sy.year.between(1994, 2011)].groupby("st").fat.mean()
donors = [s for s in MOD["controls"] if s != "IN" and sz9411[s] >= 200]
SC = {(k, y): synth(sy, y, k, F, T, donors, (1994, 2024)) for y in ["ai_share", "log_odds"] for k, (F, T) in MOD_TREAT.items()}

# ------------------------------------------------------------------ 6. tables
main, rob, bys = pd.DataFrame(main_rows), pd.DataFrame(rob_rows), pd.DataFrame(state_rows)
for df in (main, rob):
    for c in ["att", "ci_lo", "ci_hi", "placebo_sd", "placebo_mean", "mde80", "baseline"]:
        df[c] = df[c] * 100
bys["att"] = bys["att"] * 100
main.round(3).to_csv(f"{OUT}/results_main.csv", index=False)
rob.round(3).to_csv(f"{OUT}/results_robustness.csv", index=False)
bys.round(3).to_csv(f"{OUT}/results_by_state.csv", index=False)
sct = pd.DataFrame([dict(state=r["state"], outcome=r["outcome"], pre_rmspe_x100=100 * r["pre_rmspe"],
                         mean_post_gap_x100=100 * r["post_gap"], first6_post_gap_x100=100 * r["post_gap_first6"], post_pre_rmspe_ratio=r["ratio"],
                         placebo_rank_p=r["p"], n_placebos=len(r["plac"]), donor_weights=r["weights"])
                    for r in SC.values()])
sct.round(3).to_csv(f"{OUT}/synthetic_control.csv", index=False)
pd.DataFrame({f"{k}_{y}": r["gap"] * 100 for (k, y), r in SC.items()}).round(3).to_csv(f"{OUT}/synthetic_control_gap_paths.csv")

# ------------------------------------------------------------------ 7. figures
COL = ["tab:blue", "tab:orange", "tab:green", "tab:red", "tab:purple", "tab:brown", "tab:pink"]


def es_plot(ax, es, title, individual=True):
    E = np.array(es["E"])
    # The pooled line and placebo band are drawn only for event years every treated state reaches; at the edges,
    # where fewer states contribute, the pooled mean is shown dotted so it is not read as a full-sample estimate.
    full = (es["act"].notna().sum(axis=1) == es["act"].shape[1]).to_numpy()
    lo, hi, pooled = es["lo"] * 100, es["hi"] * 100, np.asarray(es["pooled"], dtype=float) * 100
    ax.fill_between(E, np.where(full, lo, np.nan), np.where(full, hi, np.nan), color="0.86", lw=0,
                    label="95% placebo range (all states)")
    for i, k in enumerate(es["act"].columns):
        ax.plot(E, es["act"][k] * 100, color=COL[i] if individual else "0.6", lw=0.9, alpha=0.75,
                label=k if individual else ("Individual states" if i == 0 else None))
    ax.plot(E, np.where(full, pooled, np.nan), color="black", lw=2, marker="o", ms=3.5, label="Pooled (all states)")
    if (~full & ~np.isnan(pooled)).any():
        ax.plot(E, np.where(~full, pooled, np.nan), color="black", lw=1.1, ls=":", marker="o", ms=2.5,
                mfc="white", label="Pooled (fewer states)")
    ax.axhline(0, color="0.4", lw=0.8)
    ax.axvline(-0.5, color="0.4", ls="--", lw=0.8)
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("Years relative to first full year under the new law", fontsize=8.5)


for design, outs, fname, title, indiv in [
        ("modern_repeals", ["ai_share", "log_odds", "ddd_net"], "fig1_modern_repeals_event_study.png",
         "Modern repeals (KS 2012, IL 2015, OK 2018): actual minus imputed counterfactual", True),
        ("adoption_1980s", ["ai_share", "svn_share", "ddd_net"], "fig3_adoption_wave_event_study.png",
         "1980s bans (MA, KS, IN, NC, VT, IL): actual minus imputed counterfactual", False)]:
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.6))
    lab = dict(OUTCOMES)
    for ax, y in zip(axes, outs):
        es_plot(ax, ES[(design, y)], lab[y], individual=indiv)
    axes[0].legend(fontsize=7.5, loc="upper left")
    fig.suptitle(title, fontsize=11.5)
    fig.tight_layout()
    fig.savefig(f"{FIG}/{fname}", dpi=150)
    plt.close(fig)

fig, axes = plt.subplots(1, 3, figsize=(16, 4.4), sharey=True)
for ax, k in zip(axes, MOD_TREAT):
    r = SC[(k, "ai_share")]
    for dn, (g, p0, p1) in r["plac"].items():
        if p0 <= 5 * r["pre_rmspe"]:
            ax.plot(g.index, g.to_numpy() * 100, color="0.8", lw=0.7)
    ax.plot(r["gap"].index, r["gap"].to_numpy() * 100, color="black", lw=2.2, label=f"{k} minus synthetic {k}")
    ax.axvline(r["T"], color="tab:red", ls="--", lw=1)
    ax.axhline(0, color="0.4", lw=0.8)
    ax.set_title(f"{k}: repeal {r['T']} | post gap {100 * r['post_gap']:+.1f} pp | placebo rank p = {r['p']:.2f}", fontsize=10)
    ax.set_xlabel("Year", fontsize=9)
    ax.legend(fontsize=8, loc="lower left")
axes[0].set_ylabel("Alcohol-impaired share: actual minus synthetic (pp)")
fig.suptitle("Synthetic control with in-space placebos (gray = donor states run as fake treated units)", fontsize=11.5)
fig.tight_layout()
fig.savefig(f"{FIG}/fig2_synthetic_control.png", dpi=150)
plt.close(fig)

fig, axes = plt.subplots(1, 2, figsize=(15, 4.6), sharey=True)
for ax, design, title in [(axes[0], "modern_repeals", "Modern repeals: effect of LIFTING a ban\n(+ would mean bans were working)"),
                          (axes[1], "adoption_1980s", "1980s adoptions: effect of IMPOSING a ban\n(- would mean bans work)")]:
    m = main[main.design == design].reset_index(drop=True)
    yy = np.arange(len(m))[::-1]
    for yv, (_, r) in zip(yy, m.iterrows()):
        ax.plot([r.ci_lo, r.ci_hi], [yv, yv], color="0.35", lw=2.2)
        ax.plot(r.att, yv, "o", color="black", ms=6)
        ax.text(r.ci_hi, yv + 0.18, " p<0.001" if r.p < 0.001 else f" p={r.p:.2f}", fontsize=8, color="0.3")
    ax.axvline(0, color="tab:red", ls="--", lw=0.9)
    ax.set_yticks(yy)
    ax.set_yticklabels(m.label, fontsize=9)
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("Estimate with 95% randomization-inference interval (units in labels)", fontsize=8.5)
fig.tight_layout()
fig.savefig(f"{FIG}/fig4_summary_estimates.png", dpi=150)
plt.close(fig)

# ------------------------------------------------------------------ 8. print
pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 20)
cols = ["design", "outcome", "att", "ci_lo", "ci_hi", "p", "placebo_mean", "mde80", "baseline"]
print("\nMAIN (x100)\n", main[cols].round(2).to_string())
print("\nBY STATE (att x100)\n", bys.pivot_table(index=["design", "outcome"], columns="state", values=["att", "p"]).round(2).to_string())
print("\nROBUSTNESS (x100)\n", rob[["design", "spec", "outcome", "att", "ci_lo", "ci_hi", "p"]].round(2).to_string())
print("\nSYNTHETIC CONTROL\n", sct.round(3).to_string())
print("\nTWFE replication: coef %.4f (SE %.4f, p %.3f) vs original +0.0155 (0.0120)"
      % (twfe.params["banned"], twfe.std_errors["banned"], twfe.pvalues["banned"]))
print("\nDonor pool for SC:", donors)
