from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import TypeAlias

Numeric: TypeAlias = int | float | Decimal
ActorId: TypeAlias = str
CohortId: TypeAlias = str
OutcomeIndex: TypeAlias = int


class MechanismVariant(str, Enum):
    BASELINE_FIXED_B = "baseline_fixed_b"
    REFERENCE_PARALLEL_LMSR = "reference_parallel_lmsr"
    REFERENCE_PARALLEL_LMSR_RESERVE_RESIDUAL = "reference_parallel_lmsr_reserve_residual"
    FPMM_POOL_SHARE = "fpmm_pool_share"
    GLOBAL_STATE_FUNGIBLE_FEES_COHORT_RESIDUAL = "global_state_fungible_fees_cohort_residual"
    GLOBAL_STATE_FUNGIBLE_FEES_RESERVE_RESIDUAL = "global_state_fungible_fees_reserve_residual"
    GLOBAL_STATE_AVM_FIXED_POINT = "global_state_avm_fixed_point"
    GLOBAL_STATE_FULLY_FUNGIBLE = "global_state_fully_fungible"
    GLOBAL_STATE_GOVERNANCE_SCHEDULE = "global_state_governance_schedule"


class MarketStatus(str, Enum):
    CREATED = "created"
    ACTIVE = "active"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


class EventKind(str, Enum):
    BOOTSTRAP_MARKET = "bootstrap_market"
    LP_ENTER_ACTIVE = "lp_enter_active"
    BUY_OUTCOME = "buy_outcome"
    SELL_OUTCOME = "sell_outcome"
    RESOLVE_MARKET = "resolve_market"
    CANCEL_MARKET = "cancel_market"
    CLAIM_WINNINGS = "claim_winnings"
    CLAIM_REFUND = "claim_refund"
    CLAIM_LP_FEES = "claim_lp_fees"
    WITHDRAW_LP_FEES = "withdraw_lp_fees"
    CLAIM_LP_RESIDUAL = "claim_lp_residual"
