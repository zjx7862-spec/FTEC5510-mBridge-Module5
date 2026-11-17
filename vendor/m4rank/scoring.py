"""The four score components of proposal section 4.2.1, and their combination.

    score_i = w_P * P_i + w_D * D_i + w_A * A_i - w_L * L_i

Each component is mapped onto a common [0, 1] scale before weighting, so the
weights are directly comparable and can be swept for the sensitivity analysis
required by proposal 4.4.1.

``P`` business priority  points[priority] / max(points)
``D`` deadline urgency   1 - min(1, slack / deadline_normalizer)     (linear)
                          exp(-slack / deadline_normalizer)          (exponential)
``A`` aging              min(1, waiting / aging_normalizer)          (linear)
                         1 - exp(-waiting / aging_normalizer)        (exponential)
``L`` funding demand     amount / reference                          (ratio)
                         (amount - min) / (max - min) over the queue (queue_range)

where ``slack = deadline_time - t - expected_confirmation_delay - deadline_guard``.

Monotonicity guarantees the two properties the module is graded on:

* ``D`` is strictly non-increasing in ``slack``: less remaining time never
  lowers the deadline score, so a payment cannot lose priority by having a
  tighter deadline.
* ``A`` is strictly non-decreasing in waiting time, so an ordinary payment
  moves up the queue the longer it waits.

``L`` is a *penalty*: the larger the funding demand, the lower the score, which
is the mechanism proposal 4.2.1 introduces to test "small payments first"
behaviour.  Its default weight is 0, i.e. it is switched off in the initial
experiment exactly as the proposal specifies.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Mapping, Sequence

from .params import (RankingInputError, RankingParams, PRIORITIES, to_decimal)

_EPS = 1e-12


# ----------------------------------------------------------------------
# Individual components
# ----------------------------------------------------------------------

def priority_component(priority: str, params: RankingParams) -> float:
    """``P`` in [0, 1]: raw priority points divided by the largest point value."""
    if priority not in params.points:
        raise RankingInputError(
            f"unknown priority {priority!r}; the Module 2 contract allows {list(PRIORITIES)}")
    return float(params.points[priority]) / float(params.points_max)


def deadline_slack(payment: Mapping, now: int, params: RankingParams) -> tuple[int, int]:
    """Return ``(slack_raw, slack_used)`` in whole seconds.

    ``slack_raw``  = deadline_time - now
    ``slack_used`` = slack_raw - expected confirmation delay - deadline guard

    ``slack_used`` is what the score uses: the proposal subtracts the expected
    confirmation delay because a payment submitted exactly at its deadline can
    no longer settle in time.  ``slack_raw`` is kept for the audit trail.
    """
    deadline = _require_int(payment, "deadline_time")
    slack_raw = deadline - int(now)
    slack_used = int(round(slack_raw
                           - params.expected_confirmation_delay_sec
                           - params.deadline_guard_sec))
    return slack_raw, slack_used


def deadline_component(slack_used: int, params: RankingParams) -> float:
    """``D`` in [0, 1]: a smaller slack always yields a higher (or equal) score."""
    if params.deadline_mode == "exponential":
        value = math.exp(-float(slack_used) / params.deadline_normalizer_sec)
    else:
        value = 1.0 - float(slack_used) / params.deadline_normalizer_sec
    return _clamp01(value)


def waiting_seconds(payment: Mapping, now: int) -> int:
    """Seconds spent in the queue at ``now``; never negative."""
    arrival = _require_int(payment, "arrival_time")
    return max(0, int(now) - arrival)


def aging_component(waiting_sec: int, params: RankingParams) -> float:
    """``A`` in [0, 1]: strictly non-decreasing in waiting time."""
    ratio = max(0, int(waiting_sec)) / float(params.aging_normalizer_sec)
    if params.aging_mode == "exponential":
        value = 1.0 - math.exp(-ratio)
    else:
        value = ratio
    return _clamp01(value)


def funding_component(amount: Decimal, params: RankingParams,
                      queue_amounts: Sequence[Decimal] | None = None) -> float:
    """``L`` in [0, 1]: larger funding demand scores lower once weighted by -w_L."""
    if params.funding_demand_mode == "off":
        return 0.0

    amount_f = float(amount)
    if params.funding_demand_mode == "queue_range":
        amounts = [float(a) for a in (queue_amounts or [amount])]
        low, high = min(amounts), max(amounts)
        if high - low <= _EPS:
            return 0.0  # every queued payment is the same size: no discrimination
        return _clamp01((amount_f - low) / (high - low))

    reference = params.funding_demand_reference_rmb
    if reference is None:
        # No configured scale: fall back to the largest amount in this queue.
        # Documented, deterministic per decision event, never silent.
        amounts = [float(a) for a in (queue_amounts or [amount])]
        reference_f = max(amounts) if amounts else amount_f
    else:
        reference_f = float(reference)
    if reference_f <= _EPS:
        return 0.0
    return _clamp01(amount_f / reference_f)


# ----------------------------------------------------------------------
# Full row
# ----------------------------------------------------------------------

def score_row(payment: Mapping, now: int, params: RankingParams,
              queue_amounts: Sequence[Decimal]) -> dict:
    """Score one queued payment and return every term of the calculation.

    The returned dict is the audit record: it contains the three raw inputs
    (priority, slack, waiting time, amount), the four normalised components,
    each weighted contribution, the total score and a one-line explanation that
    can be pasted into the report or the event log.
    """
    payment_id = str(_require(payment, "payment_id"))
    priority = str(_require(payment, "priority")).upper()
    arrival_time = _require_int(payment, "arrival_time")
    deadline_time = _require_int(payment, "deadline_time")
    amount = to_decimal(_require(payment, "amount_rmb"))

    p_raw = float(params.points[priority])
    p = priority_component(priority, params)
    slack_raw, slack_used = deadline_slack(payment, now, params)
    d = deadline_component(slack_used, params)
    waiting = waiting_seconds(payment, now)
    a = aging_component(waiting, params)
    l = funding_component(amount, params, queue_amounts)

    weighted_p = params.weight_priority * p
    weighted_d = params.weight_deadline * d
    weighted_a = params.weight_aging * a
    weighted_l = params.weight_funding * l
    score = weighted_p + weighted_d + weighted_a - weighted_l

    return {
        "payment_id": payment_id,
        "priority": priority,
        "priority_points": p_raw,
        "arrival_time": arrival_time,
        "amount_rmb": str(amount),
        "deadline_time": deadline_time,
        "waiting_sec": waiting,
        "slack_raw_sec": slack_raw,
        "slack_sec": slack_used,
        "overdue": slack_raw < 0,
        "at_risk": slack_used <= 0,
        "p_component": round(p, 6),
        "d_component": round(d, 6),
        "a_component": round(a, 6),
        "l_component": round(l, 6),
        "w_p": round(weighted_p, 6),
        "w_d": round(weighted_d, 6),
        "w_a": round(weighted_a, 6),
        "w_l": round(weighted_l, 6),
        "score": round(score, 9),
        "explanation": (
            f"P={p:.3f}x{params.weight_priority:.2f}={weighted_p:.4f} + "
            f"D={d:.3f}x{params.weight_deadline:.2f}={weighted_d:.4f} + "
            f"A={a:.3f}x{params.weight_aging:.2f}={weighted_a:.4f} - "
            f"L={l:.3f}x{params.weight_funding:.2f}={weighted_l:.4f} "
            f"=> {score:.4f}"
        ),
    }


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _clamp01(value: float) -> float:
    if value != value:  # NaN guard
        return 0.0
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _require(payment: Mapping, key: str):
    if key not in payment:
        raise RankingInputError(
            f"queued payment is missing the contract field {key!r}: {sorted(payment)}")
    return payment[key]


def _require_int(payment: Mapping, key: str) -> int:
    value = _require(payment, key)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise RankingInputError(
            f"{key} must be whole seconds, got {value!r} in {payment.get('payment_id')!r}"
        ) from None
