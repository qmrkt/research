from __future__ import annotations

from dataclasses import dataclass, field

from research.active_lp.types import ActorId, CohortId, MarketStatus, MechanismVariant, Numeric


@dataclass(slots=True)
class MarketPricingState:
    num_outcomes: int
    pricing_q: tuple[Numeric, ...]
    depth_b: Numeric
    price_vector: tuple[Numeric, ...]
    status: MarketStatus
    timestamp: int


@dataclass(slots=True)
class TraderPositionBook:
    positions_by_trader: dict[ActorId, tuple[Numeric, ...]] = field(default_factory=dict)
    cost_basis_by_trader: dict[ActorId, tuple[Numeric, ...]] = field(default_factory=dict)
    aggregate_outstanding_claims: tuple[Numeric, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class SponsorPosition:
    sponsor_id: ActorId
    cohort_id: CohortId
    entry_timestamp: int
    share_units: Numeric
    target_delta_b: Numeric
    collateral_posted: Numeric
    locked_collateral: Numeric
    withdrawable_fee_surplus: Numeric
    claimable_fees: Numeric
    fee_snapshot: Numeric
    entry_price_vector: tuple[Numeric, ...]
    entry_gauge_alpha: Numeric | None = None
    residual_basis_by_outcome: tuple[Numeric, ...] | None = None
    net_outcome_claims: tuple[Numeric, ...] | None = None
    baseline_q: tuple[Numeric, ...] | None = None
    current_q: tuple[Numeric, ...] | None = None
    external_outcome_tokens: tuple[Numeric, ...] | None = None
    trade_cash_balance: Numeric = 0
    residual_claimed: Numeric = 0


@dataclass(slots=True)
class TreasuryState:
    contract_funds: Numeric
    lp_fee_balance: Numeric = 0
    protocol_fee_balance: Numeric = 0
    pending_payouts: dict[ActorId, Numeric] = field(default_factory=dict)
    rounding_dust: Numeric = 0


@dataclass(slots=True)
class SimulationState:
    mechanism: MechanismVariant
    pricing: MarketPricingState
    traders: TraderPositionBook
    sponsors: dict[ActorId, SponsorPosition]
    treasury: TreasuryState
    winning_outcome: int | None = None
    settlement_timestamp: int | None = None
    residual_weight_scheme: str = "linear"
    residual_linear_lambda: Numeric = 1
    event_index: int = 0
