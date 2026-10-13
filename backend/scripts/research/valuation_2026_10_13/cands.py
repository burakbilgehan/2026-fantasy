"""Candidate static models as numpy functions of the per-category z matrix (throwaway)."""
import numpy as np
from statistics import NormalDist
from vdata import *
from app.analytics.valuation.core import CATEGORIES, PERCENT, basis_stats

PAPER_G = np.array([0.56, 0.58, 0.72, 0.65, 0.69, 0.75, 0.44, 0.68, 0.62])  # fg ft tpm pts reb ast stl blk tov


def raw_cats(rows, basis='totals', skew=None):
    stats = {p: basis_stats(r, basis) for p, r in rows.items() if r['gp'] > 0}
    rate = {c: sum(s[m] for s in stats.values()) / (sum(s[a] for s in stats.values()) or 1) for c, (m, a) in PERCENT.items()}
    players, R = [], []
    for p, s in stats.items():
        v = []
        for c in CATEGORIES:
            if c in PERCENT:
                m, a = PERCENT[c]; x = s[m] - rate[c] * s[a]
            elif c == 'tov':
                x = -s['tov']
            else:
                x = s[c]
            if skew and c in skew:
                x = skew[c](x)
            v.append(x)
        players.append(p); R.append(v)
    return players, np.array(R)


def zmat(rows, basis='totals', pool=200, skew=None, kind='z'):
    """players, Z (P, 9). Pool: top N by the plain z sum, refined 3 rounds (as the project does)."""
    players, R = raw_cats(rows, basis, skew)
    n = len(players)
    if kind == 'pct':
        ranks = R.argsort(0).argsort(0) + 0.5
        nd = NormalDist()
        return players, np.vectorize(nd.inv_cdf)(ranks / n)
    idx = np.arange(n)
    for _ in range(3):
        X = R[idx]
        if kind == 'robust':
            m = np.median(X, 0); s = np.median(np.abs(X - m), 0) * 1.4826
        else:
            m, s = X.mean(0), X.std(0)
        Z = (R - m) / np.where(s > 0, s, 1)
        if pool is None or pool >= n:
            break
        idx = np.argsort(-Z.sum(1))[:pool]
    return players, Z


def fpts(rows, basis='totals'):
    out = {}
    for p, r in rows.items():
        if r['gp'] <= 0: continue
        s = basis_stats(r, basis)
        out[p] = s['pts'] + 1.2 * s['reb'] + 1.5 * s['ast'] + 3 * s['stl'] + 3 * s['blk'] - s['tov']
    return out


SQRT = {'blk': np.sqrt, 'stl': np.sqrt}


def tanh_s(Z, s):
    return (np.tanh(Z / s) * s).sum(1)


def minus1(Z):
    return Z.sum(1) - Z.min(1)


def minus2(Z):
    S = np.sort(Z, 1)
    return Z.sum(1) - S[:, 0] - S[:, 1]


def candidates(rows, basis='totals', pool=200):
    """name -> {player: value}. All on one basis."""
    P, Z = zmat(rows, basis, pool)
    _, Zs = zmat(rows, basis, pool, skew=SQRT)
    _, Zr = zmat(rows, basis, pool, kind='robust')
    _, Zp = zmat(rows, basis, pool, kind='pct')
    Z8, Zs8 = Z[:, :8], Zs[:, :8]
    out = {
        'z9': Z.sum(1),
        'minus1': minus1(Z),
        'minus2': minus2(Z),
        'durant_approx (8cat minus1)': minus1(Z8),
        'gscore (paper w)': (Z * PAPER_G).sum(1),
        'g minus1': minus1(Z * PAPER_G),
        'punt FT': Z.sum(1) - Z[:, 1],
        'punt TO': Z8.sum(1),
        'robust z9 (median/MAD)': Zr.sum(1),
        'pct z9 (normal scores)': Zp.sum(1),
        'tanh z9 s=1.5': tanh_s(Z, 1.5),
        'tanh z9 s=2.5': tanh_s(Z, 2.5),
        'tanh z8 s=2 (no TO)': tanh_s(Z8, 2.0),
        'tanh z9 s=2 minus1': tanh_s(Z, 2.0) - np.tanh(Z / 2.0).min(1) * 2.0,
        'sqrt-skew z9': Zs.sum(1),
        'sqrt-skew z8 (no TO)': Zs8.sum(1),
        'sqrt-skew z8 minus1': minus1(Zs8),
        'sqrt-skew tanh z8 s=2': tanh_s(Zs8, 2.0),
        'sqrt-skew tanh z8 s=2 minus1': tanh_s(Zs8, 2.0) - np.tanh(Zs8 / 2.0).min(1) * 2.0,
    }
    res = {k: dict(zip(P, v)) for k, v in out.items()}
    res['fantasy pts (yahoo)'] = fpts(rows, basis)
    return res
