"""Execution-accuracy comparison between a candidate result and the reference result."""
from __future__ import annotations

import datetime as dt
import decimal
from collections import Counter
from typing import Any


def _norm(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, decimal.Decimal)):
        return round(float(value), 2) + 0.0  # +0.0 turns -0.0 into 0.0
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()[:10]
    if value is None:
        return None
    return str(value).strip()


def _rows(rows: list[list[Any]]) -> Counter:
    return Counter(tuple(_norm(v) for v in r) for r in rows)


def strict_match(candidate: list[list[Any]], reference: list[list[Any]]) -> bool:
    """Same multiset of rows (row order ignored, column order significant)."""
    return _rows(candidate) == _rows(reference)


def lenient_match(candidate: list[list[Any]], reference: list[list[Any]]) -> bool:
    """Same row count and every reference column appears (as a value multiset) among the candidate's columns.

    Accepts answers that add helper columns (e.g. an id next to a name) or reorder columns.
    """
    if strict_match(candidate, reference):
        return True
    if len(candidate) != len(reference) or not reference:
        return False
    cand_cols = [Counter(_norm(r[i]) for r in candidate) for i in range(len(candidate[0]))] if candidate else []
    ref_cols = [Counter(_norm(r[i]) for r in reference) for i in range(len(reference[0]))]
    used: set[int] = set()
    for ref in ref_cols:
        hit = next((i for i, c in enumerate(cand_cols) if i not in used and c == ref), None)
        if hit is None:
            return False
        used.add(hit)
    return True
