from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class InvariantCheckResult:
    name: str
    passed: bool
    severity: str
    details: str
    event_index: int


@dataclass(slots=True)
class CanonicalEvaluation:
    price_continuity: dict[str, object] = field(default_factory=dict)
    slippage_improvement: dict[str, object] = field(default_factory=dict)
    lp_fairness_by_entry_time: dict[str, object] = field(default_factory=dict)
    residual_release: dict[str, object] = field(default_factory=dict)
    solvency: dict[str, object] = field(default_factory=dict)
    path_dependence: dict[str, object] = field(default_factory=dict)
    exact_vs_simplified_divergence: dict[str, object] = field(default_factory=dict)
