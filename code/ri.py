"""
ri.py -- joint randomization inference for the imputation difference-in-differences estimator.

Each draw assigns every treated slot (a real state's event dates) to a distinct never-treated state from
that slot's size-matched pool, treats all of those placebo states at once, re-fits the fixed-effects model
on the remaining untreated state-years, and recomputes the pooled ATT. Re-fitting jointly keeps the
estimation error in the year effects, which all treated states share, inside the null distribution. The
audit (audit.py) showed that building the null from separate one-state fits understates it when several
treated states share event dates, as in the 1980s wave.

Speed: the fixed-effects normal equations are formed once; each draw only subtracts the placebo states'
excluded rows (post-treatment and transition years) before solving.
"""
import numpy as np


def joint_ri(panel, y, treat, yrs, controls, pools, rng, B=2000, covars=(), extra_drop=(), trends=False,
             horizon=(0, 5), weights=None, E=None, avail=None):
    """Return (null distribution of the pooled ATT, B x len(E) matrix of pooled placebo event-time gaps)."""
    d = panel[panel.st.isin(controls) & panel.year.between(*yrs)]
    for s, yr_ in extra_drop:
        d = d[~((d.st == s) & (d.year == yr_))]
    d = d[d[y].notna()]
    for c in covars:
        d = d[d[c].notna()]
    states, years = sorted(d.st.unique()), sorted(d.year.unique())
    si, ti = {s: i for i, s in enumerate(states)}, {t: i for i, t in enumerate(years)}
    s_idx, t_idx = d.st.map(si).to_numpy(), d.year.map(ti).to_numpy()
    yr, yv = d.year.to_numpy(), d[y].to_numpy(dtype=float)
    n, ns, nt, nc = len(d), len(states), len(years), len(covars)
    X = np.zeros((n, ns + nt - 1 + nc + (ns if trends else 0)))
    X[np.arange(n), s_idx] = 1.0
    X[np.where(t_idx > 0)[0], ns + t_idx[t_idx > 0] - 1] = 1.0
    for j, c in enumerate(covars):
        X[:, ns + nt - 1 + j] = d[c].to_numpy(dtype=float)
    if trends:
        X[np.arange(n), ns + nt - 1 + nc + s_idx] = (yr - 2000) / 10.0
    XtX, Xty = X.T @ X, X.T @ yv
    ridge = 1e-9 * np.trace(XtX) / len(XtX) * np.eye(len(XtX))   # guards the collinear state-trend case
    rows = {s: np.where(s_idx == si[s])[0] for s in states}
    keys = list(treat)
    w = np.array([1.0 if weights is None else weights[k] for k in keys], dtype=float)
    pos = None if E is None else {e: i for i, e in enumerate(E)}
    dist = np.full(B, np.nan)
    evm = None if E is None else np.full((B, len(E)), np.nan)
    for b in range(B):
        used, excl, picks = set(), [], []
        for k in keys:
            cand = [c for c in pools[k] if c in rows and c not in used] or [c for c in rows if c not in used]
            c = cand[rng.integers(len(cand))]
            used.add(c)
            F, T = treat[k]
            r = rows[c]
            drop = (yr[r] >= F) if T is None else ((yr[r] >= F) | (yr[r] == T))
            excl.append(r[drop])
            picks.append((k, r if T is None else r[yr[r] != T], F))
        ex = np.concatenate(excl)
        Xe = X[ex]
        beta = np.linalg.solve(XtX - Xe.T @ Xe + ridge, Xty - Xe.T @ yv[ex])
        slot = np.full(len(keys), np.nan)
        ev_rows = []
        for i, (k, r, F) in enumerate(picks):
            e = yr[r] - F
            g = yv[r] - X[r] @ beta
            sel = (e >= horizon[0]) & (e <= horizon[1])
            if sel.any():
                slot[i] = g[sel].mean()
            if E is not None:
                v = np.full(len(E), np.nan)
                for ee, gg in zip(e, g):
                    jj = pos.get(int(ee))
                    if jj is not None:
                        v[jj] = gg
                if avail is not None:
                    v[~avail[k]] = np.nan
                ev_rows.append(v)
        ok = ~np.isnan(slot)
        if ok.any():
            dist[b] = np.dot(w[ok], slot[ok]) / w[ok].sum()
        if E is not None:
            evm[b] = np.nanmean(np.vstack(ev_rows), axis=0)
    return dist, evm
