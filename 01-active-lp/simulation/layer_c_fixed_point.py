from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

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
from research.active_lp.reference_math import max_abs_diff, uniform_price_vector
from research.active_lp.reference_parallel_lmsr import (
    BPS_DENOMINATOR,
    _aggregate_outstanding,
    _all_sponsors,
    _available_non_fee_assets,
    _basis_reduction,
    _current_price_vector,
    _debit_sponsor_assets,
    _ensure_trader,
    _replace_tuple_entry,
    _set_tuple_entry,
    _sponsor_keys,
    _zero_vector,
)
from research.active_lp.state import MarketPricingState, SimulationState, SponsorPosition, TraderPositionBook, TreasuryState
from research.active_lp.types import MarketStatus, MechanismVariant, Numeric
from smart_contracts.lmsr_math import SCALE as AVM_SCALE
from smart_contracts.lmsr_math import lmsr_cost_delta as avm_lmsr_cost_delta
from smart_contracts.lmsr_math import lmsr_liquidity_scale as avm_lmsr_liquidity_scale
from smart_contracts.lmsr_math import lmsr_prices as avm_lmsr_prices
from smart_contracts.lmsr_math import lmsr_sell_return as avm_lmsr_sell_return

FP_PRICE_TOLERANCE = Decimal("0.000005")
FP_NAV_TOLERANCE = Decimal("0.00005")
FP_PRICE_FLOOR = 1
FP_ENTRY_SAFETY_MARGIN = 1
FP_ORDER_TOLERANCE = Decimal("10")
FP_STALE_REJECTION_TOLERANCE = Decimal("0.01")
AVM_AMOUNT_SCALE = Decimal("1000000")


def _to_uint64(value: Numeric, *, name: str) -> int:
    decimal_value = to_decimal(value)
    if decimal_value < 0:
        raise ValueError(f"{name} must be non-negative")
    integer_value = int(decimal_value)
    if decimal_value != integer_value:
        raise ValueError(f"{name} must be an integer-compatible quantity")
    return integer_value


def _ceil_uint64(value: Numeric, *, name: str) -> int:
    decimal_value = to_decimal(value)
    if decimal_value < 0:
        raise ValueError(f"{name} must be non-negative")
    return int(decimal_value.to_integral_value(rounding=ROUND_CEILING))


def _amount_to_fp(value: Numeric, *, rounding=ROUND_CEILING, name: str = "amount") -> int:
    decimal_value = to_decimal(value)
    if decimal_value < 0:
        raise ValueError(f"{name} must be non-negative")
    scaled = (decimal_value * AVM_AMOUNT_SCALE).to_integral_value(rounding=rounding)
    return int(scaled)


def _fp_to_amount(value_fp: int | Decimal) -> Decimal:
    return to_decimal(value_fp) / AVM_AMOUNT_SCALE


def _active_sponsors(state: SimulationState) -> list[SponsorPosition]:
    active: list[SponsorPosition] = []
    for sponsor in _all_sponsors(state):
        if to_decimal(sponsor.target_delta_b) <= 0:
            continue
        active.append(sponsor)
    return active


def _total_depth_u64(state: SimulationState) -> int:
    total = 0
    for sponsor in _active_sponsors(state):
        total += _amount_to_fp(sponsor.target_delta_b, name="target_delta_b")
    return total


def _cohort_net_claims(state: SimulationState, sponsor: SponsorPosition) -> tuple[Decimal, ...]:
    if sponsor.net_outcome_claims is None:
        return _zero_vector(state.pricing.num_outcomes)
    return tuple(map(to_decimal, sponsor.net_outcome_claims))


def _component_residuals(state: SimulationState, sponsor: SponsorPosition) -> tuple[Decimal, ...]:
    locked = to_decimal(sponsor.locked_collateral)
    trade_cash = to_decimal(sponsor.trade_cash_balance)
    net_claims = _cohort_net_claims(state, sponsor)
    return tuple(locked + trade_cash - claim for claim in net_claims)


def _fp_prices_to_decimal(prices_fp: list[int] | tuple[int, ...]) -> tuple[Decimal, ...]:
    with high_precision():
        values = [Decimal(price) / Decimal(AVM_SCALE) for price in prices_fp]
        if len(values) >= 2:
            values[-1] = DECIMAL_ONE - sum(values[:-1], start=DECIMAL_ZERO)
        return tuple(values)


def _decimal_prices_to_fp(prices: tuple[Decimal, ...]) -> tuple[int, ...]:
    if not prices:
        raise ValueError("prices must be non-empty")
    raw: list[int] = []
    allocated = 0
    for idx, price in enumerate(prices):
        if idx == len(prices) - 1:
            price_fp = AVM_SCALE - allocated
        else:
            scaled = (to_decimal(price) * Decimal(AVM_SCALE)).to_integral_value(rounding=ROUND_FLOOR)
            price_fp = int(scaled)
            allocated += price_fp
        raw.append(max(0, min(AVM_SCALE, price_fp)))
    if sum(raw) != AVM_SCALE:
        raw[-1] += AVM_SCALE - sum(raw)
    return tuple(raw)


def _apply_price_floor(prices_fp: tuple[int, ...], *, floor_fp: int = FP_PRICE_FLOOR) -> tuple[int, ...]:
    if floor_fp <= 0:
        return prices_fp
    adjusted = [max(price, floor_fp) for price in prices_fp]
    total = sum(adjusted)
    if total <= AVM_SCALE:
        adjusted[-1] += AVM_SCALE - total
        return tuple(adjusted)

    excess = total - AVM_SCALE
    order = sorted(range(len(adjusted)), key=lambda idx: adjusted[idx], reverse=True)
    for idx in order:
        if excess <= 0:
            break
        removable = adjusted[idx] - floor_fp
        if removable <= 0:
            continue
        delta = min(removable, excess)
        adjusted[idx] -= delta
        excess -= delta
    if excess > 0:
        raise ValueError("price floor too large for outcome count")
    adjusted[-1] += AVM_SCALE - sum(adjusted)
    return tuple(adjusted)


def _gauge_shifted_q_from_prices_fp(prices_fp: tuple[int, ...], depth_b: int) -> tuple[int, ...]:
    if depth_b <= 0:
        raise ValueError("depth_b must be positive")
    safe_prices = _apply_price_floor(prices_fp)
    price_decimals = _fp_prices_to_decimal(safe_prices)
    with high_precision():
        alpha = max((DECIMAL_ONE / price).ln() for price in price_decimals)
        values: list[int] = []
        for price in price_decimals:
            q_value = (Decimal(depth_b) * (price.ln() + alpha)).to_integral_value(rounding=ROUND_FLOOR)
            values.append(max(0, int(q_value)))
        return tuple(values)


def _collateral_required_fp(delta_b: int, prices_fp: tuple[int, ...], *, safety_margin: int = FP_ENTRY_SAFETY_MARGIN) -> int:
    if delta_b <= 0:
        raise ValueError("delta_b must be positive")
    safe_prices = _apply_price_floor(prices_fp)
    price_decimals = _fp_prices_to_decimal(safe_prices)
    with high_precision():
        alpha = max((DECIMAL_ONE / price).ln() for price in price_decimals)
        base = (Decimal(delta_b) * alpha).to_integral_value(rounding=ROUND_CEILING)
        return int(base) + max(0, safety_margin)


def _route_by_depth_u64(state: SimulationState, shares: int) -> dict[str, int]:
    total_depth = _total_depth_u64(state)
    if total_depth <= 0:
        raise ValueError("total depth must be positive")
    routed: dict[str, int] = {}
    remaining = shares
    active = [sponsor.cohort_id for sponsor in _active_sponsors(state)]
    for idx, key in enumerate(active):
        sponsor = state.sponsors[key]
        sponsor_b = _amount_to_fp(sponsor.target_delta_b, name="target_delta_b")
        if idx == len(active) - 1:
            routed[key] = remaining
            break
        routed_shares = (shares * sponsor_b) // total_depth
        routed[key] = routed_shares
        remaining -= routed_shares
    return routed


def _route_by_positive_claims_u64(state: SimulationState, outcome_index: int, shares_fp: int) -> dict[str, int]:
    positive_weights: list[tuple[str, Decimal]] = []
    total_weight = DECIMAL_ZERO
    for key in _sponsor_keys(state):
        sponsor = state.sponsors[key]
        claim = _cohort_net_claims(state, sponsor)[outcome_index]
        if claim <= 0:
            continue
        positive_weights.append((key, claim))
        total_weight += claim
    if total_weight <= 0:
        return _route_by_depth_u64(state, shares_fp)

    routed: dict[str, int] = {}
    remaining = shares_fp
    for idx, (key, weight) in enumerate(positive_weights):
        if idx == len(positive_weights) - 1:
            routed[key] = remaining
            break
        routed_shares = int((Decimal(shares_fp) * weight / total_weight).to_integral_value(rounding=ROUND_FLOOR))
        routed[key] = routed_shares
        remaining -= routed_shares
    return routed


def _allocate_lp_fees(state: SimulationState, lp_fee: Decimal) -> None:
    if lp_fee <= 0:
        return
    total_depth = Decimal(_total_depth_u64(state))
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
    if total_positive + FP_NAV_TOLERANCE < shares:
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


def _component_q_from_prices_fp(prices_fp: tuple[int, ...], depth_b: int) -> tuple[int, ...]:
    return _gauge_shifted_q_from_prices_fp(prices_fp, depth_b)


def _sum_component_amounts(component_amounts: dict[str, int]) -> int:
    return sum(component_amounts.values())


def _allocate_global_amount_by_components(total_amount: int, component_amounts: dict[str, int]) -> dict[str, Decimal]:
    if total_amount < 0:
        raise ValueError("total_amount must be non-negative")
    if not component_amounts:
        return {}
    total_component = _sum_component_amounts(component_amounts)
    if total_component <= 0:
        equal_share = Decimal(total_amount) / Decimal(len(component_amounts))
        allocated: dict[str, Decimal] = {}
        remaining = Decimal(total_amount)
        for idx, key in enumerate(sorted(component_amounts)):
            if idx == len(component_amounts) - 1:
                allocated[key] = remaining
            else:
                allocated[key] = equal_share
                remaining -= equal_share
        return allocated

    remaining = Decimal(total_amount)
    allocated = {}
    ordered = sorted(component_amounts)
    for idx, key in enumerate(ordered):
        component_amount = component_amounts[key]
        if idx == len(ordered) - 1:
            allocated[key] = remaining
        else:
            share = Decimal(total_amount) * Decimal(component_amount) / Decimal(total_component)
            allocated[key] = share
            remaining -= share
    return allocated


def _sync_state(state: SimulationState) -> SimulationState:
    num_outcomes = state.pricing.num_outcomes
    total_depth = _total_depth_u64(state)
    state.pricing.depth_b = total_depth
    if state.pricing.status is MarketStatus.ACTIVE and total_depth > 0:
        prices_fp = avm_lmsr_prices(list(map(int, state.pricing.pricing_q)), int(state.pricing.depth_b))
        state.pricing.price_vector = _fp_prices_to_decimal(prices_fp)
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


class LayerCFixedPointEngine:
    def __init__(
        self,
        *,
        lp_fee_bps: Numeric = 0,
        protocol_fee_bps: Numeric = 0,
        price_floor_fp: int = FP_PRICE_FLOOR,
        entry_safety_margin: int = FP_ENTRY_SAFETY_MARGIN,
    ) -> None:
        self.lp_fee_bps = to_decimal(lp_fee_bps)
        self.protocol_fee_bps = to_decimal(protocol_fee_bps)
        self.price_floor_fp = price_floor_fp
        self.entry_safety_margin = entry_safety_margin

    def clone_state(self, state: SimulationState) -> SimulationState:
        return deepcopy(state)

    def price_vector(self, state: MarketPricingState) -> tuple[Decimal, ...]:
        return tuple(map(to_decimal, state.price_vector))

    def buy_cost(self, state: MarketPricingState, outcome_index: int, shares: Numeric) -> Decimal:
        quote = avm_lmsr_cost_delta(
            list(map(int, state.pricing_q)),
            int(state.depth_b),
            int(outcome_index),
            _amount_to_fp(shares, name="shares"),
        )
        return _fp_to_amount(quote)

    def sell_return(self, state: MarketPricingState, outcome_index: int, shares: Numeric) -> Decimal:
        quote = avm_lmsr_sell_return(
            list(map(int, state.pricing_q)),
            int(state.depth_b),
            int(outcome_index),
            _amount_to_fp(shares, name="shares"),
        )
        return _fp_to_amount(quote)

    def route_trade(self, state: SimulationState, event: BuyOutcome | SellOutcome) -> dict[str, int]:
        return _route_by_depth_u64(state, _amount_to_fp(event.shares, name="shares"))

    def apply_lp_entry(self, state: SimulationState, event: LpEnterActive) -> dict[str, Decimal | SimulationState]:
        working = self.clone_state(state)
        if working.pricing.status is not MarketStatus.ACTIVE:
            raise ValueError("lp entry requires ACTIVE market")
        current_prices = _current_price_vector(working)
        expected_prices = tuple(map(to_decimal, event.expected_price_vector))
        if len(current_prices) != len(expected_prices):
            raise ValueError("expected_price_vector length mismatch")
        allowed_tolerance = max(to_decimal(event.price_tolerance), FP_STALE_REJECTION_TOLERANCE)
        if max_abs_diff(current_prices, expected_prices) > allowed_tolerance:
            raise ValueError("stale LP entry price")

        delta_b_units = to_decimal(event.target_delta_b)
        delta_b = _amount_to_fp(delta_b_units, name="target_delta_b")
        if delta_b <= 0:
            raise ValueError("target_delta_b must be positive")
        if event.min_delta_b is not None and delta_b < _amount_to_fp(event.min_delta_b, name="min_delta_b"):
            raise ValueError("target_delta_b below min_delta_b")

        current_prices_fp = avm_lmsr_prices(list(map(int, working.pricing.pricing_q)), int(working.pricing.depth_b))
        required_deposit = _collateral_required_fp(
            delta_b,
            tuple(current_prices_fp),
            safety_margin=self.entry_safety_margin,
        )
        if required_deposit > _amount_to_fp(event.max_deposit, name="max_deposit"):
            raise ValueError("max_deposit too small")

        cohort_id = f"{event.sponsor_id}:{working.event_index + 1}"
        zero_claims = _zero_vector(working.pricing.num_outcomes)
        required_deposit_amount = _fp_to_amount(required_deposit)
        working.sponsors[cohort_id] = SponsorPosition(
            sponsor_id=event.sponsor_id,
            cohort_id=cohort_id,
            entry_timestamp=event.timestamp,
            share_units=delta_b_units,
            target_delta_b=delta_b_units,
            collateral_posted=required_deposit_amount,
            locked_collateral=required_deposit_amount,
            withdrawable_fee_surplus=DECIMAL_ZERO,
            claimable_fees=DECIMAL_ZERO,
            fee_snapshot=DECIMAL_ZERO,
            entry_price_vector=current_prices,
            entry_gauge_alpha=required_deposit_amount / delta_b_units,
            residual_basis_by_outcome=tuple(required_deposit_amount for _ in range(working.pricing.num_outcomes)),
            net_outcome_claims=zero_claims,
            trade_cash_balance=DECIMAL_ZERO,
        )
        old_depth = int(working.pricing.depth_b)
        new_depth = _total_depth_u64(working)
        working.pricing.depth_b = new_depth
        if old_depth > 0:
            scaled_q, scaled_b = avm_lmsr_liquidity_scale(
                list(map(int, working.pricing.pricing_q)),
                old_depth,
                delta_b,
                old_depth,
            )
            working.pricing.pricing_q = tuple(scaled_q)
            working.pricing.depth_b = scaled_b
        else:
            working.pricing.pricing_q = _gauge_shifted_q_from_prices_fp(tuple(current_prices_fp), new_depth)
        working.treasury.contract_funds += required_deposit_amount
        working.pricing.timestamp = event.timestamp
        working.event_index += 1
        return {"deposit_required": required_deposit_amount, "state": _sync_state(working)}

    def mark_to_market_nav(self, state: SimulationState) -> dict[str, Decimal]:
        prices = _current_price_vector(state)
        nav: dict[str, Decimal] = {}
        for key in _sponsor_keys(state):
            sponsor = state.sponsors[key]
            if state.pricing.status is MarketStatus.RESOLVED and state.winning_outcome is not None:
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
            prices = uniform_price_vector(working.pricing.num_outcomes)
            prices_fp = _decimal_prices_to_fp(prices)
            depth_b_units = to_decimal(event.initial_depth_b)
            depth_b = _amount_to_fp(depth_b_units, name="initial_depth_b")
            required_collateral = _collateral_required_fp(
                depth_b,
                prices_fp,
                safety_margin=self.entry_safety_margin,
            )
            initial_collateral = _amount_to_fp(event.initial_collateral, name="initial_collateral")
            if initial_collateral < required_collateral:
                raise ValueError("initial_collateral below LMSR funding floor")
            cohort_id = f"{event.creator_id}:bootstrap"
            zero_claims = _zero_vector(working.pricing.num_outcomes)
            initial_collateral_amount = _fp_to_amount(initial_collateral)
            required_collateral_amount = _fp_to_amount(required_collateral)
            working.sponsors[cohort_id] = SponsorPosition(
                sponsor_id=event.creator_id,
                cohort_id=cohort_id,
                entry_timestamp=event.timestamp,
                share_units=depth_b_units,
                target_delta_b=depth_b_units,
                collateral_posted=initial_collateral_amount,
                locked_collateral=initial_collateral_amount,
                withdrawable_fee_surplus=DECIMAL_ZERO,
                claimable_fees=DECIMAL_ZERO,
                fee_snapshot=DECIMAL_ZERO,
                entry_price_vector=prices,
                entry_gauge_alpha=required_collateral_amount / depth_b_units,
                residual_basis_by_outcome=tuple(initial_collateral_amount for _ in range(working.pricing.num_outcomes)),
                net_outcome_claims=zero_claims,
                trade_cash_balance=DECIMAL_ZERO,
            )
            working.pricing.status = MarketStatus.ACTIVE
            working.pricing.timestamp = event.timestamp
            working.pricing.depth_b = depth_b
            working.pricing.pricing_q = _gauge_shifted_q_from_prices_fp(prices_fp, depth_b)
            working.treasury.contract_funds = initial_collateral_amount
            working.event_index += 1
            return _sync_state(working)

        if isinstance(event, LpEnterActive):
            return self.apply_lp_entry(working, event)["state"]  # type: ignore[return-value]

        if isinstance(event, BuyOutcome):
            if working.pricing.status is not MarketStatus.ACTIVE:
                raise ValueError("buy requires ACTIVE market")
            shares_fp = _amount_to_fp(event.shares, name="shares")
            shares_amount = _fp_to_amount(shares_fp)
            if shares_fp <= 0:
                raise ValueError("shares must be positive")
            _ensure_trader(working, event.trader_id)
            current_prices_fp = tuple(avm_lmsr_prices(list(map(int, working.pricing.pricing_q)), int(working.pricing.depth_b)))
            routed = self.route_trade(working, event)
            total_cost_fp = avm_lmsr_cost_delta(
                list(map(int, working.pricing.pricing_q)),
                int(working.pricing.depth_b),
                int(event.outcome_index),
                shares_fp,
            )
            total_cost = _fp_to_amount(total_cost_fp)
            component_costs: dict[str, int] = {}
            for key, routed_shares in routed.items():
                sponsor = working.sponsors[key]
                component_q = _component_q_from_prices_fp(current_prices_fp, _amount_to_fp(sponsor.target_delta_b, name="target_delta_b"))
                component_costs[key] = avm_lmsr_cost_delta(
                    list(component_q),
                    _amount_to_fp(sponsor.target_delta_b, name="target_delta_b"),
                    int(event.outcome_index),
                    int(routed_shares),
                )
            allocated_cash = {
                key: _fp_to_amount(amount_fp)
                for key, amount_fp in _allocate_global_amount_by_components(total_cost_fp, component_costs).items()
            }
            for key, routed_shares in routed.items():
                sponsor = working.sponsors[key]
                claims = _cohort_net_claims(working, sponsor)
                next_claims = _set_tuple_entry(claims, event.outcome_index, _fp_to_amount(routed_shares))
                working.sponsors[key] = replace(
                    sponsor,
                    net_outcome_claims=next_claims,
                    trade_cash_balance=to_decimal(sponsor.trade_cash_balance) + allocated_cash[key],
                )
            lp_fee = total_cost * self.lp_fee_bps / BPS_DENOMINATOR
            protocol_fee = total_cost * self.protocol_fee_bps / BPS_DENOMINATOR
            total_paid = total_cost + lp_fee + protocol_fee
            if total_paid - to_decimal(event.max_total_cost) > FP_ORDER_TOLERANCE:
                raise ValueError("max_total_cost exceeded")
            positions = tuple(map(to_decimal, working.traders.positions_by_trader[event.trader_id]))
            basis = tuple(map(to_decimal, working.traders.cost_basis_by_trader[event.trader_id]))
            positions = _set_tuple_entry(positions, event.outcome_index, shares_amount)
            basis = _set_tuple_entry(basis, event.outcome_index, total_cost)
            working.traders.positions_by_trader[event.trader_id] = positions
            working.traders.cost_basis_by_trader[event.trader_id] = basis
            aggregate = _aggregate_outstanding(working)
            working.traders.aggregate_outstanding_claims = _set_tuple_entry(aggregate, event.outcome_index, shares_amount)
            working.pricing.pricing_q = _set_tuple_entry(tuple(map(Decimal, working.pricing.pricing_q)), event.outcome_index, Decimal(shares_fp))
            working.treasury.contract_funds += total_paid
            working.treasury.protocol_fee_balance += protocol_fee
            _allocate_lp_fees(working, lp_fee)
            working.pricing.timestamp = event.timestamp
            working.event_index += 1
            return _sync_state(working)

        if isinstance(event, SellOutcome):
            if working.pricing.status is not MarketStatus.ACTIVE:
                raise ValueError("sell requires ACTIVE market")
            shares_fp = _amount_to_fp(event.shares, name="shares")
            shares_amount = _fp_to_amount(shares_fp)
            if shares_fp <= 0:
                raise ValueError("shares must be positive")
            _ensure_trader(working, event.trader_id)
            positions = tuple(map(to_decimal, working.traders.positions_by_trader[event.trader_id]))
            basis = tuple(map(to_decimal, working.traders.cost_basis_by_trader[event.trader_id]))
            current_shares = positions[event.outcome_index]
            if current_shares < shares_amount:
                raise ValueError("insufficient shares")
            current_prices_fp = tuple(avm_lmsr_prices(list(map(int, working.pricing.pricing_q)), int(working.pricing.depth_b)))
            routed = _route_by_positive_claims_u64(working, event.outcome_index, shares_fp)
            gross_return_fp = avm_lmsr_sell_return(
                list(map(int, working.pricing.pricing_q)),
                int(working.pricing.depth_b),
                int(event.outcome_index),
                shares_fp,
            )
            gross_return = _fp_to_amount(gross_return_fp)
            allocated_returns = {
                key: _fp_to_amount(amount_fp)
                for key, amount_fp in _allocate_global_amount_by_components(gross_return_fp, routed).items()
            }
            for key, routed_shares in routed.items():
                sponsor = working.sponsors[key]
                claims = _cohort_net_claims(working, sponsor)
                next_claims = _set_tuple_entry(claims, event.outcome_index, -_fp_to_amount(routed_shares))
                working.sponsors[key] = replace(
                    sponsor,
                    net_outcome_claims=next_claims,
                    trade_cash_balance=to_decimal(sponsor.trade_cash_balance) - allocated_returns[key],
                )
            lp_fee = gross_return * self.lp_fee_bps / BPS_DENOMINATOR
            protocol_fee = gross_return * self.protocol_fee_bps / BPS_DENOMINATOR
            net_return = gross_return - lp_fee - protocol_fee
            if to_decimal(event.min_total_return) - net_return > FP_ORDER_TOLERANCE:
                raise ValueError("min_total_return not met")
            basis_reduction = _basis_reduction(current_shares, basis[event.outcome_index], shares_amount)
            positions = _replace_tuple_entry(positions, event.outcome_index, current_shares - shares_amount)
            basis = _replace_tuple_entry(basis, event.outcome_index, basis[event.outcome_index] - basis_reduction)
            working.traders.positions_by_trader[event.trader_id] = positions
            working.traders.cost_basis_by_trader[event.trader_id] = basis
            aggregate = _aggregate_outstanding(working)
            working.traders.aggregate_outstanding_claims = _replace_tuple_entry(
                aggregate,
                event.outcome_index,
                aggregate[event.outcome_index] - shares_amount,
            )
            working.pricing.pricing_q = _set_tuple_entry(tuple(map(Decimal, working.pricing.pricing_q)), event.outcome_index, -Decimal(shares_fp))
            working.treasury.contract_funds -= net_return
            working.treasury.protocol_fee_balance += protocol_fee
            _allocate_lp_fees(working, lp_fee)
            working.pricing.timestamp = event.timestamp
            working.event_index += 1
            return _sync_state(working)

        if isinstance(event, ResolveMarket):
            if working.pricing.status is not MarketStatus.ACTIVE:
                raise ValueError("resolve requires ACTIVE market")
            working.pricing.status = MarketStatus.RESOLVED
            working.winning_outcome = event.winning_outcome
            working.pricing.timestamp = event.timestamp
            working.event_index += 1
            return _sync_state(working)

        if isinstance(event, ClaimWinnings):
            if working.pricing.status is not MarketStatus.RESOLVED:
                raise ValueError("claim requires RESOLVED market")
            if working.winning_outcome != event.outcome_index:
                raise ValueError("only winning outcome may be claimed")
            _ensure_trader(working, event.trader_id)
            shares = _fp_to_amount(_amount_to_fp(event.shares, name="shares"))
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
            working.pricing.timestamp = event.timestamp
            working.event_index += 1
            return _sync_state(working)

        if isinstance(event, ClaimRefund):
            if working.pricing.status is not MarketStatus.CANCELLED:
                raise ValueError("refund requires CANCELLED market")
            _ensure_trader(working, event.trader_id)
            shares = _fp_to_amount(_amount_to_fp(event.shares, name="shares"))
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
            for key in _sponsor_keys(working):
                sponsor = working.sponsors[key]
                if sponsor.sponsor_id != event.sponsor_id:
                    continue
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
            working.treasury.contract_funds -= payout
            working.pricing.timestamp = event.timestamp
            working.event_index += 1
            return _sync_state(working)

        raise TypeError(f"unsupported event type: {type(event)!r}")


class LayerCInvariantChecker:
    def check_price_continuity(self, before: SimulationState, after: SimulationState) -> InvariantCheckResult:
        diff = max_abs_diff(_current_price_vector(before), _current_price_vector(after))
        return InvariantCheckResult(
            name="price_continuity",
            passed=diff <= FP_PRICE_TOLERANCE,
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
        passed = min_margin is None or min_margin >= -FP_NAV_TOLERANCE
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
            passed=diff <= FP_NAV_TOLERANCE,
            severity="error",
            details=f"diff={diff}",
            event_index=state.event_index,
        )

    def check_no_instantaneous_value_transfer(self, before: SimulationState, after: SimulationState) -> InvariantCheckResult:
        if after.event_index == before.event_index:
            return InvariantCheckResult(
                name="no_instantaneous_value_transfer",
                passed=True,
                severity="error",
                details="no event applied",
                event_index=after.event_index,
            )
        engine = LayerCFixedPointEngine()
        before_nav = engine.mark_to_market_nav(before)
        after_nav = engine.mark_to_market_nav(after)
        max_change = DECIMAL_ZERO
        for key in set(before_nav):
            max_change = max(max_change, abs(after_nav.get(key, DECIMAL_ZERO) - before_nav[key]))
        return InvariantCheckResult(
            name="no_instantaneous_value_transfer",
            passed=max_change <= FP_NAV_TOLERANCE,
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
                passed=all(abs(trader_sum[idx] - aggregate[idx]) <= FP_NAV_TOLERANCE for idx in range(len(aggregate))),
                severity="error",
                details=f"aggregate={aggregate}, trader_sum={tuple(trader_sum)}",
                event_index=state.event_index,
            ),
            self.check_sponsor_solvency(state),
            self.check_settlement_conservation(state),
        ]
        if state.pricing.status is MarketStatus.ACTIVE and int(state.pricing.depth_b) > 0:
            derived_prices = _fp_prices_to_decimal(avm_lmsr_prices(list(map(int, state.pricing.pricing_q)), int(state.pricing.depth_b)))
            max_price_diff = max_abs_diff(derived_prices, _current_price_vector(state))
            checks.append(
                InvariantCheckResult(
                    name="aggregate_pricing_consistency",
                    passed=max_price_diff <= FP_PRICE_TOLERANCE,
                    severity="error",
                    details=f"max_price_diff={max_price_diff}",
                    event_index=state.event_index,
                )
            )
        return checks


class LayerCMetricCollector:
    def __init__(self) -> None:
        self.engine = LayerCFixedPointEngine()

    def price_continuity(self, before: SimulationState, after: SimulationState) -> dict[str, object]:
        return {
            "before": _current_price_vector(before),
            "after": _current_price_vector(after),
            "max_abs_change": max_abs_diff(_current_price_vector(before), _current_price_vector(after)),
        }

    def slippage_report(self, before: SimulationState, after: SimulationState, reference_trades: list[SimulationEvent]) -> dict[str, object]:
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
        result = LayerCInvariantChecker().check_sponsor_solvency(state)
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
        rows = []
        for key in _sponsor_keys(state):
            sponsor = state.sponsors[key]
            rows.append(
                {
                    "cohort_id": key,
                    "sponsor_id": sponsor.sponsor_id,
                    "share_units": to_decimal(sponsor.share_units),
                    "residual_claimed": to_decimal(sponsor.residual_claimed),
                }
            )
        return {"policy": "strict_all_claimed", "rows": rows}

    def divergence(self, reference_result: CanonicalEvaluation, candidate_result: CanonicalEvaluation) -> dict[str, object]:
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
        max_nav_diff = DECIMAL_ZERO
        max_nav_per_deposit_diff = DECIMAL_ZERO
        for key in sorted(set(ref_fairness) & set(cand_fairness)):
            max_nav_diff = max(max_nav_diff, abs(to_decimal(ref_fairness[key]["nav"]) - to_decimal(cand_fairness[key]["nav"])))
            max_nav_per_deposit_diff = max(
                max_nav_per_deposit_diff,
                abs(to_decimal(ref_fairness[key]["nav_per_deposit"]) - to_decimal(cand_fairness[key]["nav_per_deposit"])),
            )
        return {
            "implemented": True,
            "max_price_entry_diff_vs_reference": max_price_vector_diff,
            "max_quote_diff_vs_reference": max_quote_diff,
            "max_nav_diff_vs_reference": max_nav_diff,
            "max_nav_per_deposit_diff_vs_reference": max_nav_per_deposit_diff,
            "solvency_match": reference_result.solvency.get("passed") == candidate_result.solvency.get("passed"),
            "math_mode": "avm_fixed_point_uint64",
            "price_floor_fp": self.engine.price_floor_fp,
            "entry_safety_margin": self.engine.entry_safety_margin,
        }

    def protocol_complexity(self, state_history: list[SimulationState]) -> dict[str, object]:
        max_cohorts = 0
        for state in state_history:
            max_cohorts = max(max_cohorts, len(state.sponsors))
        return {
            "max_cohorts": max_cohorts,
            "active_path_complexity": "O(num_cohorts + num_outcomes)",
            "pricing_state": "uint64 fixed point",
            "routing_mode": "integer floor + remainder",
        }


class LayerCScenarioRunner:
    def __init__(
        self,
        num_outcomes: int,
        *,
        engine: LayerCFixedPointEngine | None = None,
        invariant_checker: LayerCInvariantChecker | None = None,
        reference_trade_size: Numeric = 1,
        reference_trades: tuple[SimulationEvent, ...] | None = None,
    ) -> None:
        self.num_outcomes = num_outcomes
        self.engine = engine or LayerCFixedPointEngine()
        self.collector = LayerCMetricCollector()
        self.invariant_checker = invariant_checker or LayerCInvariantChecker()
        self.reference_trade_size = to_decimal(reference_trade_size)
        self.reference_trades = reference_trades

    def run(self, events: list[SimulationEvent], mechanism: MechanismVariant) -> CanonicalEvaluation:
        if mechanism is not MechanismVariant.GLOBAL_STATE_AVM_FIXED_POINT:
            raise ValueError("LayerCScenarioRunner only supports GLOBAL_STATE_AVM_FIXED_POINT")
        state = create_layer_c_initial_state(self.num_outcomes)
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
        return CanonicalEvaluation(
            price_continuity={
                "entries": price_reports,
                "max_abs_change": max_price_change,
                "all_within_tolerance": max_price_change <= FP_PRICE_TOLERANCE,
            },
            slippage_improvement={
                "entries": slippage_reports,
                "all_buy_quotes_improved": all_slippage_improved,
            },
            lp_fairness_by_entry_time=self.collector.lp_fairness(fairness_state),
            solvency={
                **self.collector.solvency_report(state),
                "invariants": [result for result in invariant_results if result.name == "sponsor_solvency"],
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


def create_layer_c_initial_state(num_outcomes: int) -> SimulationState:
    zero_prices = uniform_price_vector(num_outcomes)
    return SimulationState(
        mechanism=MechanismVariant.GLOBAL_STATE_AVM_FIXED_POINT,
        pricing=MarketPricingState(
            num_outcomes=num_outcomes,
            pricing_q=_zero_vector(num_outcomes),
            depth_b=0,
            price_vector=zero_prices,
            status=MarketStatus.CREATED,
            timestamp=0,
        ),
        traders=TraderPositionBook(aggregate_outstanding_claims=_zero_vector(num_outcomes)),
        sponsors={},
        treasury=TreasuryState(contract_funds=DECIMAL_ZERO),
    )
