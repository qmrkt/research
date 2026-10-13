"""Frozen, paired multi-seed experiments for the funded resolution game.

Run: python -m research.resolution_trust.economy_validation --output-dir DIR
The 20 seeds and 250 episodes per seed are fixed before reading outcomes.
Every treatment shares the same actor/arrival/adjudication random numbers.
Reported uncertainty is simulation uncertainty conditional on the assumptions,
not a calibration of human attention, capital supply, or adjudicator accuracy.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass, replace
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import statistics
import sys
import time

from .economics import GameConfig, draw_latents, play


@dataclass(frozen=True)
class Case:
    family: str
    group: str
    treatment: str
    baseline: str
    config: GameConfig

    @property
    def key(self):
        return f"{self.family}/{self.group}/{self.treatment}"


def cases() -> list[Case]:
    base = GameConfig()
    output = []

    def add(family, group, treatment, baseline, **kwargs):
        cfg = replace(base, **kwargs)
        if "proposer_fee" not in kwargs:
            # Hold normal truthful service viable while studying other knobs.
            # This is a declared fee rule, not a posterior per-episode subsidy.
            cfg = replace(cfg, proposer_fee=max(5., cfg.proposer_work + cfg.proposer_opportunity_cost + 1.))
        output.append(Case(family, group, treatment, baseline, cfg))

    for pool in (50, 500, 5_000, 50_000):
        for attention in ("lazy", "attentive"):
            group = f"L{pool}-{attention}"
            add("bond_scaling", group, "flat10", "flat10", pool=pool, attention=attention, bond_rule="flat")
            for rho in (.05, .10, .15, .25, .50):
                add("bond_scaling", group, f"rho{rho:g}", "flat10", pool=pool, attention=attention, bond_rate=rho)
    for pool in (5_000, 50_000):
        group = f"L{pool}-mixed"
        add("bond_cap", group, "uncapped", "uncapped", pool=pool, capital_profile="mixed")
        for cap in (250, 500, 1_000, 5_000):
            add("bond_cap", group, f"cap{cap}", "uncapped", pool=pool, capital_profile="mixed", bond_rule="capped", bond_cap=cap)
    for attention in ("lazy", "attentive", "stake"):
        for window in (2, 12, 24, 48, 72):
            add("window", attention, f"w{window}", "w24", attention=attention, window=window)
    for attention in ("lazy", "attentive"):
        for accuracy in (.7, .9, .95, .99, 1):
            add("accuracy", attention, f"a{accuracy:g}", "a0.95", attention=attention, accuracy=accuracy)
    for n in (3, 10, 30):
        for eta in (0, .05, .15, .5, 1):
            add("reward", f"n{n}", f"eta{eta:g}", "eta0", participants=n, reward_fraction=eta)
    for n in (10, 30):
        for attention in ("lazy", "attentive"):
            for positions in ("uniform", "power_law", "whale"):
                add("positions", f"n{n}-{attention}", positions, "uniform", participants=n, attention=attention, positions=positions)
    for pool in (5_000, 50_000):
        for capital in ("retail", "mixed", "specialized"):
            for fee in (0, 5, 15, 50):
                add("compensation", f"L{pool}-{capital}", f"fee{fee}", "fee0", pool=pool,
                    capital_profile=capital, proposer_fee=fee, proposer_work=10, positions="power_law")
    for accuracy in (.7, .9, .99):
        for ratio in (.001, .01, .1, 1):
            add("honest_griefing", f"a{accuracy:g}", f"ratio{ratio:g}", "ratio1", accuracy=accuracy,
                challenger_ratio=ratio, honest_proposer=True, proposer_fee=100, positions="whale")
    for n in (3, 10, 30):
        for multiplier in (.1, 1, 5):
            add("thin_attention", f"n{n}", f"multiplier{multiplier:g}", "multiplier1", participants=n,
                attention="stake", attention_multiplier=multiplier)
    for profile in ("retail", "mixed"):
        for ratio in (.01, .1, .5, 1):
            add("challenge_access", profile, f"ratio{ratio:g}", "ratio1", pool=50_000,
                capital_profile=profile, challenger_ratio=ratio)
    for attention in ("lazy", "attentive"):
        for positions in ("uniform", "whale"):
            for selection in ("first_willing", "worst_willing"):
                add("selection", f"{attention}-{positions}", selection, "first_willing", attention=attention,
                    positions=positions, proposer_selection=selection)
    assert len({c.key for c in output}) == len(output)
    for c in output:
        assert any((b.family, b.group, b.treatment) == (c.family, c.group, c.baseline) for b in output)
    return output


RATE_KEYS = ("submitted_rate", "deferred_rate", "attack_attempt_rate", "wrong_all_rate", "wrong_submitted_rate",
             "false_challenge_all_rate", "wrongful_slash_all_rate", "capital_eligible_rate", "truth_choice_positive_gain_rate")
CONTRAST_KEYS = ("wrong_all_rate", "wrong_submitted_rate", "submitted_rate", "attack_attempt_rate",
                 "false_challenge_all_rate", "truth_choice_positive_gain_rate", "mean_resource_cost", "mean_checks")


class Totals:
    def __init__(self):
        self.n = self.submitted = self.wrong = self.attacks = self.false_challenges = self.wrongful_slashes = 0
        self.eligible = self.positive = self.positive_truth = 0
        self.checks = self.cost = self.opportunity = self.locked = self.latency = self.fees = 0.
        self.protocol = self.misallocation = self.proposer_net = self.expected_net = 0.
        self.expected_wrong = self.wrong_variance = self.expected_challenge = self.challenges = 0.
        self.balance_max = 0.

    def add(self, e):
        self.n += 1
        self.submitted += e["status"] != "deferred"
        self.wrong += e["final_wrong"]
        self.attacks += e["attack_attempted"]
        self.false_challenges += e["false_challenge"]
        self.wrongful_slashes += e["wrongful_proposer_slash"]
        self.eligible += e["eligible"] > 0
        self.positive += e["positive_gain_candidates"]
        self.positive_truth += e["positive_gain_truthful"]
        for own, field in (("checks", "checks"), ("cost", "resource_cost"), ("opportunity", "opportunity_cost"),
                           ("locked", "bond_locked"), ("latency", "latency"), ("fees", "proposer_fee_paid"),
                           ("protocol", "protocol_receipt"), ("misallocation", "payout_misallocation"),
                           ("proposer_net", "proposer_net"), ("expected_net", "expected_proposer_net"),
                           ("expected_wrong", "expected_wrong"), ("expected_challenge", "expected_challenge"),
                           ("challenges", "challenged")):
            setattr(self, own, getattr(self, own) + e[field])
        self.wrong_variance += e["expected_wrong"] * (1-e["expected_wrong"])
        self.balance_max = max(self.balance_max, abs(e["balance_error"]))

    def summary(self):
        n = max(1, self.n)
        return {
            "episodes": self.n, "submitted": self.submitted, "wrong": self.wrong,
            "submitted_rate": self.submitted/n, "deferred_rate": 1-self.submitted/n,
            "attack_attempt_rate": self.attacks/n, "wrong_all_rate": self.wrong/n,
            "wrong_submitted_rate": self.wrong/self.submitted if self.submitted else None,
            "false_challenge_all_rate": self.false_challenges/n, "wrongful_slash_all_rate": self.wrongful_slashes/n,
            "capital_eligible_rate": self.eligible/n,
            "truth_choice_positive_gain_rate": self.positive_truth/self.positive if self.positive else None,
            "positive_gain_candidate_count": self.positive, "positive_gain_truthful_count": self.positive_truth,
            "mean_checks": self.checks/n, "mean_resource_cost": self.cost/n,
            "mean_opportunity_cost": self.opportunity/n, "mean_bond_locked": self.locked/n,
            "mean_latency": self.latency/n, "mean_fee_paid": self.fees/n,
            "mean_protocol_receipt": self.protocol/n, "mean_payout_misallocation": self.misallocation/n,
            "mean_proposer_net": self.proposer_net/n, "mean_expected_proposer_net": self.expected_net/n,
            "expected_wrong_rate": self.expected_wrong/n,
            "mc_wrong_standardized_error": ((self.wrong-self.expected_wrong)/math.sqrt(self.wrong_variance)
                                             if self.wrong_variance else 0.),
            "challenge_all_rate": self.challenges/n, "expected_challenge_rate": self.expected_challenge/n,
            "max_balance_error": self.balance_max,
        }


def wilson(success, n, z=1.959963984540054):
    if not n:
        return [None, None]
    p = success/n
    denominator = 1+z*z/n
    center = (p+z*z/(2*n))/denominator
    radius = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/denominator
    return [max(0., center-radius), min(1., center+radius)]


def paired_interval(differences: list[float]) -> dict:
    """Paired seed-cluster t interval; full publication uses twenty clusters."""
    n = len(differences)
    mean = statistics.fmean(differences)
    # Exact 0.975 t quantiles for df 1..29; normal only for larger smoke/custom runs.
    critical = (12.7062,4.30265,3.18245,2.77645,2.57058,2.44691,2.36462,2.306,
                2.26216,2.22814,2.20099,2.17881,2.16037,2.14479,2.13145,2.11991,
                2.10982,2.10092,2.09302,2.08596,2.07961,2.07387,2.06866,2.06390,
                2.05954,2.05553,2.05183,2.04841,2.04523)
    se = statistics.stdev(differences)/math.sqrt(n) if n > 1 else None
    t = critical[n-2] if 2 <= n <= 30 else 1.96
    return {"difference": mean, "se": se, "ci_low": mean-t*se if se is not None else None,
            "ci_high": mean+t*se if se is not None else None, "seed_clusters": n}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def source_hashes():
    here = Path(__file__).parent
    return {name: hashlib.sha256((here/name).read_bytes()).hexdigest()
            for name in ("economics.py", "economy_validation.py")}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+"\n")


def write_csv(path, rows):
    if not rows:
        return
    keys = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def run(output: Path, seeds: list[int], episodes: int, selected: list[Case] | None = None):
    selected = selected or cases()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output must be absent or empty; historical results are never overwritten")
    output.mkdir(parents=True, exist_ok=True)
    if not seeds or len(set(seeds)) != len(seeds) or episodes < 1:
        raise ValueError("Distinct seeds and positive episode count required")
    hashes = source_hashes()
    plan = {
        "schema": "funded_resolution_game_v1", "seeds": seeds, "episodes_per_seed": episodes,
        "pairing": "same latent actor, arrival, detection, and adjudicator draws across every treatment",
        "terminal_statuses": ["correct", "incorrect", "deferred"],
        "composition": "NONE; no implicit detection discount or source-topology probabilities",
        "inspection_policy": "exogenous provisioned Poisson readiness; positive-EV first-ready filing; monitoring equilibrium tested separately",
        "fee_rule": "Except explicit compensation and griefing sweeps: F=max(5, proposer_work+maximum_lock_opportunity_cost+1)",
        "claim_scope": "conditional one-shot operational game; no calibration to human attention or full strategic waiting equilibrium",
        "inference": "Wilson intervals for aggregate binary rates; paired twenty-seed cluster t intervals for differences",
        "cases": [{"key": c.key, "family": c.family, "group": c.group, "treatment": c.treatment,
                   "baseline": c.baseline, "config": asdict(c.config)} for c in selected],
    }
    write_json(output/"plan.json", plan)
    write_json(output/"provenance.json", {"sources": hashes, "plan_sha256": hashlib.sha256(canonical(plan)).hexdigest(),
                                        "python": sys.version, "platform": platform.platform()})
    max_n = max(c.config.participants for c in selected)
    latent = {seed: [draw_latents(seed, i, max_n) for i in range(episodes)] for seed in seeds}
    summaries, seed_rows, witnesses = [], [], []
    start = time.monotonic()
    with (output/"episodes.jsonl.gz").open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, compresslevel=6) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8") as stream:
                for index, case in enumerate(selected):
                    total = Totals()
                    for seed in seeds:
                        per_seed = Totals()
                        for episode, values in enumerate(latent[seed]):
                            e = play(case.config, values, keep_actors=(seed == seeds[0] and episode < 4))
                            if "actors" in e:
                                witnesses.append({"case": case.key, "seed": seed, "episode": episode, **e})
                            saved = {key: value for key, value in e.items() if key not in {"actors", "candidate_actions", "candidate_values"}}
                            stream.write(json.dumps({"case": case.key, "seed": seed, "episode": episode, **saved},
                                                    separators=(",", ":"), allow_nan=False)+"\n")
                            total.add(e)
                            per_seed.add(e)
                        seed_rows.append({"case": case.key, "seed": seed, **per_seed.summary()})
                    summary = {"case": case.key, "family": case.family, "group": case.group,
                               "treatment": case.treatment, **total.summary()}
                    summary["wrong_all_wilson95"] = wilson(total.wrong, total.n)
                    summary["wrong_submitted_wilson95"] = wilson(total.wrong, total.submitted)
                    summaries.append(summary)
                    print(f"{index+1}/{len(selected)} {case.key} wrong={summary['wrong_all_rate']:.4f} "
                          f"live={summary['submitted_rate']:.4f} elapsed={time.monotonic()-start:.1f}s", flush=True)
    by_key_seed = {(row["case"], row["seed"]): row for row in seed_rows}
    contrasts = []
    for case in selected:
        baseline = f"{case.family}/{case.group}/{case.baseline}"
        if baseline == case.key:
            continue
        for metric in CONTRAST_KEYS:
            diffs = [by_key_seed[(case.key, seed)][metric] - by_key_seed[(baseline, seed)][metric]
                     for seed in seeds if by_key_seed[(case.key, seed)][metric] is not None
                     and by_key_seed[(baseline, seed)][metric] is not None]
            if diffs:
                contrasts.append({"case": case.key, "baseline": baseline, "metric": metric, **paired_interval(diffs)})
    write_json(output/"summary.json", summaries)
    write_csv(output/"summary.csv", [{k:v for k,v in row.items() if not isinstance(v,list)} for row in summaries])
    write_csv(output/"seed_rows.csv", seed_rows)
    write_csv(output/"paired_contrasts.csv", contrasts)
    with (output/"witnesses.jsonl").open("w") as handle:
        for witness in witnesses:
            handle.write(json.dumps(witness, separators=(",", ":"), allow_nan=False)+"\n")
    assert hashes == source_hashes(), "Source changed during experiment"
    max_error = max(abs(row["mc_wrong_standardized_error"]) for row in summaries)
    report = ["# Funded resolution game: publication validation", "",
              f"{len(selected)} configurations × {len(seeds)} seeds × {episodes} episodes = {len(selected)*len(seeds)*episodes:,} episodes.", "",
              "Market claims sum to the collateral pool under each outcome. Fees are prepaid; bond transfers and resource costs balance in every episode. "
              "Checks occur on honest and false proposals. Detection is 1 for the NONE composition model. No source-resilience probabilities enter this game.", "",
              f"Maximum cash conservation residual: {max(row['max_balance_error'] for row in summaries):.6g}. "
              f"Maximum absolute standardized Monte Carlo error against exact conditional wrong-outcome probability: {max_error:.4f}.", "",
              "Rates below are per episode; deferred episodes remain a separate endpoint. The complete CSV also reports wrong/submitted rates, "
              "Wilson intervals, work costs, capital costs, expected probabilities, and payout redistribution. Paired treatment differences and seed-cluster "
              "95% t intervals are in paired_contrasts.csv. The twenty-seed intervals quantify Monte Carlo uncertainty only.", "",
              "| Configuration | Wrong | Submitted | Attack | Checks | Resource cost |", "|---|---:|---:|---:|---:|---:|"]
    for row in summaries:
        report.append(f"| {row['case']} | {row['wrong_all_rate']:.4f} | {row['submitted_rate']:.4f} | "
                      f"{row['attack_attempt_rate']:.4f} | {row['mean_checks']:.3f} | {row['mean_resource_cost']:.3f} |")
    report += ["", "## Scope and decision rules", "",
               "The first willing proposer in an independent random priority order submits; a separately labeled worst-willing stress gives priority to fraud. "
               "Candidates choose truth, falsehood, or abstention from the same expected challenge rule used in execution. Inspection readiness is provisioned "
               "operational capacity, and each ready observer follows a positive incremental-EV filing policy. This experiment does not claim that this policy "
               "is the unique dynamic waiting equilibrium. The separate neutral-monitor inspection game tests endogenous participation and free-riding.", "",
               "Free bond capital excludes already collateralized positions. Capital eligibility covers bond plus cash work costs. Opportunity cost reserves the "
               "maximum proposer lock (window plus adjudication delay); challenger opportunity cost covers adjudication. A failed challenge goes entirely to "
               "protocol reserve; an overturned proposer funds the declared challenger reward and protocol remainder. The proposer success fee is paid even "
               "when an erroneous outcome survives, as the protocol cannot observe objective truth directly.", "",
               "Except in the explicit compensation and honest-griefing treatments, the success fee is F=max(5, proposer work + conservative lock opportunity "
               "cost +1). Thus the bond/window comparisons include this declared service-funding rule; they do not silently hold an inadequate fixed fee while "
               "counting resulting deferral as integrity. The compensation family separately tests inadequate versus adequate service payment.", "",
               "All candidates' abstention benchmark is zero incremental service payoff relative to eventual truthful fallback; a no-submission episode is "
               "recorded as deferred, without fabricating a correct immediate finalization. Outcome-neutral payment for legitimate blueprint cancellations "
               "belongs to the separate executable-workflow model. Composition-blocked attacks and missing-evidence cancellations are likewise not relabeled "
               "as economic deterrence in this game.", "",
               "Each uniform/power-law/whale allocation puts exclusive binary claims into two nonempty groups and normalizes each outcome column to the same pool. "
               "This makes signed gains sum to zero. Payout misallocation is a redistribution measure, not aggregate welfare destruction; real work and capital "
               "opportunity cost are reported separately. Numerical rates are synthetic comparative statics, not empirically calibrated deployment defaults."]
    (output/"report.md").write_text("\n".join(report)+"\n")
    (output/"README.md").write_text("\n".join([
        "# Funded resolution game: publication validation",
        "",
        "- [Experiment report](report.md)",
        "- [Design](plan.json) · [Summary](summary.json) · [Paired contrasts](paired_contrasts.csv)",
        "- [Raw episodes](episodes.jsonl.gz) · [Seed results](seed_rows.csv)",
        "- [Paper](../../trust-explicit-resolution.pdf) · [Reproduction guide](../../REPRODUCIBILITY.md)",
    ])+"\n")
    manifest = {p.name: {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}
                for p in sorted(output.iterdir()) if p.is_file()}
    write_json(output/"manifest.json", manifest)
    return summaries, contrasts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--episodes", type=int, default=250, help="Episodes per seed, default250")
    parser.add_argument("--seeds", default=",".join(str(s) for s in range(64000,64020)))
    parser.add_argument("--family", action="append", help="Restrict to whole scenario families for smoke tests")
    args = parser.parse_args(argv)
    selected = [c for c in cases() if not args.family or c.family in args.family]
    if not selected:
        parser.error("No matching cases")
    run(args.output_dir, [int(s) for s in args.seeds.split(",")], args.episodes, selected)


if __name__ == "__main__":
    main()
