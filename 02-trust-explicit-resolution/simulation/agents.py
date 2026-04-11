"""Agent behavior models for the dispute economics simulation."""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from research.resolution_trust.types import Participant, SimConfig


COMPOSITION_FALSE_SUBMISSION_PROB = {
    "none": 1.0,
    "single_source_corrupt": 1.0,
    "three_source_one_corrupt": 0.20,
    "three_source_two_corrupt": 0.80,
}
COMPOSITION_HONEST_COUNTERS = {
    "none": 0,
    "single_source_corrupt": 0,
    "three_source_one_corrupt": 2,
    "three_source_two_corrupt": 1,
}
COMPOSITION_BASE_DETECTION = 0.35
COMPOSITION_DETECTION_PER_COUNTER = 0.30


def generate_participants(config: SimConfig, rng: random.Random) -> list[Participant]:
    """Generate market participants with positions and attention probabilities."""
    from research.resolution_trust.types import (
        ChallengerMix,
        Participant,
        ProposerBudgetProfile,
        StakeDistribution,
    )

    k = config.num_participants
    L = config.pool_size

    # Generate stake distribution
    if config.stake_distribution == StakeDistribution.UNIFORM:
        raw_stakes = [L / k] * k
    elif config.stake_distribution == StakeDistribution.CONCENTRATED:
        whale_stake = 0.6 * L
        rest_stake = 0.4 * L / max(1, k - 1)
        raw_stakes = [whale_stake] + [rest_stake] * (k - 1)
    elif config.stake_distribution == StakeDistribution.POWER_LAW:
        raw = [1.0 / (i + 1) ** 0.8 for i in range(k)]
        total = sum(raw)
        raw_stakes = [r * L / total for r in raw]
    else:
        raw_stakes = [L / k] * k

    participants = []
    for i in range(k):
        wins_under_true = rng.random() < 0.5
        stake = raw_stakes[i]

        # Attention probability: per-participant check probability during the window.
        # Uses a Poisson model where the check rate depends on the participant mix.
        # The window duration matters: longer windows give more chances to check.
        w = config.challenge_window_hours
        if config.challenger_mix == ChallengerMix.ALL_ATTENTIVE:
            # Everyone checks regularly: rate 0.05-0.15 per hour
            personal_rate = 0.05 + rng.random() * 0.10
            attn = _poisson_check_prob(w, personal_rate)
        elif config.challenger_mix == ChallengerMix.MAJORITY_LAZY:
            # 15% check occasionally (rate ~0.01-0.03/h),
            # 85% check very rarely (rate ~0.0005-0.003/h).
            if rng.random() < 0.15:
                personal_rate = 0.01 + rng.random() * 0.02
            else:
                personal_rate = 0.0005 + rng.random() * 0.0025
            attn = _poisson_check_prob(w, personal_rate)
        elif config.challenger_mix == ChallengerMix.STAKE_PROPORTIONAL:
            # Rate proportional to stake fraction with noise
            base_rate = config.attention_coefficient * 0.02 * stake / L
            personal_rate = base_rate * (0.3 + rng.random() * 1.4)
            attn = _poisson_check_prob(w, personal_rate)
        else:
            attn = 0.0

        role = "lazy" if attn < 0.01 else "challenger"

        participants.append(Participant(
            index=i,
            stake=abs(stake),
            is_winner_under_true=wins_under_true,
            is_winner_under_false=not wins_under_true,
            attention_prob=attn,
            capital_budget=_sample_capital_budget(config.proposer_budget_profile, rng),
            role=role,
        ))

    return participants


def composition_false_submission_probability(config: SimConfig) -> float:
    """Probability that a corrupted source topology yields a false submit path."""
    return COMPOSITION_FALSE_SUBMISSION_PROB[config.composition_scenario.value]


def composition_detection_probability(config: SimConfig) -> float:
    """
    Probability that a checker can diagnose a false trace once they inspect it.

    Honest counter-sources leave contradictory artifacts in the published trace.
    More honest counter-sources make the false path easier to challenge.
    """
    honest_counters = COMPOSITION_HONEST_COUNTERS[config.composition_scenario.value]
    return min(1.0, COMPOSITION_BASE_DETECTION + honest_counters * COMPOSITION_DETECTION_PER_COUNTER)


def _poisson_check_prob(window_hours: float, rate_per_hour: float) -> float:
    """Probability of checking at least once during window (Poisson model)."""
    return 1.0 - math.exp(-rate_per_hour * window_hours)


def _log_uniform(rng: random.Random, low: float, high: float) -> float:
    """Sample from a log-uniform distribution on [low, high]."""
    return math.exp(rng.uniform(math.log(low), math.log(high)))


def _sample_capital_budget(profile, rng: random.Random) -> float:
    """Stylized proposer-capital profiles."""
    from research.resolution_trust.types import ProposerBudgetProfile

    if profile == ProposerBudgetProfile.UNCONSTRAINED:
        return 1e18

    draw = rng.random()
    if profile == ProposerBudgetProfile.RETAIL_HEAVY:
        if draw < 0.70:
            return _log_uniform(rng, 100.0, 1_000.0)
        if draw < 0.95:
            return _log_uniform(rng, 1_000.0, 5_000.0)
        return _log_uniform(rng, 5_000.0, 20_000.0)

    if profile == ProposerBudgetProfile.MIXED:
        if draw < 0.35:
            return _log_uniform(rng, 250.0, 2_500.0)
        if draw < 0.75:
            return _log_uniform(rng, 2_500.0, 10_000.0)
        return _log_uniform(rng, 10_000.0, 50_000.0)

    if profile == ProposerBudgetProfile.SPECIALIZED:
        if draw < 0.15:
            return _log_uniform(rng, 1_000.0, 5_000.0)
        if draw < 0.70:
            return _log_uniform(rng, 5_000.0, 25_000.0)
        return _log_uniform(rng, 25_000.0, 100_000.0)

    return 1e18


def select_proposer(
    config: SimConfig,
    participants: list[Participant],
    proposer_actions: dict[int, Literal["abstain", "truthful", "false"]],
    rng: random.Random,
) -> tuple[Participant | None, int, int]:
    """Return the chosen proposer plus capital-eligible and willing counts."""
    eligible = [p for p in participants if p.capital_budget >= config.proposer_bond]
    willing = [p for p in eligible if proposer_actions[p.index] != "abstain"]
    if not willing:
        return None, len(eligible), 0

    from research.resolution_trust.types import ProposerMEVModel

    if config.proposer_mev_model == ProposerMEVModel.POSITION_BOUNDED:
        # Conservative open-market assumption: the most exposed eligible actor
        # is the one with the greatest temptation to misresolve.
        proposer = max(willing, key=lambda p: p.stake)
    else:
        proposer = rng.choice(willing)
    return proposer, len(eligible), len(willing)


def estimate_challenge_probability(
    config: SimConfig,
    proposer: Participant,
    participants: list[Participant],
) -> float:
    """Estimate the probability that a false proposal is challenged."""
    detection_prob = composition_detection_probability(config)

    # Estimate challenge probability from participant attention.
    # Only participants who would lose under the false outcome (winners under true)
    # have incentive to challenge.
    p_no_challenge = 1.0
    for p in participants:
        if p.index == proposer.index:
            continue
        if p.is_winner_under_true and p.attention_prob > 0:
            p_no_challenge *= (1.0 - p.attention_prob * detection_prob)

    p_challenge = 1.0 - p_no_challenge

    # Account for verification bounty increasing effective challenge prob.
    # The bounty attracts external verifiers who are not market participants.
    # Model: each potential external verifier has effort cost ~ 5-50 USDC
    # (re-executing a blueprint). They verify if bounty > effort cost.
    # The number of potential external verifiers is limited (not everyone
    # knows about the market), so the effect is bounded.
    if config.bounty_fraction > 0:
        bounty_value = config.bounty_fraction * config.proposer_bond
        # Sigmoid-like response: bounty effectiveness increases with value
        # but saturates. External verifiers have varying effort costs.
        # At bounty=10 USDC: modest boost. At bounty=100: significant.
        # At bounty=1000: near-maximum.
        external_check_prob = min(0.4, 0.05 * math.log1p(bounty_value / 10.0))
        p_challenge = min(1.0, p_challenge + external_check_prob * detection_prob * (1.0 - p_challenge))

    return p_challenge


def proposer_action(
    config: SimConfig,
    proposer: Participant,
    participants: list[Participant],
    mev: float,
) -> Literal["abstain", "truthful", "false"]:
    """
    Choose the proposer's action among abstain, truthful proposal, and false proposal.

    Truthful proposals earn success-conditioned proposer compensation and incur the
    submission cost. False proposals also incur submission cost, receive the proposer
    fee only if they survive, and lose the bond if successfully challenged.
    """
    from research.resolution_trust.types import ProposerType

    truthful_payoff = config.proposer_fee - config.proposer_submission_cost

    if config.proposer_type == ProposerType.HONEST:
        return "truthful" if truthful_payoff >= 0.0 else "abstain"

    p_challenge = estimate_challenge_probability(config, proposer, participants)
    p_false_submit = composition_false_submission_probability(config)
    accepted_payoff = mev + config.proposer_fee - config.proposer_submission_cost
    corrected_payoff = -config.proposer_bond - config.proposer_submission_cost
    materialized_false_payoff = (
        (1.0 - p_challenge) * accepted_payoff
        + p_challenge * (
            (1.0 - config.adjudicator_accuracy) * accepted_payoff
            + config.adjudicator_accuracy * corrected_payoff
        )
    )
    false_payoff = p_false_submit * materialized_false_payoff + (1.0 - p_false_submit) * truthful_payoff

    if false_payoff > truthful_payoff and false_payoff > 0.0:
        return "false"
    if truthful_payoff >= 0.0:
        return "truthful"
    return "abstain"


def estimate_proposer_mev(
    config: SimConfig,
    proposer: Participant,
    rng: random.Random,
) -> float:
    """Estimate proposer-side extractable value under the configured model."""
    from research.resolution_trust.types import ProposerMEVModel

    if config.proposer_mev_model == ProposerMEVModel.POSITION_BOUNDED:
        return proposer.stake

    base_mev_fraction = 0.15 + rng.random() * 0.30  # 15% to 45% of pool
    return config.pool_size * base_mev_fraction


def participant_checks(participant: Participant, rng: random.Random) -> bool:
    """Return True if this participant checks during the challenge window."""
    if participant.attention_prob < 0.001:
        return False
    return rng.random() < participant.attention_prob


def challenger_decides(
    participant: Participant,
    config: SimConfig,
) -> bool:
    """
    Return True if a participant who has already checked decides to challenge.
    """
    if participant.is_winner_under_false:
        return False

    p_a = config.adjudicator_accuracy
    b_c = config.challenger_bond
    # Reward if adjudicator overturns: share of proposer bond + recovered stake
    reward = config.proposer_bond * 0.5 + participant.stake
    cost = b_c

    expected = p_a * reward - (1.0 - p_a) * cost
    return expected > 0
