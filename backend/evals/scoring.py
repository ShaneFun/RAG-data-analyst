"""How an agent answer is scored against a gold answer.

Execution accuracy: run the gold SQL and the agent's SQL and compare the RESULTS, not the
SQL text (many different queries are correct). The comparison is deliberately lenient about
presentation (row order, column order, extra columns, rounding) and strict about content
(same number of rows, every gold column's values present).
"""
from __future__ import annotations

import math
import re

REL_TOL = 0.005   # 0.5% relative tolerance (rounding to 2-4 decimals)
ABS_TOL = 0.006   # absorbs rounding to 2 decimals on small numbers

DECLINE_PATTERN = re.compile(
    r"\b(can't|cannot|can not|unable|not able|won't|will not|don't have access|"
    r"not available|decline|sorry|only answer|only help)\b",
    re.IGNORECASE,
)


def _norm(value):
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    text = str(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T00:00:00.*", text):  # timestamp at midnight -> date
        text = text[:10]
    return text


def _same(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=REL_TOL, abs_tol=ABS_TOL)
    return a == b


def _sort_key(value):
    return (0, value, "") if isinstance(value, float) else (1, 0.0, str(value))


def _column_equal(gold: list, pred: list) -> bool:
    return all(_same(g, p) for g, p in zip(sorted(gold, key=_sort_key),
                                           sorted(pred, key=_sort_key), strict=True))


def results_match(gold_rows: list[list], pred_rows: list[list]) -> bool:
    """True if every gold column appears (as a multiset of values) among the predicted columns."""
    if len(gold_rows) != len(pred_rows):
        return False
    if not gold_rows:
        return True
    gold_cols = [list(col) for col in zip(*[[_norm(v) for v in r] for r in gold_rows], strict=True)]
    pred_cols = [list(col) for col in zip(*[[_norm(v) for v in r] for r in pred_rows], strict=True)]
    unused = list(range(len(pred_cols)))
    for gold in gold_cols:
        match = next((i for i in unused if _column_equal(gold, pred_cols[i])), None)
        if match is None:
            return False
        unused.remove(match)
    return True


def keywords_ok(answer: str, groups: list[list[str]]) -> bool:
    """Every group must have at least one keyword in the answer (case-insensitive)."""
    text = answer.lower()
    return all(any(word.lower() in text for word in group) for group in groups)


def looks_like_refusal(answer: str, sql_count: int) -> bool:
    return sql_count == 0 and bool(DECLINE_PATTERN.search(answer))


def score_item(item: dict, answer: str, sql_count: int, pred_rows: list[list],
               gold_rows: list[list] | None) -> dict:
    """Score one question. Returns {"passed": bool, "checks": {name: bool}}."""
    checks: dict[str, bool] = {}
    if item.get("expect_refusal"):
        checks["refused"] = looks_like_refusal(answer, sql_count)
    if gold_rows is not None:
        checks["result"] = results_match(gold_rows, pred_rows)
    if item.get("keywords"):
        checks["keywords"] = keywords_ok(answer, item["keywords"])
    return {"passed": bool(checks) and all(checks.values()), "checks": checks}
