"""Loading and overriding the hand-checkable ranking cases.

A *case* is one decision event frozen on disk::

    {
      "case_id": "...",
      "description": "...",
      "state": {"t": 1800, "rmb_available": "600000.00", ...},
      "queue": [ {payment_id, arrival_time, amount_rmb, priority, deadline_time}, ... ],
      "config": {"ranking_parameters": {...}}
    }

Keeping the case in a file (instead of inside a test) means the report, the
tests and Module 3 all rank exactly the same ten-odd instructions, which is what
the "before-and-after ranking example" hand-over requires.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

from .params import RankingInputError, to_decimal

DEFAULT_CASE_PATH = (Path(__file__).resolve().parent.parent / "examples" / "demo_case.json")

REQUIRED_PAYMENT_FIELDS = ("payment_id", "arrival_time", "amount_rmb", "priority",
                           "deadline_time")


def load_case(path=None) -> dict:
    """Read and minimally validate a case file."""
    target = Path(path) if path else DEFAULT_CASE_PATH
    if not target.exists():
        raise FileNotFoundError(f"case file not found: {target}")
    with target.open(encoding="utf-8") as handle:
        case = json.load(handle)

    for key in ("queue", "state", "config"):
        if key not in case:
            raise RankingInputError(f"{target.name}: missing top-level key {key!r}")
    queue = case["queue"]
    if not isinstance(queue, list) or not queue:
        raise RankingInputError(f"{target.name}: 'queue' must be a non-empty list")
    for index, payment in enumerate(queue, start=1):
        missing = [field for field in REQUIRED_PAYMENT_FIELDS if field not in payment]
        if missing:
            raise RankingInputError(f"{target.name}: queue item {index} is missing {missing}")
        to_decimal(payment["amount_rmb"])  # rejects non-numeric amounts early
    if "t" not in case["state"]:
        raise RankingInputError(f"{target.name}: state is missing 't'")

    case.setdefault("case_id", target.stem)
    case["source_path"] = str(target)
    return case


def case_queue(case: Mapping) -> list[dict]:
    return copy.deepcopy(list(case["queue"]))


def case_state(case: Mapping) -> dict:
    return copy.deepcopy(dict(case["state"]))


def case_config(case: Mapping, overrides: Mapping | None = None) -> dict:
    """Deep copy of the case config with flat ``{key: value}`` overrides applied.

    A key that already exists inside ``ranking_parameters`` is overridden there
    (that is what "changing a ranking weight" means); any other key is set at the
    root of the config, which is how the Module 2/3 config is laid out.
    """
    config = copy.deepcopy(dict(case["config"]))
    ranking = config.setdefault("ranking_parameters", {})
    for key, value in (overrides or {}).items():
        if key in ranking:
            ranking[key] = value
        else:
            config[key] = value
    return config


def parse_overrides(pairs) -> dict:
    """Turn ``["weight_funding=1.0", "deadline_mode=exponential"]`` into a dict.

    Values are parsed as JSON when possible (so ``1.0`` becomes a number and
    ``true`` a bool); anything else stays a string.
    """
    overrides: dict[str, Any] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise ValueError(f"--set expects key=value, got {pair!r}")
        key, _, raw = pair.partition("=")
        key, raw = key.strip(), raw.strip()
        if not key:
            raise ValueError(f"--set expects key=value, got {pair!r}")
        try:
            overrides[key] = json.loads(raw)
        except json.JSONDecodeError:
            overrides[key] = raw
    return overrides


def describe_case(case: Mapping) -> str:
    """Two-line header used before every printed ranking table."""
    config = case["config"]
    scenario = config.get("scenario_id") or case.get("case_id")
    n = len(case["queue"])
    return (f"case       : {case.get('case_id')}  ({case.get('description', '')})\n"
            f"scenario   : {scenario}\n"
            f"decision t : {case['state']['t']} s\n"
            f"queue      : {n} payments")
