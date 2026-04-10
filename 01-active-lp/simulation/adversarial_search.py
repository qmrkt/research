from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import product

from research.active_lp.experiments import ExperimentResult, ExperimentRunner
from research.active_lp.scenarios import ScenarioBundle, ScenarioConfig, _ScenarioBuilder, _default_reference_trades
from research.active_lp.types import MechanismVariant


@dataclass(slots=True)
class AdversarialSearchConfig:
    name: str = "active_lp_adversarial"
    num_outcomes_choices: tuple[int, ...] = (3, 5)
    initial_depth_choices: tuple[Decimal, ...] = (Decimal("100"),)
    fee_bps_choices: tuple[Decimal, ...] = (Decimal("100"),)
    protocol_fee_bps_choices: tuple[Decimal, ...] = (Decimal("25"),)
    late_delta_b_choices: tuple[Decimal, ...] = (Decimal("20"), Decimal("50"))
    pre_entry_shares_choices: tuple[Decimal, ...] = (Decimal("6"), Decimal("20"))
    post_entry_shares_choices: tuple[Decimal, ...] = (Decimal("0"), Decimal("12"))
    counterflow_ratio_choices: tuple[Decimal, ...] = (Decimal("0"), Decimal("0.25"))
    post_entry_modes: tuple[str, ...] = ("idle", "trend", "reversion")
    winner_policies: tuple[str, ...] = ("favorite", "hedge")
    mechanisms: tuple[MechanismVariant, ...] = (MechanismVariant.REFERENCE_PARALLEL_LMSR,)


def _build_bundle(
    config: AdversarialSearchConfig,
    trial_index: int,
    *,
    num_outcomes: int,
    initial_depth_b: Decimal,
    fee_bps: Decimal,
    protocol_fee_bps: Decimal,
    late_delta_b: Decimal,
    pre_entry_shares: Decimal,
    post_entry_shares: Decimal,
    counterflow_ratio: Decimal,
    post_entry_mode: str,
    winner_policy: str,
) -> ScenarioBundle:
    scenario_config = ScenarioConfig(
        name=f"{config.name}_{trial_index:04d}",
        seed=trial_index,
        num_outcomes=num_outcomes,
        initial_depth_b=initial_depth_b,
        fee_bps=fee_bps,
        protocol_fee_bps=protocol_fee_bps,
        mechanisms=config.mechanisms,
        reference_trades=_default_reference_trades(num_outcomes, shares=max(pre_entry_shares, late_delta_b / Decimal("4"))),
        evaluation_orderings=tuple(),
        news_process=f"winner_policy={winner_policy}",
        lp_entry_schedule=("late",),
        trader_population=("alpha", "beta", "gamma"),
        precision_mode="decimal",
    )

    builder = _ScenarioBuilder(scenario_config)
    favorite_outcome = 0
    hedge_outcome = 1 if num_outcomes > 1 else 0

    builder.bootstrap()
    builder.buy("alpha", favorite_outcome, pre_entry_shares)
    if counterflow_ratio > 0:
        builder.buy("beta", hedge_outcome, pre_entry_shares * counterflow_ratio)
    builder.lp_enter("lp_late", late_delta_b)
    if post_entry_mode == "trend" and post_entry_shares > 0:
        builder.buy("gamma", favorite_outcome, post_entry_shares)
    elif post_entry_mode == "reversion" and post_entry_shares > 0:
        builder.buy("gamma", hedge_outcome, post_entry_shares)

    winning_outcome = favorite_outcome if winner_policy == "favorite" else hedge_outcome
    builder.finish_resolved(winning_outcome)

    description = (
        f"Adversarial fairness search: pre_entry={pre_entry_shares}, late_delta_b={late_delta_b}, "
        f"counterflow_ratio={counterflow_ratio}, post_entry_mode={post_entry_mode}, winner_policy={winner_policy}"
    )
    return ScenarioBundle(
        config=scenario_config,
        description=description,
        primary_path=builder.path("primary"),
    )


def generate_adversarial_bundles(config: AdversarialSearchConfig) -> list[ScenarioBundle]:
    bundles: list[ScenarioBundle] = []
    for trial_index, params in enumerate(
        product(
            config.num_outcomes_choices,
            config.initial_depth_choices,
            config.fee_bps_choices,
            config.protocol_fee_bps_choices,
            config.late_delta_b_choices,
            config.pre_entry_shares_choices,
            config.post_entry_shares_choices,
            config.counterflow_ratio_choices,
            config.post_entry_modes,
            config.winner_policies,
        )
    ):
        (
            num_outcomes,
            initial_depth_b,
            fee_bps,
            protocol_fee_bps,
            late_delta_b,
            pre_entry_shares,
            post_entry_shares,
            counterflow_ratio,
            post_entry_mode,
            winner_policy,
        ) = params
        if post_entry_mode == "idle" and post_entry_shares != Decimal("0"):
            continue
        if post_entry_mode != "idle" and post_entry_shares == Decimal("0"):
            continue
        bundles.append(
            _build_bundle(
                config,
                trial_index,
                num_outcomes=num_outcomes,
                initial_depth_b=initial_depth_b,
                fee_bps=fee_bps,
                protocol_fee_bps=protocol_fee_bps,
                late_delta_b=late_delta_b,
                pre_entry_shares=pre_entry_shares,
                post_entry_shares=post_entry_shares,
                counterflow_ratio=counterflow_ratio,
                post_entry_mode=post_entry_mode,
                winner_policy=winner_policy,
            )
        )
    return bundles


def run_adversarial_search(
    config: AdversarialSearchConfig,
    *,
    runner: ExperimentRunner | None = None,
) -> list[ExperimentResult]:
    experiment_runner = runner or ExperimentRunner()
    return experiment_runner.run_bundles(generate_adversarial_bundles(config), run_family="adversarial")
