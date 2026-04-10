from __future__ import annotations

from dataclasses import dataclass

from research.active_lp.types import ActorId, EventKind, Numeric, OutcomeIndex


@dataclass(slots=True)
class BootstrapMarket:
    timestamp: int
    creator_id: ActorId
    initial_collateral: Numeric
    initial_depth_b: Numeric
    kind: EventKind = EventKind.BOOTSTRAP_MARKET


@dataclass(slots=True)
class LpEnterActive:
    timestamp: int
    sponsor_id: ActorId
    target_delta_b: Numeric
    max_deposit: Numeric
    expected_price_vector: tuple[Numeric, ...]
    price_tolerance: Numeric
    min_delta_b: Numeric | None = None
    cohort_policy_hint: str | None = None
    kind: EventKind = EventKind.LP_ENTER_ACTIVE


@dataclass(slots=True)
class BuyOutcome:
    timestamp: int
    trader_id: ActorId
    outcome_index: OutcomeIndex
    shares: Numeric
    max_total_cost: Numeric
    kind: EventKind = EventKind.BUY_OUTCOME


@dataclass(slots=True)
class SellOutcome:
    timestamp: int
    trader_id: ActorId
    outcome_index: OutcomeIndex
    shares: Numeric
    min_total_return: Numeric
    kind: EventKind = EventKind.SELL_OUTCOME


@dataclass(slots=True)
class ResolveMarket:
    timestamp: int
    winning_outcome: OutcomeIndex
    kind: EventKind = EventKind.RESOLVE_MARKET


@dataclass(slots=True)
class CancelMarket:
    timestamp: int
    reason: str
    kind: EventKind = EventKind.CANCEL_MARKET


@dataclass(slots=True)
class ClaimWinnings:
    timestamp: int
    trader_id: ActorId
    outcome_index: OutcomeIndex
    shares: Numeric
    kind: EventKind = EventKind.CLAIM_WINNINGS


@dataclass(slots=True)
class ClaimRefund:
    timestamp: int
    trader_id: ActorId
    outcome_index: OutcomeIndex
    shares: Numeric
    kind: EventKind = EventKind.CLAIM_REFUND


@dataclass(slots=True)
class ClaimLpFees:
    timestamp: int
    sponsor_id: ActorId
    kind: EventKind = EventKind.CLAIM_LP_FEES


@dataclass(slots=True)
class WithdrawLpFees:
    timestamp: int
    sponsor_id: ActorId
    amount: Numeric
    kind: EventKind = EventKind.WITHDRAW_LP_FEES


@dataclass(slots=True)
class ClaimLpResidual:
    timestamp: int
    sponsor_id: ActorId
    kind: EventKind = EventKind.CLAIM_LP_RESIDUAL


SimulationEvent = (
    BootstrapMarket
    | LpEnterActive
    | BuyOutcome
    | SellOutcome
    | ResolveMarket
    | CancelMarket
    | ClaimWinnings
    | ClaimRefund
    | ClaimLpFees
    | WithdrawLpFees
    | ClaimLpResidual
)
