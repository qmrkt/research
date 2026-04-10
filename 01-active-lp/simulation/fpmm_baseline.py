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
from research.active_lp.reference_math import collateral_required, max_abs_diff, uniform_price_vector
from research.active_lp.reference_parallel_lmsr import (
    BPS_DENOMINATOR,
    NAV_TOLERANCE,
    PRICE_TOLERANCE,
    _replace_tuple_entry,
    _set_tuple_entry,
    _zero_vector,
)
from research.active_lp.state import MarketPricingState, SimulationState, SponsorPosition, TraderPositionBook, TreasuryState
from research.active_lp.types import ActorId, MarketStatus, MechanismVariant, Numeric


def _pool_balances(state: SimulationState) -> tuple[Decimal, ...]:
    return tuple(map(to_decimal, state.pricing.pricing_q))


def _zero_token_holdings(num_outcomes: int) -> tuple[Decimal, ...]:
    return tuple(DECIMAL_ZERO for _ in range(num_outcomes))


def _ensure_trader(state: SimulationState, trader_id: ActorId) -> None:
    zeroes = _zero_vector(state.pricing.num_outcomes)
    state.traders.positions_by_trader.setdefault(trader_id, zeroes)
    state.traders.cost_basis_by_trader.setdefault(trader_id, zeroes)
    if not state.traders.aggregate_outstanding_claims:
        state.traders.aggregate_outstanding_claims = zeroes


def _sponsor_keys(state: SimulationState) -> list[str]:
    return sorted(state.sponsors.keys())


def _all_sponsors(state: SimulationState) -> list[SponsorPosition]:
    return [state.sponsors[key] for key in _sponsor_keys(state)]


def _total_share_supply(state: SimulationState) -> Decimal:
    total = DECIMAL_ZERO
    for sponsor in _all_sponsors(state):
        total += max(DECIMAL_ZERO, to_decimal(sponsor.share_units))
    return total


def _fee_rate(lp_fee_bps: Decimal, protocol_fee_bps: Decimal) -> Decimal:
    return (lp_fee_bps + protocol_fee_bps) / BPS_DENOMINATOR


def _price_vector_from_balances(balances: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    if not balances:
        return tuple()
    if any(balance <= 0 for balance in balances):
        raise ValueError("pool balances must stay positive")
    with high_precision():
        inverse_sum = sum((DECIMAL_ONE / balance for balance in balances), start=DECIMAL_ZERO)
        return tuple((DECIMAL_ONE / balance) / inverse_sum for balance in balances)


def _pool_inventory_value(state: SimulationState) -> Decimal:
    balances = _pool_balances(state)
    prices = tuple(map(to_decimal, state.pricing.price_vector))
    return sum((balance * price for balance, price in zip(balances, prices)), start=DECIMAL_ZERO)


def _external_token_value(state: SimulationState, sponsor: SponsorPosition) -> Decimal:
    holdings = sponsor.external_outcome_tokens or _zero_token_holdings(state.pricing.num_outcomes)
    prices = tuple(map(to_decimal, state.pricing.price_vector))
    return sum((to_decimal(amount) * price for amount, price in zip(holdings, prices)), start=DECIMAL_ZERO)


def _pool_claim_value(state: SimulationState, sponsor: SponsorPosition) -> Decimal:
    total_shares = _total_share_supply(state)
    if total_shares <= 0:
        return DECIMAL_ZERO
    return _pool_inventory_value(state) * to_decimal(sponsor.share_units) / total_shares


def _pool_share_fraction(state: SimulationState, sponsor: SponsorPosition) -> Decimal:
    total_shares = _total_share_supply(state)
    if total_shares <= 0:
        return DECIMAL_ZERO
    return max(DECIMAL_ZERO, to_decimal(sponsor.share_units)) / total_shares


def _sync_state(state: SimulationState) -> SimulationState:
    total_shares = _total_share_supply(state)
    state.pricing.depth_b = total_shares
    if state.pricing.status is MarketStatus.ACTIVE and any(balance > 0 for balance in _pool_balances(state)):
        state.pricing.price_vector = _price_vector_from_balances(_pool_balances(state))
    elif state.pricing.status is MarketStatus.RESOLVED and state.winning_outcome is not None:
        vector = [DECIMAL_ZERO for _ in range(state.pricing.num_outcomes)]
        vector[state.winning_outcome] = DECIMAL_ONE
        state.pricing.price_vector = tuple(vector)
    elif state.pricing.status is MarketStatus.CANCELLED:
        state.pricing.price_vector = uniform_price_vector(state.pricing.num_outcomes)
    elif not state.pricing.price_vector:
        state.pricing.price_vector = uniform_price_vector(state.pricing.num_outcomes)
    state.treasury.contract_funds = to_decimal(state.treasury.lp_fee_balance) + to_decimal(state.treasury.protocol_fee_balance)
    return state


def _calc_buy_tokens(
    balances: tuple[Decimal, ...],
    outcome_index: int,
    gross_investment: Decimal,
    total_fee_rate: Decimal,
) -> Decimal:
    if gross_investment <= 0:
        return DECIMAL_ZERO
    net_investment = gross_investment * (DECIMAL_ONE - total_fee_rate)
    buy_balance = balances[outcome_index]
    with high_precision():
        ending_balance = buy_balance
        for idx, balance in enumerate(balances):
            if idx == outcome_index:
                continue
            ending_balance *= balance / (balance + net_investment)
        return buy_balance + net_investment - ending_balance


def _calc_sell_tokens_required(
    balances: tuple[Decimal, ...],
    outcome_index: int,
    net_return: Decimal,
    total_fee_rate: Decimal,
) -> Decimal:
    if net_return <= 0:
        return DECIMAL_ZERO
    if total_fee_rate >= DECIMAL_ONE:
        raise ValueError("fee rate must be below 100%")
    gross_return = net_return / (DECIMAL_ONE - total_fee_rate)
    sell_balance = balances[outcome_index]
    with high_precision():
        ending_balance = sell_balance
        for idx, balance in enumerate(balances):
            if idx == outcome_index:
                continue
            if balance - gross_return <= 0:
                return Decimal("1e50")
            ending_balance *= balance / (balance - gross_return)
        return gross_return + ending_balance - sell_balance


def _binary_search_buy_cost(
    balances: tuple[Decimal, ...],
    outcome_index: int,
    shares: Decimal,
    total_fee_rate: Decimal,
) -> Decimal:
    if shares <= 0:
        return DECIMAL_ZERO
    low = DECIMAL_ZERO
    high = max(shares, DECIMAL_ONE)
    while _calc_buy_tokens(balances, outcome_index, high, total_fee_rate) < shares:
        high *= Decimal("2")
        if high > Decimal("1e12"):
            raise ValueError("buy cost search failed to bracket")
    for _ in range(200):
        mid = (low + high) / Decimal("2")
        bought = _calc_buy_tokens(balances, outcome_index, mid, total_fee_rate)
        if bought >= shares:
            high = mid
        else:
            low = mid
    return high


def _binary_search_sell_return(
    balances: tuple[Decimal, ...],
    outcome_index: int,
    shares: Decimal,
    total_fee_rate: Decimal,
) -> Decimal:
    if shares <= 0:
        return DECIMAL_ZERO
    other_balances = [balance for idx, balance in enumerate(balances) if idx != outcome_index]
    if not other_balances:
        return DECIMAL_ZERO
    fee_scale = DECIMAL_ONE - total_fee_rate
    upper = min(other_balances) * fee_scale * Decimal("0.999999999999")
    low = DECIMAL_ZERO
    high = max(upper, DECIMAL_ZERO)
    for _ in range(200):
        mid = (low + high) / Decimal("2")
        required = _calc_sell_tokens_required(balances, outcome_index, mid, total_fee_rate)
        if required <= shares:
            low = mid
        else:
            high = mid
    return low


class FpmmBaselineEngine:
    def __init__(self, *, lp_fee_bps: Numeric = 0, protocol_fee_bps: Numeric = 0) -> None:
        self.lp_fee_bps = to_decimal(lp_fee_bps)
        self.protocol_fee_bps = to_decimal(protocol_fee_bps)

    def clone_state(self, state: SimulationState) -> SimulationState:
        return deepcopy(state)

    def buy_cost(self, pricing: MarketPricingState, outcome_index: int, shares: Numeric) -> Decimal:
        return _binary_search_buy_cost(
            tuple(map(to_decimal, pricing.pricing_q)),
            outcome_index,
            to_decimal(shares),
            _fee_rate(self.lp_fee_bps, self.protocol_fee_bps),
        )

    def sell_return(self, pricing: MarketPricingState, outcome_index: int, shares: Numeric) -> Decimal:
        return _binary_search_sell_return(
            tuple(map(to_decimal, pricing.pricing_q)),
            outcome_index,
            to_decimal(shares),
            _fee_rate(self.lp_fee_bps, self.protocol_fee_bps),
        )

    def mark_to_market_nav(self, state: SimulationState) -> dict[str, Decimal]:
        nav: dict[str, Decimal] = {}
        for key in _sponsor_keys(state):
            sponsor = state.sponsors[key]
            nav[key] = (
                _pool_claim_value(state, sponsor)
                + _external_token_value(state, sponsor)
                + to_decimal(sponsor.claimable_fees)
                + to_decimal(sponsor.withdrawable_fee_surplus)
            )
        return nav

    def _allocate_lp_fees(self, state: SimulationState, lp_fee: Decimal) -> None:
        if lp_fee <= 0:
            return
        total_shares = _total_share_supply(state)
        if total_shares <= 0:
            return
        state.treasury.lp_fee_balance += lp_fee
        remaining = lp_fee
        keys = _sponsor_keys(state)
        for idx, key in enumerate(keys):
            sponsor = state.sponsors[key]
            if idx == len(keys) - 1:
                fee_share = remaining
            else:
                fee_share = lp_fee * to_decimal(sponsor.share_units) / total_shares
                remaining -= fee_share
            state.sponsors[key] = replace(sponsor, claimable_fees=to_decimal(sponsor.claimable_fees) + fee_share)

    def apply_event(self, state: SimulationState, event: SimulationEvent) -> SimulationState:
        working = self.clone_state(state)
        total_fee_rate = _fee_rate(self.lp_fee_bps, self.protocol_fee_bps)

        if isinstance(event, BootstrapMarket):
            if working.pricing.status is not MarketStatus.CREATED:
                raise ValueError("market already bootstrapped")
            collateral = to_decimal(event.initial_collateral)
            if collateral <= 0:
                raise ValueError("bootstrap funding must be positive")
            pool_balances = tuple(collateral for _ in range(working.pricing.num_outcomes))
            creator_key = f"{event.creator_id}:bootstrap"
            working.sponsors[creator_key] = SponsorPosition(
                sponsor_id=event.creator_id,
                cohort_id=creator_key,
                entry_timestamp=event.timestamp,
                share_units=collateral,
                target_delta_b=collateral,
                collateral_posted=collateral,
                locked_collateral=DECIMAL_ZERO,
                withdrawable_fee_surplus=DECIMAL_ZERO,
                claimable_fees=DECIMAL_ZERO,
                fee_snapshot=DECIMAL_ZERO,
                entry_price_vector=uniform_price_vector(working.pricing.num_outcomes),
                residual_basis_by_outcome=None,
                external_outcome_tokens=_zero_token_holdings(working.pricing.num_outcomes),
            )
            working.pricing = replace(
                working.pricing,
                pricing_q=pool_balances,
                status=MarketStatus.ACTIVE,
                timestamp=event.timestamp,
            )
            working.event_index += 1
            return _sync_state(working)

        if isinstance(event, LpEnterActive):
            if working.pricing.status is not MarketStatus.ACTIVE:
                raise ValueError("LP entry requires active market")
            deposit = collateral_required(to_decimal(event.target_delta_b), tuple(map(to_decimal, event.expected_price_vector)))
            if deposit > to_decimal(event.max_deposit) + PRICE_TOLERANCE:
                raise ValueError("LP max deposit exceeded")
            pool_balances = _pool_balances(working)
            pool_share_supply = _total_share_supply(working)
            if pool_share_supply <= 0:
                raise ValueError("pool share supply must be positive")
            pool_weight = max(pool_balances)
            if pool_weight <= 0:
                raise ValueError("pool weight must be positive")
            remaining_amounts = tuple(deposit * balance / pool_weight for balance in pool_balances)
            send_back_amounts = tuple(deposit - remaining for remaining in remaining_amounts)
            new_balances = tuple(balance + remaining for balance, remaining in zip(pool_balances, remaining_amounts))
            minted_shares = deposit * pool_share_supply / pool_weight
            cohort_id = f"{event.sponsor_id}:{event.timestamp}"
            working.sponsors[cohort_id] = SponsorPosition(
                sponsor_id=event.sponsor_id,
                cohort_id=cohort_id,
                entry_timestamp=event.timestamp,
                share_units=minted_shares,
                target_delta_b=minted_shares,
                collateral_posted=deposit,
                locked_collateral=DECIMAL_ZERO,
                withdrawable_fee_surplus=DECIMAL_ZERO,
                claimable_fees=DECIMAL_ZERO,
                fee_snapshot=DECIMAL_ZERO,
                entry_price_vector=tuple(map(to_decimal, working.pricing.price_vector)),
                residual_basis_by_outcome=None,
                external_outcome_tokens=send_back_amounts,
            )
            working.pricing = replace(working.pricing, pricing_q=new_balances, timestamp=event.timestamp)
            working.event_index += 1
            return _sync_state(working)

        if isinstance(event, BuyOutcome):
            if working.pricing.status is not MarketStatus.ACTIVE:
                raise ValueError("buy requires active market")
            _ensure_trader(working, event.trader_id)
            shares = to_decimal(event.shares)
            gross_cost = self.buy_cost(working.pricing, event.outcome_index, shares)
            lp_fee = gross_cost * self.lp_fee_bps / BPS_DENOMINATOR
            protocol_fee = gross_cost * self.protocol_fee_bps / BPS_DENOMINATOR
            net_investment = gross_cost - lp_fee - protocol_fee
            pool_balances = [balance + net_investment for balance in _pool_balances(working)]
            pool_balances[event.outcome_index] -= shares
            if any(balance <= 0 for balance in pool_balances):
                raise ValueError("buy would exhaust pool balance")
            position = tuple(map(to_decimal, working.traders.positions_by_trader[event.trader_id]))
            aggregate = tuple(map(to_decimal, working.traders.aggregate_outstanding_claims))
            working.traders.positions_by_trader[event.trader_id] = _set_tuple_entry(position, event.outcome_index, shares)
            working.traders.aggregate_outstanding_claims = _set_tuple_entry(aggregate, event.outcome_index, shares)
            working.treasury.protocol_fee_balance += protocol_fee
            self._allocate_lp_fees(working, lp_fee)
            working.pricing = replace(working.pricing, pricing_q=tuple(pool_balances), timestamp=event.timestamp)
            working.event_index += 1
            return _sync_state(working)

        if isinstance(event, SellOutcome):
            if working.pricing.status is not MarketStatus.ACTIVE:
                raise ValueError("sell requires active market")
            _ensure_trader(working, event.trader_id)
            shares = to_decimal(event.shares)
            position = tuple(map(to_decimal, working.traders.positions_by_trader[event.trader_id]))
            if position[event.outcome_index] + PRICE_TOLERANCE < shares:
                raise ValueError("insufficient trader inventory")
            net_return = self.sell_return(working.pricing, event.outcome_index, shares)
            gross_return = net_return / (DECIMAL_ONE - total_fee_rate) if total_fee_rate < DECIMAL_ONE else net_return
            total_fee = gross_return - net_return
            lp_fee = total_fee * self.lp_fee_bps / (self.lp_fee_bps + self.protocol_fee_bps) if total_fee > 0 and (self.lp_fee_bps + self.protocol_fee_bps) > 0 else DECIMAL_ZERO
            protocol_fee = total_fee - lp_fee
            pool_balances = list(_pool_balances(working))
            pool_balances[event.outcome_index] += shares
            pool_balances = [balance - gross_return for balance in pool_balances]
            if any(balance <= -PRICE_TOLERANCE for balance in pool_balances):
                raise ValueError("sell would drive pool negative")
            aggregate = tuple(map(to_decimal, working.traders.aggregate_outstanding_claims))
            working.traders.positions_by_trader[event.trader_id] = _set_tuple_entry(position, event.outcome_index, -shares)
            working.traders.aggregate_outstanding_claims = _set_tuple_entry(aggregate, event.outcome_index, -shares)
            working.treasury.protocol_fee_balance += protocol_fee
            self._allocate_lp_fees(working, lp_fee)
            working.pricing = replace(
                working.pricing,
                pricing_q=tuple(max(balance, DECIMAL_ZERO) for balance in pool_balances),
                timestamp=event.timestamp,
            )
            working.event_index += 1
            return _sync_state(working)

        if isinstance(event, ResolveMarket):
            working.pricing = replace(
                working.pricing,
                status=MarketStatus.RESOLVED,
                timestamp=event.timestamp,
            )
            working.winning_outcome = event.winning_outcome
            working.settlement_timestamp = event.timestamp
            working.event_index += 1
            return _sync_state(working)

        if isinstance(event, CancelMarket):
            working.pricing = replace(
                working.pricing,
                status=MarketStatus.CANCELLED,
                timestamp=event.timestamp,
            )
            working.settlement_timestamp = event.timestamp
            working.event_index += 1
            return _sync_state(working)

        if isinstance(event, ClaimWinnings):
            if working.pricing.status is not MarketStatus.RESOLVED or event.outcome_index != working.winning_outcome:
                raise ValueError("claim winnings requires resolved winning outcome")
            _ensure_trader(working, event.trader_id)
            shares = to_decimal(event.shares)
            position = tuple(map(to_decimal, working.traders.positions_by_trader[event.trader_id]))
            if position[event.outcome_index] + PRICE_TOLERANCE < shares:
                raise ValueError("insufficient winning inventory")
            aggregate = tuple(map(to_decimal, working.traders.aggregate_outstanding_claims))
            working.traders.positions_by_trader[event.trader_id] = _set_tuple_entry(position, event.outcome_index, -shares)
            working.traders.aggregate_outstanding_claims = _set_tuple_entry(aggregate, event.outcome_index, -shares)
            working.event_index += 1
            working.pricing = replace(working.pricing, timestamp=event.timestamp)
            return _sync_state(working)

        if isinstance(event, ClaimRefund):
            if working.pricing.status is not MarketStatus.CANCELLED:
                raise ValueError("refund requires cancelled market")
            _ensure_trader(working, event.trader_id)
            shares = to_decimal(event.shares)
            position = tuple(map(to_decimal, working.traders.positions_by_trader[event.trader_id]))
            if position[event.outcome_index] + PRICE_TOLERANCE < shares:
                raise ValueError("insufficient refunded inventory")
            aggregate = tuple(map(to_decimal, working.traders.aggregate_outstanding_claims))
            working.traders.positions_by_trader[event.trader_id] = _set_tuple_entry(position, event.outcome_index, -shares)
            working.traders.aggregate_outstanding_claims = _set_tuple_entry(aggregate, event.outcome_index, -shares)
            working.event_index += 1
            working.pricing = replace(working.pricing, timestamp=event.timestamp)
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
            working.pricing = replace(working.pricing, timestamp=event.timestamp)
            return _sync_state(working)

        if isinstance(event, WithdrawLpFees):
            matched = False
            for key in _sponsor_keys(working):
                sponsor = working.sponsors[key]
                if sponsor.sponsor_id != event.sponsor_id:
                    continue
                amount = min(to_decimal(event.amount), to_decimal(sponsor.withdrawable_fee_surplus))
                working.sponsors[key] = replace(
                    sponsor,
                    withdrawable_fee_surplus=to_decimal(sponsor.withdrawable_fee_surplus) - amount,
                )
                working.treasury.lp_fee_balance -= amount
                matched = True
            if not matched:
                raise ValueError("unknown sponsor_id")
            working.event_index += 1
            working.pricing = replace(working.pricing, timestamp=event.timestamp)
            return _sync_state(working)

        if isinstance(event, ClaimLpResidual):
            if working.pricing.status not in (MarketStatus.RESOLVED, MarketStatus.CANCELLED):
                raise ValueError("LP residual requires settled market")
            matched_key = None
            for key in _sponsor_keys(working):
                if working.sponsors[key].sponsor_id == event.sponsor_id:
                    matched_key = key
                    break
            if matched_key is None:
                raise ValueError("unknown sponsor_id")
            sponsor = working.sponsors[matched_key]
            share_fraction = _pool_share_fraction(working, sponsor)
            pool_payout = _pool_inventory_value(working) * share_fraction
            external_payout = _external_token_value(working, sponsor)
            fee_payout = to_decimal(sponsor.claimable_fees) + to_decimal(sponsor.withdrawable_fee_surplus)
            updated_balances = tuple(balance * (DECIMAL_ONE - share_fraction) for balance in _pool_balances(working))
            updated = replace(
                sponsor,
                share_units=DECIMAL_ZERO,
                target_delta_b=DECIMAL_ZERO,
                claimable_fees=DECIMAL_ZERO,
                withdrawable_fee_surplus=DECIMAL_ZERO,
                external_outcome_tokens=_zero_token_holdings(working.pricing.num_outcomes),
                residual_claimed=to_decimal(sponsor.residual_claimed) + pool_payout + external_payout + fee_payout,
            )
            working.sponsors[matched_key] = updated
            working.pricing = replace(working.pricing, pricing_q=updated_balances, timestamp=event.timestamp)
            working.treasury.lp_fee_balance -= fee_payout
            working.event_index += 1
            return _sync_state(working)

        raise TypeError(f"unsupported event type: {type(event)!r}")


class FpmmInvariantChecker:
    def __init__(self, *, lp_fee_bps: Numeric = 0, protocol_fee_bps: Numeric = 0) -> None:
        self.engine = FpmmBaselineEngine(lp_fee_bps=lp_fee_bps, protocol_fee_bps=protocol_fee_bps)

    def check_price_continuity(self, before: SimulationState, after: SimulationState) -> InvariantCheckResult:
        diff = max_abs_diff(tuple(map(to_decimal, before.pricing.price_vector)), tuple(map(to_decimal, after.pricing.price_vector)))
        return InvariantCheckResult(
            name="price_continuity",
            passed=diff <= PRICE_TOLERANCE,
            severity="error",
            details=f"max_diff={diff}",
            event_index=after.event_index,
        )

    def check_nonnegative_pool(self, state: SimulationState) -> InvariantCheckResult:
        min_balance = min(_pool_balances(state), default=DECIMAL_ZERO)
        return InvariantCheckResult(
            name="nonnegative_pool_balances",
            passed=min_balance >= -PRICE_TOLERANCE,
            severity="error",
            details=f"min_balance={min_balance}",
            event_index=state.event_index,
        )

    def check_nonnegative_share_supply(self, state: SimulationState) -> InvariantCheckResult:
        total_shares = _total_share_supply(state)
        return InvariantCheckResult(
            name="nonnegative_share_supply",
            passed=total_shares >= -PRICE_TOLERANCE,
            severity="error",
            details=f"total_share_supply={total_shares}",
            event_index=state.event_index,
        )

    def check_no_instantaneous_value_transfer(self, before: SimulationState, after: SimulationState) -> InvariantCheckResult:
        before_nav = self.engine.mark_to_market_nav(before)
        after_nav = self.engine.mark_to_market_nav(after)
        max_change = DECIMAL_ZERO
        for key in before_nav:
            max_change = max(max_change, abs(after_nav.get(key, DECIMAL_ZERO) - before_nav[key]))
        return InvariantCheckResult(
            name="no_instantaneous_value_transfer",
            passed=max_change <= NAV_TOLERANCE,
            severity="error",
            details=f"max_preexisting_nav_change={max_change}",
            event_index=after.event_index,
        )

    def check_all(self, state: SimulationState) -> list[InvariantCheckResult]:
        return [
            self.check_nonnegative_pool(state),
            self.check_nonnegative_share_supply(state),
        ]


class FpmmMetricCollector:
    def __init__(self, *, lp_fee_bps: Numeric = 0, protocol_fee_bps: Numeric = 0) -> None:
        self.engine = FpmmBaselineEngine(lp_fee_bps=lp_fee_bps, protocol_fee_bps=protocol_fee_bps)

    def price_continuity(self, before: SimulationState, after: SimulationState) -> dict[str, object]:
        return {
            "before": tuple(map(to_decimal, before.pricing.price_vector)),
            "after": tuple(map(to_decimal, after.pricing.price_vector)),
            "max_abs_change": max_abs_diff(tuple(map(to_decimal, before.pricing.price_vector)), tuple(map(to_decimal, after.pricing.price_vector))),
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
                        "improvement_ratio": after_return / before_return if before_return > 0 else DECIMAL_ONE,
                    }
                )
        return {"rows": rows}

    def lp_fairness(self, final_state: SimulationState) -> dict[str, object]:
        nav = self.engine.mark_to_market_nav(final_state)
        rows = []
        for key in _sponsor_keys(final_state):
            sponsor = final_state.sponsors[key]
            collateral = to_decimal(sponsor.collateral_posted)
            nav_value = nav[key]
            rows.append(
                {
                    "cohort_id": key,
                    "sponsor_id": sponsor.sponsor_id,
                    "entry_timestamp": sponsor.entry_timestamp,
                    "nav": nav_value,
                    "nav_per_deposit": nav_value / collateral if collateral > 0 else DECIMAL_ZERO,
                    "nav_per_risk": nav_value / collateral if collateral > 0 else DECIMAL_ZERO,
                }
            )
        return {"rows": rows}

    def solvency_report(self, state: SimulationState) -> dict[str, object]:
        min_balance = min(_pool_balances(state), default=DECIMAL_ZERO)
        total_shares = _total_share_supply(state)
        return {
            "passed": min_balance >= -PRICE_TOLERANCE and total_shares >= -PRICE_TOLERANCE,
            "details": f"min_balance={min_balance}, total_share_supply={total_shares}",
        }

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
            max_price_diff = max(
                max_price_diff,
                max_abs_diff(tuple(map(to_decimal, reference_state.pricing.price_vector)), tuple(map(to_decimal, state.pricing.price_vector))),
            )
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
                    "share_fraction": _pool_share_fraction(state, sponsor),
                    "pool_claim_value": _pool_claim_value(state, sponsor),
                    "external_token_value": _external_token_value(state, sponsor),
                    "claimable_fees": to_decimal(sponsor.claimable_fees),
                    "withdrawable_fee_surplus": to_decimal(sponsor.withdrawable_fee_surplus),
                    "residual_claimed": to_decimal(sponsor.residual_claimed),
                }
            )
        return {
            "policy": "pool_share",
            "reserve_required": DECIMAL_ZERO,
            "available_non_fee_assets": _pool_inventory_value(state),
            "releasable_pool": _pool_inventory_value(state),
            "total_residual_claimed": sum((to_decimal(row["residual_claimed"]) for row in rows), start=DECIMAL_ZERO),
            "rows": rows,
        }

    def divergence(self, reference_result: CanonicalEvaluation, candidate_result: CanonicalEvaluation) -> dict[str, object]:
        return {
            "implemented": False,
            "reason": "cross-mechanism comparison is reported separately from exact-reference divergence",
        }


class FpmmScenarioRunner:
    def __init__(
        self,
        num_outcomes: int,
        *,
        engine: FpmmBaselineEngine | None = None,
        invariant_checker: FpmmInvariantChecker | None = None,
        collector: FpmmMetricCollector | None = None,
        reference_trade_size: Numeric = 1,
        reference_trades: tuple[SimulationEvent, ...] | None = None,
    ) -> None:
        self.num_outcomes = num_outcomes
        self.engine = engine or FpmmBaselineEngine()
        self.collector = collector or FpmmMetricCollector(
            lp_fee_bps=self.engine.lp_fee_bps,
            protocol_fee_bps=self.engine.protocol_fee_bps,
        )
        self.invariant_checker = invariant_checker or FpmmInvariantChecker(
            lp_fee_bps=self.engine.lp_fee_bps,
            protocol_fee_bps=self.engine.protocol_fee_bps,
        )
        self.reference_trade_size = to_decimal(reference_trade_size)
        self.reference_trades = reference_trades

    def run(self, events: list[SimulationEvent], mechanism: MechanismVariant) -> CanonicalEvaluation:
        if mechanism is not MechanismVariant.FPMM_POOL_SHARE:
            raise ValueError("FpmmScenarioRunner only supports the FPMM mechanism variant")
        state = create_fpmm_initial_state(self.num_outcomes)
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
                invariant_results.append(self.invariant_checker.check_price_continuity(before, state))
                invariant_results.append(self.invariant_checker.check_no_instantaneous_value_transfer(before, state))

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
                "invariants": [result for result in invariant_results if result.name in {"nonnegative_pool_balances", "nonnegative_share_supply"}],
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


def create_fpmm_initial_state(num_outcomes: int) -> SimulationState:
    return SimulationState(
        mechanism=MechanismVariant.FPMM_POOL_SHARE,
        pricing=MarketPricingState(
            num_outcomes=num_outcomes,
            pricing_q=_zero_vector(num_outcomes),
            depth_b=DECIMAL_ZERO,
            price_vector=uniform_price_vector(num_outcomes),
            status=MarketStatus.CREATED,
            timestamp=0,
        ),
        traders=TraderPositionBook(aggregate_outstanding_claims=_zero_vector(num_outcomes)),
        sponsors={},
        treasury=TreasuryState(contract_funds=DECIMAL_ZERO),
    )
