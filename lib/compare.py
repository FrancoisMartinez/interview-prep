"""Comparator modes.

LeetCode's judge is not always `==`. Some problems accept any ordering, some
accept any valid answer at all. The mode lives in cases.json (set at import
time) so the harness stays generic.

Modes:
  exact        deep equality
  unordered    outer order irrelevant  -- [[1,2],[3]] == [[3],[1,2]]
  set_of_sets  outer AND inner order irrelevant -- 3sum, group-anagrams
  float        numeric, within `tolerance` (elementwise for sequences)
  any_of       case's `expected` is a list of acceptable answers; match any
  custom       delegate to validate(args, actual) in the problem's validate.py
"""

from __future__ import annotations

import json
import math

DEFAULT_TOLERANCE = 1e-5


def _key(value) -> str:
    """A stable sort key for arbitrarily nested JSON-ish values."""
    return json.dumps(value, sort_keys=True, default=repr)


def _canon_unordered(value):
    return sorted((v for v in value), key=_key) if isinstance(value, list) else value


def _canon_set_of_sets(value):
    if not isinstance(value, list):
        return value
    inner = [sorted(v, key=_key) if isinstance(v, list) else v for v in value]
    return sorted(inner, key=_key)


def _float_equal(expected, actual, tolerance) -> bool:
    if isinstance(expected, (list, tuple)):
        if not isinstance(actual, (list, tuple)) or len(expected) != len(actual):
            return False
        return all(_float_equal(e, a, tolerance) for e, a in zip(expected, actual))
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected == actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return math.isclose(expected, actual, rel_tol=tolerance, abs_tol=tolerance)
    return expected == actual


def compare(mode, expected, actual, *, tolerance=DEFAULT_TOLERANCE,
            validator=None, args=None):
    """Return (ok, detail). `detail` is '' when ok, else a human-readable note."""
    mode = mode or "exact"

    if mode == "custom":
        if validator is None:
            return False, "compare mode is 'custom' but no validate.py was found"
        verdict = validator(args, actual)
        if isinstance(verdict, tuple):
            ok, detail = verdict
            return bool(ok), ("" if ok else str(detail))
        return bool(verdict), ("" if verdict else "custom validator rejected the answer")

    if mode == "any_of":
        if not isinstance(expected, list):
            return False, "compare mode is 'any_of' but expected is not a list of answers"
        ok = any(candidate == actual for candidate in expected)
        return ok, "" if ok else f"no match among {len(expected)} accepted answers"

    if mode == "float":
        ok = _float_equal(expected, actual, tolerance)
        return ok, "" if ok else f"outside tolerance {tolerance}"

    if mode == "unordered":
        ok = _canon_unordered(expected) == _canon_unordered(actual)
        return ok, "" if ok else "differs even ignoring order"

    if mode == "set_of_sets":
        ok = _canon_set_of_sets(expected) == _canon_set_of_sets(actual)
        return ok, "" if ok else "differs even ignoring inner and outer order"

    if mode == "exact":
        return expected == actual, ""

    return False, f"unknown compare mode {mode!r}"


VALID_MODES = frozenset(
    {"exact", "unordered", "set_of_sets", "float", "any_of", "custom"}
)
