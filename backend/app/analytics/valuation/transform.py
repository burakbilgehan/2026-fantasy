"""Yeo-Johnson power transform (pure, stdlib). Used by the DURANT models (docs/modules/valuation.md).

y = ((x + 1)^lambda - 1) / lambda for x >= 0 (log(x + 1) when lambda = 0);
y = -(((1 - x)^(2 - lambda)) - 1) / (2 - lambda) for x < 0 (-log(1 - x) when lambda = 2).
lambda is fitted by maximum likelihood (golden-section search on [-5, 5]), as sklearn's
PowerTransformer and scipy.stats.yeojohnson do. Checked against scipy on 2026-10-13: same lambda
to 4 decimals, same transformed values to 1e-4.
"""

import math
from collections.abc import Sequence


def yeo_johnson(x: Sequence[float], lam: float) -> list[float]:
    out = []
    for v in x:
        if v >= 0:
            out.append(((v + 1.0) ** lam - 1.0) / lam if abs(lam) > 1e-9 else math.log(v + 1.0))
        else:
            out.append(-(((1.0 - v) ** (2.0 - lam)) - 1.0) / (2.0 - lam) if abs(lam - 2.0) > 1e-9 else -math.log(1.0 - v))
    return out


def _log_likelihood(x: Sequence[float], lam: float) -> float:
    y = yeo_johnson(x, lam)
    n = len(y)
    m = sum(y) / n
    var = sum((v - m) ** 2 for v in y) / n
    if var <= 0:
        return -math.inf
    return -n / 2.0 * math.log(var) + (lam - 1.0) * sum(math.copysign(math.log(abs(v) + 1.0), v) for v in x)


def fit_lambda(x: Sequence[float], lo: float = -5.0, hi: float = 5.0, tol: float = 1e-5) -> float:
    """Maximum-likelihood lambda. `x` needs at least 2 distinct values."""
    g = (math.sqrt(5.0) - 1.0) / 2.0
    a, b = lo, hi
    c, d = b - g * (b - a), a + g * (b - a)
    fc, fd = _log_likelihood(x, c), _log_likelihood(x, d)
    while b - a > tol:
        if fc < fd:
            a, c, fc = c, d, fd
            d = a + g * (b - a)
            fd = _log_likelihood(x, d)
        else:
            b, d, fd = d, c, fc
            c = b - g * (b - a)
            fc = _log_likelihood(x, c)
    return (a + b) / 2.0
