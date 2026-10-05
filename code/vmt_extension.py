#!/usr/bin/env python3
"""
vmt_extension.py -- add FHWA VM-2 vehicle-miles traveled (1980-2024) to both designs.

VM-2 export: Year, State, Area (Rural/Urban), FClass (functional system), VMT (annual miles).
Summed to state-year totals, it gives
  vmt          total vehicle-miles traveled
  rural_share  rural VMT / total VMT
  log_vmt      log of total VMT
New outcomes (x100 = log points, roughly percent changes)
  ai_per_vmt     log(alcohol-impaired deaths per 100 million VMT)
  sober_per_vmt  log(sober deaths per 100 million VMT)   placebo: should not move
  fat_per_vmt    log(all deaths per 100 million VMT)
Same imputation DiD and size-matched randomization inference as analysis.py; synthetic DiD for the
modern repeals as in followup.py. Also checks VM-2 against Cohen & Einav's VMT series (1983-1997).
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
VM2 = str(INPUTS / "fhwa_vm2_export.csv")
AER, SEAT = str(INPUTS / "fatalities.csv"), str(INPUTS / "usseatbelts.csv")
rng = np.random.default_rng(20260926)
B, H = 5000, (0, 5)
NAMES = {"Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA", "Colorado": "CO",
         "Connecticut": "CT", "Delaware": "DE", "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA",
         "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
         "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA",
         "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO", "Montana": "MT",
         "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
         "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
         "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD",
         "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
         "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY"}

# ---------------------------------------------------------------- 1. VM-2 -> state-year
vm = pd.read_csv(VM2)
vm["VMT"] = pd.to_numeric(vm.VMT.astype(str).str.replace(",", "", regex=False), errors="coerce")
vm["st"] = vm.State.str.strip().map(NAMES)
dropped = sorted(vm.loc[vm.st.isna(), "State"].astype(str).unique())
vm = vm.dropna(subset=["st"])
key = ["st", "Year"]
V = pd.DataFrame({"vmt": vm.groupby(key).VMT.sum(min_count=1),
                  "rural_vmt": vm[vm.Area == "Rural"].groupby(key).VMT.sum(min_count=1)}).reset_index()
V = V.rename(columns={"Year": "year"})
nat = V.groupby("year").vmt.sum()
rescaled = {}
for y, v in nat.items():                      # guard against years exported in thousands or millions
    for f in (1e3, 1e6):
        if 1.2e12 <= v * f <= 4.0e12 and not (1.2e12 <= v <= 4.0e12):
            V.loc[V.year == y, ["vmt", "rural_vmt"]] *= f
            rescaled[int(y)] = f
V.loc[~(V.vmt > 0), "vmt"] = np.nan
V["rural_share"] = V.rural_vmt / V.vmt
V["log_vmt"] = np.log(V.vmt)
V = V.sort_values(["st", "year"])
V["dlog"] = V.groupby("st").log_vmt.diff()
jumps = V[V.dlog.abs() > 0.25][["st", "year", "dlog"]].round(3)
coverage = V.groupby("year").vmt.count()
V.drop(columns=["dlog"]).round(6).to_csv(f"{OUT}/fhwa_vm2_state_year.csv", index=False)

# ---------------------------------------------------------------- 2. merge, validate
sy = pd.read_csv(f"{OUT}/hh_state_year_panel.csv")
p = sy.merge(V[["st", "year", "vmt", "rural_share", "log_vmt"]], on=["st", "year"], how="left")
p["ai_per_vmt"] = np.log(p.ai08 / (p.vmt / 1e8))
p["sober_per_vmt"] = np.log(p.sober / (p.vmt / 1e8))
p["fat_per_vmt"] = np.log(p.fat / (p.vmt / 1e8))
p = p.replace([np.inf, -np.inf], np.nan)
u = pd.read_csv(SEAT).rename(columns={"state": "st"})
chk = V.merge(u[["st", "year", "miles"]], on=["st", "year"]).dropna()
chk["ratio"] = chk.vmt / 1e6 / chk.miles
check = dict(n=int(len(chk)), median_ratio=float(chk.ratio.median()), p05=float(chk.ratio.quantile(0.05)),
             p95=float(chk.ratio.quantile(0.95)), corr=float(np.corrcoef(np.log(chk.vmt), np.log(chk.miles))[0, 1]))
u["belt_primary"] = (u.enforce == "primary").astype(float)
u["belt_secondary"] = (u.enforce == "secondary").astype(float)
u["speed65"] = (u.speed65 == "yes").astype(float)
u["bac08"] = (u.alcohol == "yes").astype(float)
u["log_income"] = np.log(u.income)
p = p.merge(u[["st", "year", "belt_primary", "belt_secondary", "speed65", "bac08", "log_income"]], on=["st", "year"], how="left")
p.round(6).to_csv(f"{OUT}/hh_state_year_panel_vmt.csv", index=False)


# ---------------------------------------------------------------- 3. estimator (as in analysis.py)
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


def run(panel, y, treat, yrs, states, covars=(), extra_drop=()):
    d = panel[panel.st.isin(states) & panel.year.between(*yrs)].copy()
    for s, (F, T) in treat.items():
        if T is not None:
            d = d[~((d.st == s) & (d.year == T))]
    for s, yr in extra_drop:
        d = d[~((d.st == s) & (d.year == yr))]
    d["e"] = d.year - d.st.map({s: F for s, (F, T) in treat.items()})
    d["untreated"] = ~(d.st.isin(list(treat)) & (d.e >= 0))
    d["gap"] = d[y] - fe_predict(d, y, covars)
    return d


def pre_size(panel, entry, y0):
    F, T = entry
    return panel[panel.year.between(y0, (T if T is not None else F) - 1)].groupby("st").fat.mean()


def make_pools(panel, treat, controls, yrs, exclude=(), lo=0.5, hi=2.0, min_n=8):
    pools = {}
    for k, entry in treat.items():
        sz = pre_size(panel, entry, yrs[0])
        r = sz[[c for c in controls if c not in exclude and c in sz.index]] / sz[k]
        P = list(r[(r >= lo) & (r <= hi)].index)
        pools[k] = P if len(P) >= min_n else list(np.log(r).abs().sort_values().index[:min_n])
    return pools


def draw_sets(pools, keys):
    """Independent draws for each treated slot (with replacement across slots). Drawing without replacement
    shrinks the placebo variance when several slots share a small pool, which the audit showed over-rejects."""
    return [[pools[k][rng.integers(len(pools[k]))] for k in keys] for _ in range(B)]


def ri_summary(att, dist):
    dist = dist[~np.isnan(dist)]
    n = len(dist)
    q_lo, q_hi = np.quantile(dist, [0.025, 0.975])
    p_ = min(1.0, 2 * min((1 + np.sum(dist >= att)) / (1 + n), (1 + np.sum(dist <= att)) / (1 + n)))
    return dict(att=att, ci_lo=att - q_hi, ci_hi=att - q_lo, p=p_, mde80=2.8 * dist.std())


from ri import joint_ri


def analyze(panel, y, treat, yrs, states, controls, covars=(), extra_drop=(), pool_excl=(), E=(-10, 11)):
    d = run(panel, y, treat, yrs, states, covars, extra_drop)
    keys = list(treat)
    actual = {k: d[(d.st == k) & d.e.between(*H)].gap.mean() for k in keys}
    pools = make_pools(panel, treat, controls, yrs, exclude=pool_excl)
    Ev = list(range(E[0], E[1] + 1))
    act = pd.DataFrame({k: pd.Series(d[d.st == k].gap.to_numpy(), index=d[d.st == k].e.astype(int).to_numpy())
                        .reindex(Ev) for k in keys}, index=Ev)
    dist, evm = joint_ri(panel, y, treat, yrs, controls, pools, rng, B=B, covars=covars, extra_drop=extra_drop,
                         horizon=H, E=Ev, avail={k: act[k].notna().to_numpy() for k in keys})
    res = ri_summary(float(np.mean([actual[k] for k in keys])), dist)
    res["by_state"] = {k: float(actual[k]) for k in keys}
    res["es"] = dict(E=Ev, act=act, pooled=act.mean(axis=1), lo=np.nanquantile(evm, 0.025, axis=0),
                     hi=np.nanquantile(evm, 0.975, axis=0))
    return res


def sdid(w, unit, pool, T, F):
    yr = w.index.to_numpy()
    pre, post = yr < T, yr >= F
    Y0, y1 = w[pool].to_numpy(), w[unit].to_numpy()
    Y0pre, Y0post, y1pre, y1post = Y0[pre], Y0[post], y1[pre], y1[post]
    T0, T1, N0 = Y0pre.shape[0], Y0post.shape[0], Y0pre.shape[1]
    sigma = np.std(np.diff(Y0pre, axis=0), ddof=1)
    zeta, M = T1 ** 0.25 * sigma, 1e4
    A, b = Y0pre - Y0pre.mean(axis=0), y1pre - y1pre.mean()
    omega, _ = nnls(np.vstack([A, np.sqrt(zeta ** 2 * T0) * np.eye(N0), M * np.ones((1, N0))]),
                    np.concatenate([b, np.zeros(N0), [M]]))
    C, dd = Y0pre.T - Y0pre.T.mean(axis=0), Y0post.mean(axis=0) - Y0post.mean()
    lam, _ = nnls(np.vstack([C, np.sqrt((1e-6 * sigma) ** 2 * N0) * np.eye(T0), M * np.ones((1, T0))]),
                  np.concatenate([dd, np.zeros(T0), [M]]))
    return float((y1post.mean() - lam @ y1pre) - omega @ (Y0post.mean(axis=0) - lam @ Y0pre))


# ---------------------------------------------------------------- 4. designs and runs
ALL = sorted(p.st.unique())
MOD_TREAT = {"KS": (2013, 2012), "IL": (2016, 2015), "OK": (2019, 2018)}
MOD = dict(treat=MOD_TREAT, yrs=(1994, 2024), states=ALL, controls=[s for s in ALL if s not in MOD_TREAT],
           extra_drop=[("IN", 2024)], pool_excl=["IN"], E=(-10, 11))
aer = pd.read_csv(AER)
EXCL = ["NE", "NJ", "MI", "OH", "TX", "DE", "ME", "WA", "OK", "UT"]
from designs import AD_TREAT, AD_STATES as VERIFIED_STATES  # noqa: E402
AD_STATES = list(VERIFIED_STATES)
ADO = dict(treat=AD_TREAT, yrs=(1982, 1995), states=AD_STATES, controls=[s for s in AD_STATES if s not in AD_TREAT],
           covars=("mlda",), E=(-8, 10))
TRAFFIC = ("mlda", "belt_primary", "belt_secondary", "speed65", "bac08", "log_income", "rural_share")
LAB = {"ai_per_vmt": "Impaired deaths per mile (log x100)", "sober_per_vmt": "Sober deaths per mile: placebo (log x100)",
       "fat_per_vmt": "All deaths per mile (log x100)", "ai_share": "Impaired share (pp)",
       "log_odds": "Log odds, impaired vs. sober (x100)"}
no_covid = p[~p.year.isin([2020, 2021])]
RUNS = [("modern_repeals", "main", p, MOD, ["ai_per_vmt", "sober_per_vmt", "fat_per_vmt"]),
        ("modern_repeals", "excl. 2020-21", no_covid, MOD, ["ai_per_vmt", "sober_per_vmt"]),
        ("modern_repeals", "+ log VMT, rural share", p, dict(MOD, covars=("log_vmt", "rural_share")),
         ["ai_share", "log_odds", "ai_per_vmt"]),
        ("adoption_1980s", "1982-95, drinking age", p, ADO, ["ai_per_vmt", "sober_per_vmt", "fat_per_vmt"]),
        ("adoption_1980s", "1983-95, traffic-safety controls", p, dict(ADO, yrs=(1983, 1995), covars=TRAFFIC),
         ["ai_per_vmt", "sober_per_vmt", "fat_per_vmt", "ai_share", "log_odds"])]
rows, ES = [], {}
for design, spec, pnl, cfg, outs in RUNS:
    for y in outs:
        r = analyze(pnl, y, **cfg)
        rows.append(dict(design=design, spec=spec, outcome=y, label=LAB[y],
                         **{k: 100 * r[k] for k in ["att", "ci_lo", "ci_hi", "mde80"]}, p=r["p"],
                         **{f"state_{k}": 100 * v for k, v in r["by_state"].items()}))
        ES[(design, spec, y)] = r["es"]
R = pd.DataFrame(rows)
R.round(3).to_csv(f"{OUT}/vmt_results.csv", index=False)

size = p[p.year.between(1994, 2011)].groupby("st").fat.mean()
donors = [s for s in ALL if s not in MOD_TREAT and s != "IN" and size[s] >= 200]
srows = []
for y in ["ai_per_vmt", "sober_per_vmt"]:
    taus, plac = {}, {}
    for k, (F, T) in MOD_TREAT.items():
        w = p[p.year.between(1994, 2024)].pivot(index="year", columns="st", values=y).drop(index=[T])
        taus[k] = sdid(w, k, donors, T, F)
        plac[k] = {d: sdid(w, d, [x for x in donors if x != d], T, F) for d in donors}
        pv = np.array(list(plac[k].values()))
        pr = min(1.0, 2 * min((1 + np.sum(pv >= taus[k])) / (1 + len(pv)), (1 + np.sum(pv <= taus[k])) / (1 + len(pv))))
        srows.append(dict(outcome=y, unit=k, tau=100 * taus[k], ci_lo=100 * (taus[k] - 1.96 * pv.std(ddof=1)),
                          ci_hi=100 * (taus[k] + 1.96 * pv.std(ddof=1)), p=pr))
    keys = list(MOD_TREAT)
    sets = draw_sets({k: donors for k in keys}, keys)
    dist = np.array([np.mean([plac[k][row[i]] for i, k in enumerate(keys)]) for row in sets])
    r = ri_summary(float(np.mean([taus[k] for k in keys])), dist)
    srows.append(dict(outcome=y, unit="Pooled (mean of 3)", tau=100 * r["att"], ci_lo=100 * r["ci_lo"],
                      ci_hi=100 * r["ci_hi"], p=r["p"]))
S = pd.DataFrame(srows)
S.round(3).to_csv(f"{OUT}/vmt_sdid.csv", index=False)

# baseline rates (deaths per 100 million VMT), three years before the change
def base_rate(states_entries):
    num = den = 0.0
    for s, (F, T) in states_entries.items():
        last = (T if T is not None else F) - 1
        g = p[(p.st == s) & p.year.between(last - 2, last)]
        num += g.ai08.sum(); den += g.vmt.sum() / 1e8
    return num / den
rates = dict(modern_treated=base_rate(MOD_TREAT), adoption_treated=base_rate(AD_TREAT))
natr = p.groupby("year")[["ai08", "vmt"]].sum()
rates.update({f"national_{y}": float(natr.loc[y, "ai08"] / (natr.loc[y, "vmt"] / 1e8)) for y in [1982, 1995, 2019, 2024]})

# ---------------------------------------------------------------- 5. figure
fig, axes = plt.subplots(1, 3, figsize=(16, 4.6))
for ax, key, title, indiv in [
        (axes[0], ("modern_repeals", "main", "ai_per_vmt"), "Modern repeals: impaired deaths per mile (log x100)", True),
        (axes[1], ("modern_repeals", "main", "sober_per_vmt"), "Modern repeals: sober deaths per mile, placebo (log x100)", True),
        (axes[2], ("adoption_1980s", "1982-95, drinking age", "ai_per_vmt"), "1980s bans: impaired deaths per mile (log x100)", False)]:
    es = ES[key]
    E = np.array(es["E"])
    ax.fill_between(E, 100 * es["lo"], 100 * es["hi"], color="0.86", lw=0, label="95% placebo range (pooled)")
    for i, k in enumerate(es["act"].columns):
        ax.plot(E, 100 * es["act"][k], color=["tab:blue", "tab:orange", "tab:green"][i] if indiv else "0.6", lw=0.9,
                alpha=0.75, label=k if indiv else ("Individual states" if i == 0 else None))
    ax.plot(E, 100 * es["pooled"], color="black", lw=2, marker="o", ms=3.5, label="Pooled (mean of states)")
    ax.axhline(0, color="0.4", lw=0.8)
    ax.axvline(-0.5, color="0.4", ls="--", lw=0.8)
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("Years relative to first full year under the new law", fontsize=8.5)
    ax.legend(fontsize=7, loc="upper left")
fig.suptitle("Deaths per vehicle-mile (FHWA VM-2): actual minus imputed counterfactual", fontsize=11.5)
fig.tight_layout()
fig.savefig(f"{FIG}/fig7_per_mile_event_study.png", dpi=150)
plt.close(fig)

json.dump(dict(rows=json.loads(R.to_json(orient="records")), sdid=json.loads(S.to_json(orient="records")),
               check=check, rates=rates, dropped=dropped, rescaled=rescaled,
               years=[int(V.year.min()), int(V.year.max())]),
          open(str(JSON / "vmt_data.json"), "w"))

pd.set_option("display.width", 220)
print("Dropped names:", dropped, "| rescaled years:", rescaled, "| years", V.year.min(), "-", V.year.max())
print("States with VMT per year (min/max):", coverage.min(), coverage.max())
print("National VMT (billions):", (V.groupby("year").vmt.sum() / 1e9).loc[[1980, 1982, 1990, 2000, 2010, 2019, 2020, 2024]].round(0).to_dict())
print("Year-to-year |dlog VMT| > 0.25:", jumps.to_dict("records"))
print("Check vs Cohen-Einav:", {k: round(v, 3) for k, v in check.items()})
print("Missing VMT in analysis panel:", int(p.vmt.isna().sum()), "state-years")
print("Baseline impaired deaths per 100M VMT:", {k: round(v, 3) for k, v in rates.items()})
print("\nRESULTS (x100)\n", R[["design", "spec", "outcome", "att", "ci_lo", "ci_hi", "p", "mde80"] +
                            [c for c in R.columns if c.startswith("state_")]].round(2).to_string(index=False))
print("\nSDID (x100)\n", S.round(2).to_string(index=False))
