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
from research.active_lp.precision import DECIMAL_ONE, DECIMAL_ZERO, to_decimal
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
from research.active_lp.reference_parallel_lmsr import (
    BPS_DENOMINATOR,
    NAV_TOLERANCE,
    PRICE_TOLERANCE,
    RESERVE_POOL,
    ReferenceParallelLmsrEngine,
    STRICT_ALL_CLAIMED,
    _aggregate_outstanding,
    _all_sponsors,
    _available_non_fee_assets,
    _basis_reduction,
    _claimable_residual_for_cohort,
    _cohort_residual_share,
    _cohort_residual_weight,
    _cohort_time_weight,
    _current_price_vector,
    _debit_sponsor_assets,
    _ensure_trader,
    _releasable_residual_pool,
    _replace_tuple_entry,
    _set_tuple_entry,
    _sponsor_keys,
    _total_non_fee_assets,
    _total_residual_claimed,
    _winner_reserve_requirement,
    _zero_vector,
)
from research.active_lp.state import MarketPricingState, SimulationState, SponsorPosition, TraderPositionBook, TreasuryState
from research.active_lp.types import ActorId, MarketStatus, MechanismVariant, Numeric


def _active_sponsors(state: SimulationState) -> list[SponsorPosition]:
    active: list[SponsorPosition] = []
    for sponsor in _all_sponsors(state):
        if to_decimal(sponsor.target_delta_b) <= 0:
            continue
        active.append(sponsor)
    return active


def _total_depth(state: SimulationState) -> Decimal:
    total = DECIMAL_ZERO
    for sponsor in _active_sponsors(state):
        total += to_decimal(sponsor.target_delta_b)
    return total


def _cohort_net_claims(state: SimulationState, sponsor: SponsorPosition) -> tuple[Decimal, ...]:
    if sponsor.net_outcome_claims is not None:
        return tuple(map(to_decimal, sponsor.net_outcome_claims))
    return _zero_vector(state.pricing.num_outcomes)


def _component_residuals(state: SimulationState, sponsor: SponsorPosition) -> tuple[Decimal, ...]:
    locked = to_decimal(sponsor.locked_collateral)
    trade_cash = to_decimal(sponsor.trade_cash_balance)
    net_claims = _cohort_net_claims(state, sponsor)
    return tuple(locked + trade_cash - claim for claim in net_claims)


def _sync_state(state: SimulationState) -> SimulationState:
    num_outcomes = state.pricing.num_outcomes
    total_depth = _total_depth(state)
    state.pricing.depth_b = total_depth
    if state.pricing.status is MarketStatus.ACTIVE and total_depth > 0:
        state.pricing.price_vector = lmsr_prices(tuple(map(to_decimal, state.pricing.pricing_q)), total_depth)
    elif state.pricing.status is MarketStatus.RESOLVED and state.winning_outcome is not None:
        vector = [DECIMAL_ZERO for _ in range(num_outcomes)]
        vector[state.winning_outcome] = DECIMAL_ONE
        state.pricing.price_vector = tuple(vector)
    elif state.pricing.status is MarketStatus.CANCELLED:
        state.pricing.price_vector = uniform_price_vector(num_outcomes)
    elif not state.pricing.price_vector:
        state.pricing.price_vector = uniform_price_vector(num_outcomes)

    for key in _sponsor_keys(state):
        sponsor = state.sponsors[key]
        state.sponsors[key] = replace(
            sponsor,
            residual_basis_by_outcome=_component_residuals(state, sponsor),
        )
    return state


def _route_by_depth(state: SimulationState, shares: Decimal) -> dict[str, Decimal]:
    total_depth = _total_depth(state)
    if total_depth <= 0:
        raise ValueError("total depth must be positive")
    active = [sponsor.cohort_id for sponsor in _active_sponsors(state)]
    routed: dict[str, Decimal] = {}
    remaining = shares
    for idx, key in enumerate(active):
        sponsor = state.sponsors[key]
        if idx == len(active) - 1:
            routed[key] = remaining
            break
        weight = to_decimal(sponsor.target_delta_b) / total_depth
        cohort_shares = shares * weight
        routed[key] = cohort_shares
        remaining -= cohort_shares
    return routed


def _allocate_lp_fees(state: SimulationState, lp_fee: Decimal) -> None:
    if lp_fee <= 0:
        return
    total_depth = _total_depth(state)
    if total_depth <= 0:
        return
    state.treasury.lp_fee_balance += lp_fee
    remaining = lp_fee
    active = [sponsor.cohort_id for sponsor in _active_sponsors(state)]
    for idx, key in enumerate(active):
        sponsor = state.sponsors[key]
        if idx == len(active) - 1:
            fee_share = remaining
        else:
            fee_share = lp_fee * (to_decimal(sponsor.share_units) / total_depth)
            remaining -= fee_share
        state.sponsors[key] = replace(sponsor, claimable_fees=to_decimal(sponsor.claimable_fees) + fee_share)


def _reduce_cohort_outcome_claims(state: SimulationState, outcome_index: int, shares: Decimal) -> dict[str, Decimal]:
    positive_rows: list[tuple[str, Decimal]] = []
    total_positive = DECIMAL_ZERO
    for key in _sponsor_keys(state):
        sponsor = state.sponsors[key]
        claims = _cohort_net_claims(state, sponsor)
        liability = claims[outcome_index]
        if liability > 0:
            positive_rows.append((key, liability))
            total_positive += liability
    if total_positive + PRICE_TOLERANCE < shares:
        raise ValueError("insufficient cohort liability for claim")

    allocations: dict[str, Decimal] = {}
    remaining = shares
    for idx, (key, liability) in enumerate(positive_rows):
        sponsor = state.sponsors[key]
        claims = _cohort_net_claims(state, sponsor)
        if idx == len(positive_rows) - 1:
            allocation = remaining
        else:
            allocation = shares * liability / total_positive
            remaining -= allocation
        next_claims = _set_tuple_entry(claims, outcome_index, -allocation)
        state.sponsors[key] = replace(sponsor, net_outcome_claims=next_claims)
        allocations[key] = allocation
    return allocations


def _component_q_from_prices(prices: tuple[Decimal, ...], depth_b: Decimal) -> tuple[Decimal, ...]:
    if depth_b <= 0:
        raise ValueError("depth_b must be positive")
    return normalized_q_from_prices(prices, depth_b)


class CandidateGlobalStateEngine:
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
        zero_claims = _zero_vector(working.pricing.num_outcomes)
        working.sponsors[cohort_id] = SponsorPosition(
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
            residual_basis_by_outcome=tuple(required_deposit for _ in range(working.pricing.num_outcomes)),
            net_outcome_claims=zero_claims,
            trade_cash_balance=DECIMAL_ZERO,
            residual_claimed=DECIMAL_ZERO,
        )
        new_depth = _total_depth(working)
        working.pricing.depth_b = new_depth
        working.pricing.pricing_q = normalized_q_from_prices(current_prices, new_depth)
        working.treasury.contract_funds += required_deposit
        working.pricing.timestamp = event.timestamp
        working.event_index += 1
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
                    residual_value = (sponsor.residual_basis_by_outcome or _component_residuals(state, sponsor))[
                        state.winning_outcome
                    ]
            elif state.pricing.status is MarketStatus.CANCELLED:
                residual_value = _available_non_fee_assets(sponsor)
            else:
                residuals = sponsor.residual_basis_by_outcome or _component_residuals(state, sponsor)
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
            cohort_id = f"{event.creator_id}:bootstrap"
            zero_claims = _zero_vector(working.pricing.num_outcomes)
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
                residual_basis_by_outcome=tuple(initial_collateral for _ in range(working.pricing.num_outcomes)),
                net_outcome_claims=zero_claims,
                trade_cash_balance=DECIMAL_ZERO,
                residual_claimed=DECIMAL_ZERO,
            )
            working.pricing.status = MarketStatus.ACTIVE
            working.pricing.timestamp = event.timestamp
            working.pricing.depth_b = depth_b
            working.pricing.pricing_q = normalized_q_from_prices(prices, depth_b)
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
            current_prices = _current_price_vector(working)
            routed = self.route_trade(working, event)
            total_cost = DECIMAL_ZERO
            global_cost = self.buy_cost(working.pricing, event.outcome_index, shares)
            for key, routed_shares in routed.items():
                sponsor = working.sponsors[key]
                component_q = _component_q_from_prices(current_prices, to_decimal(sponsor.target_delta_b))
                component_cost = lmsr_cost_delta(
                    component_q,
                    to_decimal(sponsor.target_delta_b),
                    event.outcome_index,
                    routed_shares,
                )
                claims = _cohort_net_claims(working, sponsor)
                next_claims = _set_tuple_entry(claims, event.outcome_index, routed_shares)
                working.sponsors[key] = replace(
                    sponsor,
                    net_outcome_claims=next_claims,
                    trade_cash_balance=to_decimal(sponsor.trade_cash_balance) + component_cost,
                )
                total_cost += component_cost
            if abs(total_cost - global_cost) > Decimal("1e-16"):
                raise ValueError("candidate buy routing diverged from aggregate quote")
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
            working.pricing.pricing_q = _set_tuple_entry(tuple(map(to_decimal, working.pricing.pricing_q)), event.outcome_index, shares)
            working.treasury.contract_funds += total_paid
            working.treasury.protocol_fee_balance += protocol_fee
            _allocate_lp_fees(working, lp_fee)
            working.pricing.timestamp = event.timestamp
            working.event_index += 1
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
            current_prices = _current_price_vector(working)
            routed = self.route_trade(working, event)
            gross_return = DECIMAL_ZERO
            global_return = self.sell_return(working.pricing, event.outcome_index, shares)
            for key, routed_shares in routed.items():
                sponsor = working.sponsors[key]
                component_q = _component_q_from_prices(current_prices, to_decimal(sponsor.target_delta_b))
                component_return = lmsr_sell_return(
                    component_q,
                    to_decimal(sponsor.target_delta_b),
                    event.outcome_index,
                    routed_shares,
                )
                claims = _cohort_net_claims(working, sponsor)
                next_claims = _set_tuple_entry(claims, event.outcome_index, -routed_shares)
                working.sponsors[key] = replace(
                    sponsor,
                    net_outcome_claims=next_claims,
                    trade_cash_balance=to_decimal(sponsor.trade_cash_balance) - component_return,
                )
                gross_return += component_return
            if abs(gross_return - global_return) > Decimal("1e-16"):
                raise ValueError("candidate sell routing diverged from aggregate quote")
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
            working.pricing.pricing_q = _set_tuple_entry(tuple(map(to_decimal, working.pricing.pricing_q)), event.outcome_index, -shares)
            working.treasury.contract_funds -= net_return
            working.treasury.protocol_fee_balance += protocol_fee
            _allocate_lp_fees(working, lp_fee)
            working.pricing.timestamp = event.timestamp
            working.event_index += 1
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
            allocations = _reduce_cohort_outcome_claims(working, event.outcome_index, shares)
            for key, allocation in allocations.items():
                sponsor = working.sponsors[key]
                working.sponsors[key] = replace(
                    sponsor,
                    trade_cash_balance=to_decimal(sponsor.trade_cash_balance) - allocation,
                )
            working.treasury.contract_funds -= shares
            working.pricing.timestamp = event.timestamp
            working.event_index += 1
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
            _reduce_cohort_outcome_claims(working, event.outcome_index, shares)
            _debit_sponsor_assets(working, basis_reduction)
            working.treasury.contract_funds -= basis_reduction
            working.pricing.timestamp = event.timestamp
            working.event_index += 1
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
            working.pricing.timestamp = event.timestamp
            working.event_index += 1
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
            working.pricing.timestamp = event.timestamp
            working.event_index += 1
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
                        residual_basis_by_outcome=zero_q,
                        net_outcome_claims=zero_q,
                        trade_cash_balance=DECIMAL_ZERO,
                        baseline_q=zero_q,
                        current_q=zero_q,
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
            working.pricing.timestamp = event.timestamp
            working.event_index += 1
            return _sync_state(working)

        raise TypeError(f"unsupported event type: {type(event)!r}")


class CandidateInvariantChecker:
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
            residuals = sponsor.residual_basis_by_outcome or _component_residuals(state, sponsor)
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
        engine = CandidateGlobalStateEngine()
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
        if state.pricing.status is MarketStatus.ACTIVE and to_decimal(state.pricing.depth_b) > 0:
            derived_prices = lmsr_prices(tuple(map(to_decimal, state.pricing.pricing_q)), to_decimal(state.pricing.depth_b))
            max_price_diff = max_abs_diff(derived_prices, _current_price_vector(state))
            checks.append(
                InvariantCheckResult(
                    name="aggregate_pricing_consistency",
                    passed=max_price_diff <= Decimal("1e-16"),
                    severity="error",
                    details=f"max_price_diff={max_price_diff}",
                    event_index=state.event_index,
                )
            )
        return checks


class CandidateMetricCollector:
    def __init__(self, *, residual_policy: str = STRICT_ALL_CLAIMED) -> None:
        self.residual_policy = residual_policy
        self.engine = CandidateGlobalStateEngine(residual_policy=residual_policy)
        self.reference_collector = ReferenceParallelLmsrEngine()

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
        rows: list[dict[str, object]] = []
        for event in reference_trades:
            if isinstance(event, BuyOutcome):
                before_cost = self.engine.buy_cost(before.pricing, event.outcome_index, event.shares)
                after_cost = self.engine.buy_cost(after.pricing, event.outcome_index, event.shares)
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
                before_return = self.engine.sell_return(before.pricing, event.outcome_index, event.shares)
                after_return = self.engine.sell_return(after.pricing, event.outcome_index, event.shares)
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
        checker = CandidateInvariantChecker(residual_policy=self.residual_policy)
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
                        max(DECIMAL_ZERO, to_decimal(sponsor.share_units)) / _total_depth(state)
                        if _total_depth(state) > 0
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
        reference_price_entries = list(reference_result.price_continuity.get("entries", []))
        candidate_price_entries = list(candidate_result.price_continuity.get("entries", []))
        max_price_vector_diff = DECIMAL_ZERO
        for ref_entry, cand_entry in zip(reference_price_entries, candidate_price_entries):
            max_price_vector_diff = max(
                max_price_vector_diff,
                max_abs_diff(tuple(ref_entry["after"]), tuple(cand_entry["after"])),
            )

        reference_slippage_entries = list(reference_result.slippage_improvement.get("entries", []))
        candidate_slippage_entries = list(candidate_result.slippage_improvement.get("entries", []))
        max_quote_diff = DECIMAL_ZERO
        for ref_report, cand_report in zip(reference_slippage_entries, candidate_slippage_entries):
            for ref_row, cand_row in zip(ref_report["rows"], cand_report["rows"]):
                if ref_row["kind"] == "buy":
                    max_quote_diff = max(
                        max_quote_diff,
                        abs(to_decimal(ref_row["before_cost"]) - to_decimal(cand_row["before_cost"])),
                        abs(to_decimal(ref_row["after_cost"]) - to_decimal(cand_row["after_cost"])),
                    )
                else:
                    max_quote_diff = max(
                        max_quote_diff,
                        abs(to_decimal(ref_row["before_return"]) - to_decimal(cand_row["before_return"])),
                        abs(to_decimal(ref_row["after_return"]) - to_decimal(cand_row["after_return"])),
                    )

        ref_fairness = {row["cohort_id"]: row for row in reference_result.lp_fairness_by_entry_time.get("rows", [])}
        cand_fairness = {row["cohort_id"]: row for row in candidate_result.lp_fairness_by_entry_time.get("rows", [])}
        common_cohorts = sorted(set(ref_fairness) & set(cand_fairness))
        max_nav_diff = DECIMAL_ZERO
        max_nav_per_deposit_diff = DECIMAL_ZERO
        for key in common_cohorts:
            max_nav_diff = max(max_nav_diff, abs(to_decimal(ref_fairness[key]["nav"]) - to_decimal(cand_fairness[key]["nav"])))
            max_nav_per_deposit_diff = max(
                max_nav_per_deposit_diff,
                abs(
                    to_decimal(ref_fairness[key]["nav_per_deposit"])
                    - to_decimal(cand_fairness[key]["nav_per_deposit"])
                ),
            )

        return {
            "implemented": True,
            "matching_cohort_count": len(common_cohorts),
            "max_price_entry_diff_vs_reference": max_price_vector_diff,
            "max_quote_diff_vs_reference": max_quote_diff,
            "max_nav_diff_vs_reference": max_nav_diff,
            "max_nav_per_deposit_diff_vs_reference": max_nav_per_deposit_diff,
            "solvency_match": reference_result.solvency.get("passed") == candidate_result.solvency.get("passed"),
        }

    def protocol_complexity(self, state_history: list[SimulationState]) -> dict[str, object]:
        max_cohorts = 0
        for state in state_history:
            max_cohorts = max(max_cohorts, len(state.sponsors))
        return {
            "max_cohorts": max_cohorts,
            "active_path_complexity": "O(num_cohorts)",
            "pricing_state": "O(num_outcomes)",
            "settlement_state": "O(num_cohorts * num_outcomes)",
        }


class CandidateScenarioRunner:
    def __init__(
        self,
        num_outcomes: int,
        *,
        engine: CandidateGlobalStateEngine | None = None,
        invariant_checker: CandidateInvariantChecker | None = None,
        collector: CandidateMetricCollector | None = None,
        reference_trade_size: Numeric = 1,
        reference_trades: tuple[SimulationEvent, ...] | None = None,
    ) -> None:
        self.num_outcomes = num_outcomes
        self.engine = engine or CandidateGlobalStateEngine()
        self.collector = collector or CandidateMetricCollector(residual_policy=self.engine.residual_policy)
        self.invariant_checker = invariant_checker or CandidateInvariantChecker(residual_policy=self.engine.residual_policy)
        self.reference_trade_size = to_decimal(reference_trade_size)
        self.reference_trades = reference_trades

    def run(self, events: list[SimulationEvent], mechanism: MechanismVariant) -> CanonicalEvaluation:
        if mechanism not in (
            MechanismVariant.GLOBAL_STATE_FUNGIBLE_FEES_COHORT_RESIDUAL,
            MechanismVariant.GLOBAL_STATE_FUNGIBLE_FEES_RESERVE_RESIDUAL,
        ):
            raise ValueError("CandidateScenarioRunner only supports candidate mechanism variants")
        state = create_candidate_initial_state(self.num_outcomes, mechanism=mechanism)
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


def create_candidate_initial_state(
    num_outcomes: int,
    *,
    mechanism: MechanismVariant = MechanismVariant.GLOBAL_STATE_FUNGIBLE_FEES_COHORT_RESIDUAL,
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
