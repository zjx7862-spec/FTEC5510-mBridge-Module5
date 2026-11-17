"""Module 4 delivery file for Module 3 — exposes exactly ``rank_payments``.

Module 3 loads this module by name (``M3_MODULE4_MODULE=module4_rank``) and calls

    rank_payments(queue, state, config) -> {"order": [...], "scores": {...}}

Two ways to make it importable:

1. **Recommended — put this folder on PYTHONPATH** (nothing is copied)::

       set PYTHONPATH=C:\\...\\module4
       python module3/run_engine.py --dataset <dataset> --strategy S2

2. Copy ``module4_rank.py`` **and** the ``m4rank`` package into
   ``module3/m3engine/`` and set ``M3_MODULE4_MODULE=m3engine.module4_rank``.

The import is guarded so both layouts work without editing this file.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:  # normal case: this folder is on sys.path / PYTHONPATH
    from m4rank import __version__ as module4_version
    from m4rank.ranking import (available_rmb, compare_orders, rank_payments,
                                rank_with_ranks, select_payable)
except ImportError as exc:  # pragma: no cover - only if the package is missing
    raise ImportError(
        "module4_rank.py could not import the m4rank package. Keep module4_rank.py and the "
        f"m4rank/ folder in the same directory (looked in {_HERE}). Original error: {exc}"
    ) from exc

__all__ = ["rank_payments", "rank_with_ranks", "select_payable", "compare_orders",
           "available_rmb", "module4_version"]
