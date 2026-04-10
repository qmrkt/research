"""Core dispute economics simulation engine."""

from __future__ import annotations

import random

from research.resolution_trust.agents import (
    challenger_decides,
    estimate_proposer_mev,
    generate_participants,
    participant_checks,
    proposer_action,
    select_proposer,
)
from research.resolution_trust.types import (
    EpisodeResult,
    SimConfig,
    SimResult,
)


def run_episode(config: SimConfig, rng: random.Random) -> EpisodeResult:
    """Run a single resolution episode and return the result."""
    participants = generate_participants(config, rng)
    proposer_mevs = {
        p.index: estimate_proposer_mev(config, p, rng) for p in participants
    }
    proposer_actions = {
        p.index: proposer_action(config, p, participants, proposer_mevs[p.index])
        for p in participants
    }
    proposer, eligible_count, willing_count = select_proposer(
        config, participants, proposer_actions, rng
    )

    if proposer is None:
        return EpisodeResult(
            proposal_is_false=False,
            challenged=False,
            proposal_submitted=False,
            resolution_correct=True,
            eligible_proposers=eligible_count,
            willing_proposers=willing_count,
            num_verifiers=0,
            proposer_payoff=0.0,
            challenger_payoff=0.0,
            total_bond_locked=0.0,
            time_to_finalization_hours=0.0,
            bounty_paid=0.0,
        )

    action = proposer_actions[proposer.index]
    proposal_is_false = action == "false"

    if not proposal_is_false:
        # Honest proposal: always correct, minimal lockup
        return EpisodeResult(
            proposal_is_false=False,
            challenged=False,
            proposal_submitted=True,
            adjudicator_correct=True,
            resolution_correct=True,
            eligible_proposers=eligible_count,
            willing_proposers=willing_count,
            num_verifiers=0,
            proposer_payoff=config.proposer_fee - config.proposer_submission_cost,
            challenger_payoff=0.0,
            total_bond_locked=config.proposer_bond,
            time_to_finalization_hours=config.challenge_window_hours,
            bounty_paid=0.0,
        )

    # Step 2: False proposal submitted. Check if anyone challenges.
    challengers = []
    num_verifiers = 0
    for p in participants:
        if p.index == proposer.index:
            continue
        if participant_checks(p, rng):
            num_verifiers += 1
            if challenger_decides(p, config):
                challengers.append(p)

    # Verification bounty attracts additional non-stake verifiers.
    # Unlike stake-motivated challengers, bounty hunters verify regardless
    # of their position. They challenge if the trace doesn't match.
    import math
    bounty_paid = 0.0
    if config.bounty_fraction > 0:
        bounty_value = config.verification_bounty
        # Sigmoid response matching the proposer's model
        external_check_prob = min(0.4, 0.05 * math.log1p(bounty_value / 10.0))
        if rng.random() < external_check_prob:
            num_verifiers += 1
            # External verifier detects the false proposal
            challengers.append(None)  # sentinel for external challenger
            bounty_paid = bounty_value

    challenged = len(challengers) > 0

    if not challenged:
        # False proposal finalizes unchallenged
        mev = proposer_mevs[proposer.index]
        return EpisodeResult(
            proposal_is_false=True,
            challenged=False,
            proposal_submitted=True,
            adjudicator_correct=True,  # irrelevant
            resolution_correct=False,
            eligible_proposers=eligible_count,
            willing_proposers=willing_count,
            num_verifiers=num_verifiers,
            proposer_payoff=mev + config.proposer_fee - config.proposer_submission_cost,
            challenger_payoff=0.0,
            total_bond_locked=config.proposer_bond,
            time_to_finalization_hours=config.challenge_window_hours,
            bounty_paid=0.0,
        )

    # Step 3: Challenge submitted. Adjudicator rules.
    adjudicator_correct = rng.random() < config.adjudicator_accuracy

    if adjudicator_correct:
        # False proposal overturned
        proposer_loss = config.proposer_bond
        challenger_reward = config.proposer_bond * 0.5  # half of proposer bond
        return EpisodeResult(
            proposal_is_false=True,
            challenged=True,
            proposal_submitted=True,
            adjudicator_correct=True,
            resolution_correct=True,
            eligible_proposers=eligible_count,
            willing_proposers=willing_count,
            num_verifiers=num_verifiers,
            proposer_payoff=-(proposer_loss + config.proposer_submission_cost),
            challenger_payoff=challenger_reward,
            total_bond_locked=config.proposer_bond + config.challenger_bond,
            time_to_finalization_hours=config.challenge_window_hours + 24.0,  # adjudication adds time
            bounty_paid=bounty_paid,
        )
    else:
        # Adjudicator incorrectly upholds false proposal
        mev = proposer_mevs[proposer.index]
        return EpisodeResult(
            proposal_is_false=True,
            challenged=True,
            proposal_submitted=True,
            adjudicator_correct=False,
            resolution_correct=False,
            eligible_proposers=eligible_count,
            willing_proposers=willing_count,
            num_verifiers=num_verifiers,
            proposer_payoff=mev + config.proposer_fee - config.proposer_submission_cost,
            challenger_payoff=-config.challenger_bond,
            total_bond_locked=config.proposer_bond + config.challenger_bond,
            time_to_finalization_hours=config.challenge_window_hours + 24.0,
            bounty_paid=0.0,
        )


def run_simulation(config: SimConfig) -> SimResult:
    """Run a full simulation with config.num_episodes episodes."""
    rng = random.Random(config.seed)
    result = SimResult(config=config)

    for _ in range(config.num_episodes):
        episode = run_episode(config, rng)
        result.episodes.append(episode)

    return result


def run_parameter_sweep(configs: list[SimConfig]) -> list[SimResult]:
    """Run simulation across multiple configurations."""
    return [run_simulation(c) for c in configs]
