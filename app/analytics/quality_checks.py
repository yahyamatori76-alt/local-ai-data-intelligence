"""Bounded quality checks for normalized input rows."""

from collections import Counter
from typing import Iterable


def summarize_rejections(reasons: Iterable[str]) -> dict[str, int]:
    return dict(Counter(reasons))
