#!/usr/bin/env python3
"""
final_specs.py -- headline estimates and figures for the research poster.

Uses the same designs as the paper: the six verified 1980s bans (MA, KS, IN, NC, VT, IL) against the 29 states
where the law check found no statewide change, and the three modern repeals. For both experiments it estimates
the impaired share, log odds of impaired vs sober deaths, impaired deaths per capita and per vehicle-mile, and
the two timing tests; reports one-sided 95% equivalence limits (the 90% interval); and pools all nine law
changes as the effect of HAVING a ban (repeals sign-flipped). It draws its own randomization samples, so its
intervals can differ from the paper's in the last digit.
Outputs: final_results.csv/.json and poster figures in figures/poster_*.png
"""
from paths import RESULTS, FIGURES, INPUTS, JSON, RAW as RAW_DIR, AGG as AGG_DIR, TMP as TMP_DIR, CODE  # noqa: E402
import sys, json, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")
OUT = str(RESULTS)
from ri import joint_ri

import estimator  # noqa: E402
estimator.configure(B=5000, seed=151)
ns = vars(estimator)
run, make_pools = ns["run"], ns["make_pools"]
rng = np.random.default_rng(152)

P = pd.read_csv(f"{OUT}/hh_state_year_panel_full.csv")
raw = pd.read_csv(f"{OUT}/hh_state_year_dow_hour_counts.csv")
eve = raw.hbin.isin(["16-18", "19-21"])
Wk = raw[raw.dow.between(2, 6) & eve].groupby(["st", "year"])[["ai08", "sober"]].sum()
We = raw[raw.dow.isin([1, 7]) & eve].groupby(["st", "year"])[["ai08", "sober"]].sum()
P = P.set_index(["st", "year"])
P["we_net"] = np.log(Wk.ai08 / We.ai08) - np.log(Wk.sober / We.sober)
P = P.replace([np.inf, -np.inf], np.nan).reset_index()

L = pd.read_csv(INPUTS / "happy_hour_law_changes_1980_1995.csv")
aer = sorted(pd.read_csv(INPUTS / "fatalities.csv").state.str.upper().unique())
CLEAN = [s for s in sorted(L[L.change_type == "none found"].state.unique()) if s in aer]
ALL = sorted(P.st.unique())
MOD_T = {"KS": (2013, 2012), "IL": (2016, 2015), "OK": (2019, 2018)}
BAN6 = {"MA": (1985, None), "KS": (1986, 1985), "IN": (1986, 1985), "NC": (1986, 1985), "VT": (1986, 1985), "IL": (1990, 1989)}
DES = {"modern": dict(treat=MOD_T, yrs=(1994, 2024), states=ALL, controls=[s for s in ALL if s not in MOD_T],
                      cov=(), extra=[("IN", 2024)], excl=["IN"], E=(-10, 11)),
       "1980s": dict(treat=BAN6, yrs=(1982, 1995), states=list(BAN6) + CLEAN, controls=CLEAN,
                     cov=("mlda",), extra=[], excl=[], E=(-8, 10))}
OUTS = {"ai_share": "Impaired share of deaths (pp)", "log_odds": "Odds a death involved an impaired driver",
        "ai_per_cap": "Impaired deaths per resident", "ai_per_vmt": "Impaired deaths per mile driven",
        "ddd_net": "Evening vs night (timing test)", "we_net": "Weekday vs weekend evenings (timing test)"}


def est(y, c, events=False):
    d = run(P, y, c["treat"], c["yrs"], c["states"], c["cov"], c["extra"])
    keys = list(c["treat"])
    att = float(np.mean([d[(d.st == k) & d.e.between(0, 5)].gap.mean() for k in keys]))
    Ev = list(range(c["E"][0], c["E"][1] + 1)) if events else None
    act = None
    if events:
        act = pd.DataFrame({k: pd.Series(d[d.st == k].gap.to_numpy(), index=d[d.st == k].e.astype(int).to_numpy()).reindex(Ev)
                            for k in keys}, index=Ev)
    dist, evm = joint_ri(P, y, c["treat"], c["yrs"], c["controls"], make_pools(P, c["treat"], c["controls"], c["yrs"], exclude=c["excl"]),
                         rng, B=5000, covars=c["cov"], extra_drop=c["extra"], E=Ev,
                         avail=None if not events else {k: act[k].notna().to_numpy() for k in keys})
    dist = dist[~np.isnan(dist)]
    return att, dist, (dict(E=Ev, pooled=act.mean(axis=1).to_numpy(), lo=np.nanquantile(evm, 0.025, axis=0),
                            hi=np.nanquantile(evm, 0.975, axis=0)) if events else None)


def summ(att, dist):
    n = len(dist)
    q = np.quantile(dist, [0.025, 0.05, 0.95, 0.975])
    return dict(att=100 * att, ci95_lo=100 * (att - q[3]), ci95_hi=100 * (att - q[0]), ci90_lo=100 * (att - q[2]),
                ci90_hi=100 * (att - q[1]), p=min(1.0, 2 * min((1 + np.sum(dist >= att)) / (1 + n), (1 + np.sum(dist <= att)) / (1 + n))))


rows, ES, DD = [], {}, {}
for g, c in DES.items():
    for y in OUTS:
        att, dist, es = est(y, c, events=y in ("ai_share", "log_odds"))
        DD[(g, y)] = (att, dist)
        if es:
            ES[(g, y)] = es
        rows.append(dict(design=g, outcome=y, label=OUTS[y], **summ(att, dist)))
    print("done", g, flush=True)
for y in ["log_odds", "ai_per_cap", "ai_per_vmt", "ai_share"]:          # all nine law changes that began or ended a ban
    (am, dm), (ab, db) = DD[("modern", y)], DD[("1980s", y)]
    n = min(len(dm), len(db))
    wm = 3 / 9
    rows.append(dict(design="pooled9", outcome=y, label=OUTS[y],
                     **summ(wm * (-am) + (1 - wm) * ab, wm * (-dm[:n]) + (1 - wm) * db[:n])))
R = pd.DataFrame(rows)
R.round(4).to_csv(f"{OUT}/final_results.csv", index=False)

# ---------------------------------------------------------------- poster figures
pct = lambda x: 100 * (np.exp(np.asarray(x) / 100) - 1)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 15, "axes.spines.top": False, "axes.spines.right": False})
INK, ACC, MUT = "#1d2a3a", "#c2410c", "#9aa5b1"

# 1. effect of having a ban, in percent, three rate measures x three samples (repeals sign-flipped)
fig, ax = plt.subplots(figsize=(12, 6.2))
groups = [("modern", "3 repeals (KS 2012, IL 2015, OK 2018)", -1), ("1980s", "6 adoptions (MA, KS, IN, NC, VT, IL, 1984-89)", 1),
          ("pooled9", "All 9 law changes", 1)]
meas = [("log_odds", "Odds a death involved\nan impaired driver"), ("ai_per_cap", "Impaired deaths\nper resident"),
        ("ai_per_vmt", "Impaired deaths\nper mile driven")]
cols = [MUT, "#5b7083", ACC]
y0 = 0
yt, yl = [], []
for mi, (m, mlab) in enumerate(meas):
    for gi, (g, glab, sgn) in enumerate(groups):
        r = R[(R.design == g) & (R.outcome == m)].iloc[0]
        a, lo, hi = sgn * r.att, (sgn * r.ci95_lo if sgn > 0 else -r.ci95_hi), (sgn * r.ci95_hi if sgn > 0 else -r.ci95_lo)
        yy = y0 - gi * 0.8
        ax.plot(pct([lo, hi]), [yy, yy], color=cols[gi], lw=5 if g == "pooled9" else 3.2, solid_capstyle="round")
        ax.plot(pct(a), yy, "o", color=cols[gi], ms=13 if g == "pooled9" else 10, mec="white", mew=1.5,
                label=glab if mi == 0 else None)
    yt.append(y0 - 0.8)
    yl.append(mlab)
    y0 -= 3.2
ax.axvline(0, color=INK, lw=1.2)
ax.set_yticks(yt)
ax.set_yticklabels(yl, fontsize=15)
ax.set_xlabel("Effect of HAVING a happy hour ban (%), with 95% interval", fontsize=15)
ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:+.0f}%"))
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3, frameon=False, fontsize=12.5)
ax.grid(axis="x", color="#e5e7eb")
fig.tight_layout()
fig.savefig(f"{FIGURES}/poster_effects.png", dpi=220, bbox_inches="tight")
plt.close(fig)

# 2. event studies: impaired share, both experiments
fig, axes = plt.subplots(1, 2, figsize=(14, 5.2), sharey=True)
for ax, (g, title) in zip(axes, [("modern", "Repeals: lifting a ban"), ("1980s", "1980s: imposing a ban")]):
    es = ES[(g, "ai_share")]
    E = np.array(es["E"])
    ax.fill_between(E, 100 * es["lo"], 100 * es["hi"], color="#e5e7eb", lw=0, label="95% range for placebo states")
    ax.plot(E, 100 * es["pooled"], color=ACC, lw=3, marker="o", ms=6, label="Treated states: actual minus counterfactual")
    ax.axhline(0, color=INK, lw=1)
    ax.axvline(-0.5, color=INK, ls="--", lw=1)
    ax.set_title(title, fontsize=17, loc="left", color=INK, fontweight="bold")
    ax.set_xlabel("Years since the law changed"); ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
axes[0].set_ylabel("Impaired share of traffic deaths (points)")
axes[0].legend(fontsize=11.5, loc="lower left", frameon=False)
fig.tight_layout()
fig.savefig(f"{FIGURES}/poster_event_studies.png", dpi=220, bbox_inches="tight")
plt.close(fig)

# 3. timeline of the law changes used
ev = [(1984.95, "MA", "ban"), (1985.5, "KS", "ban"), (1985.5, "IN", "ban"), (1985.58, "NC", "ban"), (1985.9, "VT", "ban"),
      (1989.5, "IL", "ban"), (2012.5, "KS", "repeal"), (2015.54, "IL", "repeal"), (2018.75, "OK", "repeal"), (2024.5, "IN", "later")]
fig, ax = plt.subplots(figsize=(14, 2.6))
ax.axhline(0, color=MUT, lw=2)
lev = {}
for x, s, k in ev:
    b = round(x)
    lev[b] = lev.get(b, 0) + 1
    h = 0.5 * lev[b] * (1 if k == "ban" else -1)
    c = INK if k == "ban" else (ACC if k == "repeal" else MUT)
    ax.plot([x, x], [0, h], color=c, lw=1.5)
    ax.plot(x, 0, "o", color=c, ms=8)
    ax.text(x, h + (0.12 if h > 0 else -0.12), s, ha="center", va="bottom" if h > 0 else "top", fontsize=13, color=c, fontweight="bold")
ax.text(1983.2, 1.6, "Bans adopted", color=INK, fontsize=13)
ax.text(2009.3, -1.75, "Bans lifted", color=ACC, fontsize=13)
ax.text(2021.2, -1.75, "Indiana 2024:\nno data yet", color=MUT, fontsize=11)
ax.set_xlim(1981, 2026)
ax.set_ylim(-2.2, 2.2)
ax.set_yticks([])
for s in ["left", "top", "right"]:
    ax.spines[s].set_visible(False)
fig.tight_layout()
fig.savefig(f"{FIGURES}/poster_timeline.png", dpi=220, bbox_inches="tight")
plt.close(fig)

json.dump(dict(rows=json.loads(R.to_json(orient="records")), n_clean=len(CLEAN)), open(f"{OUT}/final_results.json", "w"), indent=1)
pd.set_option("display.width", 220)
print(R[["design", "outcome", "att", "ci95_lo", "ci95_hi", "ci90_lo", "ci90_hi", "p"]].round(2).to_string(index=False))

# ---------------------------------------------------------------- poster figures sized for a Letter-landscape layout (SVG)
json.dump({f"{g}|{y}": {"E": list(map(int, v["E"])), "pooled": [None if np.isnan(x) else float(x) for x in v["pooled"]],
                         "lo": [None if np.isnan(x) else float(x) for x in v["lo"]], "hi": [None if np.isnan(x) else float(x) for x in v["hi"]]}
           for (g, y), v in ES.items()}, open(f"{OUT}/final_event_studies.json", "w"))
GREEN, ASPH, SLATE, LIGHT, BAND = "#0B5E3C", "#22272B", "#4A5560", "#9AA3A8", "#DCE1DD"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "svg.fonttype": "path", "axes.edgecolor": ASPH,
                     "axes.labelcolor": ASPH, "xtick.color": ASPH, "ytick.color": ASPH, "axes.linewidth": 0.8})
fig, ax = plt.subplots(figsize=(3.73, 2.75))
ax.set_facecolor("none")
meas = [("log_odds", "Odds a death involved an impaired driver"), ("ai_per_cap", "Impaired deaths per resident"),
        ("ai_per_vmt", "Impaired deaths per mile driven")]
grp = [("modern", "3 repeals, sign-flipped", -1, LIGHT, 1.6, 4), ("1980s", "6 bans, 1984-89", 1, SLATE, 1.6, 4),
       ("pooled9", "All 9 law changes", 1, GREEN, 3.0, 6)]
y = 0.0
for m, mlab in meas:
    ax.text(-27, y + 0.4, mlab, fontsize=9, color=ASPH, va="bottom", ha="left", fontweight="bold")
    for g, glab, sg, c, lw, ms in grp:
        r = R[(R.design == g) & (R.outcome == m)].iloc[0]
        lo, hi = sorted([sg * r.ci95_lo, sg * r.ci95_hi])
        ax.plot(pct([lo, hi]), [y, y], color=c, lw=lw, solid_capstyle="butt")
        ax.plot(pct(sg * r.att), y, "o", color=c, ms=ms, mec="white", mew=0.8, label=glab if m == "log_odds" else None)
        y -= 0.42
    y -= 0.95
ax.axvline(0, color=ASPH, lw=0.9)
ax.set_xlim(-27, 30)
ax.set_yticks([])
ax.spines[["left", "top", "right"]].set_visible(False)
ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:+.0f}%" if v else "0"))
ax.set_xlabel("Effect of having a ban, with 95% interval", fontsize=9)
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=3, frameon=False, fontsize=8.6, handlelength=1.2, columnspacing=0.9)
fig.savefig(f"{FIGURES}/poster_effects.svg", bbox_inches="tight", transparent=True)
fig.savefig(str(TMP_DIR / "poster_effects_preview.png"), bbox_inches="tight", dpi=250, facecolor="#F3F4F1")
plt.close(fig)
fig, axes = plt.subplots(1, 2, figsize=(3.73, 1.78), sharey=True)
for ax, (g, t) in zip(axes, [("modern", "Lifting (3 states)"), ("1980s", "Imposing (6 states)")]):
    ax.set_facecolor("none")
    es = ES[(g, "ai_share")]
    E = np.array(es["E"])
    ax.fill_between(E, 100 * es["lo"], 100 * es["hi"], color=BAND, lw=0)
    ax.plot(E, 100 * es["pooled"], color=GREEN, lw=1.6, marker="o", ms=2.6)
    ax.axhline(0, color=ASPH, lw=0.8)
    ax.axvline(-0.5, color=ASPH, ls=(0, (3, 2)), lw=0.8)
    ax.set_title(t, fontsize=9, loc="left", color=ASPH, fontweight="bold")
    ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True, nbins=5))
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=8.5)
axes[0].set_ylabel("Impaired share (points)", fontsize=9)
fig.text(0.55, -0.02, "Years since the law changed", ha="center", fontsize=9, color=ASPH)
fig.tight_layout(w_pad=0.8)
fig.savefig(f"{FIGURES}/poster_event_studies.svg", bbox_inches="tight", transparent=True)
fig.savefig(str(TMP_DIR / "poster_event_studies_preview.png"), bbox_inches="tight", dpi=250, facecolor="#F3F4F1")
plt.close(fig)
