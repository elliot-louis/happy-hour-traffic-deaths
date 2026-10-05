#!/usr/bin/env python3
"""
tests_now.py -- checks that can be run with the data already in hand.

  power     Monte Carlo with the real event dates given to random never-treated states: false-positive
            rate of the joint randomization test, power at the reported minimum detectable effect (MDE,
            injected into the fake treated states), and bias of the estimator.
  dates     1980s coding sensitivity: move each adopter's date one year earlier or later, one at a time.
  monthly   Month-level data from the 2016-2024 FARS files: an early look at Indiana's July 2024 change
            (six post months) and a monthly-timing check of Oklahoma's October 2018 repeal.
Usage: python3 tests_now.py power_modern power_1980s dates monthly
"""
from paths import RESULTS, FIGURES, INPUTS, JSON, RAW as RAW_DIR, AGG as AGG_DIR, TMP as TMP_DIR, CODE  # noqa: E402
import os, sys, json, importlib.util, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")
OUT = str(RESULTS)
from ri import joint_ri

RES = f"{OUT}/tests_now_results.json"
res = json.load(open(RES)) if os.path.exists(RES) else {}
import estimator  # noqa: E402
estimator.configure(B=5000, seed=2026)
ns = vars(estimator)
run, make_pools, analyze = ns["run"], ns["make_pools"], ns["analyze"]
sy = pd.read_csv(f"{OUT}/hh_state_year_panel.csv")
aer = pd.read_csv(INPUTS / "fatalities.csv")
ALL = sorted(sy.st.unique())
MOD_TREAT = {"KS": (2013, 2012), "IL": (2016, 2015), "OK": (2019, 2018)}
from designs import AD_TREAT, AD_STATES as VERIFIED_STATES  # noqa: E402
EXCL80 = ["NE", "NJ", "MI", "OH", "TX", "DE", "ME", "WA", "OK", "UT"]
AD_STATES = list(VERIFIED_STATES)
AD_CTRL = [s for s in AD_STATES if s not in AD_TREAT]
MAIN = pd.read_csv(f"{OUT}/results_main.csv").set_index(["design", "outcome"])
FIPS = {1: "AL", 2: "AK", 4: "AZ", 5: "AR", 6: "CA", 8: "CO", 9: "CT", 10: "DE", 11: "DC", 12: "FL", 13: "GA",
        15: "HI", 16: "ID", 17: "IL", 18: "IN", 19: "IA", 20: "KS", 21: "KY", 22: "LA", 23: "ME", 24: "MD",
        25: "MA", 26: "MI", 27: "MN", 28: "MS", 29: "MO", 30: "MT", 31: "NE", 32: "NV", 33: "NH", 34: "NJ",
        35: "NM", 36: "NY", 37: "NC", 38: "ND", 39: "OH", 40: "OK", 41: "OR", 42: "PA", 44: "RI", 45: "SC",
        46: "SD", 47: "TN", 48: "TX", 49: "UT", 50: "VT", 51: "VA", 53: "WA", 54: "WV", 55: "WI", 56: "WY"}


def eq_p(stat, dist):
    dist = dist[~np.isnan(dist)]
    n = len(dist)
    return min(1.0, 2 * min((1 + np.sum(dist >= stat)) / (1 + n), (1 + np.sum(dist <= stat)) / (1 + n)))


# ====================================================================== power / size
def mc(design, y, nsim, delta, seed, B=500):
    g = np.random.default_rng(seed)
    if design == "modern_repeals":
        dates, pool0, yrs, cov = list(MOD_TREAT.values()), [s for s in ALL if s not in MOD_TREAT and s != "IN"], (1994, 2024), ()
    else:
        dates, pool0, yrs, cov = list(AD_TREAT.values()), AD_CTRL, (1982, 1995), ("mlda",)
    ps, est = [], []
    for _ in range(nsim):
        fake = list(g.choice(pool0, len(dates), replace=False))
        treat, ctrls = dict(zip(fake, dates)), [s for s in pool0 if s not in fake]
        panel = sy
        if delta:
            panel = sy.copy()
            for s, (F, T) in treat.items():
                m = (panel.st == s) & (panel.year >= F)
                panel.loc[m, y] = panel.loc[m, y] + delta
        d = run(panel, y, treat, yrs, ctrls + fake, cov)
        att = float(np.mean([d[(d.st == k) & d.e.between(0, 5)].gap.mean() for k in treat]))
        dist, _ = joint_ri(panel, y, treat, yrs, ctrls, make_pools(panel, treat, ctrls, yrs), g, B=B, covars=cov)
        ps.append(eq_p(att, dist))
        est.append(att)
    ps, est = np.array(ps), np.array(est)
    r05 = float(np.mean(ps < 0.05))
    return dict(design=design, outcome=y, injected_x100=round(100 * delta, 3), sims=nsim, reject_5pct=r05,
                mc_se=float(np.sqrt(max(r05 * (1 - r05), 1e-9) / nsim)), reject_10pct=float(np.mean(ps < 0.10)),
                mean_estimate_x100=float(100 * est.mean()), sd_estimate_x100=float(100 * est.std()))


def power(design):
    rows = []
    if design == "modern_repeals":
        mde = MAIN.loc[("modern_repeals", "ai_share"), "mde80"] / 100
        plan = [("ai_share", 300, 0.0, 1), ("ai_share", 150, mde, 2), ("ddd_net", 150, 0.0, 3)]
    else:
        mde = MAIN.loc[("adoption_1980s", "ai_share"), "mde80"] / 100
        plan = [("ai_share", 300, 0.0, 4), ("ai_share", 150, mde, 5), ("svn_share", 150, 0.0, 6)]
    for y, n, dlt, seed in plan:
        r = mc(design, y, n, dlt, seed)
        rows.append(r)
        print(r, flush=True)
    res.setdefault("power", {})[design] = rows


# ====================================================================== 1980s date sensitivity
def dates():
    rows = []
    for y in ["ai_share", "svn_share"]:
        base = analyze(sy, y, AD_TREAT, (1982, 1995), AD_STATES, AD_CTRL, covars=("mlda",), E=(-1, 1))["summary"]
        rows.append(dict(outcome=y, state="none", shift=0, att=100 * base["att"], p=base["p"],
                         ci_lo=100 * base["ci_lo"], ci_hi=100 * base["ci_hi"]))
        for s, (F, T) in AD_TREAT.items():
            adopt = T if T is not None else F - 1                   # MA: Dec 1984 counted as a clean 1985 start
            for shift in (-1, 1):
                new = dict(AD_TREAT)
                new[s] = (adopt + shift + 1, adopt + shift)         # new adoption year dropped as a transition year
                r = analyze(sy, y, new, (1982, 1995), AD_STATES, AD_CTRL, covars=("mlda",), E=(-1, 1))["summary"]
                rows.append(dict(outcome=y, state=s, shift=shift, att=100 * r["att"], p=r["p"],
                                 ci_lo=100 * r["ci_lo"], ci_hi=100 * r["ci_hi"]))
        print(y, "done", flush=True)
    D = pd.DataFrame(rows)
    D.round(3).to_csv(f"{OUT}/tests_now_dates.csv", index=False)
    summ = {}
    for y, g in D[D.state != "none"].groupby("outcome"):
        b = D[(D.outcome == y) & (D.state == "none")].iloc[0]
        summ[y] = dict(base_att=b.att, base_p=b.p, min_att=g.att.min(), max_att=g.att.max(), min_p=g.p.min(), max_p=g.p.max(),
                       min_ci_lo=g.ci_lo.min(), max_ci_hi=g.ci_hi.max(),
                       most_sensitive=f"{g.loc[(g.att - b.att).abs().idxmax(), 'state']} {int(g.loc[(g.att - b.att).abs().idxmax(), 'shift']):+d}")
    res["dates"] = summ
    print(json.dumps(summ, indent=1, default=float))


# ====================================================================== monthly: Indiana early look, Oklahoma timing
def monthly():
    cache = f"{OUT}/fars_state_month_2016_2024.csv"
    have_raw = all(any(f.lower() == f"{p}_{y}.csv".lower() for f in os.listdir(RAW_DIR))
                   for p in ("accident", "MIPER") for y in range(2016, 2025)) if os.path.isdir(RAW_DIR) else False
    if not have_raw and os.path.exists(cache):
        # Raw 2016-2024 NHTSA files absent: reuse the month-level aggregates built from them earlier.
        M = pd.read_csv(cache)
        print("monthly: raw 2016-2024 files not found in data/raw; using", cache, flush=True)
    else:
        M = build_monthly()
    _monthly_estimates(M)


def build_monthly():
    spec = importlib.util.spec_from_file_location("bf", f"{CODE}/build_fars.py")
    bf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bf)
    PC = bf.PCOLS
    parts = []
    for year in range(2016, 2025):
        acc, mi = bf.upload("accident", year), bf.upload("MIPER", year)
        mi = mi[["ST_CASE", "VEH_NO", "PER_NO"] + PC].apply(pd.to_numeric, errors="coerce").dropna(subset=["ST_CASE"])
        pos = mi[PC].values.ravel()
        pos = pos[(pos > 0) & ~np.isnan(pos)]
        scale = 1000.0 if np.percentile(pos, 90) > 60 else 100.0
        drv = mi[mi.VEH_NO > 0].sort_values("PER_NO").drop_duplicates(["ST_CASE", "VEH_NO"])
        hi = drv.groupby("ST_CASE")[PC].max() / scale
        hi.index = hi.index.astype("int64")
        for c in ["STATE", "ST_CASE", "FATALS", "MONTH"]:
            acc[c] = pd.to_numeric(acc[c], errors="coerce")
        acc = acc.dropna(subset=["ST_CASE"])
        acc["ST_CASE"] = acc.ST_CASE.astype("int64")
        acc["ai08"] = acc.FATALS * acc.ST_CASE.map((hi >= 0.08).mean(axis=1)).fillna(0.0)
        g = acc.groupby(["STATE", "MONTH"])[["FATALS", "ai08"]].sum().reset_index()
        g.insert(0, "year", year)
        parts.append(g)
    M = pd.concat(parts, ignore_index=True).rename(columns={"FATALS": "fat", "MONTH": "month"})
    M = M[M.STATE.isin(FIPS) & M.month.between(1, 12)].copy()
    M["st"] = M.STATE.map(FIPS)
    chk = M.groupby(["st", "year"])[["fat", "ai08"]].sum().join(sy.set_index(["st", "year"])[["fat", "ai08"]], rsuffix="_annual")
    consistency = dict(max_deaths_diff=float((chk.fat - chk.fat_annual).abs().max()),
                       max_impaired_diff=float((chk.ai08 - chk.ai08_annual).abs().max()))
    M["t"] = (M.year - 2016) * 12 + M.month - 1
    M["ai_share"] = M.ai08 / M.fat
    M[["st", "year", "month", "t", "fat", "ai08", "ai_share"]].round(4).to_csv(f"{OUT}/fars_state_month_2016_2024.csv", index=False)
    return M


def _monthly_estimates(M):
    chk = M.groupby(["st", "year"])[["fat", "ai08"]].sum().join(sy.set_index(["st", "year"])[["fat", "ai08"]], rsuffix="_annual")
    consistency = dict(max_deaths_diff=float((chk.fat - chk.fat_annual).abs().max()),
                       max_impaired_diff=float((chk.ai08 - chk.ai08_annual).abs().max()))
    size = sy[sy.year.between(2016, 2023)].groupby("st").fat.mean()
    big = [s for s in ALL if size[s] >= 300]

    def gaps(unit, start, tr, ctrls, seasonal):
        d = M[M.st.isin(ctrls + [unit]) & M.t.between(*tr) & M.ai_share.notna()].reset_index(drop=True)
        treated = ((d.st == unit) & (d.t >= start)).to_numpy()
        key = (d.st + "_" + d.month.astype(str)) if seasonal else d.st
        X = np.hstack([pd.get_dummies(key, dtype=float).to_numpy(), pd.get_dummies(d.t, dtype=float).to_numpy()[:, 1:]])
        beta = np.linalg.lstsq(X[~treated], d.ai_share.to_numpy()[~treated], rcond=None)[0]
        u = (d.st == unit).to_numpy()
        return pd.Series(d.ai_share.to_numpy()[u] - X[u] @ beta, index=d.t.to_numpy()[u])

    def study(unit, start, post_len, tr, ctrls, seasonal, label):
        g = gaps(unit, start, tr, ctrls, seasonal)
        att = g.loc[start:start + post_len - 1].mean()
        plac = {c: gaps(c, start, tr, [x for x in ctrls if x != c], seasonal) for c in ctrls}
        pv = np.array([s.loc[start:start + post_len - 1].mean() for s in plac.values()])
        q_lo, q_hi = np.quantile(pv, [0.025, 0.975])
        base = M[(M.st == unit) & M.t.between(tr[0], start - 1)]
        return dict(label=label, unit=unit, post_months=post_len, att_pp=100 * att, ci_lo_pp=100 * (att - q_hi),
                    ci_hi_pp=100 * (att - q_lo), p=eq_p(att, pv), mde80_pp=100 * 2.8 * pv.std(), placebos=len(pv),
                    baseline_share_pct=100 * base.ai08.sum() / base.fat.sum(),
                    monthly_deaths=float(base.fat.mean())), g, plac

    t0724, t1018 = (2024 - 2016) * 12 + 6, (2018 - 2016) * 12 + 9
    rows = []
    ctrl_in = [s for s in big if s != "IN"]
    r_in, g_in, plac_in = study("IN", t0724, 6, (36, 107), ctrl_in, True, "Indiana, Jul-Dec 2024 (state x month seasonality)")
    rows.append(r_in)
    rows.append(study("IN", t0724, 6, (36, 107), ctrl_in, False, "Indiana, Jul-Dec 2024 (common seasonality only)")[0])
    fake = []                                            # in-time placebos: pretend Indiana changed each July 2018-2023
    ctrl_t = [s for s in big if s not in ("IN", "OK")]
    for yr in range(2018, 2024):
        st_ = (yr - 2016) * 12 + 6
        fake.append(100 * gaps("IN", st_, (0, t0724 - 1), ctrl_t, True).loc[st_:st_ + 5].mean())
    ctrl_ok = [s for s in big if s not in ("OK", "IN")]
    rows.append(study("OK", t1018, 72, (0, 107), ctrl_ok, False, "Oklahoma, Oct 2018-Sep 2024 (monthly, includes late 2018)")[0])
    rows.append(study("OK", t1018, 72, (0, 107), ctrl_ok, True, "Oklahoma, Oct 2018-Sep 2024 (state x month seasonality)")[0])
    T = pd.DataFrame(rows)
    T.round(3).to_csv(f"{OUT}/tests_now_monthly.csv", index=False)
    res["monthly"] = dict(rows=json.loads(T.to_json(orient="records")), consistency=consistency,
                          indiana_in_time_placebos_pp=[round(x, 2) for x in fake], n_states=len(big))
    # figure: Indiana monthly gaps with the in-space placebo range
    P = pd.DataFrame({c: s for c, s in plac_in.items()})
    fig, ax = plt.subplots(figsize=(11, 4.2))
    x = pd.to_datetime([f"{2016 + t // 12}-{t % 12 + 1:02d}-15" for t in g_in.index])
    ax.fill_between(x, 100 * P.quantile(0.025, axis=1).reindex(g_in.index), 100 * P.quantile(0.975, axis=1).reindex(g_in.index),
                    color="0.86", lw=0, label="95% range, placebo states given the same date")
    ax.plot(x, 100 * g_in.to_numpy(), color="black", lw=1.4, marker="o", ms=2.5, label="Indiana: actual minus imputed")
    ax.axvline(pd.Timestamp("2024-07-01"), color="tab:red", ls="--", lw=1)
    ax.axhline(0, color="0.4", lw=0.8)
    ax.set_ylabel("Alcohol-impaired share of deaths (pp)")
    ax.set_title(f"Early look at Indiana (law effective July 1, 2024): Jul-Dec 2024 average {r_in['att_pp']:+.1f} pp, "
                 f"95% interval {r_in['ci_lo_pp']:+.1f} to {r_in['ci_hi_pp']:+.1f}", fontsize=10)
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(f"{FIGURES}/fig8_indiana_early_look.png", dpi=150)
    plt.close(fig)
    print(json.dumps(res["monthly"], indent=1, default=float))


if __name__ == "__main__":
    for part in sys.argv[1:]:
        {"power_modern": lambda: power("modern_repeals"), "power_1980s": lambda: power("adoption_1980s"),
         "dates": dates, "monthly": monthly}[part]()
        json.dump(res, open(RES, "w"), indent=1, default=float)
