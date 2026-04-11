"""Core types for the resolution trust dispute simulation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class BondStructure(Enum):
    FLAT = "flat"
    POOL_PROPORTIONAL = "pool_proportional"
    CAPPED_POOL_PROPORTIONAL = "capped_pool_proportional"
    LINEAR_ESCALATION = "linear_escalation"
    EXPONENTIAL_ESCALATION = "exponential_escalation"


class ChallengerMix(Enum):
    ALL_ATTENTIVE = "all_attentive"
    MAJORITY_LAZY = "majority_lazy"
    STAKE_PROPORTIONAL = "stake_proportional"


class StakeDistribution(Enum):
    UNIFORM = "uniform"
    CONCENTRATED = "concentrated"  # one whale
    POWER_LAW = "power_law"


class ProposerType(Enum):
    HONEST = "honest"
    STRATEGIC = "strategic"


class ProposerMEVModel(Enum):
    POOL_FRACTION = "pool_fraction"
    POSITION_BOUNDED = "position_bounded"


class ProposerBudgetProfile(Enum):
    UNCONSTRAINED = "unconstrained"
    RETAIL_HEAVY = "retail_heavy"
    MIXED = "mixed"
    SPECIALIZED = "specialized"


class CompositionScenario(Enum):
    NONE = "none"
    SINGLE_SOURCE_CORRUPT = "single_source_corrupt"
    THREE_SOURCE_ONE_CORRUPT = "three_source_one_corrupt"
    THREE_SOURCE_TWO_CORRUPT = "three_source_two_corrupt"


@dataclass(frozen=True)
class SimConfig:
    """Full configuration for one simulation run."""

    pool_size: float  # L, total market pool in USDC
    num_participants: int  # k
    num_outcomes: int = 2

    # Bond parameters
    bond_structure: BondStructure = BondStructure.POOL_PROPORTIONAL
    flat_bond: float = 10.0  # for FLAT structure
    bond_rate: float = 0.10  # rho, for POOL_PROPORTIONAL
    bond_cap: float | None = None  # optional cap for CAPPED_POOL_PROPORTIONAL
    challenger_bond_symmetric: bool = True  # b_C = b_P
    escalation_base: float = 2.0  # for exponential escalation

    # Challenge window (hours)
    challenge_window_hours: float = 24.0

    # Participant attention
    attention_coefficient: float = 1.0  # alpha
    check_rate_per_hour: float = 0.1  # lambda_check for Poisson model

    # Adjudicator
    adjudicator_accuracy: float = 0.9  # p_A

    # Verification bounty
    bounty_fraction: float = 0.0  # phi, 0 = no bounty

    # Proposer type
    proposer_type: ProposerType = ProposerType.STRATEGIC
    proposer_mev_model: ProposerMEVModel = ProposerMEVModel.POOL_FRACTION
    proposer_budget_profile: ProposerBudgetProfile = ProposerBudgetProfile.UNCONSTRAINED
    proposer_fee: float = 0.0  # success-conditioned proposer compensation
    proposer_work_cost: float = 0.0  # fixed operational cost per submitted proposal
    proposer_capital_cost_apy: float = 0.0  # annualized opportunity cost on locked bond

    # Blueprint composition / source corruption
    composition_scenario: CompositionScenario = CompositionScenario.NONE

    # Participant mix
    challenger_mix: ChallengerMix = ChallengerMix.STAKE_PROPORTIONAL
    stake_distribution: StakeDistribution = StakeDistribution.UNIFORM

    # Monte Carlo
    num_episodes: int = 1000
    seed: int = 42

    @property
    def proposer_bond(self) -> float:
        """Compute proposer bond under configured structure."""
        if self.bond_structure == BondStructure.FLAT:
            return self.flat_bond
        elif self.bond_structure == BondStructure.POOL_PROPORTIONAL:
            return max(self.flat_bond, self.bond_rate * self.pool_size)
        elif self.bond_structure == BondStructure.CAPPED_POOL_PROPORTIONAL:
            uncapped = max(self.flat_bond, self.bond_rate * self.pool_size)
            if self.bond_cap is None:
                return uncapped
            return min(uncapped, self.bond_cap)
        elif self.bond_structure == BondStructure.LINEAR_ESCALATION:
            return max(self.flat_bond, self.bond_rate * self.pool_size * 0.5)
        elif self.bond_structure == BondStructure.EXPONENTIAL_ESCALATION:
            return max(self.flat_bond, self.bond_rate * self.pool_size * 0.3)
        return self.flat_bond

    @property
    def challenger_bond(self) -> float:
        if self.challenger_bond_symmetric:
            return self.proposer_bond
        return self.proposer_bond * 0.5

    @property
    def verification_bounty(self) -> float:
        return self.bounty_fraction * self.proposer_bond

    @property
    def proposer_submission_cost(self) -> float:
        capital_cost = (
            self.proposer_bond
            * self.proposer_capital_cost_apy
            * self.challenge_window_hours
            / (24.0 * 365.0)
        )
        return self.proposer_work_cost + capital_cost


@dataclass
class Participant:
    """A market participant with a position."""

    index: int
    stake: float  # absolute payout difference between true and proposed outcome
    is_winner_under_true: bool  # wins under correct resolution
    is_winner_under_false: bool  # wins under false resolution
    attention_prob: float = 0.0  # probability of verifying during window
    capital_budget: float = float("inf")
    role: Literal["proposer", "challenger", "lazy"] = "lazy"


@dataclass
class EpisodeResult:
    """Result of a single resolution episode."""

    proposal_is_false: bool
    challenged: bool
    proposal_submitted: bool = True
    adjudicator_correct: bool = True
    resolution_correct: bool = True
    eligible_proposers: int = 0
    willing_proposers: int = 0
    num_verifiers: int = 0
    proposer_payoff: float = 0.0
    challenger_payoff: float = 0.0
    total_bond_locked: float = 0.0
    time_to_finalization_hours: float = 0.0
    bounty_paid: float = 0.0


@dataclass
class SimResult:
    """Aggregated results from a simulation run."""

    config: SimConfig
    episodes: list[EpisodeResult] = field(default_factory=list)

    @property
    def false_resolution_rate(self) -> float:
        submitted = [e for e in self.episodes if e.proposal_submitted]
        if not submitted:
            return 0.0
        return sum(1 for e in submitted if not e.resolution_correct) / len(submitted)

    @property
    def challenge_rate(self) -> float:
        false_eps = [e for e in self.episodes if e.proposal_submitted and e.proposal_is_false]
        if not false_eps:
            return 0.0
        return sum(1 for e in false_eps if e.challenged) / len(false_eps)

    @property
    def mean_verification_coverage(self) -> float:
        submitted = [e for e in self.episodes if e.proposal_submitted]
        if not submitted:
            return 0.0
        return sum(e.num_verifiers for e in submitted) / len(submitted)

    @property
    def mean_bond_locked(self) -> float:
        submitted = [e for e in self.episodes if e.proposal_submitted]
        if not submitted:
            return 0.0
        return sum(e.total_bond_locked for e in submitted) / len(submitted)

    @property
    def mean_time_to_finalization(self) -> float:
        submitted = [e for e in self.episodes if e.proposal_submitted]
        if not submitted:
            return 0.0
        return sum(e.time_to_finalization_hours for e in submitted) / len(submitted)

    @property
    def proposer_deterrence(self) -> float:
        """Fraction of episodes where a strategic proposer chose truthful."""
        submitted = [e for e in self.episodes if e.proposal_submitted]
        if not submitted:
            return 0.0
        total = len(submitted)
        false_count = sum(1 for e in submitted if e.proposal_is_false)
        return 1.0 - false_count / total

    @property
    def proposer_liveness_rate(self) -> float:
        if not self.episodes:
            return 0.0
        return sum(1 for e in self.episodes if e.proposal_submitted) / len(self.episodes)

    @property
    def capital_eligibility_rate(self) -> float:
        if not self.episodes:
            return 0.0
        return sum(1 for e in self.episodes if e.eligible_proposers > 0) / len(self.episodes)

    @property
    def mean_eligible_proposers(self) -> float:
        if not self.episodes:
            return 0.0
        return sum(e.eligible_proposers for e in self.episodes) / len(self.episodes)

    @property
    def mean_willing_proposers(self) -> float:
        if not self.episodes:
            return 0.0
        return sum(e.willing_proposers for e in self.episodes) / len(self.episodes)

    @property
    def single_eligible_rate(self) -> float:
        submitted = [e for e in self.episodes if e.proposal_submitted]
        if not submitted:
            return 0.0
        return sum(1 for e in submitted if e.eligible_proposers == 1) / len(submitted)

    @property
    def single_willing_rate(self) -> float:
        submitted = [e for e in self.episodes if e.proposal_submitted]
        if not submitted:
            return 0.0
        return sum(1 for e in submitted if e.willing_proposers == 1) / len(submitted)

    @property
    def welfare_loss(self) -> float:
        """Total payoff loss from incorrect resolutions."""
        return sum(
            abs(e.proposer_payoff) for e in self.episodes if not e.resolution_correct
        )
