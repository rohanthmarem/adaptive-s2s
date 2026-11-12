"""Policy defaults.

Every number in this file is an engineering choice that the evaluation is meant to test and tune.
None of them is a research-backed optimum. Tune them on the dev split only, then freeze them before
the held-out run.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyConfig:
    # --- pace -----------------------------------------------------------------------------------
    # Articulation rate treated as "ordinary" until it is calibrated on real recordings.
    neutral_rate_sps: float = 4.7
    rate_ema_alpha: float = 0.4  # weight of the newest valid turn
    # Share of the user's deviation from neutral that the agent follows. Below 1 on purpose: the
    # agent converges part of the way and never copies the user outright.
    rate_follow: float = 0.6
    speed_min: float = 0.85
    speed_max: float = 1.15
    # With too little speech to measure, the estimate moves this far back toward neutral per turn.
    invalid_relax: float = 0.2
    min_words_for_rate: int = 4
    min_articulation_s: float = 1.0

    # --- pauses ---------------------------------------------------------------------------------
    base_pause_ms: int = 180  # silence between sentences at pause_scale 1.0
    pause_ema_alpha: float = 0.4
    pausey_user_fraction: float = 0.25  # above this, the agent leaves a little more room
    pausey_pause_scale: float = 1.2

    # --- register -------------------------------------------------------------------------------
    register_beta: float = 0.5  # weight of the newest turn's evidence
    register_margin: float = 0.25  # one side must lead the other by this much
    register_floor: float = 0.3  # and reach at least this level
    max_slang_reuse: int = 2
    slang_memory: int = 5

    # --- support (distress) -----------------------------------------------------------------------
    support_on: float = 0.4  # supportive mode is active at or above this level
    support_release: float = 0.6  # multiplier per turn without new evidence (slow release)
    support_quiet_evidence: float = 0.2  # evidence below this counts as "no new evidence"
    lexical_distress_one_hit: float = 0.5
    lexical_distress_many_hits: float = 1.0
    # The emotion model counts only when sad + fearful together reach this share and one of them
    # is the top label. Pitch, loudness and slowness alone never trigger support.
    ser_distress_min: float = 0.6
    ser_min_speech_s: float = 1.0
    supportive_speed_cap: float = 0.95
    supportive_pause_scale: float = 1.4
    supportive_max_sentences: int = 3

    # --- defaults ---------------------------------------------------------------------------------
    default_voice: str = "af_heart"
    default_max_sentences: int = 3


DEFAULT_POLICY = PolicyConfig()
