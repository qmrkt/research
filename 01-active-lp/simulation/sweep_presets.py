from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from research.active_lp.adversarial_search import AdversarialSearchConfig
from research.active_lp.monte_carlo import MonteCarloSweepConfig
from research.active_lp.scenarios import deterministic_scenario_names


@dataclass(slots=True)
class SweepPreset:
    name: str
    description: str
    deterministic_names: tuple[str, ...]
    monte_carlo: MonteCarloSweepConfig
    adversarial: AdversarialSearchConfig | None = None


def build_sweep_preset(name: str) -> SweepPreset:
    deterministic = deterministic_scenario_names()
    if name == "paper_quick":
        return SweepPreset(
            name="paper_quick",
            description="Fast first-pass sweep: full deterministic suite plus a moderate Monte Carlo batch for actionable results.",
            deterministic_names=deterministic,
            monte_carlo=MonteCarloSweepConfig(
                name="paper_quick_mc",
                seed=17,
                num_trials=64,
                num_outcomes_choices=(3, 5, 8, 12),
                initial_depth_choices=(Decimal("80"), Decimal("100"), Decimal("140"), Decimal("180")),
                fee_bps_choices=(Decimal("50"), Decimal("100"), Decimal("150"), Decimal("200")),
                protocol_fee_bps_choices=(Decimal("0"), Decimal("25"), Decimal("50")),
                lp_delta_b_choices=(Decimal("20"), Decimal("35"), Decimal("50"), Decimal("70")),
                trade_count_range=(5, 10),
                active_lp_entry_count_choices=(1, 2, 3),
                sell_probability=0.25,
                cancel_probability=0.15,
            ),
            adversarial=AdversarialSearchConfig(
                name="paper_quick_adv",
                num_outcomes_choices=(3, 8),
                initial_depth_choices=(Decimal("100"), Decimal("140")),
                fee_bps_choices=(Decimal("100"),),
                protocol_fee_bps_choices=(Decimal("25"),),
                late_delta_b_choices=(Decimal("20"), Decimal("50")),
                pre_entry_shares_choices=(Decimal("6"), Decimal("20")),
                post_entry_shares_choices=(Decimal("0"), Decimal("12")),
                counterflow_ratio_choices=(Decimal("0"), Decimal("0.25")),
                post_entry_modes=("idle", "trend", "reversion"),
                winner_policies=("favorite", "hedge"),
            ),
        )
    if name == "paper_core":
        return SweepPreset(
            name="paper_core",
            description="Heavier paper-oriented sweep: full deterministic suite plus a broader Monte Carlo batch.",
            deterministic_names=deterministic,
            monte_carlo=MonteCarloSweepConfig(
                name="paper_core_mc",
                seed=29,
                num_trials=256,
                num_outcomes_choices=(3, 5, 8, 12, 16),
                initial_depth_choices=(Decimal("60"), Decimal("80"), Decimal("100"), Decimal("140"), Decimal("200")),
                fee_bps_choices=(Decimal("25"), Decimal("50"), Decimal("100"), Decimal("150"), Decimal("200")),
                protocol_fee_bps_choices=(Decimal("0"), Decimal("25"), Decimal("50")),
                lp_delta_b_choices=(Decimal("15"), Decimal("25"), Decimal("35"), Decimal("50"), Decimal("70"), Decimal("100")),
                trade_count_range=(6, 12),
                active_lp_entry_count_choices=(1, 2, 3, 4),
                sell_probability=0.30,
                cancel_probability=0.20,
            ),
            adversarial=AdversarialSearchConfig(
                name="paper_core_adv",
                num_outcomes_choices=(3, 8),
                initial_depth_choices=(Decimal("80"), Decimal("140")),
                fee_bps_choices=(Decimal("100"), Decimal("200")),
                protocol_fee_bps_choices=(Decimal("25"),),
                late_delta_b_choices=(Decimal("20"), Decimal("50"), Decimal("70")),
                pre_entry_shares_choices=(Decimal("6"), Decimal("20")),
                post_entry_shares_choices=(Decimal("0"), Decimal("12")),
                counterflow_ratio_choices=(Decimal("0"), Decimal("0.25")),
                post_entry_modes=("idle", "trend", "reversion"),
                winner_policies=("favorite", "hedge"),
            ),
        )
    raise KeyError(f"unknown sweep preset: {name}")


def sweep_preset_names() -> tuple[str, ...]:
    return ("paper_quick", "paper_core")
