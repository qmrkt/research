from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from random import Random

from research.active_lp.experiments import ExperimentResult, ExperimentRunner
from research.active_lp.scenarios import ScenarioBundle, ScenarioConfig, ScenarioPath, _ScenarioBuilder, _default_reference_trades
from research.active_lp.types import MechanismVariant, Numeric


@dataclass(slots=True)
class MonteCarloSweepConfig:
    name: str = "active_lp_monte_carlo"
    seed: int = 1
    num_trials: int = 25
    num_outcomes_choices: tuple[int, ...] = (3, 5, 8)
    initial_depth_choices: tuple[Numeric, ...] = (Decimal("80"), Decimal("100"), Decimal("140"))
    fee_bps_choices: tuple[Numeric, ...] = (Decimal("50"), Decimal("100"), Decimal("200"))
    protocol_fee_bps_choices: tuple[Numeric, ...] = (Decimal("0"), Decimal("25"))
    lp_delta_b_choices: tuple[Numeric, ...] = (Decimal("20"), Decimal("35"), Decimal("50"))
    trade_count_range: tuple[int, int] = (4, 8)
    trader_population: tuple[str, ...] = ("alice", "bob", "carol", "dave")
    max_trade_share_choices: tuple[Numeric, ...] = (Decimal("2"), Decimal("4"), Decimal("6"), Decimal("8"))
    active_lp_entry_count_choices: tuple[int, ...] = (1, 2, 3)
    sell_probability: float = 0.2
    cancel_probability: float = 0.15
    mechanisms: tuple[MechanismVariant, ...] = (MechanismVariant.REFERENCE_PARALLEL_LMSR,)


def _pick(rng: Random, values: tuple[Numeric, ...] | tuple[int, ...]) -> Numeric | int:
    return values[rng.randrange(len(values))]


def _sample_outcome(rng: Random, probabilities: tuple[Decimal, ...]) -> int:
    threshold = Decimal(str(rng.random()))
    cumulative = Decimal("0")
    for idx, probability in enumerate(probabilities):
        cumulative += probability
        if threshold <= cumulative:
            return idx
    return len(probabilities) - 1


def _build_trial_bundle(config: MonteCarloSweepConfig, trial_index: int) -> ScenarioBundle:
    rng = Random(config.seed + trial_index)
    num_outcomes = int(_pick(rng, config.num_outcomes_choices))
    initial_depth_b = Decimal(str(_pick(rng, config.initial_depth_choices)))
    fee_bps = Decimal(str(_pick(rng, config.fee_bps_choices)))
    protocol_fee_bps = Decimal(str(_pick(rng, config.protocol_fee_bps_choices)))
    trade_count_min, trade_count_max = config.trade_count_range
    trade_count = rng.randint(trade_count_min, trade_count_max)
    lp_entry_count = int(_pick(rng, config.active_lp_entry_count_choices))
    max_trade_share = Decimal(str(_pick(rng, config.max_trade_share_choices)))

    scenario_config = ScenarioConfig(
        name=f"{config.name}_{trial_index:04d}",
        seed=config.seed + trial_index,
        num_outcomes=num_outcomes,
        initial_depth_b=initial_depth_b,
        fee_bps=fee_bps,
        protocol_fee_bps=protocol_fee_bps,
        mechanisms=config.mechanisms,
        reference_trades=_default_reference_trades(num_outcomes, shares=max_trade_share),
        evaluation_orderings=tuple(),
        news_process="random_terminal_outcome",
        lp_entry_schedule=tuple(f"entry_{idx}" for idx in range(lp_entry_count)),
        trader_population=config.trader_population,
        precision_mode="decimal",
    )

    builder = _ScenarioBuilder(scenario_config)
    builder.bootstrap()

    entry_slots = Counter(rng.randrange(trade_count + 1) for _ in range(lp_entry_count))
    sponsor_index = 0
    for slot in range(trade_count + 1):
        for _ in range(entry_slots.get(slot, 0)):
            sponsor_id = f"lp_{sponsor_index}"
            sponsor_index += 1
            builder.lp_enter(sponsor_id, Decimal(str(_pick(rng, config.lp_delta_b_choices))))
        if slot == trade_count:
            break

        sellable_positions = [
            (trader_id, outcome_index, Decimal(str(shares)))
            for trader_id, positions in builder.state.traders.positions_by_trader.items()
            for outcome_index, shares in enumerate(positions)
            if Decimal(str(shares)) > 0
        ]
        choose_sell = bool(sellable_positions) and rng.random() < config.sell_probability
        if choose_sell:
            trader_id, outcome_index, held_shares = sellable_positions[rng.randrange(len(sellable_positions))]
            candidate_sizes = [
                Decimal(str(size))
                for size in config.max_trade_share_choices
                if Decimal(str(size)) <= held_shares
            ]
            shares = candidate_sizes[rng.randrange(len(candidate_sizes))] if candidate_sizes else held_shares
            builder.sell(trader_id, outcome_index, shares)
        else:
            trader_id = config.trader_population[rng.randrange(len(config.trader_population))]
            outcome_index = rng.randrange(num_outcomes)
            shares = Decimal(str(_pick(rng, config.max_trade_share_choices)))
            builder.buy(trader_id, outcome_index, shares)

    if rng.random() < config.cancel_probability:
        builder.finish_cancelled()
        description = "Randomized active-LP cancellation path."
    else:
        winning_outcome = _sample_outcome(rng, tuple(map(Decimal, builder.state.pricing.price_vector)))
        builder.finish_resolved(winning_outcome)
        description = "Randomized active-LP resolved market path."

    return ScenarioBundle(
        config=scenario_config,
        description=description,
        primary_path=builder.path("primary"),
    )


def generate_monte_carlo_bundles(config: MonteCarloSweepConfig) -> list[ScenarioBundle]:
    return [_build_trial_bundle(config, trial_index) for trial_index in range(config.num_trials)]


def run_monte_carlo_sweep(
    config: MonteCarloSweepConfig,
    *,
    runner: ExperimentRunner | None = None,
) -> list[ExperimentResult]:
    experiment_runner = runner or ExperimentRunner()
    return experiment_runner.run_bundles(generate_monte_carlo_bundles(config), run_family="monte_carlo")
