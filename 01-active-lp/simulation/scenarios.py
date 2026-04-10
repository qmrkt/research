from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Callable, Protocol

from research.active_lp.events import (
    BootstrapMarket,
    BuyOutcome,
    CancelMarket,
    ClaimLpResidual,
    ClaimRefund,
    ClaimWinnings,
    LpEnterActive,
    ResolveMarket,
    SellOutcome,
    SimulationEvent,
)
from research.active_lp.precision import DECIMAL_ZERO, to_decimal
from research.active_lp.reference_math import collateral_required
from research.active_lp.reference_parallel_lmsr import (
    RESERVE_POOL,
    ReferenceParallelLmsrEngine,
    create_initial_state,
)
from research.active_lp.state import SimulationState
from research.active_lp.types import MechanismVariant, Numeric

DEFAULT_MECHANISMS = (MechanismVariant.REFERENCE_PARALLEL_LMSR,)
DEFAULT_REFERENCE_TRADE_SHARES = Decimal("5")
BPS_DENOMINATOR = Decimal("10000")


@dataclass(slots=True)
class ScenarioConfig:
    name: str
    seed: int
    num_outcomes: int
    initial_depth_b: Numeric
    fee_bps: Numeric
    protocol_fee_bps: Numeric
    mechanisms: tuple[MechanismVariant, ...]
    reference_trades: tuple[BuyOutcome | SellOutcome, ...]
    evaluation_orderings: tuple[tuple[str, ...], ...]
    news_process: str | None = None
    lp_entry_schedule: tuple[str, ...] = field(default_factory=tuple)
    trader_population: tuple[str, ...] = field(default_factory=tuple)
    precision_mode: str | None = "decimal"
    residual_weight_scheme: str = "linear"
    residual_linear_lambda: Numeric = Decimal("1")
    duration_steps: int | None = None
    duration_bucket: str | None = None
    clock_mode: str = "event_step"
    split: str | None = None


@dataclass(slots=True)
class ScenarioPath:
    label: str
    events: tuple[SimulationEvent, ...]


@dataclass(slots=True)
class ScenarioBundle:
    config: ScenarioConfig
    description: str
    primary_path: ScenarioPath
    alternate_paths: tuple[ScenarioPath, ...] = field(default_factory=tuple)


def _restamp_events_to_duration(
    events: tuple[SimulationEvent, ...] | list[SimulationEvent],
    *,
    duration_steps: int,
) -> tuple[SimulationEvent, ...]:
    original_events = tuple(events)
    if not original_events:
        return tuple()
    if duration_steps < 1:
        raise ValueError("duration_steps must be positive")

    first_timestamp = original_events[0].timestamp
    settlement_timestamp = None
    for event in original_events:
        if isinstance(event, (ResolveMarket, CancelMarket)):
            settlement_timestamp = event.timestamp
            break
    if settlement_timestamp is None:
        settlement_timestamp = max(event.timestamp for event in original_events)

    pre_settlement_groups = sorted({event.timestamp for event in original_events if event.timestamp <= settlement_timestamp})
    post_settlement_groups = sorted({event.timestamp for event in original_events if event.timestamp > settlement_timestamp})

    timestamp_map: dict[int, int] = {}
    if len(pre_settlement_groups) == 1:
        timestamp_map[pre_settlement_groups[0]] = first_timestamp
    else:
        target_settlement = max(first_timestamp, duration_steps)
        span = target_settlement - first_timestamp
        last_index = len(pre_settlement_groups) - 1
        for index, timestamp in enumerate(pre_settlement_groups):
            mapped = first_timestamp + (span * index) // last_index
            timestamp_map[timestamp] = mapped
        timestamp_map[pre_settlement_groups[-1]] = target_settlement

    next_timestamp = timestamp_map[pre_settlement_groups[-1]] + 1
    for timestamp in post_settlement_groups:
        timestamp_map[timestamp] = next_timestamp
        next_timestamp += 1

    return tuple(replace(event, timestamp=timestamp_map[event.timestamp]) for event in original_events)


def restamp_bundle_duration(
    bundle: ScenarioBundle,
    *,
    duration_steps: int,
    duration_bucket: str,
    clock_mode: str = "duration_scaled",
    name_suffix: str | None = None,
    split: str | None = None,
) -> ScenarioBundle:
    suffix = name_suffix or duration_bucket
    return replace(
        bundle,
        config=replace(
            bundle.config,
            name=f"{bundle.config.name}_{suffix}",
            duration_steps=duration_steps,
            duration_bucket=duration_bucket,
            clock_mode=clock_mode,
            split=split,
        ),
        description=f"{bundle.description} [{duration_bucket} duration]",
        primary_path=replace(
            bundle.primary_path,
            events=_restamp_events_to_duration(bundle.primary_path.events, duration_steps=duration_steps),
        ),
        alternate_paths=tuple(
            replace(path, events=_restamp_events_to_duration(path.events, duration_steps=duration_steps))
            for path in bundle.alternate_paths
        ),
    )


class ScenarioDefinition(Protocol):
    def build_events(self, config: ScenarioConfig) -> ScenarioBundle:
        ...

    def describe(self) -> str:
        ...


class _ScenarioBuilder:
    def __init__(self, config: ScenarioConfig, *, engine: ReferenceParallelLmsrEngine | None = None) -> None:
        self.config = config
        self.engine = engine or ReferenceParallelLmsrEngine(
            lp_fee_bps=config.fee_bps,
            protocol_fee_bps=config.protocol_fee_bps,
            residual_weight_scheme=config.residual_weight_scheme,
            residual_linear_lambda=config.residual_linear_lambda,
        )
        self.state = create_initial_state(
            config.num_outcomes,
            residual_weight_scheme=config.residual_weight_scheme,
            residual_linear_lambda=config.residual_linear_lambda,
        )
        self.events: list[SimulationEvent] = []
        self._next_timestamp = 1

    def _consume_timestamp(self, timestamp: int | None) -> int:
        if timestamp is None:
            timestamp = self._next_timestamp
        self._next_timestamp = max(self._next_timestamp, timestamp + 1)
        return timestamp

    def bootstrap(
        self,
        *,
        creator_id: str = "creator",
        initial_collateral: Numeric | None = None,
        initial_depth_b: Numeric | None = None,
        timestamp: int | None = None,
    ) -> BootstrapMarket:
        ts = self._consume_timestamp(timestamp)
        depth_b = to_decimal(initial_depth_b if initial_depth_b is not None else self.config.initial_depth_b)
        floor = collateral_required(depth_b, self.state.pricing.price_vector)
        collateral = to_decimal(initial_collateral) if initial_collateral is not None else floor + Decimal("20")
        event = BootstrapMarket(
            timestamp=ts,
            creator_id=creator_id,
            initial_collateral=collateral,
            initial_depth_b=depth_b,
        )
        self.state = self.engine.apply_event(self.state, event)
        self.events.append(event)
        return event

    def buy(
        self,
        trader_id: str,
        outcome_index: int,
        shares: Numeric,
        *,
        timestamp: int | None = None,
        max_total_cost: Numeric | None = None,
    ) -> BuyOutcome:
        ts = self._consume_timestamp(timestamp)
        shares_dec = to_decimal(shares)
        quoted_cost = self.engine.buy_cost(self.state.pricing, outcome_index, shares_dec)
        fee_multiplier = Decimal("1") + (to_decimal(self.config.fee_bps) + to_decimal(self.config.protocol_fee_bps)) / BPS_DENOMINATOR
        slippage_limit = (
            to_decimal(max_total_cost)
            if max_total_cost is not None
            else quoted_cost * fee_multiplier + Decimal("1")
        )
        event = BuyOutcome(
            timestamp=ts,
            trader_id=trader_id,
            outcome_index=outcome_index,
            shares=shares_dec,
            max_total_cost=slippage_limit,
        )
        self.state = self.engine.apply_event(self.state, event)
        self.events.append(event)
        return event

    def sell(
        self,
        trader_id: str,
        outcome_index: int,
        shares: Numeric,
        *,
        timestamp: int | None = None,
        min_total_return: Numeric | None = None,
    ) -> SellOutcome:
        ts = self._consume_timestamp(timestamp)
        shares_dec = to_decimal(shares)
        quoted_return = self.engine.sell_return(self.state.pricing, outcome_index, shares_dec)
        fee_multiplier = Decimal("1") - (to_decimal(self.config.fee_bps) + to_decimal(self.config.protocol_fee_bps)) / BPS_DENOMINATOR
        net_quoted_return = max(quoted_return * fee_multiplier, DECIMAL_ZERO)
        floor = (
            to_decimal(min_total_return)
            if min_total_return is not None
            else max(net_quoted_return - Decimal("1e-12"), DECIMAL_ZERO)
        )
        event = SellOutcome(
            timestamp=ts,
            trader_id=trader_id,
            outcome_index=outcome_index,
            shares=shares_dec,
            min_total_return=floor,
        )
        self.state = self.engine.apply_event(self.state, event)
        self.events.append(event)
        return event

    def lp_enter(
        self,
        sponsor_id: str,
        target_delta_b: Numeric,
        *,
        timestamp: int | None = None,
        max_deposit: Numeric | None = None,
        min_delta_b: Numeric | None = None,
        cohort_policy_hint: str | None = None,
    ) -> LpEnterActive:
        ts = self._consume_timestamp(timestamp)
        delta_b = to_decimal(target_delta_b)
        required = collateral_required(delta_b, self.state.pricing.price_vector)
        max_deposit_value = to_decimal(max_deposit) if max_deposit is not None else required + Decimal("5")
        event = LpEnterActive(
            timestamp=ts,
            sponsor_id=sponsor_id,
            target_delta_b=delta_b,
            max_deposit=max_deposit_value,
            expected_price_vector=self.state.pricing.price_vector,
            price_tolerance=Decimal("1e-18"),
            min_delta_b=min_delta_b,
            cohort_policy_hint=cohort_policy_hint,
        )
        self.state = self.engine.apply_event(self.state, event)
        self.events.append(event)
        return event

    def resolve(self, winning_outcome: int, *, timestamp: int | None = None) -> ResolveMarket:
        ts = self._consume_timestamp(timestamp)
        event = ResolveMarket(timestamp=ts, winning_outcome=winning_outcome)
        self.state = self.engine.apply_event(self.state, event)
        self.events.append(event)
        return event

    def cancel(self, *, reason: str = "manual_cancel", timestamp: int | None = None) -> CancelMarket:
        ts = self._consume_timestamp(timestamp)
        event = CancelMarket(timestamp=ts, reason=reason)
        self.state = self.engine.apply_event(self.state, event)
        self.events.append(event)
        return event

    def claim_winnings_all(self, *, timestamp: int | None = None) -> None:
        if self.state.winning_outcome is None:
            raise ValueError("market not resolved")
        ts = self._consume_timestamp(timestamp)
        winning_outcome = self.state.winning_outcome
        for trader_id in sorted(self.state.traders.positions_by_trader):
            shares = to_decimal(self.state.traders.positions_by_trader[trader_id][winning_outcome])
            if shares <= 0:
                continue
            event = ClaimWinnings(
                timestamp=ts,
                trader_id=trader_id,
                outcome_index=winning_outcome,
                shares=shares,
            )
            self.state = self.engine.apply_event(self.state, event)
            self.events.append(event)
            ts += 1
        self._next_timestamp = max(self._next_timestamp, ts)

    def claim_winnings(
        self,
        trader_id: str,
        outcome_index: int,
        shares: Numeric,
        *,
        timestamp: int | None = None,
    ) -> ClaimWinnings:
        ts = self._consume_timestamp(timestamp)
        event = ClaimWinnings(
            timestamp=ts,
            trader_id=trader_id,
            outcome_index=outcome_index,
            shares=to_decimal(shares),
        )
        self.state = self.engine.apply_event(self.state, event)
        self.events.append(event)
        return event

    def claim_refunds_all(self, *, timestamp: int | None = None) -> None:
        ts = self._consume_timestamp(timestamp)
        for trader_id in sorted(self.state.traders.positions_by_trader):
            positions = self.state.traders.positions_by_trader[trader_id]
            for outcome_index, shares_value in enumerate(positions):
                shares = to_decimal(shares_value)
                if shares <= 0:
                    continue
                event = ClaimRefund(
                    timestamp=ts,
                    trader_id=trader_id,
                    outcome_index=outcome_index,
                    shares=shares,
                )
                self.state = self.engine.apply_event(self.state, event)
                self.events.append(event)
                ts += 1
        self._next_timestamp = max(self._next_timestamp, ts)

    def claim_refund(
        self,
        trader_id: str,
        outcome_index: int,
        shares: Numeric,
        *,
        timestamp: int | None = None,
    ) -> ClaimRefund:
        ts = self._consume_timestamp(timestamp)
        event = ClaimRefund(
            timestamp=ts,
            trader_id=trader_id,
            outcome_index=outcome_index,
            shares=to_decimal(shares),
        )
        self.state = self.engine.apply_event(self.state, event)
        self.events.append(event)
        return event

    def claim_lp_residual(self, sponsor_id: str, *, timestamp: int | None = None) -> ClaimLpResidual:
        ts = self._consume_timestamp(timestamp)
        event = ClaimLpResidual(timestamp=ts, sponsor_id=sponsor_id)
        self.state = self.engine.apply_event(self.state, event)
        self.events.append(event)
        return event

    def claim_lp_residuals_all(self, *, timestamp: int | None = None) -> None:
        ts = self._consume_timestamp(timestamp)
        sponsor_ids = sorted({sponsor.sponsor_id for sponsor in self.state.sponsors.values()})
        for sponsor_id in sponsor_ids:
            self.claim_lp_residual(sponsor_id, timestamp=ts)
            ts += 1
        self._next_timestamp = max(self._next_timestamp, ts)

    def finish_resolved(self, winning_outcome: int, *, timestamp: int | None = None) -> None:
        self.resolve(winning_outcome, timestamp=timestamp)
        self.claim_winnings_all()
        self.claim_lp_residuals_all()

    def finish_cancelled(self, *, timestamp: int | None = None) -> None:
        self.cancel(timestamp=timestamp)
        self.claim_refunds_all()
        self.claim_lp_residuals_all()

    def path(self, label: str) -> ScenarioPath:
        return ScenarioPath(label=label, events=tuple(self.events))


def _default_reference_trades(num_outcomes: int, *, shares: Numeric = DEFAULT_REFERENCE_TRADE_SHARES) -> tuple[BuyOutcome, ...]:
    shares_dec = to_decimal(shares)
    return tuple(
        BuyOutcome(
            timestamp=0,
            trader_id="__probe__",
            outcome_index=outcome_index,
            shares=shares_dec,
            max_total_cost=Decimal("1e50"),
        )
        for outcome_index in range(num_outcomes)
    )


def _base_config(
    name: str,
    *,
    seed: int = 1,
    num_outcomes: int = 3,
    initial_depth_b: Numeric = Decimal("100"),
    fee_bps: Numeric = Decimal("100"),
    protocol_fee_bps: Numeric = Decimal("25"),
    mechanisms: tuple[MechanismVariant, ...] = DEFAULT_MECHANISMS,
    evaluation_orderings: tuple[tuple[str, ...], ...] = tuple(),
    trader_population: tuple[str, ...] = ("alice", "bob", "carol"),
    lp_entry_schedule: tuple[str, ...] = tuple(),
) -> ScenarioConfig:
    return ScenarioConfig(
        name=name,
        seed=seed,
        num_outcomes=num_outcomes,
        initial_depth_b=initial_depth_b,
        fee_bps=fee_bps,
        protocol_fee_bps=protocol_fee_bps,
        mechanisms=mechanisms,
        reference_trades=_default_reference_trades(num_outcomes),
        evaluation_orderings=evaluation_orderings,
        trader_population=trader_population,
        lp_entry_schedule=lp_entry_schedule,
    )


def _build_neutral_late_lp(config: ScenarioConfig) -> ScenarioBundle:
    builder = _ScenarioBuilder(config)
    builder.bootstrap()
    builder.buy("alice", 0, Decimal("5"))
    builder.buy("bob", 1, Decimal("5"))
    builder.lp_enter("lp_late", Decimal("40"))
    builder.buy("carol", 2, Decimal("4"))
    builder.finish_resolved(1)
    return ScenarioBundle(
        config=config,
        description="Near-neutral market with one late LP joining after balanced trading.",
        primary_path=builder.path("primary"),
    )


def _build_skewed_late_lp(config: ScenarioConfig) -> ScenarioBundle:
    builder = _ScenarioBuilder(config)
    builder.bootstrap()
    builder.buy("alice", 0, Decimal("18"))
    builder.buy("bob", 0, Decimal("7"))
    builder.buy("carol", 1, Decimal("3"))
    builder.lp_enter("lp_late", Decimal("50"))
    builder.buy("alice", 0, Decimal("4"))
    builder.finish_resolved(0)
    return ScenarioBundle(
        config=config,
        description="Skewed market where an LP joins after one-sided order flow develops.",
        primary_path=builder.path("primary"),
    )


def _build_long_tail_late_lp(config: ScenarioConfig) -> ScenarioBundle:
    builder = _ScenarioBuilder(config)
    builder.bootstrap()
    builder.buy("alice", 0, Decimal("4"))
    builder.buy("bob", 3, Decimal("6"))
    builder.buy("carol", 6, Decimal("9"))
    builder.lp_enter("lp_late", Decimal("60"))
    builder.buy("dave", 7, Decimal("5"))
    builder.finish_resolved(6)
    return ScenarioBundle(
        config=config,
        description="Long-tail market with many outcomes and one late LP entry.",
        primary_path=builder.path("primary"),
    )


def _build_early_vs_late_same_delta_b(config: ScenarioConfig) -> ScenarioBundle:
    builder = _ScenarioBuilder(config)
    builder.bootstrap()
    builder.lp_enter("lp_early", Decimal("30"))
    builder.buy("alice", 0, Decimal("9"))
    builder.buy("bob", 1, Decimal("6"))
    builder.lp_enter("lp_late", Decimal("30"))
    builder.buy("carol", 0, Decimal("5"))
    builder.finish_resolved(0)
    return ScenarioBundle(
        config=config,
        description="Earlier and later LP cohorts both add the same delta-b under different market states.",
        primary_path=builder.path("primary"),
    )


def _timing_variant(config: ScenarioConfig, *, lp_before_second_trade: bool) -> ScenarioPath:
    builder = _ScenarioBuilder(config)
    builder.bootstrap()
    builder.buy("alice", 0, Decimal("8"))
    if lp_before_second_trade:
        builder.lp_enter("lp_timing", Decimal("35"))
    builder.buy("bob", 1, Decimal("5"))
    if not lp_before_second_trade:
        builder.lp_enter("lp_timing", Decimal("35"))
    builder.buy("carol", 0, Decimal("3"))
    builder.finish_resolved(0)
    return builder.path("lp_before_second_trade" if lp_before_second_trade else "lp_after_second_trade")


def _build_same_final_claims_different_timing(config: ScenarioConfig) -> ScenarioBundle:
    primary = _timing_variant(config, lp_before_second_trade=True)
    alternate = _timing_variant(config, lp_before_second_trade=False)
    return ScenarioBundle(
        config=config,
        description="Same final claims and LP size, but different LP entry timing for fairness/path-dependence comparison.",
        primary_path=primary,
        alternate_paths=(alternate,),
    )


def _build_cancellation_refund_path(config: ScenarioConfig) -> ScenarioBundle:
    builder = _ScenarioBuilder(config)
    builder.bootstrap()
    builder.buy("alice", 0, Decimal("8"))
    builder.lp_enter("lp_late", Decimal("40"))
    builder.buy("bob", 2, Decimal("6"))
    builder.finish_cancelled()
    return ScenarioBundle(
        config=config,
        description="Cancellation path with active LP cohort, refunds, and post-refund LP residual claims.",
        primary_path=builder.path("primary"),
    )


def _build_repeated_lp_entries(config: ScenarioConfig) -> ScenarioBundle:
    builder = _ScenarioBuilder(config)
    builder.bootstrap()
    builder.buy("alice", 1, Decimal("6"))
    builder.lp_enter("lp_one", Decimal("25"))
    builder.buy("bob", 2, Decimal("7"))
    builder.lp_enter("lp_two", Decimal("30"))
    builder.sell("alice", 1, Decimal("2"))
    builder.lp_enter("lp_three", Decimal("20"))
    builder.buy("carol", 1, Decimal("3"))
    builder.finish_resolved(1)
    return ScenarioBundle(
        config=config,
        description="Multiple LP cohorts join during active trading, including after an intermediate sell.",
        primary_path=builder.path("primary"),
    )


def _build_zero_flow_nav_invariance(config: ScenarioConfig) -> ScenarioBundle:
    builder = _ScenarioBuilder(config)
    builder.bootstrap()
    builder.buy("alice", 0, Decimal("5"))
    builder.lp_enter("lp_static", Decimal("35"))
    return ScenarioBundle(
        config=config,
        description="Zero-flow LP entry sanity check: no trades after entry, used for NAV invariance validation.",
        primary_path=builder.path("primary"),
    )


def _same_block_variant(config: ScenarioConfig, *, lp_before_block_trade: bool) -> ScenarioPath:
    builder = _ScenarioBuilder(config)
    builder.bootstrap()
    builder.buy("alice", 0, Decimal("6"), timestamp=2)
    if lp_before_block_trade:
        builder.lp_enter("lp_block", Decimal("30"), timestamp=3)
        builder.buy("bob", 2, Decimal("4"), timestamp=3)
    else:
        builder.buy("bob", 2, Decimal("4"), timestamp=3)
        builder.lp_enter("lp_block", Decimal("30"), timestamp=3)
    builder.buy("carol", 0, Decimal("2"), timestamp=4)
    builder.finish_resolved(0, timestamp=5)
    return builder.path("lp_before_block_trade" if lp_before_block_trade else "lp_after_block_trade")


def _build_same_block_trade_reordering(config: ScenarioConfig) -> ScenarioBundle:
    primary = _same_block_variant(config, lp_before_block_trade=False)
    alternate = _same_block_variant(config, lp_before_block_trade=True)
    return ScenarioBundle(
        config=config,
        description="Same-block reordering stress test around LP entry and adjacent trades.",
        primary_path=primary,
        alternate_paths=(alternate,),
    )


def _reserve_claim_order_variant(config: ScenarioConfig, order: tuple[str, ...], label: str) -> ScenarioPath:
    builder = _ScenarioBuilder(
        config,
        engine=ReferenceParallelLmsrEngine(
            lp_fee_bps=config.fee_bps,
            protocol_fee_bps=config.protocol_fee_bps,
            residual_policy=RESERVE_POOL,
            residual_weight_scheme=config.residual_weight_scheme,
            residual_linear_lambda=config.residual_linear_lambda,
        ),
    )
    builder.bootstrap()
    builder.buy("winner", 1, Decimal("12"))
    builder.buy("loser", 0, Decimal("8"))
    builder.lp_enter("late_lp", Decimal("50"))
    builder.buy("post", 2, Decimal("4"))
    builder.resolve(1)
    builder.claim_winnings("winner", 1, Decimal("6"))
    for sponsor_id in order:
        builder.claim_lp_residual(sponsor_id)
    builder.claim_winnings("winner", 1, Decimal("6"))
    return builder.path(label)


def _build_reserve_residual_claim_ordering(config: ScenarioConfig) -> ScenarioBundle:
    primary = _reserve_claim_order_variant(config, ("creator", "late_lp"), "creator_first")
    alternate = _reserve_claim_order_variant(config, ("late_lp", "creator"), "late_first")
    return ScenarioBundle(
        config=config,
        description="Reserve-based residual ordering test: LPs claim free residual before all winners claim, with LP claim order permuted.",
        primary_path=primary,
        alternate_paths=(alternate,),
    )


_SCENARIO_BUILDERS: dict[str, Callable[[ScenarioConfig], ScenarioBundle]] = {
    "neutral_late_lp": _build_neutral_late_lp,
    "skewed_late_lp": _build_skewed_late_lp,
    "long_tail_late_lp": _build_long_tail_late_lp,
    "early_vs_late_same_delta_b": _build_early_vs_late_same_delta_b,
    "same_final_claims_different_timing": _build_same_final_claims_different_timing,
    "cancellation_refund_path": _build_cancellation_refund_path,
    "repeated_lp_entries": _build_repeated_lp_entries,
    "zero_flow_nav_invariance": _build_zero_flow_nav_invariance,
    "same_block_trade_reordering": _build_same_block_trade_reordering,
    "reserve_residual_claim_ordering": _build_reserve_residual_claim_ordering,
}


def deterministic_scenario_configs() -> dict[str, ScenarioConfig]:
    long_tail = _base_config(
        "long_tail_late_lp",
        num_outcomes=8,
        initial_depth_b=Decimal("140"),
        trader_population=("alice", "bob", "carol", "dave"),
        lp_entry_schedule=("late",),
    )
    return {
        "neutral_late_lp": _base_config("neutral_late_lp", lp_entry_schedule=("late",)),
        "skewed_late_lp": _base_config("skewed_late_lp", lp_entry_schedule=("late",)),
        "long_tail_late_lp": long_tail,
        "early_vs_late_same_delta_b": _base_config(
            "early_vs_late_same_delta_b",
            evaluation_orderings=(("lp_early", "lp_late"),),
            lp_entry_schedule=("early", "late"),
        ),
        "same_final_claims_different_timing": _base_config(
            "same_final_claims_different_timing",
            evaluation_orderings=(("lp_before_second_trade",), ("lp_after_second_trade",)),
            lp_entry_schedule=("timing_variant",),
        ),
        "cancellation_refund_path": _base_config("cancellation_refund_path", lp_entry_schedule=("late",)),
        "repeated_lp_entries": _base_config(
            "repeated_lp_entries",
            lp_entry_schedule=("entry_1", "entry_2", "entry_3"),
        ),
        "zero_flow_nav_invariance": _base_config("zero_flow_nav_invariance", lp_entry_schedule=("late",)),
        "same_block_trade_reordering": _base_config(
            "same_block_trade_reordering",
            evaluation_orderings=(("lp_after_block_trade",), ("lp_before_block_trade",)),
            lp_entry_schedule=("same_block",),
        ),
        "reserve_residual_claim_ordering": _base_config(
            "reserve_residual_claim_ordering",
            evaluation_orderings=(("creator_first",), ("late_first",)),
            lp_entry_schedule=("late",),
            mechanisms=(
                MechanismVariant.REFERENCE_PARALLEL_LMSR_RESERVE_RESIDUAL,
                MechanismVariant.GLOBAL_STATE_FUNGIBLE_FEES_RESERVE_RESIDUAL,
            ),
        ),
    }


def deterministic_scenario_names() -> tuple[str, ...]:
    return tuple(_SCENARIO_BUILDERS.keys())


def build_deterministic_scenario(name: str) -> ScenarioBundle:
    configs = deterministic_scenario_configs()
    if name not in _SCENARIO_BUILDERS:
        raise KeyError(f"unknown deterministic scenario: {name}")
    return _SCENARIO_BUILDERS[name](configs[name])


def build_deterministic_scenarios(names: tuple[str, ...] | list[str] | None = None) -> list[ScenarioBundle]:
    selected = list(names) if names is not None else list(deterministic_scenario_names())
    return [build_deterministic_scenario(name) for name in selected]
