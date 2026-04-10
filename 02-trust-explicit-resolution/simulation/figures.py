"""Paper artifact generation: figures and tables for the trust-explicit resolution paper."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from research.resolution_trust.metrics import aggregate
from research.resolution_trust.types import SimResult


ARTIFACTS_DIR = Path(__file__).resolve().parent / "output" / "paper_artifacts"

# Palette: harmonized with TikZ figure colors and active-lp paper
PRIMARY_BLUE = "#4A6FA5"
SECONDARY_BLUE = "#7C93BD"
ACCENT_ORANGE = "#C9714A"
WARM_RED = "#9f4b3f"
NEUTRAL_GRAY = "#5d554a"
GRID = "#ddd7cf"
BG = "#fbfaf7"

# Paper column width is ~5.5in with NeurIPS margins.
# Figures at 5.2 x 3.2 embed cleanly without excessive scaling.
FIG_W, FIG_H = 5.2, 3.2


def _apply_rcparams() -> None:
    """Set matplotlib defaults to match the NeurIPS-style paper."""
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
        "font.size": 9,
        "axes.labelsize": 9,
        "axes.titlesize": 10,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "lines.linewidth": 1.8,
        "lines.markersize": 5,
    })


def ensure_artifacts_dir() -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    return ARTIFACTS_DIR


def _configure_axes(ax) -> None:
    ax.set_facecolor(BG)
    ax.grid(True, axis="y", color=GRID, alpha=0.6, linewidth=0.6)
    ax.grid(False, axis="x")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(NEUTRAL_GRAY)
    ax.spines["bottom"].set_color(NEUTRAL_GRAY)
    ax.tick_params(colors=NEUTRAL_GRAY, width=0.6)


def _percent_formatter() -> FuncFormatter:
    return FuncFormatter(lambda x, _: f"{int(round(x * 100))}%")


def _save_figure(fig, name: str) -> None:
    out = ensure_artifacts_dir()
    svg = out / f"{name}.svg"
    pdf = out / f"{name}.pdf"
    fig.savefig(svg, bbox_inches="tight", facecolor=BG)
    fig.savefig(pdf, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"  -> {svg}")
    print(f"  -> {pdf}")


def _aggregated_rows(results: Iterable[SimResult]) -> list:
    return [aggregate(r) for r in results]


def write_bond_scaling_table(results: list[SimResult]) -> None:
    """Table: false resolution rate by pool size and bond structure."""
    out = ensure_artifacts_dir()
    path = out / "table_bond_scaling.csv"

    rows = []
    for r in results:
        m = aggregate(r)
        rows.append({
            "pool_size": m.pool_size,
            "bond_structure": m.bond_structure,
            "bond_rate": m.bond_rate,
            "proposer_bond": r.config.proposer_bond,
            "false_resolution_rate": f"{m.false_resolution_rate:.4f}",
            "challenge_rate": f"{m.challenge_rate:.4f}",
            "deterrence": f"{m.proposer_deterrence:.4f}",
            "mean_bond_locked": f"{m.mean_bond_locked:.2f}",
        })

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  -> {path}")


def write_bond_scaling_figure(results: list[SimResult]) -> None:
    """Figure: false resolution rate vs pool size for key bond structures."""
    rows = _aggregated_rows(results)
    by_label: dict[str, list[tuple[float, float]]] = {
        "Flat bond": [],
        "Pool-proportional (10%)": [],
        "Pool-proportional (15%)": [],
    }
    for row in rows:
        if row.bond_structure == "flat":
            by_label["Flat bond"].append((row.pool_size, row.false_resolution_rate))
        elif row.bond_structure == "pool_proportional" and abs(row.bond_rate - 0.10) < 1e-9:
            by_label["Pool-proportional (10%)"].append((row.pool_size, row.false_resolution_rate))
        elif row.bond_structure == "pool_proportional" and abs(row.bond_rate - 0.15) < 1e-9:
            by_label["Pool-proportional (15%)"].append((row.pool_size, row.false_resolution_rate))

    _apply_rcparams()
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    _configure_axes(ax)
    palette = {
        "Flat bond": WARM_RED,
        "Pool-proportional (10%)": SECONDARY_BLUE,
        "Pool-proportional (15%)": PRIMARY_BLUE,
    }
    for label, pairs in by_label.items():
        pairs = sorted(pairs)
        if not pairs:
            continue
        x, y = zip(*pairs)
        ax.plot(x, y, marker="o", color=palette[label], label=label)

    ax.set_xscale("log")
    ax.set_xticks([50, 500, 5000, 50000])
    ax.get_xaxis().set_major_formatter(FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.set_ylim(0.0, 0.75)
    ax.yaxis.set_major_formatter(_percent_formatter())
    ax.set_xlabel("Market pool size (USDC)")
    ax.set_ylabel("False resolution rate")
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    _save_figure(fig, "bond_scaling_false_resolution")


def write_bond_structure_table(results: list[SimResult]) -> None:
    """Table: bond structure comparison (Table 1 in paper)."""
    out = ensure_artifacts_dir()
    path = out / "table_bond_structure_comparison.csv"

    rows = []
    for r in results:
        m = aggregate(r)
        rows.append({
            "bond_structure": m.bond_structure,
            "bond_rate": m.bond_rate,
            "false_resolution_rate": f"{m.false_resolution_rate:.4f}",
            "challenge_rate": f"{m.challenge_rate:.4f}",
            "mean_bond_locked": f"{m.mean_bond_locked:.2f}",
            "deterrence": f"{m.proposer_deterrence:.4f}",
        })

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  -> {path}")


def write_lazy_verifier_table(results: list[SimResult]) -> None:
    """Table: false resolution rate by participant count and attention."""
    out = ensure_artifacts_dir()
    path = out / "table_lazy_verifier.csv"

    rows = []
    for r in results:
        m = aggregate(r)
        rows.append({
            "num_participants": m.num_participants,
            "attention_coefficient": m.attention_coefficient,
            "false_resolution_rate": f"{m.false_resolution_rate:.4f}",
            "mean_verification_coverage": f"{m.mean_verification_coverage:.4f}",
            "challenge_rate": f"{m.challenge_rate:.4f}",
        })

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  -> {path}")


def write_bounty_table(results: list[SimResult]) -> None:
    """Table: verification bounty effectiveness."""
    out = ensure_artifacts_dir()
    path = out / "table_verification_bounty.csv"

    rows = []
    for r in results:
        m = aggregate(r)
        rows.append({
            "num_participants": m.num_participants,
            "bounty_fraction": m.bounty_fraction,
            "false_resolution_rate": f"{m.false_resolution_rate:.4f}",
            "mean_verification_coverage": f"{m.mean_verification_coverage:.4f}",
            "challenge_rate": f"{m.challenge_rate:.4f}",
            "deterrence": f"{m.proposer_deterrence:.4f}",
        })

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  -> {path}")


def write_bounty_figure(results: list[SimResult]) -> None:
    """Figure: false resolution rate vs verification bounty."""
    rows = _aggregated_rows(results)
    by_k: dict[int, list[tuple[float, float]]] = {}
    for row in rows:
        by_k.setdefault(int(row.num_participants), []).append((row.bounty_fraction, row.false_resolution_rate))

    _apply_rcparams()
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    _configure_axes(ax)
    palette = {
        3: WARM_RED,
        5: ACCENT_ORANGE,
        10: SECONDARY_BLUE,
        30: PRIMARY_BLUE,
    }
    for k, pairs in sorted(by_k.items()):
        pairs = sorted(pairs)
        x, y = zip(*pairs)
        ax.plot(x, y, marker="o", color=palette.get(k, NEUTRAL_GRAY), label=f"$k = {k}$")

    ax.set_xlim(-0.005, 0.205)
    ax.set_ylim(0.0, 0.95)
    ax.yaxis.set_major_formatter(_percent_formatter())
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{int(round(x * 100))}%"))
    ax.set_xlabel("Verification bounty fraction ($\\phi$)")
    ax.set_ylabel("False resolution rate")
    ax.legend(frameon=False, loc="upper right")
    fig.tight_layout()
    _save_figure(fig, "verification_bounty_effect")


def write_window_table(results: list[SimResult]) -> None:
    """Table: challenge window duration effects."""
    out = ensure_artifacts_dir()
    path = out / "table_challenge_window.csv"

    rows = []
    for r in results:
        m = aggregate(r)
        rows.append({
            "challenge_window_hours": m.challenge_window_hours,
            "challenger_mix": m.challenger_mix,
            "false_resolution_rate": f"{m.false_resolution_rate:.4f}",
            "mean_time_to_finalization": f"{m.mean_time_to_finalization:.2f}",
            "challenge_rate": f"{m.challenge_rate:.4f}",
        })

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  -> {path}")


def write_window_figure(results: list[SimResult]) -> None:
    """Figure: challenge-window diminishing returns by challenger mix."""
    rows = _aggregated_rows(results)
    by_mix: dict[str, list[tuple[float, float]]] = {}
    for row in rows:
        by_mix.setdefault(row.challenger_mix, []).append((row.challenge_window_hours, row.false_resolution_rate))

    labels = {
        "all_attentive": "All attentive",
        "majority_lazy": "Majority lazy",
        "stake_proportional": "Stake-proportional",
    }
    palette = {
        "all_attentive": PRIMARY_BLUE,
        "majority_lazy": ACCENT_ORANGE,
        "stake_proportional": WARM_RED,
    }

    _apply_rcparams()
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    _configure_axes(ax)
    for mix, pairs in sorted(by_mix.items()):
        pairs = sorted(pairs)
        x, y = zip(*pairs)
        ax.plot(x, y, marker="o", color=palette.get(mix, NEUTRAL_GRAY), label=labels.get(mix, mix))

    ax.set_xticks([12, 24, 48, 72])
    ax.set_xlim(8, 76)
    ax.set_ylim(0.0, 1.05)
    ax.yaxis.set_major_formatter(_percent_formatter())
    ax.set_xlabel("Challenge window $w$ (hours)")
    ax.set_ylabel("False resolution rate")
    ax.legend(frameon=False, loc="upper right")
    fig.tight_layout()
    _save_figure(fig, "challenge_window_effect")


def write_adjudicator_table(results: list[SimResult]) -> None:
    """Table: adjudicator accuracy vs challenge probability."""
    out = ensure_artifacts_dir()
    path = out / "table_adjudicator_accuracy.csv"

    rows = []
    for r in results:
        m = aggregate(r)
        rows.append({
            "adjudicator_accuracy": m.adjudicator_accuracy,
            "challenger_mix": m.challenger_mix,
            "false_resolution_rate": f"{m.false_resolution_rate:.4f}",
            "challenge_rate": f"{m.challenge_rate:.4f}",
            "deterrence": f"{m.proposer_deterrence:.4f}",
        })

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  -> {path}")


def write_paper_tables(results_by_family: dict[str, list[SimResult]]) -> None:
    """Write all paper artifact tables."""
    print("Writing paper artifacts:")

    if "bond_scaling" in results_by_family:
        write_bond_scaling_table(results_by_family["bond_scaling"])
        write_bond_scaling_figure(results_by_family["bond_scaling"])

    if "bond_structure" in results_by_family:
        write_bond_structure_table(results_by_family["bond_structure"])

    if "lazy_verifier" in results_by_family:
        write_lazy_verifier_table(results_by_family["lazy_verifier"])

    if "verification_bounty" in results_by_family:
        write_bounty_table(results_by_family["verification_bounty"])
        write_bounty_figure(results_by_family["verification_bounty"])

    if "challenge_window" in results_by_family:
        write_window_table(results_by_family["challenge_window"])
        write_window_figure(results_by_family["challenge_window"])

    if "adjudicator_accuracy" in results_by_family:
        write_adjudicator_table(results_by_family["adjudicator_accuracy"])


def write_overview_json(results_by_family: dict[str, list[SimResult]]) -> None:
    """Write a JSON overview of all results."""
    import json
    out = ensure_artifacts_dir()
    path = out / "paper_artifacts_overview.json"

    overview = {}
    for family_name, results in results_by_family.items():
        false_rates = [r.false_resolution_rate for r in results]
        overview[family_name] = {
            "num_configs": len(results),
            "min_false_resolution_rate": min(false_rates) if false_rates else None,
            "max_false_resolution_rate": max(false_rates) if false_rates else None,
            "mean_false_resolution_rate": sum(false_rates) / len(false_rates) if false_rates else None,
        }

    with open(path, "w") as f:
        json.dump(overview, f, indent=2)
    print(f"  -> {path}")
