"""Compatibility helpers for the revised funded resolution game.

No source-topology coin or external-monitor log response is embedded here.
The actual composition prototype and endogenous monitoring game are separate.
"""
from __future__ import annotations

import math
import random

from .economics import Actor, Latents, can_challenge, challenge_probability, check_probability, choose_action, make_actors, proposer_values
from .legacy_config import to_game
from .types import Participant


def generate_participants(config, rng: random.Random):
    game = to_game(config)
    latent = Latents(tuple(tuple(rng.random() for _ in range(9)) for _ in range(game.participants)), rng.random())
    return [Participant(index=a.index, stake=abs(a.signed_gain), is_winner_under_true=a.signed_gain < 0,
                        is_winner_under_false=a.signed_gain > 0, attention_prob=check_probability(game, a),
                        capital_budget=a.capital, role="challenger", payout_true=a.payout_true, payout_false=a.payout_false)
            for a in make_actors(game, latent)]


def _actor(p, config):
    true = p.payout_true if p.payout_true is not None else (p.stake if p.is_winner_under_true else 0.)
    false = p.payout_false if p.payout_false is not None else (p.stake if p.is_winner_under_false else 0.)
    rate = (-math.log1p(-p.attention_prob) / config.challenge_window_hours
            if 0 <= p.attention_prob < 1 and config.challenge_window_hours else (1e6 if p.attention_prob else 0.))
    return Actor(p.index, true, false, p.capital_budget, rate, float(p.index))


def composition_false_submission_probability(config):
    to_game(config)
    return 1.0


def composition_detection_probability(config):
    to_game(config)
    return 1.0


def estimate_proposer_mev(config, proposer, rng=None):
    """Always the signed funded payout difference; legacy model labels cannot mint MEV."""
    return _actor(proposer, config).signed_gain


def estimate_challenge_probability(config, proposer, participants, proposal_is_false=True):
    return challenge_probability(to_game(config), tuple(_actor(p, config) for p in participants),
                                 proposer.index, int(proposal_is_false))


def proposer_action(config, proposer, participants, mev=None):
    """The old mev argument is ignored: actual signed claims govern."""
    game = to_game(config)
    actor = _actor(proposer, config)
    action = choose_action(game, actor, proposer_values(game, tuple(_actor(p, config) for p in participants), actor))
    return {"truth": "truthful", "false": "false", "abstain": "abstain", "ineligible": "abstain"}[action]


def select_proposer(config, participants, proposer_actions, rng):
    eligible = [p for p in participants if p.capital_budget >= config.proposer_bond + config.proposer_work_cost]
    willing = [p for p in eligible if proposer_actions[p.index] != "abstain"]
    return (rng.choice(willing) if willing else None), len(eligible), len(willing)


def participant_checks(participant, rng):
    return rng.random() < participant.attention_prob


def challenger_decides(participant, config, proposal_is_false=True):
    return can_challenge(to_game(config), _actor(participant, config), int(proposal_is_false))
