"""Descriptive metrics with explicit populations and undefined values."""

from collections import Counter
from math import sqrt

from agentforge.core.schemas import Confidence, Contract, Count, Metric


class Rate(Contract):
    counts: Metric
    value: Confidence | None
    wilson95: tuple[Confidence, Confidence] | None


def rate(numerator: int, denominator: int) -> Rate:
    counts = Metric(numerator=numerator, denominator=denominator)
    if denominator == 0:
        return Rate(counts=counts, value=None, wilson95=None)
    # NIST/SEMATECH e-Handbook, section 7.2.4.1: two-sided Wilson score interval.
    z = 1.959963984540054
    p = numerator / denominator
    scale = 1 + z * z / denominator
    center = (p + z * z / (2 * denominator)) / scale
    half = z * sqrt(p * (1 - p) / denominator + z * z / (4 * denominator**2)) / scale
    return Rate(counts=counts, value=p, wilson95=(max(0.0, center - half), min(1.0, center + half)))


class Agreement(Contract):
    pairs: Count
    value: float | None


def kappa(pairs: list[tuple[str, str]]) -> Agreement:
    """Unweighted Cohen kappa; undefined for no pairs or chance agreement one."""
    n = len(pairs)
    if not n:
        return Agreement(pairs=0, value=None)
    left, right = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum(left[k] * right[k] for k in left.keys() | right.keys()) / (n * n)
    observed = sum(a == b for a, b in pairs) / n
    return Agreement(
        pairs=n, value=(observed - expected) / (1 - expected) if expected < 1 else None
    )
