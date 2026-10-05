"""
estimator.py -- imputation difference-in-differences (Borusyak, Jaravel & Spiess, 2024) shared by every
analysis script. Fixed effects are fit on untreated state-years only, each treated state's untreated outcome
is imputed, and actual minus imputed outcomes are averaged over event years H. Inference comes from the joint
randomization test in ri.py. Call configure() to set the number of draws and the random seed.
"""
import numpy as np
import pandas as pd

B = 5000          # randomization-inference draws
H = (0, 5)        # event years averaged into the ATT
rng = np.random.default_rng(0)


def configure(B=5000, seed=0):
    """Set the draw count and seed used by analyze()."""
    globals()["B"] = B
    globals()["rng"] = np.random.default_rng(seed)


# ------------------------------------------------------------------ 2. estimator
def fe_predict(d, y, covars=(), trends=False):
    """Fit y on state FE + year FE (+ covariates, + state linear trends) using untreated rows only and
    return predictions for every row, i.e. the imputed untreated outcome."""
    fit = d[d.untreated & d[y].notna()]
    for c in covars:
        fit = fit[fit[c].notna()]
    states, years = sorted(d.st.unique()), sorted(d.year.unique())
    si, ti = {s: i for i, s in enumerate(states)}, {t: i for i, t in enumerate(years)}
    ns, nt, nc = len(states), len(years), len(covars)

    def X(df):
        M = np.zeros((len(df), ns + nt - 1 + nc + (ns if trends else 0)))
        r, s, t = np.arange(len(df)), df.st.map(si).to_numpy(), df.year.map(ti).to_numpy()
        M[r, s] = 1.0
        M[r[t > 0], ns + t[t > 0] - 1] = 1.0
        for k, c in enumerate(covars):
            M[:, ns + nt - 1 + k] = df[c].to_numpy()
        if trends:
            M[r, ns + nt - 1 + nc + s] = (df.year.to_numpy() - 2000) / 10.0
        return M

    beta = np.linalg.lstsq(X(fit), fit[y].to_numpy(), rcond=None)[0]
    return X(d) @ beta


def run(panel, y, treat, yrs, states, covars=(), extra_drop=(), trends=False):
    """treat = {state: (first full treated year F, mid-year transition year T or None)}"""
    d = panel[panel.st.isin(states) & panel.year.between(*yrs)].copy()
    for s, (F, T) in treat.items():
        if T is not None:
            d = d[~((d.st == s) & (d.year == T))]
    for s, yr in extra_drop:
        d = d[~((d.st == s) & (d.year == yr))]
    d["e"] = d.year - d.st.map({s: F for s, (F, T) in treat.items()})
    d["untreated"] = ~(d.st.isin(list(treat)) & (d.e >= 0))
    d["gap"] = d[y] - fe_predict(d, y, covars, trends)
    return d


def pre_size(panel, entry, y0):
    F, T = entry
    return panel[panel.year.between(y0, (T if T is not None else F) - 1)].groupby("st").fat.mean()


def make_pools(panel, treat, controls, yrs, exclude=(), lo=0.5, hi=2.0, min_n=8):
    pools = {}
    for k, entry in treat.items():
        sz = pre_size(panel, entry, yrs[0])
        cand = [c for c in controls if c not in exclude and c in sz.index]
        r = sz[cand] / sz[k]
        P = list(r[(r >= lo) & (r <= hi)].index)
        if len(P) < min_n:
            P = list(np.log(r).abs().sort_values().index[:min_n])
        pools[k] = P
    return pools




def event_bands(d, plac, keys, sets, E):
    E = list(range(E[0], E[1] + 1))
    act = pd.DataFrame({k: pd.Series(d[d.st == k].gap.to_numpy(), index=d[d.st == k].e.astype(int).to_numpy())
                        .reindex(E) for k in keys}, index=E)
    mats = []
    for i, k in enumerate(keys):
        cs = [row[i] for row in sets]
        G = pd.DataFrame({c: plac[(k, c)].reindex(E) for c in set(cs)}).T.reindex(columns=E)
        M = np.array(G.loc[cs].to_numpy(dtype=float), copy=True)
        M[:, act[k].isna().to_numpy()] = np.nan
        mats.append(M)
    S = np.nanmean(np.stack(mats), axis=0)
    return dict(E=E, act=act, pooled=act.mean(axis=1),
                lo=np.nanquantile(S, 0.025, axis=0), hi=np.nanquantile(S, 0.975, axis=0))


from ri import joint_ri


def analyze(panel, y, treat, yrs, states, controls, covars=(), extra_drop=(), trends=False,
            pool_excl=(), horizon=H, E=(-10, 11), weighting="equal"):
    d = run(panel, y, treat, yrs, states, covars, extra_drop, trends)
    keys = list(treat)
    actual = {k: d[(d.st == k) & d.e.between(*horizon)].gap.mean() for k in keys}
    baseline = np.nanmean([d[(d.st == k) & d.e.between(-4, -1)][y].mean() for k in keys])
    pools = make_pools(panel, treat, controls, yrs, exclude=pool_excl)
    pa = {}                                  # single-state placebo fits: per-state p-values
    for k, entry in treat.items():
        for c in pools[k]:
            dp = run(panel, y, {c: entry}, yrs, controls, covars, extra_drop, trends)
            g = dp[dp.st == c]
            pa[(k, c)] = g[g.e.between(*horizon)].gap.mean()
    w = np.ones(len(keys)) if weighting == "equal" else np.array([pre_size(panel, treat[k], yrs[0])[k] for k in keys])
    w = w / w.sum()
    att = float(np.dot(w, [actual[k] for k in keys]))
    Ev = list(range(E[0], E[1] + 1))
    act = pd.DataFrame({k: pd.Series(d[d.st == k].gap.to_numpy(), index=d[d.st == k].e.astype(int).to_numpy())
                        .reindex(Ev) for k in keys}, index=Ev)
    dist, evm = joint_ri(panel, y, treat, yrs, controls, pools, rng, B=B, covars=covars, extra_drop=extra_drop,
                         trends=trends, horizon=horizon, weights=dict(zip(keys, w)), E=Ev,
                         avail={k: act[k].notna().to_numpy() for k in keys})
    dist = dist[~np.isnan(dist)]
    n = len(dist)
    q_lo, q_hi = np.quantile(dist, [0.025, 0.975])
    p_eq = min(1.0, 2 * min((1 + np.sum(dist >= att)) / (1 + n), (1 + np.sum(dist <= att)) / (1 + n)))
    summary = dict(att=att, ci_lo=att - q_hi, ci_hi=att - q_lo, p=p_eq, placebo_mean=dist.mean(),
                   placebo_sd=dist.std(), mde80=2.8 * dist.std(), baseline=baseline,
                   n_treated=len(keys), n_controls=len(controls))
    by_state = {}
    for k in keys:
        pv = np.array([pa[(k, c)] for c in pools[k]])
        pv = pv[~np.isnan(pv)]
        a, m = actual[k], len(pv)
        by_state[k] = dict(att=a, p=min(1.0, 2 * min((1 + np.sum(pv >= a)) / (1 + m), (1 + np.sum(pv <= a)) / (1 + m))), pool=m)
    es = dict(E=Ev, act=act, pooled=act.mean(axis=1),
              lo=np.nanquantile(evm, 0.025, axis=0), hi=np.nanquantile(evm, 0.975, axis=0))
    return dict(summary=summary, by_state=by_state, es=es)


def cfg_with(cfg, **kw):
    c = dict(cfg)
    c.update(kw)
    return c


# ------------------------------------------------------------------ end of estimator
