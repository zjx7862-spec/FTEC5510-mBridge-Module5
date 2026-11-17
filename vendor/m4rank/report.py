"""Text / CSV rendering of ranking results (terminal tables, report tables)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Mapping, Sequence

DETAIL_FIELDS = [
    "rank", "payment_id", "priority", "amount_rmb", "arrival_time", "deadline_time",
    "waiting_sec", "slack_sec", "p_component", "d_component", "a_component",
    "l_component", "w_p", "w_d", "w_a", "w_l", "score", "fundable_now",
    "funding_gap_rmb", "overdue", "at_risk", "explanation",
]


def format_table(headers: Sequence[str], rows: Sequence[Sequence], aligns: str | None = None) -> str:
    """Fixed-width ASCII table.  ``aligns`` is one char per column: l / r / c."""
    rows = [[("" if cell is None else str(cell)) for cell in row] for row in rows]
    widths = [len(str(h)) for h in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    if aligns is None:
        aligns = "l" * len(headers)

    def line(cells: Sequence[str]) -> str:
        parts = []
        for index, cell in enumerate(cells):
            align = aligns[index] if index < len(aligns) else "l"
            if align == "r":
                parts.append(cell.rjust(widths[index]))
            elif align == "c":
                parts.append(cell.center(widths[index]))
            else:
                parts.append(cell.ljust(widths[index]))
        return "  ".join(parts).rstrip()

    out = [line([str(h) for h in headers]), "  ".join("-" * w for w in widths)]
    out.extend(line(row) for row in rows)
    return "\n".join(out)


def order_table(result: Mapping, title: str | None = None) -> str:
    """The full score breakdown in rank order."""
    headers = ["#", "payment_id", "prio", "amount_rmb", "deadline", "wait_s", "slack_s",
               "P", "D", "A", "L", "score", "pay_now"]
    rows = []
    for position, row in enumerate(result["detail"], start=1):
        fundable = row.get("fundable_now")
        rows.append([
            position,
            row["payment_id"],
            row["priority"],
            f"{float(row['amount_rmb']):,.0f}",
            row["deadline_time"],
            row["waiting_sec"],
            row["slack_sec"],
            f"{row['p_component']:.3f}",
            f"{row['d_component']:.3f}",
            f"{row['a_component']:.3f}",
            f"{row['l_component']:.3f}",
            f"{row['score']:.4f}",
            "-" if fundable is None else ("yes" if fundable else "no"),
        ])
    header = title + "\n" if title else ""
    decision = result["decision"]
    note = (f"t={decision['t']}s  queued={decision['n_queued']}  "
            f"rmb_available={decision['rmb_available']}\n")
    return header + note + format_table(headers, rows, "rllrrrrrrrrrr")


def before_after_table(comparison: Mapping, scores: Mapping) -> str:
    """Arrival order (before) against dynamic score order (after)."""
    headers = ["payment_id", "arrival #", "score #", "move", "score"]
    labels = {"up": "^ up", "down": "v down", "same": "= same"}
    rows = []
    for row in comparison["rows"]:
        rows.append([
            row["payment_id"],
            row["rank_before"],
            row["rank_after"],
            labels[row["movement"]],
            f"{float(scores[row['payment_id']]['score']):.4f}",
        ])
    summary = (f"changed positions: {comparison['changed']}/{len(rows)}   "
               f"moved up: {', '.join(comparison['moved_up']) or '-'}   "
               f"moved down: {', '.join(comparison['moved_down']) or '-'}")
    return format_table(headers, rows, "lrrrl") + "\n" + summary


def write_detail_csv(path, result: Mapping) -> Path:
    """Write the per-payment score detail (the "score breakdown" hand-over artefact)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DETAIL_FIELDS, lineterminator="\n",
                                extrasaction="ignore")
        writer.writeheader()
        for position, row in enumerate(result["detail"], start=1):
            record = dict(row)
            record["rank"] = position
            writer.writerow(record)
    return target


def markdown_order_table(result: Mapping) -> str:
    """Markdown version for the report."""
    lines = [
        "| # | payment_id | priority | amount_rmb | deadline | wait_s | slack_s | P | D | A | score |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for position, row in enumerate(result["detail"], start=1):
        lines.append(
            f"| {position} | {row['payment_id']} | {row['priority']} | "
            f"{float(row['amount_rmb']):,.0f} | {row['deadline_time']} | "
            f"{row['waiting_sec']} | {row['slack_sec']} | {row['p_component']:.3f} | "
            f"{row['d_component']:.3f} | {row['a_component']:.3f} | {row['score']:.4f} |")
    return "\n".join(lines)
