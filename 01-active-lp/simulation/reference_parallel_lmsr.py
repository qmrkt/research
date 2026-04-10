from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal

from research.active_lp.events import (
    BootstrapMarket,
    BuyOutcome,
    CancelMarket,
    ClaimLpFees,
    ClaimLpResidual,
    ClaimRefund,
    ClaimWinnings,
    LpEnterActive,
    ResolveMarket,
    SellOutcome,
    SimulationEvent,
    WithdrawLpFees,
)
from research.active_lp.metrics import CanonicalEvaluation, InvariantCheckResult
from research.active_lp.precision import DECIMAL_ONE, DECIMAL_ZERO, high_precision, to_decimal
from research.active_lp.reference_math import (
    collateral_required,
    gauge_alpha_from_prices,
    lmsr_cost_delta,
    lmsr_prices,
    lmsr_sell_return,
    max_abs_diff,
    normalized_q_from_prices,
    uniform_price_vector,
)
from research.active_lp.state import MarketPricingState, SimulationState, SponsorPosition, TraderPositionBook, TreasuryState
from research.active_lp.types import ActorId, MarketStatus, MechanismVariant, Numeric

BPS_DENOMINATOR = Decimal("10000")
PRICE_TOLERANCE = Decimal("1e-18")
NAV_TOLERANCE = Decimal("1e-12")
STRICT_ALL_CLAIMED = "strict_all_claimed"
RESERVE_POOL = "reserve_pool"


def _zero_vector(length: int) -> tuple[Decimal, ...]:
    return tuple(DECIMAL_ZERO for _ in range(length))


def _resolved_price_vector(num_outcomes: int, winning_outcome: int) -> tuple[Decimal, ...]:
    vector = [DECIMAL_ZERO for _ in range(num_outcomes)]
    vector[winning_outcome] = DECIMAL_ONE
    return tuple(vector)


def _sum_vector(vectors: list[tuple[Decimal, ...]], *, length: int) -> tuple[Decimal, ...]:
    totals = [DECIMAL_ZERO] * length
    for vector in vectors:
        if len(vector) != length:
            raise ValueError("vector length mismatch")
        for idx, value in enumerate(vector):
            totals[idx] += value
    return tuple(totals)


def _vector_sub(left: tuple[Decimal, ...], right: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    return tuple(a - b for a, b in zip(left, right))


def _set_tuple_entry(values: tuple[Decimal, ...], index: int, delta: Decimal) -> tuple[Decimal, ...]:
    updated = list(values)
    updated[index] += delta
    return tuple(updated)


def _replace_tuple_entry(values: tuple[Decimal, ...], index: int, new_value: Decimal) -> tuple[Decimal, ...]:
    updated = list(values)
    updated[index] = new_value
    return tuple(updated)


def _sponsor_keys(state: SimulationState) -> list[str]:
    return sorted(state.sponsors.keys())


def _all_sponsors(state: SimulationState) -> list[SponsorPosition]:
    return [state.sponsors[key] for key in _sponsor_keys(state)]


def _pricing_sponsors(state: SimulationState) -> list[SponsorPosition]:
    pricing: list[SponsorPosition] = []
    for sponsor in _all_sponsors(state):
        if sponsor.current_q is None or sponsor.baseline_q is None:
            continue
        if to_decimal(sponsor.target_delta_b) <= 0:
            continue
        pricing.append(sponsor)
    return pricing


def _total_depth(state: SimulationState) -> Decimal:
    total = DECIMAL_ZERO
    for sponsor in _pricing_sponsors(state):
        total += to_decimal(sponsor.target_delta_b)
    return total


def _ensure_trader(state: SimulationState, trader_id: ActorId) -> None:
    n = state.pricing.num_outcomes
    zeroes = _zero_vector(n)
    state.traders.positions_by_trader.setdefault(trader_id, zeroes)
    state.traders.cost_basis_by_trader.setdefault(trader_id, zeroes)
    if not state.traders.aggregate_outstanding_claims:
        state.traders.aggregate_outstanding_claims = zeroes


def _component_net_claims(sponsor: SponsorPosition) -> tuple[Decimal, ...]:
    if sponsor.current_q is None or sponsor.baseline_q is None:
        raise ValueError("sponsor component state missing")
    return _vector_sub(tuple(map(to_decimal, sponsor.current_q)), tuple(map(to_decimal, sponsor.baseline_q)))


def _component_residuals(sponsor: SponsorPosition) -> tuple[Decimal, ...]:
    if sponsor.current_q is None or sponsor.baseline_q is None:
        return sponsor.residual_basis_by_outcome or tuple()
    locked = to_decimal(sponsor.locked_collateral)
    trade_cash = to_decimal(sponsor.trade_cash_balance)
    net_claims = _component_net_claims(sponsor)
    return tuple(locked + trade_cash - claim for claim in net_claims)


def _available_non_fee_assets(sponsor: SponsorPosition) -> Decimal:
    return max(DECIMAL_ZERO, to_decimal(sponsor.locked_collateral) + to_decimal(sponsor.trade_cash_balance))


def _total_non_fee_assets(state: SimulationState) -> Decimal:
    total = DECIMAL_ZERO
    for sponsor in _all_sponsors(state):
        total += _available_non_fee_assets(sponsor)
    return total


def _total_residual_claimed(state: SimulationState) -> Decimal:
    total = DECIMAL_ZERO
    for sponsor in _all_sponsors(state):
        total += to_decimal(sponsor.residual_claimed)
    return total


def _current_price_vector(state: SimulationState) -> tuple[Decimal, ...]:
    if state.pricing.price_vector:
        return tuple(map(to_decimal, state.pricing.price_vector))
    return tuple()


def _aggregate_outstanding(state: SimulationState) -> tuple[Decimal, ...]:
    return tuple(map(to_decimal, state.traders.aggregate_outstanding_claims))


def _refund_reserve_requirement(state: SimulationState) -> Decimal:
    reserve = DECIMAL_ZERO
    for basis_vector in state.traders.cost_basis_by_trader.values():
        reserve += sum(map(to_decimal, basis_vector), start=DECIMAL_ZERO)
    return reserve


def _winner_reserve_requirement(state: SimulationState) -> Decimal:
    if state.pricing.status is MarketStatus.RESOLVED and state.winning_outcome is not None:
        return _aggregate_outstanding(state)[state.winning_outcome]
    if state.pricing.status is MarketStatus.CANCELLED:
        return _refund_reserve_requirement(state)
    return DECIMAL_ZERO


def _total_share_units(state: SimulationState) -> Decimal:
    total = DECIMAL_ZERO
    for sponsor in _all_sponsors(state):
        share_units = to_decimal(sponsor.share_units)
        if share_units > 0:
            total += share_units
    return total


def _cohort_elapsed_steps(state: SimulationState, sponsor: SponsorPosition) -> Decimal:
    if state.settlement_timestamp is None:
        return DECIMAL_ONE
    elapsed = Decimal(state.settlement_timestamp - sponsor.entry_timestamp)
    return max(DECIMAL_ONE, elapsed)


def _bootstrap_timestamp(state: SimulationState) -> Decimal:
    if not state.sponsors:
        return DECIMAL_ONE
    return Decimal(min(sponsor.entry_timestamp for sponsor in state.sponsors.values()))


def _cohort_normalized_exposure(state: SimulationState, sponsor: SponsorPosition) -> Decimal:
    if state.settlement_timestamp is None:
        return DECIMAL_ZERO
    settlement_timestamp = Decimal(state.settlement_timestamp)
    bootstrap_timestamp = _bootstrap_timestamp(state)
    total_active_span = max(DECIMAL_ONE, settlement_timestamp - bootstrap_timestamp)
    if total_active_span <= DECIMAL_ONE:
        return DECIMAL_ZERO
    elapsed = _cohort_elapsed_steps(state, sponsor)
    premium = max(DECIMAL_ZERO, elapsed - DECIMAL_ONE)
    return premium / (total_active_span - DECIMAL_ONE)


def _cohort_time_weight(state: SimulationState, sponsor: SponsorPosition) -> Decimal:
    elapsed = _cohort_elapsed_steps(state, sponsor)
    premium = max(DECIMAL_ZERO, elapsed - DECIMAL_ONE)
    scheme = state.residual_weight_scheme
    linear_lambda = to_decimal(state.residual_linear_lambda)
    if scheme == "flat":
        return DECIMAL_ONE
    if scheme == "linear":
        return elapsed
    if scheme == "sqrt":
        with high_precision():
            return DECIMAL_ONE + premium.sqrt()
    if scheme == "log1p":
        with high_precision():
            return DECIMAL_ONE + (DECIMAL_ONE + premium).ln()
    if scheme == "linear_lambda":
        return DECIMAL_ONE + linear_lambda * premium
    if scheme == "linear_lambda_normalized":
        return DECIMAL_ONE + linear_lambda * _cohort_normalized_exposure(state, sponsor)
    raise ValueError(f"unsupported residual_weight_scheme: {scheme}")


def _cohort_residual_weight(state: SimulationState, sponsor: SponsorPosition) -> Decimal:
    share_units = max(DECIMAL_ZERO, to_decimal(sponsor.share_units))
    if share_units <= 0:
        return DECIMAL_ZERO
    return share_units * _cohort_time_weight(state, sponsor)


def _total_residual_weight(state: SimulationState) -> Decimal:
    total = DECIMAL_ZERO
    for sponsor in _all_sponsors(state):
        total += _cohort_residual_weight(state, sponsor)
    return total


def _releasable_residual_pool(state: SimulationState) -> Decimal:
    if state.pricing.status not in (MarketStatus.RESOLVED, MarketStatus.CANCELLED):
        return DECIMAL_ZERO
    free_pool = _total_non_fee_assets(state) + _total_residual_claimed(state) - _winner_reserve_requirement(state)
    return max(DECIMAL_ZERO, free_pool)


def _cohort_residual_share(state: SimulationState, sponsor: SponsorPosition) -> Decimal:
    total_weight = _total_residual_weight(state)
    if total_weight <= 0:
        return DECIMAL_ZERO
    weight = _cohort_residual_weight(state, sponsor)
    if weight <= 0:
        return DECIMAL_ZERO
    return weight / total_weight


def _claimable_residual_for_cohort(state: SimulationState, sponsor: SponsorPosition) -> Decimal:
    if state.pricing.status not in (MarketStatus.RESOLVED, MarketStatus.CANCELLED):
        return DECIMAL_ZERO
    total_pool = _releasable_residual_pool(state)
    entitled = total_pool * _cohort_residual_share(state, sponsor)
    remaining = entitled - to_decimal(sponsor.residual_claimed)
    return max(DECIMAL_ZERO, remaining)


def _basis_reduction(current_shares: Decimal, current_basis: Decimal, shares: Decimal) -> Decimal:
    if shares == current_shares:
        return current_basis
    if current_shares <= 0:
        raise ValueError("current_shares must be positive")
    return current_basis * shares / current_shares


def _route_by_depth(state: SimulationState, shares: Decimal) -> dict[str, Decimal]:
    total_depth = _total_depth(state)
    if total_depth <= 0:
        raise ValueError("total depth must be positive")
    routed: dict[str, Decimal] = {}
    remaining = shares
    pricing_keys = [sponsor.cohort_id for sponsor in _pricing_sponsors(state)]
    for idx, key in enumerate(pricing_keys):
        if idx == len(pricing_keys) - 1:
            routed[key] = remaining
            break
        sponsor = state.sponsors[key]
        weight = to_decimal(sponsor.target_delta_b) / total_depth
        routed_shares = shares * weight
        routed[key] = routed_shares
        remaining -= routed_shares
    return routed


def _allocate_lp_fees(state: SimulationState, lp_fee: Decimal) -> None:
    if lp_fee <= 0:
        return
    total_depth = _total_depth(state)
    if total_depth <= 0:
        return
    state.treasury.lp_fee_balance += lp_fee
    remaining = lp_fee
    pricing_keys = [sponsor.cohort_id for sponsor in _pricing_sponsors(state)]
    for idx, key in enumerate(pricing_keys):
        sponsor = state.sponsors[key]
        if idx == len(pricing_keys) - 1:
            fee_share = remaining
        else:
            fee_share = lp_fee * (to_decimal(sponsor.share_units) / total_depth)
            remaining -= fee_share
        state.sponsors[key] = replace(sponsor, claimable_fees=to_decimal(sponsor.claimable_fees) + fee_share)


def _reduce_component_outcome_claims(state: SimulationState, outcome_index: int, shares: Decimal) -> dict[str, Decimal]:
    positive_liabilities: list[tuple[str, Decimal]] = []
    total_positive = DECIMAL_ZERO
    for key in _sponsor_keys(state):
        sponsor = state.sponsors[key]
        if sponsor.current_q is None or sponsor.baseline_q is None:
            continue
        liability = _component_net_claims(sponsor)[outcome_index]
        if liability > 0:
            positive_liabilities.append((key, liability))
            total_positive += liability
    if total_positive + PRICE_TOLERANCE < shares:
        raise ValueError("insufficient component liability for claim")

    allocations: dict[str, Decimal] = {}
    remaining = shares
    for idx, (key, liability) in enumerate(positive_liabilities):
        if idx == len(positive_liabilities) - 1:
            allocation = remaining
        else:
            allocation = shares * liability / total_positive
            remaining -= allocation
        sponsor = state.sponsors[key]
        current_q = tuple(map(to_decimal, sponsor.current_q or tuple()))
        next_q = _set_tuple_entry(current_q, outcome_index, -allocation)
        state.sponsors[key] = replace(sponsor, current_q=next_q)
        allocations[key] = allocation
    return allocations


def _debit_sponsor_assets(state: SimulationState, amount: Decimal) -> dict[str, Decimal]:
    if amount <= 0:
        return {}
    available_rows: list[tuple[str, Decimal]] = []
    total_available = DECIMAL_ZERO
    for key in _sponsor_keys(state):
        sponsor = state.sponsors[key]
        available = _available_non_fee_assets(sponsor)
        if available <= 0:
            continue
        available_rows.append((key, available))
        total_available += available
    if total_available + PRICE_TOLERANCE < amount:
        raise ValueError("insufficient sponsor assets")

    debits: dict[str, Decimal] = {}
    remaining = amount
    for idx, (key, available) in enumerate(available_rows):
        sponsor = state.sponsors[key]
        if idx == len(available_rows) - 1:
            debit = remaining
        else:
            debit = amount * available / total_available
            remaining -= debit
        trade_cash = to_decimal(sponsor.trade_cash_balance)
        locked = to_decimal(sponsor.locked_collateral)
        reduce_from_cash = min(max(trade_cash, DECIMAL_ZERO), debit)
        trade_cash -= reduce_from_cash
        locked -= debit - reduce_from_cash
        if locked < -PRICE_TOLERANCE:
            raise ValueError("locked collateral underflow")
        state.sponsors[key] = replace(
            sponsor,
            trade_cash_balance=trade_cash,
            locked_collateral=max(locked, DECIMAL_ZERO),
        )
        debits[key] = debit
    return debits


def _sync_state(state: SimulationState) -> SimulationState:
    pricing_sponsors = _pricing_sponsors(state)
    num_outcomes = state.pricing.num_outcomes

    if pricing_sponsors:
        aggregate_q = _sum_vector(
            [tuple(map(to_decimal, sponsor.current_q or tuple())) for sponsor in pricing_sponsors],
            length=num_outcomes,
        )
        state.pricing.depth_b = _total_depth(state)
        state.pricing.pricing_q = aggregate_q
        if state.pricing.status is MarketStatus.RESOLVED and state.winning_outcome is not None:
            state.pricing.price_vector = _resolved_price_vector(num_outcomes, state.winning_outcome)
        else:
            state.pricing.price_vector = lmsr_prices(aggregate_q, to_decimal(state.pricing.depth_b))
    else:
        state.pricing.depth_b = DECIMAL_ZERO
        state.pricing.pricing_q = _zero_vector(num_outcomes)
        if state.pricing.status is MarketStatus.RESOLVED and state.winning_outcome is not None:
            state.pricing.price_vector = _resolved_price_vector(num_outcomes, state.winning_outcome)
        elif state.pricing.status is MarketStatus.CANCELLED:
            state.pricing.price_vector = uniform_price_vector(num_outcomes)
        elif not state.pricing.price_vector:
            state.pricing.price_vector = uniform_price_vector(num_outcomes)

    for key in _sponsor_keys(state):
        sponsor = state.sponsors[key]
        residuals = _component_residuals(sponsor)
        if not residuals:
            residuals = _zero_vector(num_outcomes)
        state.sponsors[key] = replace(sponsor, residual_basis_by_outcome=residuals)
    return state


class ReferenceParallelLmsrEngine:
    def __init__(
        self,
        *,
        lp_fee_bps: Numeric = 0,
        protocol_fee_bps: Numeric = 0,
        residual_policy: str = STRICT_ALL_CLAIMED,
        residual_weight_scheme: str = "linear",
        residual_linear_lambda: Numeric = 1,
    ) -> None:
        self.lp_fee_bps = to_decimal(lp_fee_bps)
        self.protocol_fee_bps = to_decimal(protocol_fee_bps)
        self.residual_policy = residual_policy
        self.residual_weight_scheme = residual_weight_scheme
        self.residual_linear_lambda = to_decimal(residual_linear_lambda)

    def clone_state(self, state: SimulationState) -> SimulationState:
        return deepcopy(state)

    def price_vector(self, state: MarketPricingState) -> tuple[Decimal, ...]:
        return tuple(map(to_decimal, state.price_vector))

    def buy_cost(self, state: MarketPricingState, outcome_index: int, shares: Numeric) -> Decimal:
        return lmsr_cost_delta(
            tuple(map(to_decimal, state.pricing_q)),
            to_decimal(state.depth_b),
            outcome_index,
            to_decimal(shares),
        )

    def sell_return(self, state: MarketPricingState, outcome_index: int, shares: Numeric) -> Decimal:
        return lmsr_sell_return(
            tuple(map(to_decimal, state.pricing_q)),
            to_decimal(state.depth_b),
            outcome_index,
            to_decimal(shares),
        )

    def route_trade(self, state: SimulationState, event: BuyOutcome | SellOutcome) -> dict[str, Decimal]:
        return _route_by_depth(state, to_decimal(event.shares))

    def apply_lp_entry(self, state: SimulationState, event: LpEnterActive) -> dict[str, Decimal | SimulationState]:
        working = self.clone_state(state)
        if working.pricing.status is not MarketStatus.ACTIVE:
            raise ValueError("lp entry requires ACTIVE market")
        current_prices = _current_price_vector(working)
        expected_prices = tuple(map(to_decimal, event.expected_price_vector))
        if len(current_prices) != len(expected_prices):
            raise ValueError("expected_price_vector length mismatch")
        if max_abs_diff(current_prices, expected_prices) > to_decimal(event.price_tolerance):
            raise ValueError("stale LP entry price")
        delta_b = to_decimal(event.target_delta_b)
        if delta_b <= 0:
            raise ValueError("target_delta_b must be positive")
        if event.min_delta_b is not None and delta_b < to_decimal(event.min_delta_b):
            raise ValueError("target_delta_b below min_delta_b")
        required_deposit = collateral_required(delta_b, current_prices)
        if required_deposit > to_decimal(event.max_deposit):
            raise ValueError("max_deposit too small")
        cohort_id = f"{event.sponsor_id}:{working.event_index + 1}"
        baseline_q = normalized_q_from_prices(current_prices, delta_b)
        sponsor = SponsorPosition(
            sponsor_id=event.sponsor_id,
            cohort_id=cohort_id,
            entry_timestamp=event.timestamp,
            share_units=delta_b,
            target_delta_b=delta_b,
            collateral_posted=required_deposit,
            locked_collateral=required_deposit,
            withdrawable_fee_surplus=DECIMAL_ZERO,
            claimable_fees=DECIMAL_ZERO,
            fee_snapshot=DECIMAL_ZERO,
            entry_price_vector=current_prices,
            entry_gauge_alpha=gauge_alpha_from_prices(current_prices),
            baseline_q=baseline_q,
            current_q=baseline_q,
            trade_cash_balance=DECIMAL_ZERO,
        )
        working.sponsors[cohort_id] = sponsor
        working.treasury.contract_funds += required_deposit
        working.event_index += 1
        working.pricing.timestamp = event.timestamp
        return {"deposit_required": required_deposit, "state": _sync_state(working)}

    def mark_to_market_nav(self, state: SimulationState) -> dict[str, Decimal]:
        prices = _current_price_vector(state)
        nav: dict[str, Decimal] = {}
        for key in _sponsor_keys(state):
            sponsor = state.sponsors[key]
            if self.residual_policy == RESERVE_POOL and state.pricing.status in (MarketStatus.RESOLVED, MarketStatus.CANCELLED):
                residual_value = _claimable_residual_for_cohort(state, sponsor)
            elif state.pricing.status is MarketStatus.RESOLVED and state.winning_outcome is not None:
                if _aggregate_outstanding(state)[state.winning_outcome] == DECIMAL_ZERO:
                    residual_value = _available_non_fee_assets(sponsor)
                else:
                    residual_value = (sponsor.residual_basis_by_outcome or _component_residuals(sponsor))[state.winning_outcome]
            elif state.pricing.status is MarketStatus.CANCELLED:
                residual_value = _available_non_fee_assets(sponsor)
            else:
                residuals = sponsor.residual_basis_by_outcome or _component_residuals(sponsor)
                residual_value = sum(residual * price for residual, price in zip(residuals, prices))
            nav[key] = residual_value + to_decimal(sponsor.claimable_fees) + to_decimal(sponsor.withdrawable_fee_surplus)
        return nav

    def apply_event(self, state: SimulationState, event: SimulationEvent) -> SimulationState:
        working = self.clone_state(state)
        if isinstance(event, BootstrapMarket):
            if working.pricing.status is not MarketStatus.CREATED:
                raise ValueError("market already bootstrapped")
            if working.pricing.num_outcomes < 2:
                raise ValueError("num_outcomes must be at least 2")
            prices = uniform_price_vector(working.pricing.num_outcomes)
            depth_b = to_decimal(event.initial_depth_b)
            if depth_b <= 0:
                raise ValueError("initial_depth_b must be positive")
            initial_collateral = to_decimal(event.initial_collateral)
            required_collateral = collateral_required(depth_b, prices)
            if initial_collateral < required_collateral:
                raise ValueError("initial_collateral below LMSR funding floor")
            baseline_q = normalized_q_from_prices(prices, depth_b)
            cohort_id = f"{event.creator_id}:bootstrap"
            working.sponsors[cohort_id] = SponsorPosition(
                sponsor_id=event.creator_id,
                cohort_id=cohort_id,
                entry_timestamp=event.timestamp,
                share_units=depth_b,
                target_delta_b=depth_b,
                collateral_posted=initial_collateral,
                locked_collateral=initial_collateral,
                withdrawable_fee_surplus=DECIMAL_ZERO,
                claimable_fees=DECIMAL_ZERO,
                fee_snapshot=DECIMAL_ZERO,
                entry_price_vector=prices,
                entry_gauge_alpha=gauge_alpha_from_prices(prices),
                baseline_q=baseline_q,
                current_q=baseline_q,
                trade_cash_balance=DECIMAL_ZERO,
            )
            working.pricing.status = MarketStatus.ACTIVE
            working.pricing.timestamp = event.timestamp
            working.treasury.contract_funds = initial_collateral
            working.event_index += 1
            return _sync_state(working)

        if isinstance(event, LpEnterActive):
            result = self.apply_lp_entry(working, event)
            return result["state"]  # type: ignore[return-value]

        if isinstance(event, BuyOutcome):
            if working.pricing.status is not MarketStatus.ACTIVE:
                raise ValueError("buy requires ACTIVE market")
            shares = to_decimal(event.shares)
            if shares <= 0:
                raise ValueError("shares must be positive")
            _ensure_trader(working, event.trader_id)
            routed = self.route_trade(working, event)
            total_cost = DECIMAL_ZERO
            for key, routed_shares in routed.items():
                sponsor = working.sponsors[key]
                current_q = tuple(map(to_decimal, sponsor.current_q or tuple()))
                component_cost = lmsr_cost_delta(current_q, to_decimal(sponsor.target_delta_b), event.outcome_index, routed_shares)
                next_q = _set_tuple_entry(current_q, event.outcome_index, routed_shares)
                working.sponsors[key] = replace(
                    sponsor,
                    current_q=next_q,
                    trade_cash_balance=to_decimal(sponsor.trade_cash_balance) + component_cost,
                )
                total_cost += component_cost
            lp_fee = total_cost * self.lp_fee_bps / BPS_DENOMINATOR
            protocol_fee = total_cost * self.protocol_fee_bps / BPS_DENOMINATOR
            total_paid = total_cost + lp_fee + protocol_fee
            if total_paid > to_decimal(event.max_total_cost):
                raise ValueError("max_total_cost exceeded")
            positions = tuple(map(to_decimal, working.traders.positions_by_trader[event.trader_id]))
            basis = tuple(map(to_decimal, working.traders.cost_basis_by_trader[event.trader_id]))
            positions = _set_tuple_entry(positions, event.outcome_index, shares)
            basis = _set_tuple_entry(basis, event.outcome_index, total_cost)
            working.traders.positions_by_trader[event.trader_id] = positions
            working.traders.cost_basis_by_trader[event.trader_id] = basis
            aggregate = _aggregate_outstanding(working)
            working.traders.aggregate_outstanding_claims = _set_tuple_entry(aggregate, event.outcome_index, shares)
            working.treasury.contract_funds += total_paid
            working.treasury.protocol_fee_balance += protocol_fee
            _allocate_lp_fees(working, lp_fee)
            working.event_index += 1
            working.pricing.timestamp = event.timestamp
            return _sync_state(working)

        if isinstance(event, SellOutcome):
            if working.pricing.status is not MarketStatus.ACTIVE:
                raise ValueError("sell requires ACTIVE market")
            shares = to_decimal(event.shares)
            if shares <= 0:
                raise ValueError("shares must be positive")
            _ensure_trader(working, event.trader_id)
            positions = tuple(map(to_decimal, working.traders.positions_by_trader[event.trader_id]))
            basis = tuple(map(to_decimal, working.traders.cost_basis_by_trader[event.trader_id]))
            current_shares = positions[event.outcome_index]
            if current_shares < shares:
                raise ValueError("insufficient shares")
            routed = self.route_trade(working, event)
            gross_return = DECIMAL_ZERO
            for key, routed_shares in routed.items():
                sponsor = working.sponsors[key]
                current_q = tuple(map(to_decimal, sponsor.current_q or tuple()))
                component_return = lmsr_sell_return(
                    current_q,
                    to_decimal(sponsor.target_delta_b),
                    event.outcome_index,
                    routed_shares,
                )
                next_q = _set_tuple_entry(current_q, event.outcome_index, -routed_shares)
                working.sponsors[key] = replace(
                    sponsor,
                    current_q=next_q,
                    trade_cash_balance=to_decimal(sponsor.trade_cash_balance) - component_return,
                )
                gross_return += component_return
            lp_fee = gross_return * self.lp_fee_bps / BPS_DENOMINATOR
            protocol_fee = gross_return * self.protocol_fee_bps / BPS_DENOMINATOR
            net_return = gross_return - lp_fee - protocol_fee
            if net_return < to_decimal(event.min_total_return):
                raise ValueError("min_total_return not met")
            basis_reduction = _basis_reduction(current_shares, basis[event.outcome_index], shares)
            positions = _replace_tuple_entry(positions, event.outcome_index, current_shares - shares)
            basis = _replace_tuple_entry(basis, event.outcome_index, basis[event.outcome_index] - basis_reduction)
            working.traders.positions_by_trader[event.trader_id] = positions
            working.traders.cost_basis_by_trader[event.trader_id] = basis
            aggregate = _aggregate_outstanding(working)
            working.traders.aggregate_outstanding_claims = _replace_tuple_entry(
                aggregate,
                event.outcome_index,
                aggregate[event.outcome_index] - shares,
            )
            working.treasury.contract_funds -= net_return
            working.treasury.protocol_fee_balance += protocol_fee
            _allocate_lp_fees(working, lp_fee)
            working.event_index += 1
            working.pricing.timestamp = event.timestamp
            return _sync_state(working)

        if isinstance(event, ResolveMarket):
            if working.pricing.status is not MarketStatus.ACTIVE:
                raise ValueError("resolve requires ACTIVE market")
            if not 0 <= event.winning_outcome < working.pricing.num_outcomes:
                raise ValueError("winning_outcome out of range")
            working.pricing.status = MarketStatus.RESOLVED
            working.winning_outcome = event.winning_outcome
            working.settlement_timestamp = event.timestamp
            working.pricing.timestamp = event.timestamp
            working.event_index += 1
            return _sync_state(working)

        if isinstance(event, ClaimWinnings):
            if working.pricing.status is not MarketStatus.RESOLVED:
                raise ValueError("claim requires RESOLVED market")
            if working.winning_outcome != event.outcome_index:
                raise ValueError("only winning outcome may be claimed")
            _ensure_trader(working, event.trader_id)
            shares = to_decimal(event.shares)
            positions = tuple(map(to_decimal, working.traders.positions_by_trader[event.trader_id]))
            basis = tuple(map(to_decimal, working.traders.cost_basis_by_trader[event.trader_id]))
            current_shares = positions[event.outcome_index]
            if current_shares < shares:
                raise ValueError("insufficient shares")
            basis_reduction = _basis_reduction(current_shares, basis[event.outcome_index], shares)
            positions = _replace_tuple_entry(positions, event.outcome_index, current_shares - shares)
            basis = _replace_tuple_entry(basis, event.outcome_index, basis[event.outcome_index] - basis_reduction)
            working.traders.positions_by_trader[event.trader_id] = positions
            working.traders.cost_basis_by_trader[event.trader_id] = basis
            aggregate = _aggregate_outstanding(working)
            working.traders.aggregate_outstanding_claims = _replace_tuple_entry(
                aggregate,
                event.outcome_index,
                aggregate[event.outcome_index] - shares,
            )
            allocations = _reduce_component_outcome_claims(working, event.outcome_index, shares)
            for key, allocation in allocations.items():
                sponsor = working.sponsors[key]
                working.sponsors[key] = replace(
                    sponsor,
                    trade_cash_balance=to_decimal(sponsor.trade_cash_balance) - allocation,
                )
            working.treasury.contract_funds -= shares
            working.event_index += 1
            working.pricing.timestamp = event.timestamp
            return _sync_state(working)

        if isinstance(event, CancelMarket):
            if working.pricing.status is not MarketStatus.ACTIVE:
                raise ValueError("cancel requires ACTIVE market")
            working.pricing.status = MarketStatus.CANCELLED
            working.settlement_timestamp = event.timestamp
            working.pricing.timestamp = event.timestamp
            working.event_index += 1
            return _sync_state(working)

        if isinstance(event, ClaimRefund):
            if working.pricing.status is not MarketStatus.CANCELLED:
                raise ValueError("refund requires CANCELLED market")
            _ensure_trader(working, event.trader_id)
            shares = to_decimal(event.shares)
            if shares <= 0:
                raise ValueError("shares must be positive")
            positions = tuple(map(to_decimal, working.traders.positions_by_trader[event.trader_id]))
            basis = tuple(map(to_decimal, working.traders.cost_basis_by_trader[event.trader_id]))
            current_shares = positions[event.outcome_index]
            if current_shares < shares:
                raise ValueError("insufficient shares")
            basis_reduction = _basis_reduction(current_shares, basis[event.outcome_index], shares)
            positions = _replace_tuple_entry(positions, event.outcome_index, current_shares - shares)
            basis = _replace_tuple_entry(basis, event.outcome_index, basis[event.outcome_index] - basis_reduction)
            working.traders.positions_by_trader[event.trader_id] = positions
            working.traders.cost_basis_by_trader[event.trader_id] = basis
            aggregate = _aggregate_outstanding(working)
            working.traders.aggregate_outstanding_claims = _replace_tuple_entry(
                aggregate,
                event.outcome_index,
                aggregate[event.outcome_index] - shares,
            )
            _reduce_component_outcome_claims(working, event.outcome_index, shares)
            _debit_sponsor_assets(working, basis_reduction)
            working.treasury.contract_funds -= basis_reduction
            working.event_index += 1
            working.pricing.timestamp = event.timestamp
            return _sync_state(working)

        if isinstance(event, ClaimLpFees):
            matched = False
            for key in _sponsor_keys(working):
                sponsor = working.sponsors[key]
                if sponsor.sponsor_id != event.sponsor_id:
                    continue
                matched = True
                claimable = to_decimal(sponsor.claimable_fees)
                working.sponsors[key] = replace(
                    sponsor,
                    claimable_fees=DECIMAL_ZERO,
                    withdrawable_fee_surplus=to_decimal(sponsor.withdrawable_fee_surplus) + claimable,
                )
            if not matched:
                raise ValueError("unknown sponsor_id")
            working.event_index += 1
            working.pricing.timestamp = event.timestamp
            return _sync_state(working)

        if isinstance(event, WithdrawLpFees):
            amount = to_decimal(event.amount)
            if amount <= 0:
                raise ValueError("withdraw amount must be positive")
            cohort_keys = [key for key in _sponsor_keys(working) if working.sponsors[key].sponsor_id == event.sponsor_id]
            if not cohort_keys:
                raise ValueError("unknown sponsor_id")
            total_withdrawable = sum(to_decimal(working.sponsors[key].withdrawable_fee_surplus) for key in cohort_keys)
            if total_withdrawable < amount:
                raise ValueError("insufficient withdrawable LP fees")
            if to_decimal(working.treasury.lp_fee_balance) < amount:
                raise ValueError("LP fee balance underfunded")
            remaining = amount
            for idx, key in enumerate(cohort_keys):
                sponsor = working.sponsors[key]
                available = to_decimal(sponsor.withdrawable_fee_surplus)
                if idx == len(cohort_keys) - 1:
                    deduction = remaining
                else:
                    deduction = min(available, remaining)
                    remaining -= deduction
                working.sponsors[key] = replace(sponsor, withdrawable_fee_surplus=available - deduction)
            working.treasury.contract_funds -= amount
            working.treasury.lp_fee_balance -= amount
            working.event_index += 1
            working.pricing.timestamp = event.timestamp
            return _sync_state(working)

        if isinstance(event, ClaimLpResidual):
            if working.pricing.status not in (MarketStatus.RESOLVED, MarketStatus.CANCELLED):
                raise ValueError("LP residual claims require RESOLVED or CANCELLED market")
            payout = DECIMAL_ZERO
            matched = False
            if self.residual_policy == STRICT_ALL_CLAIMED:
                for key in _sponsor_keys(working):
                    sponsor = working.sponsors[key]
                    if sponsor.sponsor_id != event.sponsor_id:
                        continue
                    matched = True
                    if working.pricing.status is MarketStatus.RESOLVED:
                        winning_outcome = working.winning_outcome
                        if winning_outcome is None:
                            raise ValueError("winning outcome not set")
                        if _aggregate_outstanding(working)[winning_outcome] != DECIMAL_ZERO:
                            raise ValueError("all winner claims must be paid before LP residual claims")
                        cohort_payout = _available_non_fee_assets(sponsor)
                    else:
                        if any(outstanding != DECIMAL_ZERO for outstanding in _aggregate_outstanding(working)):
                            raise ValueError("all refunds must be paid before LP residual claims")
                        cohort_payout = _available_non_fee_assets(sponsor)
                    payout += cohort_payout
                    zero_q = _zero_vector(working.pricing.num_outcomes)
                    working.sponsors[key] = replace(
                        sponsor,
                        target_delta_b=DECIMAL_ZERO,
                        locked_collateral=DECIMAL_ZERO,
                        current_q=zero_q,
                        baseline_q=zero_q,
                        trade_cash_balance=DECIMAL_ZERO,
                        residual_basis_by_outcome=zero_q,
                    )
            else:
                updates: dict[str, Decimal] = {}
                for key in _sponsor_keys(working):
                    sponsor = working.sponsors[key]
                    if sponsor.sponsor_id != event.sponsor_id:
                        continue
                    matched = True
                    cohort_payout = _claimable_residual_for_cohort(working, sponsor)
                    payout += cohort_payout
                    updates[key] = to_decimal(sponsor.residual_claimed) + cohort_payout
                if payout > 0:
                    _debit_sponsor_assets(working, payout)
                    working.treasury.contract_funds -= payout
                for key, next_claimed in updates.items():
                    working.sponsors[key] = replace(working.sponsors[key], residual_claimed=next_claimed)
            if not matched:
                raise ValueError("unknown sponsor_id")
            if payout < DECIMAL_ZERO:
                raise ValueError("negative LP residual payout")
            if self.residual_policy == STRICT_ALL_CLAIMED:
                working.treasury.contract_funds -= payout
            working.event_index += 1
            working.pricing.timestamp = event.timestamp
            return _sync_state(working)

        raise TypeError(f"unsupported event type: {type(event)!r}")


class ReferenceInvariantChecker:
    def __init__(self, *, residual_policy: str = STRICT_ALL_CLAIMED) -> None:
        self.residual_policy = residual_policy

    def check_price_continuity(self, before: SimulationState, after: SimulationState) -> InvariantCheckResult:
        diff = max_abs_diff(_current_price_vector(before), _current_price_vector(after))
        return InvariantCheckResult(
            name="price_continuity",
            passed=diff <= PRICE_TOLERANCE,
            severity="error",
            details=f"max_diff={diff}",
            event_index=after.event_index,
        )

    def check_sponsor_solvency(self, state: SimulationState) -> InvariantCheckResult:
        min_margin = None
        for sponsor in _all_sponsors(state):
            residuals = sponsor.residual_basis_by_outcome or _component_residuals(sponsor)
            if not residuals:
                continue
            sponsor_min = min(residuals)
            min_margin = sponsor_min if min_margin is None else min(min_margin, sponsor_min)
        passed = min_margin is None or min_margin >= -PRICE_TOLERANCE
        return InvariantCheckResult(
            name="sponsor_solvency",
            passed=passed,
            severity="error",
            details=f"min_margin={min_margin if min_margin is not None else DECIMAL_ZERO}",
            event_index=state.event_index,
        )

    def check_winner_reserve_coverage(self, state: SimulationState) -> InvariantCheckResult:
        reserve_required = _winner_reserve_requirement(state)
        available = _total_non_fee_assets(state)
        margin = available - reserve_required
        return InvariantCheckResult(
            name="winner_reserve_coverage",
            passed=margin >= -PRICE_TOLERANCE,
            severity="error",
            details=f"available={available}, reserve_required={reserve_required}, margin={margin}",
            event_index=state.event_index,
        )

    def check_settlement_conservation(self, state: SimulationState) -> InvariantCheckResult:
        non_fee_assets = DECIMAL_ZERO
        for sponsor in _all_sponsors(state):
            non_fee_assets += to_decimal(sponsor.locked_collateral) + to_decimal(sponsor.trade_cash_balance)
        expected = non_fee_assets + to_decimal(state.treasury.lp_fee_balance) + to_decimal(state.treasury.protocol_fee_balance)
        diff = abs(to_decimal(state.treasury.contract_funds) - expected)
        return InvariantCheckResult(
            name="settlement_conservation",
            passed=diff <= PRICE_TOLERANCE,
            severity="error",
            details=f"diff={diff}",
            event_index=state.event_index,
        )

    def check_no_instantaneous_value_transfer(
        self, before: SimulationState, after: SimulationState
    ) -> InvariantCheckResult:
        if after.event_index == before.event_index:
            return InvariantCheckResult(
                name="no_instantaneous_value_transfer",
                passed=True,
                severity="error",
                details="no event applied",
                event_index=after.event_index,
            )
        engine = ReferenceParallelLmsrEngine()
        before_nav = engine.mark_to_market_nav(before)
        after_nav = engine.mark_to_market_nav(after)
        preexisting_keys = set(before_nav)
        max_change = DECIMAL_ZERO
        for key in preexisting_keys:
            max_change = max(max_change, abs(after_nav.get(key, DECIMAL_ZERO) - before_nav[key]))
        passed = max_change <= NAV_TOLERANCE
        return InvariantCheckResult(
            name="no_instantaneous_value_transfer",
            passed=passed,
            severity="error",
            details=f"max_preexisting_nav_change={max_change}",
            event_index=after.event_index,
        )

    def check_all(self, state: SimulationState) -> list[InvariantCheckResult]:
        aggregate = _aggregate_outstanding(state)
        trader_sum = [DECIMAL_ZERO for _ in aggregate]
        for position in state.traders.positions_by_trader.values():
            for idx, shares in enumerate(position):
                trader_sum[idx] += to_decimal(shares)

        checks = [
            InvariantCheckResult(
                name="aggregate_claims_match_traders",
                passed=all(abs(trader_sum[idx] - aggregate[idx]) <= PRICE_TOLERANCE for idx in range(len(aggregate))),
                severity="error",
                details=f"aggregate={aggregate}, trader_sum={tuple(trader_sum)}",
                event_index=state.event_index,
            ),
            self.check_settlement_conservation(state),
        ]
        if self.residual_policy == RESERVE_POOL:
            checks.append(self.check_winner_reserve_coverage(state))
        else:
            checks.append(self.check_sponsor_solvency(state))
        if state.pricing.status is MarketStatus.ACTIVE:
            component_prices = [
                lmsr_prices(tuple(map(to_decimal, sponsor.current_q or tuple())), to_decimal(sponsor.target_delta_b))
                for sponsor in _pricing_sponsors(state)
            ]
            aggregate_prices = _current_price_vector(state)
            max_component_diff = DECIMAL_ZERO
            for prices in component_prices:
                max_component_diff = max(max_component_diff, max_abs_diff(prices, aggregate_prices))
            checks.append(
                InvariantCheckResult(
                    name="component_alignment",
                    passed=max_component_diff <= Decimal("1e-16"),
                    severity="error",
                    details=f"max_component_diff={max_component_diff}",
                    event_index=state.event_index,
                )
            )
        return checks


class ReferenceMetricCollector:
    def __init__(self, *, residual_policy: str = STRICT_ALL_CLAIMED) -> None:
        self.residual_policy = residual_policy
        self.engine = ReferenceParallelLmsrEngine(residual_policy=residual_policy)

    def price_continuity(self, before: SimulationState, after: SimulationState) -> dict[str, object]:
        return {
            "before": _current_price_vector(before),
            "after": _current_price_vector(after),
            "max_abs_change": max_abs_diff(_current_price_vector(before), _current_price_vector(after)),
        }

    def slippage_report(
        self,
        before: SimulationState,
        after: SimulationState,
        reference_trades: list[SimulationEvent],
    ) -> dict[str, object]:
        engine = ReferenceParallelLmsrEngine()
        rows: list[dict[str, object]] = []
        for event in reference_trades:
            if isinstance(event, BuyOutcome):
                before_cost = engine.buy_cost(before.pricing, event.outcome_index, event.shares)
                after_cost = engine.buy_cost(after.pricing, event.outcome_index, event.shares)
                rows.append(
                    {
                        "kind": "buy",
                        "outcome": event.outcome_index,
                        "shares": event.shares,
                        "before_cost": before_cost,
                        "after_cost": after_cost,
                        "improvement_ratio": after_cost / before_cost if before_cost > 0 else DECIMAL_ONE,
                    }
                )
            elif isinstance(event, SellOutcome):
                before_return = engine.sell_return(before.pricing, event.outcome_index, event.shares)
                after_return = engine.sell_return(after.pricing, event.outcome_index, event.shares)
                rows.append(
                    {
                        "kind": "sell",
                        "outcome": event.outcome_index,
                        "shares": event.shares,
                        "before_return": before_return,
                        "after_return": after_return,
                        "improvement_ratio": before_return / after_return if after_return > 0 else DECIMAL_ONE,
                    }
                )
        return {"rows": rows}

    def lp_fairness(self, final_state: SimulationState) -> dict[str, object]:
        nav = self.engine.mark_to_market_nav(final_state)
        rows = []
        for key in _sponsor_keys(final_state):
            sponsor = final_state.sponsors[key]
            collateral = to_decimal(sponsor.collateral_posted)
            risk_capital = collateral if collateral > 0 else DECIMAL_ONE
            nav_value = nav[key]
            rows.append(
                {
                    "cohort_id": key,
                    "sponsor_id": sponsor.sponsor_id,
                    "entry_timestamp": sponsor.entry_timestamp,
                    "nav": nav_value,
                    "nav_per_deposit": nav_value / collateral if collateral > 0 else DECIMAL_ZERO,
                    "nav_per_risk": nav_value / risk_capital,
                }
            )
        return {"rows": rows}

    def solvency_report(self, state: SimulationState) -> dict[str, object]:
        checker = ReferenceInvariantChecker(residual_policy=self.residual_policy)
        if self.residual_policy == RESERVE_POOL:
            result = checker.check_winner_reserve_coverage(state)
        else:
            result = checker.check_sponsor_solvency(state)
        return {"passed": result.passed, "details": result.details}

    def path_dependence(self, states: list[SimulationState]) -> dict[str, object]:
        if not states:
            return {
                "terminal_states": 0,
                "max_price_diff": DECIMAL_ZERO,
                "max_funds_diff": DECIMAL_ZERO,
                "max_residual_claimed_diff": DECIMAL_ZERO,
            }
        reference_state = states[0]
        max_price_diff = DECIMAL_ZERO
        max_funds_diff = DECIMAL_ZERO
        max_residual_claimed_diff = DECIMAL_ZERO
        for state in states[1:]:
            max_price_diff = max(max_price_diff, max_abs_diff(_current_price_vector(reference_state), _current_price_vector(state)))
            max_funds_diff = max(
                max_funds_diff,
                abs(to_decimal(reference_state.treasury.contract_funds) - to_decimal(state.treasury.contract_funds)),
            )
            for key in sorted(set(reference_state.sponsors) | set(state.sponsors)):
                reference_claimed = to_decimal(reference_state.sponsors.get(key).residual_claimed if key in reference_state.sponsors else 0)
                state_claimed = to_decimal(state.sponsors.get(key).residual_claimed if key in state.sponsors else 0)
                max_residual_claimed_diff = max(max_residual_claimed_diff, abs(reference_claimed - state_claimed))
        return {
            "terminal_states": len(states),
            "max_price_diff": max_price_diff,
            "max_funds_diff": max_funds_diff,
            "max_residual_claimed_diff": max_residual_claimed_diff,
        }

    def residual_release(self, state: SimulationState) -> dict[str, object]:
        rows: list[dict[str, object]] = []
        for key in _sponsor_keys(state):
            sponsor = state.sponsors[key]
            rows.append(
                {
                    "cohort_id": key,
                    "sponsor_id": sponsor.sponsor_id,
                    "share_units": to_decimal(sponsor.share_units),
                    "time_weight": _cohort_time_weight(state, sponsor),
                    "residual_weight": _cohort_residual_weight(state, sponsor),
                    "share_fraction": (
                        max(DECIMAL_ZERO, to_decimal(sponsor.share_units)) / _total_share_units(state)
                        if _total_share_units(state) > 0
                        else DECIMAL_ZERO
                    ),
                    "residual_weight_fraction": _cohort_residual_share(state, sponsor),
                    "residual_claimed": to_decimal(sponsor.residual_claimed),
                    "claimable_residual": _claimable_residual_for_cohort(state, sponsor),
                }
            )
        return {
            "policy": self.residual_policy,
            "weight_scheme": state.residual_weight_scheme,
            "weight_lambda": to_decimal(state.residual_linear_lambda),
            "reserve_required": _winner_reserve_requirement(state),
            "available_non_fee_assets": _total_non_fee_assets(state),
            "releasable_pool": _releasable_residual_pool(state),
            "total_residual_claimed": _total_residual_claimed(state),
            "rows": rows,
        }

    def divergence(
        self,
        reference_result: CanonicalEvaluation,
        candidate_result: CanonicalEvaluation,
    ) -> dict[str, object]:
        return {"implemented": False, "reference": reference_result, "candidate": candidate_result}

    def protocol_complexity(self, state_history: list[SimulationState]) -> dict[str, object]:
        max_cohorts = 0
        for state in state_history:
            max_cohorts = max(max_cohorts, len(state.sponsors))
        return {"max_cohorts": max_cohorts, "active_path_complexity": "O(num_cohorts)"}


class ReferenceScenarioRunner:
    def __init__(
        self,
        num_outcomes: int,
        *,
        engine: ReferenceParallelLmsrEngine | None = None,
        invariant_checker: ReferenceInvariantChecker | None = None,
        collector: ReferenceMetricCollector | None = None,
        reference_trade_size: Numeric = 1,
        reference_trades: tuple[SimulationEvent, ...] | None = None,
    ) -> None:
        self.num_outcomes = num_outcomes
        self.engine = engine or ReferenceParallelLmsrEngine()
        self.collector = collector or ReferenceMetricCollector(residual_policy=self.engine.residual_policy)
        self.invariant_checker = invariant_checker or ReferenceInvariantChecker(residual_policy=self.engine.residual_policy)
        self.reference_trade_size = to_decimal(reference_trade_size)
        self.reference_trades = reference_trades

    def run(self, events: list[SimulationEvent], mechanism: MechanismVariant) -> CanonicalEvaluation:
        if mechanism not in (
            MechanismVariant.REFERENCE_PARALLEL_LMSR,
            MechanismVariant.REFERENCE_PARALLEL_LMSR_RESERVE_RESIDUAL,
        ):
            raise ValueError("ReferenceScenarioRunner only supports reference mechanism variants")
        state = create_initial_state(self.num_outcomes, mechanism=mechanism)
        state.residual_weight_scheme = self.engine.residual_weight_scheme
        state.residual_linear_lambda = self.engine.residual_linear_lambda
        state_history = [self.engine.clone_state(state)]
        price_reports: list[dict[str, object]] = []
        slippage_reports: list[dict[str, object]] = []
        invariant_results: list[InvariantCheckResult] = []
        fairness_snapshot: SimulationState | None = None

        for event in events:
            before = self.engine.clone_state(state)
            if fairness_snapshot is None and isinstance(event, ClaimLpResidual):
                fairness_snapshot = self.engine.clone_state(before)
            state = self.engine.apply_event(state, event)
            state_history.append(self.engine.clone_state(state))
            invariant_results.extend(self.invariant_checker.check_all(state))
            if isinstance(event, LpEnterActive):
                price_reports.append(self.collector.price_continuity(before, state))
                reference_trades = list(self.reference_trades) if self.reference_trades is not None else [
                    BuyOutcome(
                        timestamp=event.timestamp,
                        trader_id="__probe__",
                        outcome_index=outcome_index,
                        shares=self.reference_trade_size,
                        max_total_cost=Decimal("1e50"),
                    )
                    for outcome_index in range(self.num_outcomes)
                ]
                slippage_reports.append(self.collector.slippage_report(before, state, reference_trades))

        max_price_change = max((report["max_abs_change"] for report in price_reports), default=DECIMAL_ZERO)
        all_slippage_improved = True
        for report in slippage_reports:
            for row in report["rows"]:
                if row["kind"] == "buy" and row["after_cost"] > row["before_cost"]:
                    all_slippage_improved = False

        fairness_state = fairness_snapshot or state
        solvency_invariant = "winner_reserve_coverage" if self.collector.residual_policy == RESERVE_POOL else "sponsor_solvency"

        return CanonicalEvaluation(
            price_continuity={
                "entries": price_reports,
                "max_abs_change": max_price_change,
                "all_within_tolerance": max_price_change <= PRICE_TOLERANCE,
            },
            slippage_improvement={
                "entries": slippage_reports,
                "all_buy_quotes_improved": all_slippage_improved,
            },
            lp_fairness_by_entry_time=self.collector.lp_fairness(fairness_state),
            residual_release=self.collector.residual_release(state),
            solvency={
                **self.collector.solvency_report(state),
                "invariants": [result for result in invariant_results if result.name == solvency_invariant],
            },
            path_dependence={
                **self.collector.path_dependence([state_history[-1]]),
                "events_processed": len(events),
            },
            exact_vs_simplified_divergence={
                "implemented": False,
                "invariant_failures": [result for result in invariant_results if not result.passed],
            },
        )

    def compare(
        self,
        events: list[SimulationEvent],
        mechanisms: list[MechanismVariant],
    ) -> dict[MechanismVariant, CanonicalEvaluation]:
        results: dict[MechanismVariant, CanonicalEvaluation] = {}
        for mechanism in mechanisms:
            results[mechanism] = self.run(events, mechanism)
        return results


def create_initial_state(
    num_outcomes: int,
    *,
    mechanism: MechanismVariant = MechanismVariant.REFERENCE_PARALLEL_LMSR,
    residual_weight_scheme: str = "linear",
    residual_linear_lambda: Numeric = 1,
) -> SimulationState:
    zero_prices = uniform_price_vector(num_outcomes)
    return SimulationState(
        mechanism=mechanism,
        pricing=MarketPricingState(
            num_outcomes=num_outcomes,
            pricing_q=_zero_vector(num_outcomes),
            depth_b=DECIMAL_ZERO,
            price_vector=zero_prices,
            status=MarketStatus.CREATED,
            timestamp=0,
        ),
        traders=TraderPositionBook(aggregate_outstanding_claims=_zero_vector(num_outcomes)),
        sponsors={},
        treasury=TreasuryState(contract_funds=DECIMAL_ZERO),
        settlement_timestamp=None,
        residual_weight_scheme=residual_weight_scheme,
        residual_linear_lambda=residual_linear_lambda,
    )
