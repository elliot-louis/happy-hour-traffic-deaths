"""
sdid.py -- synthetic difference-in-differences (Arkhangelsky et al., 2021) for one treated state.
"""
import numpy as np
import pandas as pd
from scipy.optimize import nnls

# ---------------------------------------------------------------- C. synthetic difference-in-differences
def sdid(w, unit, pool, T, F):
    yr = w.index.to_numpy()
    pre, post = yr < T, yr >= F
    Y0, y1 = w[pool].to_numpy(), w[unit].to_numpy()
    Y0pre, Y0post, y1pre, y1post = Y0[pre], Y0[post], y1[pre], y1[post]
    T0, T1, N0 = Y0pre.shape[0], Y0post.shape[0], Y0pre.shape[1]
    sigma = np.std(np.diff(Y0pre, axis=0), ddof=1)
    zeta = T1 ** 0.25 * sigma                                     # (N_treated x T_post)^(1/4) x sigma
    M = 1e4
    A = Y0pre - Y0pre.mean(axis=0)                                # unit weights (intercept absorbed)
    b = y1pre - y1pre.mean()
    omega, _ = nnls(np.vstack([A, np.sqrt(zeta ** 2 * T0) * np.eye(N0), M * np.ones((1, N0))]),
                    np.concatenate([b, np.zeros(N0), [M]]))
    C = Y0pre.T - Y0pre.T.mean(axis=0)                            # time weights
    d = Y0post.mean(axis=0) - Y0post.mean()
    zl = 1e-6 * sigma
    lam, _ = nnls(np.vstack([C, np.sqrt(zl ** 2 * N0) * np.eye(T0), M * np.ones((1, T0))]),
                  np.concatenate([d, np.zeros(T0), [M]]))
    return float((y1post.mean() - lam @ y1pre) - omega @ (Y0post.mean(axis=0) - lam @ Y0pre))


# ---------------------------------------------------------------- end of sdid
