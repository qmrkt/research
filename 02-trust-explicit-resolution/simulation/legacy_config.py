"""Explicit compatibility mapping; publication runs use GameConfig directly."""
from .economics import GameConfig


def to_game(config):
    if config.num_outcomes != 2:
        raise ValueError("The funded compatibility game is binary")
    if config.proposer_mev_model.value != "position_bounded":
        raise ValueError("Unbacked pool-fraction MEV was retired; use actual signed collateral-backed positions")
    if config.composition_scenario.value != "none":
        raise ValueError("Source composition must be executed by the blueprint prototype, not a topology probability")
    rules = {"flat": "flat", "pool_proportional": "proportional", "capped_pool_proportional": "capped"}
    if config.bond_structure.value not in rules:
        raise ValueError("A one-shot bond multiplier is not a sequential escalation game")
    if not 0 <= .5 + config.bounty_fraction <= 1:
        raise ValueError("Base reward plus bounty cannot exceed the slashed proposer bond")
    return GameConfig(
        pool=config.pool_size, participants=config.num_participants,
        positions={"uniform": "uniform", "concentrated": "whale", "power_law": "power_law"}[config.stake_distribution.value],
        bond_rule=rules[config.bond_structure.value], bond_floor=config.flat_bond, bond_rate=config.bond_rate,
        bond_cap=config.bond_cap if config.bond_cap is not None else 1e18,
        challenger_ratio=1 if config.challenger_bond_symmetric else .5,
        reward_fraction=.5 + config.bounty_fraction,
        accuracy=config.adjudicator_accuracy, window=config.challenge_window_hours,
        adjudication_delay=config.adjudication_delay_hours,
        attention={"all_attentive": "attentive", "majority_lazy": "lazy", "stake_proportional": "stake"}[config.challenger_mix.value],
        attention_multiplier=config.attention_coefficient,
        capital_profile={"unconstrained": "unconstrained", "retail_heavy": "retail", "mixed": "mixed", "specialized": "specialized"}[config.proposer_budget_profile.value],
        proposer_fee=config.proposer_fee, proposer_work=config.proposer_work_cost,
        verification_work=config.verification_work_cost, challenge_work=config.challenge_work_cost,
        capital_apy=config.proposer_capital_cost_apy, honest_proposer=config.proposer_type.value == "honest",
    )
