"""Metric computation and reporting for simulation results."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from research.resolution_trust.types import SimConfig, SimResult


@dataclass
class AggregatedMetrics:
    """Summary metrics for a simulation run."""

    # Config identifiers
    pool_size: float
    num_participants: int
    bond_structure: str
    bond_rate: float
    flat_bond: float
    bond_cap: float | None
    proposer_bond: float
    proposer_mev_model: str
    proposer_budget_profile: str
    proposer_fee: float
    proposer_work_cost: float
    proposer_capital_cost_apy: float
    bounty_fraction: float
    challenge_window_hours: float
    attention_coefficient: float
    adjudicator_accuracy: float
    challenger_mix: str
    stake_distribution: str
    proposer_type: str

    # Results
    false_resolution_rate: float
    challenge_rate: float
    mean_verification_coverage: float
    mean_bond_locked: float
    mean_time_to_finalization: float
    proposer_deterrence: float
    proposer_liveness_rate: float
    capital_eligibility_rate: float
    mean_eligible_proposers: float
    mean_willing_proposers: float
    single_eligible_rate: float
    single_willing_rate: float
    welfare_loss: float
    num_episodes: int


def aggregate(result: SimResult) -> AggregatedMetrics:
    c = result.config
    return AggregatedMetrics(
        pool_size=c.pool_size,
        num_participants=c.num_participants,
        bond_structure=c.bond_structure.value,
        bond_rate=c.bond_rate,
        flat_bond=c.flat_bond,
        bond_cap=c.bond_cap,
        proposer_bond=c.proposer_bond,
        proposer_mev_model=c.proposer_mev_model.value,
        proposer_budget_profile=c.proposer_budget_profile.value,
        proposer_fee=c.proposer_fee,
        proposer_work_cost=c.proposer_work_cost,
        proposer_capital_cost_apy=c.proposer_capital_cost_apy,
        bounty_fraction=c.bounty_fraction,
        challenge_window_hours=c.challenge_window_hours,
        attention_coefficient=c.attention_coefficient,
        adjudicator_accuracy=c.adjudicator_accuracy,
        challenger_mix=c.challenger_mix.value,
        stake_distribution=c.stake_distribution.value,
        proposer_type=c.proposer_type.value,
        false_resolution_rate=result.false_resolution_rate,
        challenge_rate=result.challenge_rate,
        mean_verification_coverage=result.mean_verification_coverage,
        mean_bond_locked=result.mean_bond_locked,
        mean_time_to_finalization=result.mean_time_to_finalization,
        proposer_deterrence=result.proposer_deterrence,
        proposer_liveness_rate=result.proposer_liveness_rate,
        capital_eligibility_rate=result.capital_eligibility_rate,
        mean_eligible_proposers=result.mean_eligible_proposers,
        mean_willing_proposers=result.mean_willing_proposers,
        single_eligible_rate=result.single_eligible_rate,
        single_willing_rate=result.single_willing_rate,
        welfare_loss=result.welfare_loss,
        num_episodes=len(result.episodes),
    )


def write_results_csv(results: list[SimResult], path: Path) -> None:
    """Write aggregated results to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [aggregate(r) for r in results]
    if not rows:
        return

    fieldnames = list(AggregatedMetrics.__dataclass_fields__.keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def write_results_json(results: list[SimResult], path: Path) -> None:
    """Write aggregated results to JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [asdict(aggregate(r)) for r in results]
    with open(path, "w") as f:
        json.dump(rows, f, indent=2)


def print_summary(family_name: str, results: list[SimResult]) -> None:
    """Print a brief summary of results for a scenario family."""
    if not results:
        print(f"  {family_name}: no results")
        return

    false_rates = [r.false_resolution_rate for r in results]
    deterrence = [r.proposer_deterrence for r in results]
    liveness = [r.proposer_liveness_rate for r in results]
    print(f"  {family_name}: {len(results)} configs, "
          f"false_res_rate=[{min(false_rates):.3f}, {max(false_rates):.3f}], "
          f"deterrence=[{min(deterrence):.3f}, {max(deterrence):.3f}], "
          f"liveness=[{min(liveness):.3f}, {max(liveness):.3f}]")
