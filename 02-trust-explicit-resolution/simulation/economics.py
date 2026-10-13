"""Funded, one-shot resolution game used by the revised publication experiments.

This is an operational policy game, not an equilibrium model of attention.
An externally provisioned inspection schedule is an input.  The separate
monitoring module solves whether neutral inspectors will provide that service.
Here every candidate compares exact expected payoffs under that schedule;
post-inspection challenge decisions include position changes, error, work,
capital, and the declared bond transfer.  Truth is outcome 0 throughout.

Market claims are collateral backed: each of the two outcome columns sums to
L.  Free bond capital is separate.  False adjudications are possible on either
kind of proposal.  Only a successful challenger gets a bond reward; a failed
challenger's bond goes to the protocol, never to the proposer.  Success fees
come from a prepaid reserve.  Resource spending, opportunity cost, and payout
redistribution are different quantities.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import random


@dataclass(frozen=True)
class GameConfig:
    pool: float = 5_000.0
    participants: int = 10
    positions: str = "uniform"  # uniform, power_law, whale
    bond_rule: str = "proportional"  # proportional, flat, capped
    bond_floor: float = 10.0
    bond_rate: float = 0.15
    bond_cap: float = 750.0
    challenger_ratio: float = 1.0
    reward_fraction: float = 0.5
    accuracy: float = 0.95
    window: float = 24.0
    adjudication_delay: float = 24.0
    attention: str = "lazy"  # attentive, lazy, stake
    attention_multiplier: float = 1.0
    detection: float = 1.0  # NONE composition: a checker observes truth exactly
    capital_profile: str = "unconstrained"
    proposer_fee: float = 5.0
    proposer_work: float = 2.0
    verification_work: float = 0.5
    challenge_work: float = 0.25
    capital_apy: float = 0.20
    honest_proposer: bool = False
    proposer_selection: str = "first_willing"  # randomized priority, or worst_willing

    def __post_init__(self):
        if self.participants < 2:
            raise ValueError("A collateral-backed binary allocation needs >=2 actors")
        if self.positions not in {"uniform", "power_law", "whale"}:
            raise ValueError("Unknown positions")
        if self.bond_rule not in {"flat", "proportional", "capped"}:
            raise ValueError("Unknown one-shot bond rule; escalation is a different game")
        if self.attention not in {"attentive", "lazy", "stake"}:
            raise ValueError("Unknown inspection schedule")
        if self.capital_profile not in {"unconstrained", "retail", "mixed", "specialized"}:
            raise ValueError("Unknown capital profile")
        if self.proposer_selection not in {"first_willing", "worst_willing"}:
            raise ValueError("Unknown proposer selection")
        for name in ("reward_fraction", "accuracy", "detection"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(name)
        for name in ("pool", "bond_floor", "bond_rate", "bond_cap", "challenger_ratio",
                     "window", "adjudication_delay", "attention_multiplier", "proposer_fee",
                     "proposer_work", "verification_work", "challenge_work", "capital_apy"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(name)
        if self.pool == 0 or self.proposer_bond == 0:
            raise ValueError("Positive collateral and proposer bond required")

    @property
    def proposer_bond(self):
        if self.bond_rule == "flat":
            return self.bond_floor
        value = max(self.bond_floor, self.bond_rate * self.pool)
        return min(value, self.bond_cap) if self.bond_rule == "capped" else value

    @property
    def challenger_bond(self):
        return self.challenger_ratio * self.proposer_bond

    @property
    def proposer_opportunity_cost(self):
        # Conservative fixed lock contract includes the full adjudication reserve.
        return self.capital_apy * self.proposer_bond * (self.window + self.adjudication_delay) / 8760

    @property
    def challenger_opportunity_cost(self):
        return self.capital_apy * self.challenger_bond * self.adjudication_delay / 8760


@dataclass(frozen=True)
class Actor:
    index: int
    payout_true: float
    payout_false: float
    capital: float
    check_rate: float
    priority: float

    @property
    def signed_gain(self):
        return self.payout_false - self.payout_true

    def payout(self, outcome):
        return self.payout_false if outcome else self.payout_true


@dataclass(frozen=True)
class Latents:
    """Common random numbers, independent of every treatment parameter."""
    actors: tuple[tuple[float, ...], ...]
    adjudicator: float


def draw_latents(seed: int, episode: int, participants: int) -> Latents:
    rng = random.Random((seed << 40) + episode)
    rows = tuple(tuple(rng.random() for _ in range(9)) for _ in range(participants))
    # A separate stream keeps adjudication paired when participant count changes.
    judge = random.Random((seed << 40) + episode + (1 << 120)).random()
    return Latents(rows, judge)


def capital_from_uniform(profile: str, u: float, v: float) -> float:
    if profile == "unconstrained":
        return 1e9
    bands = {
        "retail": ((.70, 100, 1_000), (.95, 1_000, 5_000), (1, 5_000, 20_000)),
        "mixed": ((.35, 250, 2_500), (.75, 2_500, 10_000), (1, 10_000, 50_000)),
        "specialized": ((.15, 1_000, 5_000), (.70, 5_000, 25_000), (1, 25_000, 100_000)),
    }
    for cutoff, lo, hi in bands[profile]:
        if u <= cutoff:
            return math.exp(math.log(lo) + v * math.log(hi / lo))
    raise AssertionError("Uniform draw outside [0,1]")


def make_actors(config: GameConfig, latent: Latents) -> tuple[Actor, ...]:
    n = config.participants
    if len(latent.actors) < n:
        raise ValueError("Insufficient latent actors")
    true_set = set(sorted(range(n), key=lambda i: latent.actors[i][0])[:n // 2])
    if config.positions == "uniform":
        weights = [1.0] * n
    elif config.positions == "power_law":
        weights = [(i + 1) ** -.8 for i in range(n)]
    else:
        weights = [.60] + [.40 / (n - 1)] * (n - 1)
    totals = [sum(weights[i] for i in range(n) if (i in true_set) == (side == 0)) for side in (0, 1)]
    actors = []
    for i in range(n):
        u = latent.actors[i]
        side = 0 if i in true_set else 1
        stake = config.pool * weights[i] / totals[side]
        if config.attention == "attentive":
            rate = .05 + .10 * u[1]
        elif config.attention == "lazy":
            rate = .01 + .02 * u[2] if u[1] < .15 else .0005 + .0025 * u[2]
        else:
            rate = .02 * stake / config.pool * (.3 + 1.4 * u[1])
        actors.append(Actor(i, stake if side == 0 else 0.0, stake if side == 1 else 0.0,
                            capital_from_uniform(config.capital_profile, u[3], u[4]),
                            rate * config.attention_multiplier, u[5]))
    for side in (0, 1):
        assert math.isclose(sum(a.payout(side) for a in actors), config.pool, abs_tol=1e-8)
    return tuple(actors)


def challenge_value(config: GameConfig, actor: Actor, proposal: int) -> float:
    """Incremental value at a ready checker's last submission opportunity.

    Truth is known after detection.  An erroneous ruling on an honest proposal
    can still make a strategic false challenge profitable.  There is no
    orientation veto.  Verification cost is sunk; filing and bond costs are not.
    The prescribed ready/submit policy (not a waiting/free-rider equilibrium)
    files iff this one-shot continuation value is positive.
    """
    overturn = config.accuracy if proposal == 1 else 1 - config.accuracy
    correction_gain = actor.payout(1 - proposal) - actor.payout(proposal)
    return (overturn * (correction_gain + config.reward_fraction * config.proposer_bond)
            - (1 - overturn) * config.challenger_bond
            - config.challenge_work - config.challenger_opportunity_cost)


def can_challenge(config: GameConfig, actor: Actor, proposal: int) -> bool:
    return (actor.capital >= config.challenger_bond + config.challenge_work + config.verification_work
            and challenge_value(config, actor, proposal) > 0)


def check_probability(config: GameConfig, actor: Actor) -> float:
    if actor.capital < config.verification_work:
        return 0.0
    return -math.expm1(-actor.check_rate * config.window)


def challenge_probability(config: GameConfig, actors: tuple[Actor, ...], proposer: int, proposal: int) -> float:
    no_challenge = math.prod(1 - check_probability(config, a) * config.detection
                             for a in actors if a.index != proposer and can_challenge(config, a, proposal))
    return 1 - no_challenge


def proposer_values(config: GameConfig, actors: tuple[Actor, ...], proposer: Actor) -> tuple[float, float, float, float]:
    """Exact truth/fraud expectations for the same ready/submit policy used below."""
    q_true = challenge_probability(config, actors, proposer.index, 0)
    q_false = challenge_probability(config, actors, proposer.index, 1)
    cost = config.proposer_work + config.proposer_opportunity_cost
    truthful = config.proposer_fee - cost + q_true * (1 - config.accuracy) * (
        proposer.signed_gain - config.proposer_bond - config.proposer_fee)
    false = proposer.signed_gain + config.proposer_fee - cost - q_false * config.accuracy * (
        proposer.signed_gain + config.proposer_bond + config.proposer_fee)
    return truthful, false, q_true, q_false


def all_proposer_values(config: GameConfig, actors: tuple[Actor, ...]) -> list[tuple[float, float, float, float]]:
    """Linear-time evaluation, checked against the direct product implementation."""
    probabilities = []
    for proposal in (0, 1):
        factors = [1 - check_probability(config, a) * config.detection
                   if can_challenge(config, a, proposal) else 1.0 for a in actors]
        prefix = [1.0]
        for f in factors:
            prefix.append(prefix[-1] * f)
        suffix = 1.0
        q = [0.0] * len(actors)
        for i in range(len(actors) - 1, -1, -1):
            q[i] = 1 - prefix[i] * suffix
            suffix *= factors[i]
        probabilities.append(q)
    cost = config.proposer_work + config.proposer_opportunity_cost
    output = []
    for i, a in enumerate(actors):
        qt, qf = probabilities[0][i], probabilities[1][i]
        truth = config.proposer_fee - cost + qt * (1 - config.accuracy) * (
            a.signed_gain - config.proposer_bond - config.proposer_fee)
        false = a.signed_gain + config.proposer_fee - cost - qf * config.accuracy * (
            a.signed_gain + config.proposer_bond + config.proposer_fee)
        output.append((truth, false, qt, qf))
    return output


def choose_action(config: GameConfig, actor: Actor, values: tuple[float, float, float, float]) -> str:
    if actor.capital < config.proposer_bond + config.proposer_work:
        return "ineligible"
    truth, false = values[:2]
    if not config.honest_proposer and false > max(0.0, truth):
        return "false"
    return "truth" if truth >= 0 else "abstain"


def play(config: GameConfig, latent: Latents, *, keep_actors: bool = False) -> dict:
    actors = make_actors(config, latent)
    values = all_proposer_values(config, actors)
    actions = [choose_action(config, a, v) for a, v in zip(actors, values)]
    eligible = [a for a in actors if actions[a.index] != "ineligible"]
    willing = [a for a in eligible if actions[a.index] in {"truth", "false"}]
    result = {
        "status": "deferred", "proposer": None, "challenger": None,
        "attack_attempted": False, "proposal_false": False, "challenged": False,
        "false_challenge": False, "wrongful_proposer_slash": False,
        "final_wrong": False, "checks": 0, "eligible": len(eligible), "willing": len(willing),
        "positive_gain_candidates": sum(a.signed_gain > 0 for a in eligible),
        "positive_gain_truthful": sum(a.signed_gain > 0 and actions[a.index] == "truth" for a in eligible),
        "positive_gain_abstain": sum(a.signed_gain > 0 and actions[a.index] == "abstain" for a in eligible),
        "expected_wrong": 0.0, "expected_challenge": 0.0, "expected_proposer_net": 0.0,
        "proposer_net": 0.0, "signed_gain": 0.0, "challenge_value": None,
        "proposer_fee_paid": 0.0, "challenger_reward": 0.0, "protocol_receipt": 0.0,
        "reserve_initial": config.proposer_fee, "reserve_final": config.proposer_fee,
        "resource_cost": 0.0, "opportunity_cost": 0.0, "payout_misallocation": 0.0,
        "bond_locked": 0.0, "latency": 0.0, "balance_error": 0.0,
        "actor_cash_changes": [0.0] * len(actors),
    }
    if keep_actors:
        result["actors"] = [asdict(a) for a in actors]
        result["candidate_actions"] = actions
        result["candidate_values"] = values
    if not willing:
        # Deferred is a distinct no-submission endpoint, never a correct resolution.
        return result
    if config.proposer_selection == "first_willing":
        proposer = min(willing, key=lambda a: a.priority)
    else:
        proposer = max(willing, key=lambda a: (actions[a.index] == "false", a.signed_gain))
    pid = proposer.index
    proposal = int(actions[pid] == "false")
    result.update(proposer=pid, attack_attempted=bool(proposal), proposal_false=bool(proposal),
                  signed_gain=proposer.signed_gain, expected_proposer_net=values[pid][proposal],
                  expected_challenge=values[pid][2 + proposal],
                  expected_wrong=(1 - values[pid][3] * config.accuracy if proposal else
                                  values[pid][2] * (1 - config.accuracy)),
                  bond_locked=config.proposer_bond, latency=config.window,
                  resource_cost=config.proposer_work,
                  opportunity_cost=config.proposer_opportunity_cost)
    cash = result["actor_cash_changes"]
    cash[pid] -= config.proposer_work
    candidates = []
    for actor in actors:
        if actor.index == pid:
            continue
        u = latent.actors[actor.index]
        arrival = -math.log1p(-u[6]) / actor.check_rate if actor.check_rate else math.inf
        if arrival <= config.window and actor.capital >= config.verification_work:
            result["checks"] += 1
            result["resource_cost"] += config.verification_work
            cash[actor.index] -= config.verification_work
            if u[7] < config.detection and can_challenge(config, actor, proposal):
                candidates.append((arrival, actor))
    challenged = bool(candidates)
    final = proposal
    overturned = False
    if challenged:
        _, challenger = min(candidates, key=lambda pair: pair[0])
        cid = challenger.index
        # The same adjudicator draw means outcome 0 with probability accuracy,
        # independently of the submitted proposal's correctness.
        final = 0 if latent.adjudicator < config.accuracy else 1
        overturned = final != proposal
        result.update(challenger=cid, challenged=True, false_challenge=(proposal == 0),
                      wrongful_proposer_slash=(proposal == 0 and overturned),
                      challenge_value=challenge_value(config, challenger, proposal))
        result["resource_cost"] += config.challenge_work
        result["opportunity_cost"] += config.challenger_opportunity_cost
        result["bond_locked"] += config.challenger_bond
        result["latency"] += config.adjudication_delay
        cash[cid] -= config.challenge_work
        if overturned:
            reward = config.reward_fraction * config.proposer_bond
            cash[pid] -= config.proposer_bond
            cash[cid] += reward
            result["challenger_reward"] = reward
            result["protocol_receipt"] = config.proposer_bond - reward
        else:
            cash[cid] -= config.challenger_bond
            result["protocol_receipt"] = config.challenger_bond
    if not overturned:
        result["proposer_fee_paid"] = config.proposer_fee
        result["reserve_final"] -= config.proposer_fee
        cash[pid] += config.proposer_fee
    result.update(status="incorrect" if final else "correct", final_wrong=bool(final))
    payout_changes = [a.payout(final) - a.payout_true for a in actors]
    result["payout_misallocation"] = sum(max(0.0, -v) for v in payout_changes)
    result["proposer_net"] = cash[pid] + payout_changes[pid] - config.proposer_opportunity_cost
    result["balance_error"] = (sum(cash) + result["protocol_receipt"] + result["resource_cost"]
                               + result["reserve_final"] - result["reserve_initial"])
    if abs(result["balance_error"]) > 1e-8 or abs(sum(payout_changes)) > 1e-8:
        raise AssertionError("Budget or collateral conservation failure")
    if result["reserve_final"] < 0:
        raise AssertionError("Unfunded proposer fee")
    return result
