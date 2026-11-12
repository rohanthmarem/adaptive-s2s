"""The running style state and its update rule.

Two channels feed the state and they never mix:
  - acoustic (how it was said): pace and pauses, plus the optional emotion model
  - lexical  (what was said):   register cues and distress words

`update_state` is a pure function, so every turn's before/after state can be logged and replayed.
"""

from __future__ import annotations

import copy

from .config import DEFAULT_POLICY, PolicyConfig
from .types import AcousticFeatures, AffectReading, Register, RegisterFeatures, StyleState, Tracked

DISTRESS_LABELS = ("sad", "fearful")


def _ema(tracked: Tracked, obs: float, alpha: float, turn: int) -> Tracked:
    value = obs if tracked.value is None else (1.0 - alpha) * tracked.value + alpha * obs
    return Tracked(value=value, n_obs=tracked.n_obs + 1, last_obs=obs, last_valid_turn=turn)


def _register_label(prev: Register, casual: float, formal: float, cfg: PolicyConfig) -> Register:
    lead = casual - formal
    if casual >= cfg.register_floor and lead >= cfg.register_margin:
        return "casual"
    if formal >= cfg.register_floor and -lead >= cfg.register_margin:
        return "formal"
    # Sticky: a label that is already set stays while it still leads at half strength. This stops
    # the style from flipping back and forth around the threshold.
    if prev == "casual" and casual >= cfg.register_floor / 2 and lead >= cfg.register_margin / 2:
        return "casual"
    if prev == "formal" and formal >= cfg.register_floor / 2 and -lead >= cfg.register_margin / 2:
        return "formal"
    return "neutral"


def distress_evidence(
    acoustic: AcousticFeatures,
    affect: AffectReading,
    register: RegisterFeatures,
    cfg: PolicyConfig = DEFAULT_POLICY,
) -> tuple[float, list[str]]:
    """Strength of this turn's distress evidence (0..1) and where it came from.

    Words count on their own. The voice counts only through the emotion model, and only when it is
    confident. Low pitch, low volume or slow speech alone are never evidence: microphone gain,
    tiredness and ordinary differences between voices all produce them.
    """
    strength = 0.0
    why: list[str] = []
    hits = register.distress_hits
    if hits:
        strength = cfg.lexical_distress_one_hit if len(hits) == 1 else cfg.lexical_distress_many_hits
        why.append("words: " + ", ".join(hits[:3]))
    enough_speech = (acoustic.articulation_time_s or 0.0) >= cfg.ser_min_speech_s
    if affect.available and enough_speech and affect.top_label in DISTRESS_LABELS:
        share = sum(affect.scores.get(label, 0.0) for label in DISTRESS_LABELS)
        if share >= cfg.ser_distress_min:
            strength = max(strength, min(1.0, share))
            why.append(f"voice: sad+fearful={share:.2f} ({affect.model})")
    return strength, why


def update_state(
    prev: StyleState,
    acoustic: AcousticFeatures,
    affect: AffectReading,
    register: RegisterFeatures,
    cfg: PolicyConfig = DEFAULT_POLICY,
) -> StyleState:
    """Fold one user turn into the state and return the new state."""
    s = copy.deepcopy(prev)
    s.turn += 1

    # Pace: follow valid measurements; with too little speech, drift back toward neutral.
    if acoustic.valid and acoustic.articulation_rate_sps:
        s.rate = _ema(s.rate, acoustic.articulation_rate_sps, cfg.rate_ema_alpha, s.turn)
        if acoustic.pause_fraction is not None:
            s.pause_fraction = _ema(s.pause_fraction, acoustic.pause_fraction, cfg.pause_ema_alpha, s.turn)
    elif s.rate.value is not None:
        s.rate.value += cfg.invalid_relax * (cfg.neutral_rate_sps - s.rate.value)

    # Register: a short turn carries little evidence either way, so it moves the state less.
    # "No slang in a three-word reply" is not evidence that the speaker turned formal.
    # The first turn has nothing to average with, so it sets the level directly.
    beta = (1.0 if prev.turn == 0 else cfg.register_beta) * min(1.0, register.n_tokens / 8.0)
    s.casual = (1.0 - beta) * s.casual + beta * register.casual_evidence
    s.formal = (1.0 - beta) * s.formal + beta * register.formal_evidence
    s.register = _register_label(s.register, s.casual, s.formal, cfg)
    # Newest turn first, and slang before plain reductions, so the most distinctive expressions
    # are the ones offered back to the model.
    fresh = register.slang_hits + register.reductions
    s.slang_seen = (fresh + [t for t in s.slang_seen if t not in fresh])[: cfg.slang_memory]

    # Support: fast attack, slow release. One credible signal is enough to switch it on, and it
    # fades over the next turns instead of switching off at once.
    evidence, why = distress_evidence(acoustic, affect, register, cfg)
    if evidence > 0.0 and evidence >= s.support:
        s.support, s.support_evidence = evidence, why
    elif evidence < cfg.support_quiet_evidence:
        s.support *= cfg.support_release
    if s.support < 0.05:
        s.support, s.support_evidence = 0.0, []

    s.crisis = bool(register.crisis_hits)
    return s
