"""``rank_payments`` — the Module 4 ranking contract.

Contract (integration_contract.md v1.0.0 / team task allocation):

    rank_payments(queue, state, config)
        -> {"order": [payment_id, ...], "scores": {payment_id: {...}}}

The function is **pure**: it reads ``queue`` / ``state`` / ``config`` and
returns an ordering.  It never locks funds, never subtracts a balance and never
mutates its arguments — only Module 3 may change money or payment status.

Ordering rule (three levels, fully deterministic):

1. score, highest first, compared after rounding to ``score_round_dp`` decimals
   so that mathematically equal scores are *exactly* equal and cannot be
   separated by floating-point noise;
2. ``arrival_time``, earliest first (proposal 4.2.2: "ties are resolved first
   by arrival time");
3. ``payment_id``, ascending (proposal 4.2.2: "and then by payment_id").

Every queued ``payment_id`` is returned exactly once.  Payments that cannot be
funded right now are **ranked normally and flagged**, never dropped: skipping a
temporarily unfundable instruction is an engine action (S1-S4), not a ranking
action.  ``select_payable`` below exposes that skip logic as a pure helper so
Module 3/5 can preview it.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Mapping, Sequence

from .params import (PRIORITIES, RankingInputError, RankingParams, resolve_params,
                     to_decimal)
from .scoring import score_row

ZERO = Decimal("0.00")


def rank_payments(queue: Sequence[Mapping], state: Mapping | None,
                  config: Mapping) -> dict:
    """Rank the queued payments.  See the module docstring for the contract."""
    params = resolve_params(config)
    now = _now(state)
    rows = _score_queue(queue, now, params)

    available = available_rmb(state)
    amounts = {row["payment_id"]: to_decimal(row["amount_rmb"]) for row in rows}
    for row in rows:
        amount = amounts[row["payment_id"]]
        if available is None:
            row["fundable_now"] = None
            row["funding_gap_rmb"] = None
        else:
            row["fundable_now"] = bool(amount <= available)
            gap = amount - available
            row["funding_gap_rmb"] = str(gap if gap > ZERO else ZERO)

    rows.sort(key=lambda row: _rank_key(row, params))

    order = [row["payment_id"] for row in rows]
    scores = {row["payment_id"]: _compact(row) for row in rows}
    warnings = list(params.warnings)
    warnings.extend(_completeness_warnings(order, queue))

    return {
        "order": order,
        "scores": scores,
        "detail": rows,
        "decision": {
            "t": now,
            "n_queued": len(order),
            "rmb_available": None if available is None else str(available),
            "n_fundable_now": (None if available is None
                               else sum(1 for row in rows if row["fundable_now"])),
        },
        "parameters": params.to_dict(),
        "formula": params.formula(),
        "warnings": warnings,
    }


# ----------------------------------------------------------------------
# Internal
# ----------------------------------------------------------------------

def _now(state: Mapping | None) -> int:
    if state is None:
        return 0
    if not isinstance(state, Mapping):
        raise RankingInputError(
            f"state must be a mapping, got {type(state).__name__}")
    if "t" not in state:
        raise RankingInputError("state is missing 't' (current simulation time in seconds)")
    try:
        return int(state["t"])
    except (TypeError, ValueError):
        raise RankingInputError(f"state['t'] must be whole seconds, got {state['t']!r}") from None


def available_rmb(state: Mapping | None) -> Decimal | None:
    """Available RMB, using Module 3's definition when the engine did not send it.

    Module 3 always sends ``rmb_available``; the fallback keeps the function
    usable from a notebook or a unit test.
    """
    if not state:
        return None
    if state.get("rmb_available") is not None:
        return to_decimal(state["rmb_available"])
    keys = ("rmb_total", "rmb_locked", "rmb_reserved")
    if not all(key in state for key in keys):
        return None
    total = to_decimal(state["rmb_total"])
    locked = to_decimal(state["rmb_locked"])
    reserved = to_decimal(state["rmb_reserved"])
    available = total - locked - reserved
    return available if available > ZERO else ZERO


def _score_queue(queue: Sequence[Mapping], now: int, params: RankingParams) -> list[dict]:
    if not queue:
        return []
    seen: set[str] = set()
    amounts: list[Decimal] = []
    for payment in queue:
        if not isinstance(payment, Mapping):
            raise RankingInputError(
                f"every queued payment must be a mapping, got {type(payment).__name__}")
        payment_id = str(payment.get("payment_id", ""))
        if not payment_id:
            raise RankingInputError("a queued payment has no payment_id")
        if payment_id in seen:
            raise RankingInputError(f"duplicate payment_id in the queue: {payment_id}")
        seen.add(payment_id)
        priority = str(payment.get("priority", "")).upper()
        if priority not in PRIORITIES:
            raise RankingInputError(
                f"{payment_id}: priority {payment.get('priority')!r} is not one of {list(PRIORITIES)}")
        for required in ("amount_rmb", "arrival_time", "deadline_time"):
            if required not in payment:
                raise RankingInputError(
                    f"{payment_id}: queued payment is missing the contract field {required!r}")
        amounts.append(to_decimal(payment["amount_rmb"]))
    return [score_row(payment, now, params, amounts) for payment in queue]


def _rank_key(row: Mapping, params: RankingParams) -> tuple:
    """Score descending, then arrival time, then payment_id (proposal 4.2.2)."""
    return (-round(float(row["score"]), params.score_round_dp),
            int(row["arrival_time"]),
            str(row["payment_id"]))


def _compact(row: Mapping) -> dict:
    """The per-payment entry returned in ``scores`` (contract: at least ``score``)."""
    return {
        "score": row["score"],
        "rank": None,  # filled in below by rank_payments when needed
        "priority": row["priority"],
        "priority_points": row["priority_points"],
        "p_component": row["p_component"],
        "d_component": row["d_component"],
        "a_component": row["a_component"],
        "l_component": row["l_component"],
        "slack_sec": row["slack_sec"],
        "waiting_sec": row["waiting_sec"],
        "amount_rmb": row["amount_rmb"],
        "overdue": row["overdue"],
        "at_risk": row["at_risk"],
        "explanation": row["explanation"],
    }


def _completeness_warnings(order: list[str], queue: Sequence[Mapping]) -> list[str]:
    queued_ids = {str(payment.get("payment_id")) for payment in queue}
    missing = sorted(queued_ids - set(order))
    duplicates = len(order) - len(set(order))
    problems = []
    if missing:
        problems.append(f"ranking omitted queued payments {missing}; they were kept by the caller")
    if duplicates:
        problems.append("ranking returned a duplicate payment_id")
    return problems


def rank_with_ranks(queue: Sequence[Mapping], state: Mapping | None,
                    config: Mapping) -> dict:
    """Same as :func:`rank_payments` but also fills the 1-based ``rank`` field."""
    result = rank_payments(queue, state, config)
    for position, row in enumerate(result["detail"], start=1):
        row["rank"] = position
        result["scores"][row["payment_id"]]["rank"] = position
    return result


# ----------------------------------------------------------------------
# Temporarily unfundable instructions
# ----------------------------------------------------------------------

def select_payable(order: Sequence[str], queue: Sequence[Mapping],
                   available: Decimal | str | float | None) -> dict:
    """Preview which payments a sequential submission pass could settle.

    Walks ``order`` once, keeping a running available balance: a payment is
    payable when ``amount <= running_available``, and submitting it reduces the
    running balance.  Payments that do not fit are *blocked*, not removed, which
    is exactly what S1-S4 do inside Module 3 ("skipping is allowed").

    Returns ``payable`` / ``blocked`` / ``first_blocked`` / ``head_of_line_blocked``
    / ``remaining_rmb``.  With ``available=None`` fundability is unknown and every
    payment is reported as payable so no instruction is silently lost.
    """
    amounts = {str(p.get("payment_id")): to_decimal(p["amount_rmb"]) for p in queue}
    unknown = [pid for pid in order if pid not in amounts]
    if unknown:
        raise RankingInputError(f"order contains ids that are not in the queue: {unknown}")

    if available is None:
        return {
            "payable": list(order),
            "blocked": [],
            "first_blocked": None,
            "head_of_line_blocked": False,
            "remaining_rmb": None,
            "fundability_known": False,
        }

    running = to_decimal(available)
    payable: list[str] = []
    blocked: list[str] = []
    for payment_id in order:
        amount = amounts[payment_id]
        if amount <= running:
            payable.append(payment_id)
            running -= amount
        else:
            blocked.append(payment_id)

    return {
        "payable": payable,
        "blocked": blocked,
        "first_blocked": blocked[0] if blocked else None,
        "head_of_line_blocked": bool(order) and bool(blocked) and order[0] == blocked[0],
        "remaining_rmb": str(running),
        "fundability_known": True,
    }


def compare_orders(reference: Iterable[str], candidate: Iterable[str]) -> dict:
    """Position-by-position comparison of two orderings of the same payments.

    Used by ``run_module4.py demo`` to print the "before / after sorting" table
    required from Module 4, and by the tests to assert the exact reordering.
    """
    reference = list(reference)
    candidate = list(candidate)
    if sorted(reference) != sorted(candidate):
        raise RankingInputError("the two orderings do not contain the same payment ids")
    before = {pid: index + 1 for index, pid in enumerate(reference)}
    after = {pid: index + 1 for index, pid in enumerate(candidate)}
    rows = []
    for payment_id in reference:
        delta = before[payment_id] - after[payment_id]  # >0 means it moved up
        rows.append({
            "payment_id": payment_id,
            "rank_before": before[payment_id],
            "rank_after": after[payment_id],
            "delta": delta,
            "movement": "up" if delta > 0 else "down" if delta < 0 else "same",
        })
    return {
        "rows": rows,
        "changed": sum(1 for row in rows if row["delta"]),
        "moved_up": [row["payment_id"] for row in rows if row["delta"] > 0],
        "moved_down": [row["payment_id"] for row in rows if row["delta"] < 0],
        "unchanged": [row["payment_id"] for row in rows if row["delta"] == 0],
    }
