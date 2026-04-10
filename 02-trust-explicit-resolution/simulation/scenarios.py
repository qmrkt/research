"""Scenario families and parameter sweeps for the dispute simulation."""

from __future__ import annotations

from research.resolution_trust.types import (
    BondStructure,
    ChallengerMix,
    ProposerBudgetProfile,
    ProposerMEVModel,
    ProposerType,
    SimConfig,
    StakeDistribution,
)


def bond_scaling_sweep() -> list[SimConfig]:
    """Sweep: flat vs pool-proportional bonds across market sizes."""
    configs = []
    for pool_size in [50, 500, 5_000, 50_000]:
        # Flat bond baseline
        configs.append(SimConfig(
            pool_size=pool_size,
            num_participants=10,
            bond_structure=BondStructure.FLAT,
            flat_bond=10.0,
            challenger_mix=ChallengerMix.MAJORITY_LAZY,
            proposer_type=ProposerType.STRATEGIC,
            adjudicator_accuracy=0.9,
        ))
        # Pool-proportional at various rates
        for rho in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]:
            configs.append(SimConfig(
                pool_size=pool_size,
                num_participants=10,
                bond_structure=BondStructure.POOL_PROPORTIONAL,
                bond_rate=rho,
                challenger_mix=ChallengerMix.MAJORITY_LAZY,
                proposer_type=ProposerType.STRATEGIC,
                adjudicator_accuracy=0.9,
            ))
    return configs


def bond_structure_comparison() -> list[SimConfig]:
    """Compare flat, proportional, linear, and exponential bond structures."""
    configs = []
    pool_size = 5_000
    for structure in [
        BondStructure.FLAT,
        BondStructure.POOL_PROPORTIONAL,
        BondStructure.LINEAR_ESCALATION,
        BondStructure.EXPONENTIAL_ESCALATION,
    ]:
        configs.append(SimConfig(
            pool_size=pool_size,
            num_participants=10,
            bond_structure=structure,
            bond_rate=0.10,
            flat_bond=10.0,
            challenger_mix=ChallengerMix.MAJORITY_LAZY,
            proposer_type=ProposerType.STRATEGIC,
            adjudicator_accuracy=0.9,
        ))
    # Also proportional at 0.15
    configs.append(SimConfig(
        pool_size=pool_size,
        num_participants=10,
        bond_structure=BondStructure.POOL_PROPORTIONAL,
        bond_rate=0.15,
        challenger_mix=ChallengerMix.MAJORITY_LAZY,
        proposer_type=ProposerType.STRATEGIC,
        adjudicator_accuracy=0.9,
    ))
    # Representative capped structure: proportional target with a binding ceiling.
    configs.append(SimConfig(
        pool_size=pool_size,
        num_participants=10,
        bond_structure=BondStructure.CAPPED_POOL_PROPORTIONAL,
        bond_rate=0.15,
        bond_cap=500.0,
        challenger_mix=ChallengerMix.MAJORITY_LAZY,
        proposer_type=ProposerType.STRATEGIC,
        adjudicator_accuracy=0.9,
    ))
    return configs


def bond_cap_sweep() -> list[SimConfig]:
    """Test capped pool-proportional bonds against uncapped baselines."""
    configs = []
    for pool_size in [5_000, 50_000]:
        # Uncapped baselines at the deployment-relevant rates.
        for rho in [0.10, 0.15]:
            configs.append(SimConfig(
                pool_size=pool_size,
                num_participants=10,
                bond_structure=BondStructure.POOL_PROPORTIONAL,
                bond_rate=rho,
                challenger_mix=ChallengerMix.MAJORITY_LAZY,
                proposer_type=ProposerType.STRATEGIC,
                adjudicator_accuracy=0.9,
            ))
        # Capped versions of the recommended 15% structure.
        for cap in [250.0, 500.0, 1_000.0, 2_500.0, 5_000.0, 7_500.0, 10_000.0]:
            configs.append(SimConfig(
                pool_size=pool_size,
                num_participants=10,
                bond_structure=BondStructure.CAPPED_POOL_PROPORTIONAL,
                bond_rate=0.15,
                bond_cap=cap,
                challenger_mix=ChallengerMix.MAJORITY_LAZY,
                proposer_type=ProposerType.STRATEGIC,
                adjudicator_accuracy=0.9,
            ))
    return configs


def mev_bound_sweep() -> list[SimConfig]:
    """Compare pool-fraction and position-bounded proposer MEV models."""
    configs = []
    for pool_size in [5_000, 50_000]:
        for stake_distribution in [StakeDistribution.UNIFORM, StakeDistribution.POWER_LAW]:
            for mev_model in [ProposerMEVModel.POOL_FRACTION, ProposerMEVModel.POSITION_BOUNDED]:
                configs.append(SimConfig(
                    pool_size=pool_size,
                    num_participants=10,
                    bond_structure=BondStructure.POOL_PROPORTIONAL,
                    bond_rate=0.15,
                    challenger_mix=ChallengerMix.MAJORITY_LAZY,
                    proposer_type=ProposerType.STRATEGIC,
                    proposer_mev_model=mev_model,
                    proposer_budget_profile=ProposerBudgetProfile.UNCONSTRAINED,
                    stake_distribution=stake_distribution,
                    adjudicator_accuracy=0.9,
                ))
    return configs


def proposer_liveness_sweep() -> list[SimConfig]:
    """Stress proposer liveness under capital-budget profiles."""
    configs = []
    for pool_size in [1_000, 5_000, 10_000, 50_000]:
        for profile in [
            ProposerBudgetProfile.RETAIL_HEAVY,
            ProposerBudgetProfile.MIXED,
            ProposerBudgetProfile.SPECIALIZED,
        ]:
            configs.append(SimConfig(
                pool_size=pool_size,
                num_participants=10,
                bond_structure=BondStructure.POOL_PROPORTIONAL,
                bond_rate=0.15,
                challenger_mix=ChallengerMix.MAJORITY_LAZY,
                proposer_type=ProposerType.STRATEGIC,
                proposer_mev_model=ProposerMEVModel.POSITION_BOUNDED,
                proposer_budget_profile=profile,
                stake_distribution=StakeDistribution.POWER_LAW,
                adjudicator_accuracy=0.9,
            ))
    return configs


def proposer_compensation_sweep() -> list[SimConfig]:
    """Test whether proposer fees convert capital eligibility into actual liveness."""
    configs = []
    for pool_size in [5_000, 50_000]:
        for profile in [
            ProposerBudgetProfile.RETAIL_HEAVY,
            ProposerBudgetProfile.MIXED,
        ]:
            for fee in [0.0, 5.0, 10.0, 15.0, 25.0, 50.0]:
                configs.append(SimConfig(
                    pool_size=pool_size,
                    num_participants=10,
                    bond_structure=BondStructure.POOL_PROPORTIONAL,
                    bond_rate=0.15,
                    challenger_mix=ChallengerMix.MAJORITY_LAZY,
                    proposer_type=ProposerType.STRATEGIC,
                    proposer_mev_model=ProposerMEVModel.POSITION_BOUNDED,
                    proposer_budget_profile=profile,
                    stake_distribution=StakeDistribution.POWER_LAW,
                    proposer_fee=fee,
                    proposer_work_cost=10.0,
                    proposer_capital_cost_apy=0.20,
                    adjudicator_accuracy=0.9,
                ))
    return configs


def lazy_verifier_sweep() -> list[SimConfig]:
    """Test the lazy verifier problem across participant counts and attention levels."""
    configs = []
    for k in [3, 5, 10, 30, 100]:
        for alpha in [0.1, 0.5, 1.0, 2.0]:
            configs.append(SimConfig(
                pool_size=5_000,
                num_participants=k,
                bond_structure=BondStructure.POOL_PROPORTIONAL,
                bond_rate=0.15,
                attention_coefficient=alpha,
                challenger_mix=ChallengerMix.STAKE_PROPORTIONAL,
                proposer_type=ProposerType.STRATEGIC,
                adjudicator_accuracy=0.9,
            ))
    return configs


def verification_bounty_sweep() -> list[SimConfig]:
    """Test verification bounty effectiveness across thin and thick markets."""
    configs = []
    for k in [3, 5, 10, 30]:
        for phi in [0.0, 0.05, 0.10, 0.15, 0.20]:
            configs.append(SimConfig(
                pool_size=5_000,
                num_participants=k,
                bond_structure=BondStructure.POOL_PROPORTIONAL,
                bond_rate=0.15,
                bounty_fraction=phi,
                challenger_mix=ChallengerMix.MAJORITY_LAZY,
                proposer_type=ProposerType.STRATEGIC,
                adjudicator_accuracy=0.9,
            ))
    return configs


def challenge_window_sweep() -> list[SimConfig]:
    """Test challenge window duration effects."""
    configs = []
    for window in [12, 24, 48, 72]:
        for mix in [ChallengerMix.ALL_ATTENTIVE, ChallengerMix.MAJORITY_LAZY, ChallengerMix.STAKE_PROPORTIONAL]:
            configs.append(SimConfig(
                pool_size=5_000,
                num_participants=10,
                bond_structure=BondStructure.POOL_PROPORTIONAL,
                bond_rate=0.15,
                challenge_window_hours=float(window),
                check_rate_per_hour=0.1,
                challenger_mix=mix,
                proposer_type=ProposerType.STRATEGIC,
                adjudicator_accuracy=0.9,
            ))
    return configs


def adjudicator_accuracy_sweep() -> list[SimConfig]:
    """Test adjudicator accuracy vs challenge probability interaction."""
    configs = []
    for p_a in [0.7, 0.8, 0.9, 0.95, 1.0]:
        for mix in [ChallengerMix.ALL_ATTENTIVE, ChallengerMix.MAJORITY_LAZY]:
            configs.append(SimConfig(
                pool_size=5_000,
                num_participants=10,
                bond_structure=BondStructure.POOL_PROPORTIONAL,
                bond_rate=0.15,
                challenger_mix=mix,
                proposer_type=ProposerType.STRATEGIC,
                adjudicator_accuracy=p_a,
            ))
    return configs


def honest_majority_baseline() -> list[SimConfig]:
    """Honest proposer scenarios: test that the mechanism doesn't over-penalize honesty."""
    configs = []
    for pool_size in [50, 500, 5_000, 50_000]:
        for rho in [0.05, 0.10, 0.15, 0.20]:
            configs.append(SimConfig(
                pool_size=pool_size,
                num_participants=10,
                bond_structure=BondStructure.POOL_PROPORTIONAL,
                bond_rate=rho,
                proposer_type=ProposerType.HONEST,
                adjudicator_accuracy=0.9,
            ))
    return configs


def composition_resilience() -> list[SimConfig]:
    """Test multi-source vs single-source blueprint resilience."""
    # This is modeled indirectly: multi-source blueprints have higher
    # effective attention (participants cross-check independently),
    # which maps to higher alpha.
    configs = []
    for alpha in [0.3, 1.0, 3.0]:
        configs.append(SimConfig(
            pool_size=5_000,
            num_participants=10,
            bond_structure=BondStructure.POOL_PROPORTIONAL,
            bond_rate=0.15,
            attention_coefficient=alpha,
            challenger_mix=ChallengerMix.STAKE_PROPORTIONAL,
            proposer_type=ProposerType.STRATEGIC,
            adjudicator_accuracy=0.9,
        ))
    return configs


def stake_distribution_sweep() -> list[SimConfig]:
    """Test how stake concentration affects dispute dynamics."""
    configs = []
    for dist in StakeDistribution:
        for k in [5, 10, 30]:
            configs.append(SimConfig(
                pool_size=5_000,
                num_participants=k,
                bond_structure=BondStructure.POOL_PROPORTIONAL,
                bond_rate=0.15,
                stake_distribution=dist,
                challenger_mix=ChallengerMix.STAKE_PROPORTIONAL,
                proposer_type=ProposerType.STRATEGIC,
                adjudicator_accuracy=0.9,
            ))
    return configs


SCENARIO_FAMILIES = {
    "bond_scaling": bond_scaling_sweep,
    "bond_structure": bond_structure_comparison,
    "bond_cap": bond_cap_sweep,
    "mev_bound": mev_bound_sweep,
    "proposer_liveness": proposer_liveness_sweep,
    "proposer_compensation": proposer_compensation_sweep,
    "lazy_verifier": lazy_verifier_sweep,
    "verification_bounty": verification_bounty_sweep,
    "challenge_window": challenge_window_sweep,
    "adjudicator_accuracy": adjudicator_accuracy_sweep,
    "honest_majority": honest_majority_baseline,
    "composition": composition_resilience,
    "stake_distribution": stake_distribution_sweep,
}


def all_scenarios() -> dict[str, list[SimConfig]]:
    return {name: fn() for name, fn in SCENARIO_FAMILIES.items()}
