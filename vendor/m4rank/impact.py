"""Diagnostic: did ordinary / large payments get hurt by the dynamic order?

Module 4's task list ends with "check with a small case, and help analyse whether
ordinary and large payments are negatively affected".  Module 6 owns the official
metric definitions (metrics.csv); this module is a *diagnostic aid* that reads
Module 3's ``payment_results.csv`` + ``run_summary.json`` and reports the same
outcomes broken down by priority and by amount size, so the S2-vs-S1 claim can be
checked before Module 6 publishes anything.

Definitions used here (deliberately simple, documented, not official):

* delay              = settle_time - arrival_time, completed payments only
* submit wait         = submit_time - arrival_time; a payment never submitted is
                        capped at observation_end - arrival_time
* overdue            = deadline_time <= observation_end and the payment was not
                        settled before its deadline; still counts if outstanding
* large payment      = amount >= the case's ``large_payment_rmb`` threshold
"""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping, Sequence

PRIORITY_ORDER = ("URGENT", "HIGH", "NORMAL")
GROUP_ORDER = ("URGENT", "HIGH", "NORMAL", "ALL", "LARGE", "SMALL")

DEFAULT_LARGE_PAYMENT_RMB = Decimal("250000")


def load_run(path, large_payment_rmb: Decimal | float | str | None = None) -> dict:
    """Load one Module 3 output directory (``payment_results.csv`` + summary)."""
    directory = Path(path)
    results = directory / "payment_results.csv"
    if results.is_file():
        rows = _read_results(results)
        summary_path = directory / "run_summary.json"
        summary = {}
        if summary_path.is_file():
            with summary_path.open(encoding="utf-8") as handle:
                summary = json.load(handle)
    elif directory.suffix.lower() == ".csv" and directory.is_file():
        rows = _read_results(directory)
        summary = {}
    else:
        raise FileNotFoundError(
            f"{directory} is neither a payment_results.csv nor a Module 3 output directory")

    obs_end = int(summary.get("observation_end_sec")
                  or summary.get("simulation_window_sec")
                  or _max_time(rows))
    threshold = (DEFAULT_LARGE_PAYMENT_RMB if large_payment_rmb is None
                 else Decimal(str(large_payment_rmb)))
    return {
        "path": str(directory),
        "run_id": summary.get("run_id") or (rows[0]["run_id"] if rows else "unknown"),
        "strategy_id": summary.get("strategy_id") or (rows[0]["strategy_id"] if rows else "?"),
        "observation_end_sec": obs_end,
        "large_payment_rmb": threshold,
        "rows": rows,
        "summary": summary,
    }


def group_outcomes(run: Mapping) -> list[dict]:
    """One row per priority group, plus ALL / LARGE / SMALL."""
    rows = run["rows"]
    threshold = run["large_payment_rmb"]
    obs_end = run["observation_end_sec"]
    groups: dict[str, list[dict]] = {name: [] for name in PRIORITY_ORDER}
    groups["ALL"] = list(rows)
    groups["LARGE"] = [row for row in rows if Decimal(row["amount_rmb"]) >= threshold]
    groups["SMALL"] = [row for row in rows if Decimal(row["amount_rmb"]) < threshold]
    for row in rows:
        groups.setdefault(row["priority"], []).append(row)

    out = []
    for name in GROUP_ORDER:
        subset = groups.get(name) or []
        out.append(_summarise(name, subset, obs_end))
    return out


def compare_runs(baseline: Mapping, candidate: Mapping) -> list[dict]:
    """Per-group deltas of ``candidate`` against ``baseline`` (e.g. S2 vs S1)."""
    base = {row["group"]: row for row in group_outcomes(baseline)}
    cand = {row["group"]: row for row in group_outcomes(candidate)}
    out = []
    for name in GROUP_ORDER:
        if name not in base or name not in cand:
            continue
        b, c = base[name], cand[name]
        out.append({
            "group": name,
            "n": c["n"],
            "completed_baseline": b["completed"],
            "completed_candidate": c["completed"],
            "mean_delay_baseline": b["mean_delay_sec"],
            "mean_delay_candidate": c["mean_delay_sec"],
            "p95_delay_baseline": b["p95_delay_sec"],
            "p95_delay_candidate": c["p95_delay_sec"],
            "mean_wait_baseline": b["mean_submit_wait_sec"],
            "mean_wait_candidate": c["mean_submit_wait_sec"],
            "overdue_baseline": b["overdue"],
            "overdue_candidate": c["overdue"],
            "verdict": _verdict(b, c),
        })
    return out


# ----------------------------------------------------------------------
# internals
# ----------------------------------------------------------------------

def _read_results(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for row in reader:
            rows.append({
                "run_id": row.get("run_id", ""),
                "strategy_id": row.get("strategy_id", ""),
                "payment_id": row["payment_id"],
                "arrival_time": int(row["arrival_time"]),
                "amount_rmb": row["amount_rmb"],
                "priority": row["priority"],
                "deadline_time": int(row["deadline_time"]),
                "submit_time": _opt_int(row.get("submit_time")),
                "settle_time": _opt_int(row.get("settle_time")),
                "final_status": row.get("final_status", ""),
            })
    if not rows:
        raise ValueError(f"{path} contains no payment rows")
    return rows


def _opt_int(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return int(text)


def _max_time(rows: Iterable[Mapping]) -> int:
    latest = 0
    for row in rows:
        latest = max(latest, row["arrival_time"], row["deadline_time"],
                     row["settle_time"] or 0, row["submit_time"] or 0)
    return latest


def _summarise(name: str, rows: Sequence[Mapping], obs_end: int) -> dict:
    completed = [row for row in rows if row["final_status"] == "SETTLED"]
    delays = [row["settle_time"] - row["arrival_time"] for row in completed]
    waits = [((row["submit_time"] if row["submit_time"] is not None else obs_end)
              - row["arrival_time"]) for row in rows]
    due = [row for row in rows if row["deadline_time"] <= obs_end]
    overdue = [row for row in due
               if row["final_status"] != "SETTLED" or row["settle_time"] > row["deadline_time"]]
    outstanding = [row for row in rows if row["final_status"] != "SETTLED"]

    return {
        "group": name,
        "n": len(rows),
        "completed": len(completed),
        "completion_rate": _ratio(len(completed), len(rows)),
        "outstanding": len(outstanding),
        "outstanding_rmb": str(sum((Decimal(row["amount_rmb"]) for row in outstanding),
                                   Decimal("0"))),
        "mean_delay_sec": _mean(delays),
        "p95_delay_sec": _percentile(delays, 0.95),
        "max_delay_sec": max(delays) if delays else None,
        "mean_submit_wait_sec": _mean(waits),
        "p95_submit_wait_sec": _percentile(waits, 0.95),
        "max_submit_wait_sec": max(waits) if waits else None,
        "due": len(due),
        "overdue": len(overdue),
        "overdue_rate": _ratio(len(overdue), len(due)),
    }


def _verdict(baseline: Mapping, candidate: Mapping) -> str:
    """Plain-language reading of the delta, so nobody has to eyeball the numbers.

    Mean and P95 are reported separately on purpose: a policy can improve the
    average payment while making the tail worse, which is exactly the kind of
    hidden cost this diagnostic exists to expose.
    """
    parts = []
    if candidate["completed"] != baseline["completed"]:
        parts.append("completion +" if candidate["completed"] > baseline["completed"]
                     else "completion -")
    if _worse(candidate["mean_delay_sec"], baseline["mean_delay_sec"]):
        parts.append("mean delay worse")
    elif _better(candidate["mean_delay_sec"], baseline["mean_delay_sec"]):
        parts.append("mean delay better")
    if _worse(candidate["p95_delay_sec"], baseline["p95_delay_sec"]):
        parts.append("p95 worse")
    elif _better(candidate["p95_delay_sec"], baseline["p95_delay_sec"]):
        parts.append("p95 better")
    if candidate["overdue"] != baseline["overdue"]:
        parts.append("overdue +" if candidate["overdue"] > baseline["overdue"] else "overdue -")
    return ", ".join(parts) if parts else "no change"


def _better(a, b) -> bool:
    return a is not None and b is not None and a < b - 1e-9


def _worse(a, b) -> bool:
    return a is not None and b is not None and a > b + 1e-9


def _mean(values: Sequence[float]):
    return round(sum(values) / len(values), 3) if values else None


def _percentile(values: Sequence[float], q: float):
    """Linear-interpolation percentile (matches numpy's default method)."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    fraction = position - low
    return round(ordered[low] + (ordered[high] - ordered[low]) * fraction, 3)


def _ratio(numerator: int, denominator: int):
    return None if not denominator else round(numerator / denominator, 4)
