"""FTEC5510 Group 12 — Module 4: dynamic payment ranking (S2 / S4 ordering).

Public API — the only function Module 3 needs is :func:`rank_payments`::

    from module4_rank import rank_payments        # or m4rank directly
    ranked = rank_payments(queue, state, config)
    ranked["order"]    # -> [payment_id, ...]  highest score first
    ranked["scores"]   # -> {payment_id: {"score": float, ...}}

Everything else here supports the deliverable around that function: the case
loader, the tables for the report, the sensitivity sweep and the diagnostic that
checks whether ordinary / large payments were hurt by the new ordering.
"""

from .cases import (DEFAULT_CASE_PATH, case_config, case_queue, case_state, load_case,
                    parse_overrides)
from .impact import compare_runs, group_outcomes, load_run
from .params import (DEFAULTS, PRIORITIES, RankingConfigError, RankingInputError,
                     RankingParams, resolve_params, to_decimal)
from .ranking import (available_rmb, compare_orders, rank_payments, rank_with_ranks,
                      select_payable)
from .report import (before_after_table, format_table, markdown_order_table,
                     order_table, write_detail_csv)
from .scoring import (aging_component, deadline_component, deadline_slack,
                      funding_component, priority_component, score_row,
                      waiting_seconds)
from .sensitivity import SWEEPABLE, sweep, sweep_report

__version__ = "1.0.0"

__all__ = [
    "rank_payments", "rank_with_ranks", "select_payable", "compare_orders",
    "available_rmb",
    "resolve_params", "RankingParams", "RankingConfigError", "RankingInputError",
    "to_decimal", "DEFAULTS", "PRIORITIES",
    "priority_component", "deadline_component", "deadline_slack", "aging_component",
    "waiting_seconds", "funding_component", "score_row",
    "load_case", "case_queue", "case_state", "case_config", "parse_overrides",
    "DEFAULT_CASE_PATH",
    "order_table", "before_after_table", "format_table", "write_detail_csv",
    "markdown_order_table",
    "sweep", "sweep_report", "SWEEPABLE",
    "load_run", "group_outcomes", "compare_runs",
]
