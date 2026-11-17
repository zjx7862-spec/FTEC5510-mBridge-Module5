"""Resolution and validation of the Module 4 ranking parameters.

Every number that influences the score is read from ``config.json``
(Module 2 contract v1.0.0, object ``ranking_parameters``).  Nothing about
weights, normalisers or priority points is hard-coded in the scoring code:
``DEFAULTS`` is used *only* when a key is absent, and the resolved value,
its source and the resolved parameter block are all echoed back so that any
ordering can be traced to one configuration version.

Lookup order for a key ``k``::

    config["ranking_parameters"][k]     <- the Module 2 contract slot (wins)
    config["engine_parameters"][k]      <- Module 3 engine-owned block
    config["data_generation"][k]        <- Module 2 generator block
    config[k]                           <- flat top-level key

Aliases are accepted only where Module 2/3 already use another name
(see ``ALIASES``); the winning source is reported in ``sources``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping

CENT = Decimal("0.01")

PRIORITIES = ("URGENT", "HIGH", "NORMAL")

DEFAULT_PRIORITY_POINTS = {"URGENT": 3.0, "HIGH": 2.0, "NORMAL": 1.0}

#: Fallbacks used only when the key is absent from every config container.
DEFAULTS: dict[str, Any] = {
    "weight_priority": 0.45,
    "weight_deadline": 0.40,
    "weight_aging": 0.15,
    "weight_funding": 0.00,
    "deadline_normalizer_sec": 7200.0,
    "aging_normalizer_sec": 7200.0,
    "deadline_mode": "linear",
    "aging_mode": "linear",
    "deadline_guard_sec": 0.0,
    "funding_demand_mode": "ratio",
    "score_round_dp": 9,
}

#: key -> alternative names already used elsewhere in Module 2/3.
ALIASES: dict[str, tuple[str, ...]] = {
    # proposal 4.2.1 subtracts the expected confirmation delay from the slack;
    # Module 3 owns that number inside engine_parameters.
    "expected_confirmation_delay_sec": ("payment_confirmation_delay_sec",),
    # proposal 4.2.1 column L: reference scale may come from the generator block.
    "funding_demand_reference_rmb": ("payment_amount_max_rmb",),
}

KNOWN_KEYS = (set(DEFAULTS)
              | set(ALIASES)
              | {"priority_points", "expected_confirmation_delay_sec",
                 "funding_demand_reference_rmb"})

_LINEAR = "linear"
_EXPONENTIAL = "exponential"
_DEADLINE_MODES = (_LINEAR, _EXPONENTIAL)
_AGING_MODES = (_LINEAR, _EXPONENTIAL)
_FUNDING_MODES = ("ratio", "queue_range", "off")

_CONTAINER_NAMES = ("ranking_parameters", "engine_parameters", "data_generation")


class RankingConfigError(ValueError):
    """config.json cannot be turned into a valid ranking parameter set."""


class RankingInputError(ValueError):
    """The queue handed to rank_payments violates the Module 2/3 contract."""


def to_decimal(value: Any) -> Decimal:
    """Convert any numeric input to a 2-decimal Decimal (same rule as Module 3)."""
    if isinstance(value, Decimal):
        amount = value
    else:
        amount = Decimal(str(value))
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def _lookup(config: Mapping, key: str) -> tuple[Any, str | None]:
    """Return ``(value, source_label)`` for the first container defining ``key``."""
    for name in (key,) + ALIASES.get(key, ()):
        for container_name in _CONTAINER_NAMES:
            block = config.get(container_name)
            if isinstance(block, Mapping) and name in block:
                return block[name], f"{container_name}.{name}"
        if name in config:
            return config[name], f"root.{name}"
    return None, None


def _as_float(value: Any, label: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise RankingConfigError(
            f"{label} = {value!r} is not a number; ranking parameters must be numeric "
            f"(see docs/scoring_formula.md)") from None


def _as_points(value: Any, label: str) -> dict:
    if not isinstance(value, Mapping):
        raise RankingConfigError(
            f"{label} must be an object like {{\"URGENT\":3,\"HIGH\":2,\"NORMAL\":1}}")
    points: dict[str, float] = {}
    for name in PRIORITIES:
        if name not in value:
            raise RankingConfigError(f"{label} is missing the priority {name!r}")
        points[name] = _as_float(value[name], f"{label}.{name}")
    extra = sorted(k for k in value if k not in PRIORITIES)
    if extra:
        raise RankingConfigError(
            f"{label} contains unknown priorities {extra}; allowed: {list(PRIORITIES)}")
    if max(points.values()) <= 0:
        raise RankingConfigError(f"{label} must contain at least one positive point value")
    return points


@dataclass(frozen=True)
class RankingParams:
    """Resolved, validated ranking parameters (immutable per decision event)."""

    points: dict = field(default_factory=lambda: dict(DEFAULT_PRIORITY_POINTS))
    points_max: float = 3.0
    weight_priority: float = 0.45
    weight_deadline: float = 0.40
    weight_aging: float = 0.15
    weight_funding: float = 0.0
    deadline_normalizer_sec: float = 7200.0
    aging_normalizer_sec: float = 7200.0
    deadline_mode: str = _LINEAR
    aging_mode: str = _LINEAR
    expected_confirmation_delay_sec: float = 10.0
    deadline_guard_sec: float = 0.0
    funding_demand_mode: str = "ratio"
    funding_demand_reference_rmb: Decimal | None = None
    score_round_dp: int = 9
    sources: dict = field(default_factory=dict)
    warnings: tuple = ()

    # -- serialisation ------------------------------------------------------
    def to_dict(self) -> dict:
        """Plain-JSON snapshot; run summaries record this so a run is auditable."""
        return {
            "priority_points": dict(self.points),
            "priority_points_max": self.points_max,
            "weight_priority": self.weight_priority,
            "weight_deadline": self.weight_deadline,
            "weight_aging": self.weight_aging,
            "weight_funding": self.weight_funding,
            "deadline_normalizer_sec": self.deadline_normalizer_sec,
            "aging_normalizer_sec": self.aging_normalizer_sec,
            "deadline_mode": self.deadline_mode,
            "aging_mode": self.aging_mode,
            "expected_confirmation_delay_sec": self.expected_confirmation_delay_sec,
            "deadline_guard_sec": self.deadline_guard_sec,
            "funding_demand_mode": self.funding_demand_mode,
            "funding_demand_reference_rmb": (None if self.funding_demand_reference_rmb is None
                                             else str(self.funding_demand_reference_rmb)),
            "score_round_dp": self.score_round_dp,
            "sources": dict(sorted(self.sources.items())),
            "warnings": list(self.warnings),
        }

    def formula(self) -> str:
        """Human-readable score formula with the resolved weights plugged in."""
        sign = "-" if self.weight_funding else "+"
        return (f"score = {self.weight_priority:.4g}*P + {self.weight_deadline:.4g}*D "
                f"+ {self.weight_aging:.4g}*A {sign} {self.weight_funding:.4g}*L")


def resolve_params(config: Mapping, strict: bool = False) -> RankingParams:
    """Build a validated :class:`RankingParams` from a Module 2 config object.

    ``strict=True`` turns unknown keys inside ``ranking_parameters`` into an
    error (used by the CLI and the tests, so a typo such as ``weight_agings``
    cannot pass unnoticed).  The engine-facing path is non-strict: it reports
    the same problem through ``RankingParams.warnings`` instead of aborting a
    1000-run batch.
    """
    if not isinstance(config, Mapping):
        raise RankingConfigError("config must be a mapping (the loaded config.json object)")

    warnings: list[str] = []
    sources: dict[str, str] = {}

    block = config.get("ranking_parameters")
    if block is not None and not isinstance(block, Mapping):
        raise RankingConfigError("config.ranking_parameters must be an object")
    unknown = sorted(k for k in (block or {}) if k not in KNOWN_KEYS)
    if unknown:
        message = (f"config.ranking_parameters contains unknown keys {unknown}; "
                   f"known keys are {sorted(KNOWN_KEYS)}")
        if strict:
            raise RankingConfigError(message)
        warnings.append(message)

    raw: dict[str, Any] = {}
    for key in sorted(KNOWN_KEYS):
        value, source = _lookup(config, key)
        if source is not None:
            raw[key] = value
            sources[key] = source

    points = _as_points(raw.get("priority_points", DEFAULT_PRIORITY_POINTS),
                        sources.get("priority_points", "built-in default"))
    if "priority_points" not in sources:
        warnings.append("priority_points missing from config; using URGENT/HIGH/NORMAL = 3/2/1")

    def number(key: str, fallback: float) -> float:
        if key not in raw:
            return float(DEFAULTS.get(key, fallback))
        return _as_float(raw[key], sources[key])

    w_priority = number("weight_priority", 0.45)
    w_deadline = number("weight_deadline", 0.40)
    w_aging = number("weight_aging", 0.15)
    w_funding = number("weight_funding", 0.0)
    for name, value in (("weight_priority", w_priority), ("weight_deadline", w_deadline),
                        ("weight_aging", w_aging), ("weight_funding", w_funding)):
        if value < 0:
            raise RankingConfigError(f"{name} must be >= 0, got {value!r}")

    if w_priority + w_deadline + w_aging + w_funding <= 0:
        raise RankingConfigError("all score weights are zero, so no payment can be ranked")
    weight_total = w_priority + w_deadline + w_aging + w_funding
    if abs(weight_total - 1.0) > 1e-9:
        warnings.append(
            f"score weights sum to {weight_total:g}, not 1; the ordering is unaffected but "
            "absolute scores are not comparable across configurations")

    deadline_norm = number("deadline_normalizer_sec", 7200.0)
    aging_norm = number("aging_normalizer_sec", 7200.0)
    if deadline_norm <= 0:
        raise RankingConfigError(f"deadline_normalizer_sec must be > 0, got {deadline_norm!r}")
    if aging_norm <= 0:
        raise RankingConfigError(f"aging_normalizer_sec must be > 0, got {aging_norm!r}")

    deadline_mode = str(raw.get("deadline_mode") or DEFAULTS["deadline_mode"]).lower()
    aging_mode = str(raw.get("aging_mode") or DEFAULTS["aging_mode"]).lower()
    if deadline_mode not in _DEADLINE_MODES:
        raise RankingConfigError(
            f"deadline_mode must be one of {_DEADLINE_MODES}, got {deadline_mode!r}")
    if aging_mode not in _AGING_MODES:
        raise RankingConfigError(f"aging_mode must be one of {_AGING_MODES}, got {aging_mode!r}")

    funding_mode = str(raw.get("funding_demand_mode") or DEFAULTS["funding_demand_mode"]).lower()
    if funding_mode not in _FUNDING_MODES:
        raise RankingConfigError(
            f"funding_demand_mode must be one of {_FUNDING_MODES}, got {funding_mode!r}")
    if w_funding > 0 and funding_mode == "off":
        raise RankingConfigError(
            "weight_funding > 0 requires funding_demand_mode to be 'ratio' or 'queue_range'")

    confirm_delay = number("expected_confirmation_delay_sec", 10.0)
    if confirm_delay < 0:
        raise RankingConfigError("expected_confirmation_delay_sec must be >= 0")

    guard = number("deadline_guard_sec", 0.0)
    if guard < 0:
        raise RankingConfigError("deadline_guard_sec must be >= 0")

    reference = raw.get("funding_demand_reference_rmb")
    reference_dec = None
    if reference is not None:
        reference_dec = to_decimal(reference)
        if reference_dec <= 0:
            raise RankingConfigError("funding_demand_reference_rmb must be > 0")

    try:
        round_dp = int(raw.get("score_round_dp", DEFAULTS["score_round_dp"]))
    except (TypeError, ValueError):
        raise RankingConfigError("score_round_dp must be an integer") from None
    if not 0 <= round_dp <= 15:
        raise RankingConfigError("score_round_dp must be between 0 and 15")

    return RankingParams(
        points=points,
        points_max=max(points.values()),
        weight_priority=w_priority,
        weight_deadline=w_deadline,
        weight_aging=w_aging,
        weight_funding=w_funding,
        deadline_normalizer_sec=deadline_norm,
        aging_normalizer_sec=aging_norm,
        deadline_mode=deadline_mode,
        aging_mode=aging_mode,
        expected_confirmation_delay_sec=confirm_delay,
        deadline_guard_sec=guard,
        funding_demand_mode=funding_mode,
        funding_demand_reference_rmb=reference_dec,
        score_round_dp=round_dp,
        sources=sources,
        warnings=tuple(warnings),
    )
