"""Weight / normaliser sensitivity sweep for the score (proposal 4.4.1, step 5).

The proposal requires testing "sensitivity to scoring weights ... without retuning
them on formal-test results".  This module answers one question at a time:
*how much does the ranking of the current queue change when parameter X moves
across a grid?*  It is deliberately model-free — it re-ranks one frozen decision
event, so the effect of the parameter is isolated from the simulation dynamics.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from .cases import case_config, case_queue, case_state
from .params import RankingParams, resolve_params
from .ranking import compare_orders, rank_payments

SWEEPABLE = (
    "weight_priority", "weight_deadline", "weight_aging", "weight_funding",
    "deadline_normalizer_sec", "aging_normalizer_sec", "expected_confirmation_delay_sec",
)


def sweep(case: Mapping, key: str, values: Sequence[float]) -> list[dict]:
    """Re-rank ``case`` for each value of ``key`` and score the reordering."""
    if key not in SWEEPABLE:
        raise ValueError(f"{key!r} is not sweepable; choose from {list(SWEEPABLE)}")

    queue = case_queue(case)
    state = case_state(case)
    baseline_result = rank_payments(queue, state, case_config(case))
    baseline_order = baseline_result["order"]

    rows = []
    for value in values:
        result = rank_payments(queue, state, case_config(case, {key: value}))
        comparison = compare_orders(baseline_order, result["order"])
        params = resolve_params(case_config(case, {key: value}))
        rows.append({
            "parameter": key,
            "value": value,
            "order": result["order"],
            "changed": comparison["changed"],
            "moved_up": comparison["moved_up"],
            "moved_down": comparison["moved_down"],
            "top_payment": result["order"][0],
            "weight_sum": _weight_sum(key, params),
            "formula": result["formula"],
        })
    return rows


def _weight_sum(key: str, params: RankingParams) -> float | None:
    if not key.startswith("weight_"):
        return None
    return round(params.weight_priority + params.weight_deadline
                 + params.weight_aging + params.weight_funding, 6)


def sweep_report(rows: Sequence[Mapping]) -> str:
    """Compact table: value, changed positions, top payment, first moves."""
    from .report import format_table

    headers = ["value", "changed", "top", "moved up (first 3)", "weight sum"]
    table = []
    for row in rows:
        table.append([
            f"{row['value']:g}",
            f"{row['changed']}/{len(row['order'])}",
            row["top_payment"],
            ", ".join(row["moved_up"][:3]) or "-",
            "-" if row["weight_sum"] is None else f"{row['weight_sum']:g}",
        ])
    return format_table(headers, table, "rrlrl")
