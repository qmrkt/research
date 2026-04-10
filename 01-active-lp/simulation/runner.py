from __future__ import annotations

from typing import Protocol

from research.active_lp.events import BuyOutcome, LpEnterActive, SellOutcome, SimulationEvent
from research.active_lp.metrics import CanonicalEvaluation, InvariantCheckResult
from research.active_lp.state import MarketPricingState, SimulationState
from research.active_lp.types import MechanismVariant, Numeric


class PricingOracle(Protocol):
    def price_vector(self, state: MarketPricingState) -> tuple[Numeric, ...]:
        ...

    def buy_cost(self, state: MarketPricingState, outcome_index: int, shares: Numeric) -> Numeric:
        ...

    def sell_return(self, state: MarketPricingState, outcome_index: int, shares: Numeric) -> Numeric:
        ...

    def route_trade(self, state: SimulationState, event: BuyOutcome | SellOutcome) -> object:
        ...

    def apply_lp_entry(self, state: SimulationState, event: LpEnterActive) -> object:
        ...


class SimulationEngine(Protocol):
    def apply_event(self, state: SimulationState, event: SimulationEvent) -> SimulationState:
        ...

    def clone_state(self, state: SimulationState) -> SimulationState:
        ...

    def mark_to_market_nav(self, state: SimulationState) -> dict[str, Numeric]:
        ...


class InvariantChecker(Protocol):
    def check_all(self, state: SimulationState) -> list[InvariantCheckResult]:
        ...

    def check_price_continuity(self, before: SimulationState, after: SimulationState) -> InvariantCheckResult:
        ...

    def check_sponsor_solvency(self, state: SimulationState) -> InvariantCheckResult:
        ...

    def check_settlement_conservation(self, state: SimulationState) -> InvariantCheckResult:
        ...

    def check_no_instantaneous_value_transfer(
        self, before: SimulationState, after: SimulationState
    ) -> InvariantCheckResult:
        ...


class MetricCollector(Protocol):
    def price_continuity(self, before: SimulationState, after: SimulationState) -> dict[str, object]:
        ...

    def slippage_report(
        self,
        before: SimulationState,
        after: SimulationState,
        reference_trades: list[SimulationEvent],
    ) -> dict[str, object]:
        ...

    def lp_fairness(self, final_state: SimulationState) -> dict[str, object]:
        ...

    def residual_release(self, state: SimulationState) -> dict[str, object]:
        ...

    def solvency_report(self, state: SimulationState) -> dict[str, object]:
        ...

    def path_dependence(self, states: list[SimulationState]) -> dict[str, object]:
        ...

    def divergence(
        self,
        reference_result: CanonicalEvaluation,
        candidate_result: CanonicalEvaluation,
    ) -> dict[str, object]:
        ...

    def protocol_complexity(self, state_history: list[SimulationState]) -> dict[str, object]:
        ...


class ScenarioRunner(Protocol):
    def run(self, events: list[SimulationEvent], mechanism: MechanismVariant) -> CanonicalEvaluation:
        ...

    def compare(
        self,
        events: list[SimulationEvent],
        mechanisms: list[MechanismVariant],
    ) -> dict[MechanismVariant, CanonicalEvaluation]:
        ...
