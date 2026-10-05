#!/usr/bin/env python3
"""
audit.py -- correctness and consistency checks for the happy hour project.

Usage: python3 audit.py data estimators size repro report
Each check is appended to audit_log.csv (area, check, result, status); audit_log.md summarizes them.
  PASS = checks out, FLAG = worth knowing but not an error, FAIL = something is wrong.
"""
from paths import RESULTS, FIGURES, INPUTS, JSON, RAW as RAW_DIR, AGG as AGG_DIR, TMP as TMP_DIR, CODE  # noqa: E402
import os, re, sys, json, glob, shutil, subprocess, importlib.util, warnings
import numpy as np
import pandas as pd
from scipy.optimize import minimize, nnls

warnings.filterwarnings("ignore")
OUT = str(RESULTS)
AGG = str(AGG_DIR)
LOG = f"{OUT}/audit_log.csv"
FIPS = {1: "AL", 2: "AK", 4: "AZ", 5: "AR", 6: "CA", 8: "CO", 9: "CT", 10: "DE", 11: "DC", 12: "FL", 13: "GA",
        15: "HI", 16: "ID", 17: "IL", 18: "IN", 19: "IA", 20: "KS", 21: "KY", 22: "LA", 23: "ME", 24: "MD",
        25: "MA", 26: "MI", 27: "MN", 28: "MS", 29: "MO", 30: "MT", 31: "NE", 32: "NV", 33: "NH", 34: "NJ",
        35: "NM", 36: "NY", 37: "NC", 38: "ND", 39: "OH", 40: "OK", 41: "OR", 42: "PA", 44: "RI", 45: "SC",
        46: "SD", 47: "TN", 48: "TX", 49: "UT", 50: "VT", 51: "VA", 53: "WA", 54: "WV", 55: "WI", 56: "WY"}
MOD_TREAT = {"KS": (2013, 2012), "IL": (2016, 2015), "OK": (2019, 2018)}
from designs import AD_TREAT, AD_STATES as VERIFIED_STATES  # noqa: E402
EXCL80 = ["NE", "NJ", "MI", "OH", "TX", "DE", "ME", "WA", "OK", "UT"]
rows = []


def log(area, check, result, status):
    rows.append(dict(area=area, check=check, result=result, status=status))
    print(f"[{status}] {area} | {check} | {result}", flush=True)


def ok(cond):
    return "PASS" if cond else "FAIL"


def load(path, start, end, **extra):
    """Execute one section of a project script so the audit tests the exact code that produced the results."""
    src = open(path).read()
    ns = dict(np=np, pd=pd, nnls=nnls, H=(0, 5), B=5000, rng=np.random.default_rng(7))
    ns.update(extra)
    exec(src[src.index(start):src.index(end)], ns)
    return ns


A_START = "# ------------------------------------------------------------------ 2. estimator"
A_END = "# ------------------------------------------------------------------ end of estimator"


def panel():
    sy = pd.read_csv(f"{OUT}/hh_state_year_panel.csv")
    aer = pd.read_csv(INPUTS / "fatalities.csv")
    ad_states = list(VERIFIED_STATES)
    return sy, ad_states


# ====================================================================== data
def check_data():
    raw = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(f"{AGG}/fars_*.csv"))], ignore_index=True)
    yrs = sorted(raw.year.unique())
    log("data", "FARS years built", f"{yrs[0]}-{yrs[-1]} ({len(yrs)} years)", ok(yrs == list(range(1982, 2025))))
    log("data", "non-state codes dropped from the panel", f"codes {sorted(raw.loc[~raw.state.isin(FIPS), 'state'].unique())}", "PASS")
    r = raw[raw.state.isin(FIPS)]
    n = r.groupby("year").state.nunique()
    log("data", "all 51 jurisdictions present in every year", f"min {n.min()}, max {n.max()}", ok(n.min() == n.max() == 51))
    dups = int(r.duplicated(["year", "state", "dow", "hbin"]).sum())
    log("data", "no duplicate state-year-day-hour cells", f"{dups} duplicates", ok(dups == 0))
    bad = int(((r.ai08 < -1e-9) | (r.ai08 > r.ai01 + 1e-9) | (r.ai01 > r.fat + 1e-9) | (r.svn > r.fat)).sum())
    log("data", "0 <= impaired (.08+) <= any alcohol (.01+) <= deaths, and SVN <= deaths", f"{bad} violating cells", ok(bad == 0))
    nat = r.groupby("year")[["fat", "ai08"]].sum()
    for y, (f, a) in {1982: (43945, 21113), 1985: (43825, 18125), 2019: (36355, 10142)}.items():
        dev = 100 * (nat.ai08[y] / a - 1)
        log("data", f"{y} national totals vs NHTSA published", f"deaths {nat.fat[y]:,.0f} vs {f:,}; impaired {nat.ai08[y]:,.0f} vs {a:,} ({dev:+.1f}%)",
            ok(abs(nat.fat[y] - f) <= 5 and abs(dev) < 2))
    share = 100 * nat.ai08 / nat.fat
    dd = share.diff().abs()
    seams = [1994, 2001, 2004, 2012, 2013, 2016]      # years where the raw-file source or format changes
    ref = dd.drop(seams + [1982]).quantile(0.9)
    log("data", "no jump in national impaired share where the raw-file source changes",
        ", ".join(f"{s}: {dd[s]:.2f}" for s in seams) + f" pp (90th percentile of other years {ref:.2f})", ok(all(dd[s] <= 1.5 * ref for s in seams)))
    tot = r.groupby("year").fat.sum()
    unk = 100 * r[r.hbin == "unk"].groupby("year").fat.sum().reindex(tot.index, fill_value=0) / tot
    log("data", "deaths with unknown crash hour", f"max {unk.max():.2f}% ({unk.idxmax()}), median {unk.median():.2f}%", ok(unk.max() < 3))
    wk = r.dow.between(2, 6)
    for lab, sel, tol in [("weekday 4-10 pm", wk & r.hbin.isin(["16-18", "19-21"]), 1.5), ("10 pm-6 am", r.hbin.isin(["22-23", "00-05"]), 2.0)]:
        sh = 100 * r[sel].groupby("year").fat.sum() / tot
        j = {y: round(abs(sh.diff()[y]), 2) for y in seams}
        log("data", f"share of deaths in the {lab} window is stable where sources change", f"range {sh.min():.1f}-{sh.max():.1f}%; changes at seams {j}", ok(max(j.values()) < tol))
    sy = pd.read_csv(f"{OUT}/hh_state_year_panel.csv")
    log("data", "state-year panel is complete", f"{len(sy)} rows = {sy.st.nunique()} x {sy.year.nunique()}", ok(len(sy) == 51 * 43))
    diff = float((sy.groupby("year")[["fat", "ai08"]].sum() - nat).abs().max().max())
    log("data", "panel totals equal the microdata aggregates", f"max abs diff {diff:.1e}", ok(diff < 1e-6))
    spec = importlib.util.spec_from_file_location("bf", f"{CODE}/build_fars.py")
    bf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bf)
    bf.OUT = str(TMP_DIR / "audit_rebuild")
    os.makedirs(bf.OUT, exist_ok=True)
    os.makedirs(bf.TMP, exist_ok=True)
    for y in [1985, 1999, 2007, 2014, 2020]:          # one year from each raw-file format / code path
        try:
            info = bf.process(y)
        except FileNotFoundError:                      # 2016+ needs NHTSA's CSVs in data/raw (see README)
            log("data", f"rebuilding {y} from raw files reproduces the stored aggregates",
                "skipped: raw NHTSA files for this year are not in data/raw", "SKIP")
            continue
        new, old = pd.read_csv(f"{bf.OUT}/fars_{y}.csv"), pd.read_csv(f"{AGG}/fars_{y}.csv")
        m = old.merge(new, on=["year", "state", "dow", "hbin"], how="outer", suffixes=("_o", "_n"), indicator=True)
        md = max(float((m[f"{c}_o"] - m[f"{c}_n"]).abs().max()) for c in ["fat", "ai08", "ai01", "svn", "crashes"])
        log("data", f"rebuilding {y} from raw files reproduces the stored aggregates",
            f"max abs diff {md:.1e}; cells matched {int((m._merge == 'both').sum())}/{len(m)}; MI records per vehicle "
            f"{info['max_MI_rows_per_vehicle']} after keeping one driver per vehicle (extra records dropped: {info['extra_MI_records_dropped']}); crashes without driver MI {100 * info['crashes_without_driver_MI']:.2f}%",
            ok(md < 1e-6 and (m._merge == "both").all() and info["max_MI_rows_per_vehicle"] == 1))
    V = pd.read_csv(f"{OUT}/fhwa_vm2_state_year.csv")
    vd = json.load(open(str(JSON / "vmt_data.json")))["check"]
    log("data", "FHWA VM-2 complete and consistent with Cohen-Einav mileage",
        f"{V.st.nunique()} jurisdictions x {V.year.nunique()} years, {int(V.vmt.isna().sum())} missing; ratio to Cohen-Einav median "
        f"{vd['median_ratio']:.3f} (5th-95th pct {vd['p05']:.3f}-{vd['p95']:.3f})", ok(V.vmt.notna().all() and abs(vd["median_ratio"] - 1) < 0.01))


# ====================================================================== estimators
def check_estimators():
    sy, ad_states = panel()
    ALL = sorted(sy.st.unique())
    A = load(f"{CODE}/estimator.py", A_START, A_END)
    run, analyze = A["run"], A["analyze"]
    d = run(sy, "ai_share", MOD_TREAT, (1994, 2024), ALL, extra_drop=[("IN", 2024)])
    left = [(s, y) for s, y in [("KS", 2012), ("IL", 2015), ("OK", 2018), ("IN", 2024)] if ((d.st == s) & (d.year == y)).any()]
    first = {s: int(d[(d.st == s) & (d.e == 0)].year.iloc[0]) for s in MOD_TREAT}
    log("estimators", "modern coding: transition years dropped, first full treated years, treated cells",
        f"transition rows left {left}; first treated {first}; treated-post cells {int((~d.untreated).sum())}",
        ok(not left and first == {"KS": 2013, "IL": 2016, "OK": 2019} and (~d.untreated).sum() == 12 + 9 + 6))
    d80 = run(sy, "ai_share", AD_TREAT, (1982, 1995), ad_states, ("mlda",))
    first80 = {s: int(d80[(d80.st == s) & (d80.e == 0)].year.iloc[0]) for s in AD_TREAT}
    left80 = [s for s, (F, T) in AD_TREAT.items() if T and ((d80.st == s) & (d80.year == T)).any()]
    log("estimators", "1980s coding: first treated years, transition years dropped, excluded states absent",
        f"first treated {first80}; transition rows left {left80}; excluded states present {sorted(set(EXCL80) & set(d80.st))}",
        ok(first80 == {k: v[0] for k, v in AD_TREAT.items()} and not left80 and not (set(d80.st) - set(VERIFIED_STATES))))
    mlda_na = int(d80.mlda.isna().sum())
    ma = sy[(sy.st == "MA") & sy.year.between(1983, 1987)].set_index("year").mlda.to_dict()
    log("estimators", "drinking-age covariate complete in the 1980s sample", f"{mlda_na} missing; Massachusetts {ma}", ok(mlda_na == 0))
    main = pd.read_csv(f"{OUT}/results_main.csv")
    for design, y, treat, yrs, states, cov, drop in [
            ("modern_repeals", "ai_share", MOD_TREAT, (1994, 2024), ALL, (), [("IN", 2024)]),
            ("modern_repeals", "ddd_net", MOD_TREAT, (1994, 2024), ALL, (), [("IN", 2024)]),
            ("adoption_1980s", "ai_share", AD_TREAT, (1982, 1995), ad_states, ("mlda",), []),
            ("adoption_1980s", "svn_share", AD_TREAT, (1982, 1995), ad_states, ("mlda",), [])]:
        d = run(sy, y, treat, yrs, states, cov, drop)
        dd = d[d[y].notna()].reset_index(drop=True)
        post = dd[~dd.untreated]
        D = np.zeros((len(dd), len(post)))
        D[post.index.to_numpy(), np.arange(len(post))] = 1.0
        parts = [pd.get_dummies(dd.st, dtype=float).to_numpy(), pd.get_dummies(dd.year, dtype=float).to_numpy()[:, 1:]]
        if cov:
            parts.append(dd[list(cov)].to_numpy())
        coef = np.linalg.lstsq(np.hstack(parts + [D]), dd[y].to_numpy(), rcond=None)[0][-len(post):]
        e, s = post.e.to_numpy(), post.st.to_numpy()
        att = 100 * np.mean([coef[(s == k) & (e >= 0) & (e <= 5)].mean() for k in treat])
        rep = main[(main.design == design) & (main.outcome == y)].att.iloc[0]
        log("estimators", f"{design} {y}: independent saturated-TWFE regression reproduces the estimate",
            f"max residual gap {np.abs(coef - post.gap.to_numpy()).max():.1e}; ATT {att:.3f} vs reported {rep:.3f}",
            ok(np.abs(coef - post.gap.to_numpy()).max() < 1e-8 and abs(att - rep) < 0.002))
    rob = pd.read_csv(f"{OUT}/results_robustness.csv")
    both = pd.concat([main, rob])
    incons = both[((both.ci_lo > 0) | (both.ci_hi < 0)) != (both.p < 0.05)]
    log("estimators", "p-values agree with 95% intervals (both inverted from the same placebo distribution)",
        f"{len(incons)} of {len(both)} rows disagree" + (": " + "; ".join(f"{r.design} {r.spec} {r.outcome} p={r.p:.3f} [{r.ci_lo:.2f},{r.ci_hi:.2f}]" for r in incons.itertuples()) if len(incons) else ""),
        "PASS" if len(incons) == 0 else "FLAG")
    off = main[(main.placebo_mean.abs() > 0.5 * main.placebo_sd)]
    log("estimators", "placebo distributions centered near zero (|mean| < 0.5 SD)",
        f"{len(off)} of {len(main)} off-center" + (": " + ", ".join(f"{r.design} {r.outcome} mean {r.placebo_mean:.2f} sd {r.placebo_sd:.2f}" for r in off.itertuples()) if len(off) else ""),
        "PASS" if len(off) == 0 else "FLAG")
    # synthetic control: penalty-row NNLS weights vs an exact constrained optimizer
    ns = load(f"{CODE}/analysis.py", "# ------------------------------------------------------------------ 5. synthetic control",
              "# ------------------------------------------------------------------ 6. tables",
              sy=sy, MOD=dict(controls=[s for s in ALL if s not in MOD_TREAT]), MOD_TREAT=MOD_TREAT)
    donors = ns["donors"]
    w = sy[sy.year.between(1994, 2024)].pivot(index="year", columns="st", values="ai_share").drop(index=[2015])
    pre = w.index < 2015
    Y0, y1 = w[donors].to_numpy()[pre], w["IL"].to_numpy()[pre]
    wn = ns["synth_weights"](y1, Y0)
    res = minimize(lambda v: ((y1 - Y0 @ v) ** 2).sum(), np.ones(len(donors)) / len(donors), method="SLSQP",
                   bounds=[(0, 1)] * len(donors), constraints={"type": "eq", "fun": lambda v: v.sum() - 1},
                   options=dict(ftol=1e-14, maxiter=1000))
    post = w.index >= 2016
    g_n = (w["IL"].to_numpy()[post] - w[donors].to_numpy()[post] @ wn).mean()
    g_s = (w["IL"].to_numpy()[post] - w[donors].to_numpy()[post] @ res.x).mean()
    log("estimators", "synthetic-control weights: nonnegative, sum to 1, match an exact optimizer (Illinois)",
        f"sum {wn.sum():.6f}, min {wn.min():.1e}; pre-fit SSE {((y1 - Y0 @ wn) ** 2).sum():.3e} vs exact {res.fun:.3e}; post gap {100 * g_n:.3f} vs {100 * g_s:.3f} pp",
        ok(abs(wn.sum() - 1) < 1e-5 and wn.min() >= 0 and abs(g_n - g_s) < 0.002))
    # synthetic DiD: recovery on simulated data, and penalty-row NNLS vs exact optimizer
    F = load(f"{CODE}/sdid.py", "# ---------------------------------------------------------------- C. synthetic difference-in-differences", "# ---------------------------------------------------------------- end of sdid")
    sdid = F["sdid"]
    g = np.random.default_rng(3)
    Tn, N0 = 31, 36
    f1, f2 = np.cumsum(g.normal(0, 0.01, Tn)), np.linspace(0, 1, Tn)
    lam = g.uniform(0.5, 1.5, (N0, 2))
    Y = 0.3 + g.normal(0, 0.03, N0)[None, :] + np.outer(f1, lam[:, 0]) + np.outer(f2, lam[:, 1]) * 0.05 + g.normal(0, 0.003, (Tn, N0))
    wt = g.dirichlet(np.ones(N0))
    yt = 0.35 + np.outer(f1, lam[:, 0]) @ wt + (np.outer(f2, lam[:, 1]) * 0.05) @ wt + g.normal(0, 0.003, Tn)
    yt[20:] += 0.02
    sim = pd.DataFrame(np.column_stack([Y, yt]), index=range(1994, 1994 + Tn), columns=[f"c{i}" for i in range(N0)] + ["T"])
    tau = sdid(sim, "T", [f"c{i}" for i in range(N0)], 1994 + 20, 1994 + 20)
    log("estimators", "synthetic DiD recovers a known effect on simulated data", f"true +2.00, estimated {100 * tau:+.2f} (x100)", ok(abs(tau - 0.02) < 0.005))

    def sdid_exact(w, unit, pool, T, Fy):
        yr = w.index.to_numpy()
        pr, po = yr < T, yr >= Fy
        Y0, y1 = w[pool].to_numpy(), w[unit].to_numpy()
        a, b = Y0[pr] - Y0[pr].mean(axis=0), y1[pr] - y1[pr].mean()
        sig = np.std(np.diff(Y0[pr], axis=0), ddof=1)
        z2 = (po.sum() ** 0.25 * sig) ** 2 * pr.sum()
        cons = {"type": "eq", "fun": lambda v: v.sum() - 1}
        om = minimize(lambda v: ((a @ v - b) ** 2).sum() + z2 * (v ** 2).sum(), np.ones(len(pool)) / len(pool), method="SLSQP",
                      bounds=[(0, 1)] * len(pool), constraints=cons, options=dict(ftol=1e-15, maxiter=2000)).x
        C, dd = Y0[pr].T - Y0[pr].T.mean(axis=0), Y0[po].mean(axis=0) - Y0[po].mean()
        la = minimize(lambda v: ((C @ v - dd) ** 2).sum() + (1e-6 * sig) ** 2 * len(pool) * (v ** 2).sum(), np.ones(pr.sum()) / pr.sum(),
                      method="SLSQP", bounds=[(0, 1)] * pr.sum(), constraints=cons, options=dict(ftol=1e-15, maxiter=2000)).x
        return float((y1[po].mean() - la @ y1[pr]) - om @ (Y0[po].mean(axis=0) - la @ Y0[pr]))

    diffs = []
    for k, (Fy, T) in MOD_TREAT.items():
        w = sy[sy.year.between(1994, 2024)].pivot(index="year", columns="st", values="ai_share").drop(index=[T])
        diffs.append((k, 100 * sdid(w, k, donors, T, Fy), 100 * sdid_exact(w, k, donors, T, Fy)))
    log("estimators", "synthetic DiD: penalty-row NNLS solution matches an exact constrained optimizer",
        "; ".join(f"{k} {a:+.3f} vs {b:+.3f}" for k, a, b in diffs), ok(all(abs(a - b) < 0.1 for _, a, b in diffs)))
    # coding sensitivity: Utah (listicles date its ban to 2011; APIS coding treats it as banned throughout)
    MOD = dict(treat=MOD_TREAT, yrs=(1994, 2024), extra_drop=[("IN", 2024)], pool_excl=["IN"], E=(-2, 2))
    noUT = [s for s in ALL if s != "UT"]
    for y in ["ai_share", "log_odds"]:
        r = analyze(sy, y, states=noUT, controls=[s for s in noUT if s not in MOD_TREAT], **MOD)["summary"]
        m = main[(main.design == "modern_repeals") & (main.outcome == y)].iloc[0]
        log("estimators", f"modern {y} without Utah in the comparison group", f"{100 * r['att']:+.2f} (p = {r['p']:.2f}) vs main {m.att:+.2f} (p = {m.p:.2f})", "PASS")
    # hard-coded statements in the report
    US = sy.groupby("year")[["ai08", "fat"]].sum()
    us = 100 * US.ai08 / US.fat
    il = 100 * sy[sy.st == "IL"].set_index("year").eval("ai08 / fat")
    dIL, dUS = il.loc[2016:2019].mean() - il.loc[2012:2014].mean(), us.loc[2016:2019].mean() - us.loc[2012:2014].mean()
    log("report", "claim: Illinois impaired share fell ~1.7 points 2012-14 to 2016-19, same as the nation", f"Illinois {dIL:+.2f}, nation {dUS:+.2f}", ok(abs(dIL + 1.7) < 0.2 and abs(dUS + 1.7) < 0.2))
    j = {s: round(100 * (sy[(sy.st == s) & (sy.year == 2024)].eval("ai08/fat").iloc[0] - sy[(sy.st == s) & (sy.year == 2023)].eval("ai08/fat").iloc[0]), 1) for s in ["KS", "OK"]}
    log("report", "claim: Kansas and Oklahoma impaired shares jump 7-10 points in 2024", f"{j}", ok(6 <= min(j.values()) and max(j.values()) <= 10.5))
    log("report", "claim: with 3 states tested, chance one reaches p <= 0.03 by luck ~9%", f"1 - 0.97^3 = {100 * (1 - 0.97 ** 3):.1f}%", ok(abs(100 * (1 - 0.97 ** 3) - 9) < 0.5))


# ====================================================================== inference size (Monte Carlo)
def check_size():
    """Size and power of the joint randomization test. The simulations themselves run in tests_now.py (300 null
    simulations per design); the audit reports them from that one source so the paper and the log agree."""
    tn = json.load(open(f"{OUT}/tests_now_results.json"))["power"]
    for design, label in [("modern_repeals", "modern design"), ("adoption_1980s", "1980s design")]:
        for r in tn[design]:
            kind = "power at the minimum detectable effect" if r["injected_x100"] else "false-positive rate"
            res = f"{r['sims']} simulations ({r['outcome']}): rejected {100 * r['reject_5pct']:.1f}% at 5% (s.e. {100 * r['mc_se']:.1f}), {100 * r['reject_10pct']:.1f}% at 10%"
            if r["injected_x100"]:
                status = "PASS" if r["reject_5pct"] >= 0.5 else "FLAG"
            else:
                status = "PASS" if r["reject_5pct"] <= 0.075 else "FLAG"
            log("inference", f"randomization test {kind}, {label}", res, status)


def check_repro():
    snap = str(TMP_DIR / "audit_snapshot")
    shutil.rmtree(snap, ignore_errors=True)
    os.makedirs(snap)
    csvs = [f for f in sorted(glob.glob(f"{OUT}/*.csv")) if not os.path.basename(f).startswith("audit_")]
    for f in csvs + [str(JSON / "followup_data.json"), str(JSON / "vmt_data.json")]:
        shutil.copy(f, snap)
    for script in ["analysis.py", "followup.py", "vmt_extension.py"]:
        r = subprocess.run(["python3", script], cwd=str(CODE), capture_output=True, text=True)
        log("reproducibility", f"{script} re-runs cleanly", f"exit code {r.returncode}", ok(r.returncode == 0))
    changed = []
    for f in csvs:
        a, b = pd.read_csv(f"{snap}/{os.path.basename(f)}"), pd.read_csv(f)
        same = a.shape == b.shape and all(
            np.allclose(a[c].fillna(-9e9), b[c].fillna(-9e9), atol=1e-9) if pd.api.types.is_numeric_dtype(a[c])
            else a[c].fillna("").equals(b[c].fillna("")) for c in a.columns)
        if not same:
            changed.append(os.path.basename(f))
    for jf in ["followup_data.json", "vmt_data.json"]:
        if json.load(open(f"{snap}/{jf}")) != json.load(open(str(JSON / jf))):
            changed.append(jf)
    log("reproducibility", "every output table is identical after re-running all three scripts", f"{len(csvs) + 2} files compared; changed: {changed or 'none'}", ok(not changed))


# ====================================================================== report
def check_report():
    doc = str(CODE.parent / "paper" / "happy_hour_report.docx")
    txt = subprocess.run(["pandoc", "-t", "plain", "--wrap=none", doc], capture_output=True, text=True).stdout
    import re as _re
    # JavaScript formatting artifacts; the plain English word "null" (a null result) is allowed
    bad = [w for w in ["NaN", "undefined", "Infinity", "[object"] if w in txt] + \
          _re.findall(r"(?:p = |[\[(,]\s?)null|null(?:%| points| pp|\])", txt)
    log("report", "no formatting artifacts (NaN, undefined, null) in the report text", f"{bad or 'none'}", ok(not bad))
    D = json.load(open(str(JSON / "report_data.json")))
    Fj = json.load(open(str(JSON / "followup_data.json")))
    Vj = json.load(open(str(JSON / "vmt_data.json")))
    rd = lambda f: json.loads(pd.read_csv(f"{OUT}/{f}").to_json(orient="records"))
    pairs = [("main", D["main"], "results_main.csv"), ("robustness", D["rob"], "results_robustness.csv"),
             ("by state", D["bystate"], "results_by_state.csv"), ("synthetic control", D["sc"], "synthetic_control.csv"),
             ("1980s controls", Fj["A"], "followup_1980s_controls.csv"), ("Illinois tests", Fj["B"], "followup_illinois_sc_tests.csv"),
             ("synthetic DiD", Fj["C"], "followup_sdid.csv"), ("per-mile", Vj["rows"], "vmt_results.csv"), ("per-mile SDID", Vj["sdid"], "vmt_sdid.csv")]
    def same(j, c):                     # JSON keeps full precision; the CSVs are rounded to 3 decimals
        if len(j) != len(c):
            return False
        for x, y in zip(j, c):
            for k, v in y.items():
                u = x.get(k)
                if isinstance(v, (int, float)) and isinstance(u, (int, float)):
                    if abs(round(u, 3) - v) > 1e-9:
                        return False
                elif u != v:
                    return False
        return True
    stale = [lab for lab, j, f in pairs if not same(j, rd(f))]
    log("report", "numbers fed to the report equal the current result tables", f"{len(pairs)} tables compared; stale: {stale or 'none'}", ok(not stale))
    tw = pd.read_csv(f"{OUT}/replication_twfe.csv").iloc[0]
    log("report", "TWFE replication in the report matches its table", f"coef {tw.coef:.4f} (SE {tw.se:.4f})", ok(abs(D["twfe"]["coef"] - tw.coef) < 1e-9))
    mm = pd.read_csv(f"{OUT}/results_main.csv").set_index(["design", "outcome"])
    fmt = lambda x: ("\u2212" if x < 0 else "+") + f"{abs(x):.1f}"
    want = ["21,113", "18,125", "10,142", "0.0155", "S.3178", "April 1, 2026", "12 to 15 months", "1.7 points", "roughly 9%",
            f"{fmt(mm.loc[('modern_repeals', 'ai_share'), 'att'])} percentage points", f"p = {mm.loc[('modern_repeals', 'ai_share'), 'p']:.2f}",
            f"{fmt(mm.loc[('adoption_1980s', 'ai_share'), 'att'])} points", f"p = {mm.loc[('adoption_1980s', 'ai_share'), 'p']:.2f}"]
    miss = [w for w in want if w not in txt]
    log("report", "spot-check of key numbers and facts in the report text", f"{len(want) - len(miss)}/{len(want)} found" + (f"; missing {miss}" if miss else ""), ok(not miss))
    figs = sorted(glob.glob(f"{FIGURES}/*.png"))
    newest_data = max(os.path.getmtime(f"{OUT}/{f}") for f in ["results_main.csv", "followup_sdid.csv", "vmt_results.csv"])
    expected = [f"fig{i}_" for i in range(1, 10)]
    missing = [e for e in expected if not any(os.path.basename(f).startswith(e) for f in figs)]
    log("report", "all nine report figures exist", f"{len(figs)} figure files; missing {missing or 'none'}", ok(not missing))


if __name__ == "__main__":
    for part in sys.argv[1:]:
        {"data": check_data, "estimators": check_estimators, "size": check_size, "repro": check_repro, "report": check_report}[part]()
    if rows:
        new = pd.DataFrame(rows)
        if os.path.exists(LOG):          # replace earlier rows for the parts re-run now; keep everything else
            old = pd.read_csv(LOG)
            new = pd.concat([old[~old.area.isin(new.area.unique())], new])
        new.to_csv(LOG, index=False)
    allr = pd.read_csv(LOG)
    with open(f"{OUT}/audit_log.md", "w") as f:
        f.write("# Audit log\n\n")
        for area, g in allr.groupby("area", sort=False):
            f.write(f"## {area}\n\n| Status | Check | Result |\n|---|---|---|\n")
            for r in g.itertuples():
                f.write(f"| {r.status} | {r.check} | {re.sub(r'np\.(?:float|int)64\(([^)]*)\)', r'\1', str(r.result)).replace('|', '/')} |\n")
            f.write("\n")
    print("\nTotals:", allr.status.value_counts().to_dict())
