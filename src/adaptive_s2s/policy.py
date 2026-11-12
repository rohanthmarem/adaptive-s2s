"""The policy: style state in, controls out.

The text controls go to the language model as a style brief. The voice controls go to the
synthesiser. The two halves can be switched off separately, which gives the four arms of the
ablation (see `types.ARMS`).
"""

from __future__ import annotations

from .config import DEFAULT_POLICY, PolicyConfig
from .types import ARMS, Arm, Controls, StyleState, TextControls, VoiceControls

_CONTRACTIONS = {"casual": "use", "neutral": "some", "formal": "avoid"}


def target_speed(rate_sps: float | None, cfg: PolicyConfig = DEFAULT_POLICY) -> float:
    """Requested TTS speed for a user speaking at `rate_sps` syllables per second.

    The agent follows only part of the user's deviation from neutral, and the result is clamped.
    Bounded, partial convergence is the point: the agent moves toward the user and never copies them.
    """
    if rate_sps is None:
        return 1.0
    ratio = rate_sps / cfg.neutral_rate_sps
    speed = 1.0 + cfg.rate_follow * (ratio - 1.0)
    return min(cfg.speed_max, max(cfg.speed_min, speed))


def decide(state: StyleState, arm: Arm = ARMS["full"], cfg: PolicyConfig = DEFAULT_POLICY) -> Controls:
    """Choose this turn's controls from the state."""
    text = TextControls(max_sentences=cfg.default_max_sentences)
    voice = VoiceControls(voice=cfg.default_voice)
    why: list[str] = [f"arm={arm.name}"]
    supportive = state.support >= cfg.support_on

    if arm.text_adaptive:
        text.register = state.register
        text.contractions = _CONTRACTIONS[state.register]
        why.append(f"register={state.register} (casual {state.casual:.2f}, formal {state.formal:.2f})")
        if state.register == "casual":
            text.slang_allowed = state.slang_seen[: cfg.max_slang_reuse]
        if supportive:
            text.supportive = True
            text.slang_allowed = []
            text.max_sentences = cfg.supportive_max_sentences
            why.append(f"supportive wording (support {state.support:.2f}; {'; '.join(state.support_evidence)})")

    if arm.voice_adaptive:
        speed = target_speed(state.rate.value, cfg)
        if state.rate.value is None:
            why.append("speed=1.00 (no valid pace measurement yet)")
        else:
            why.append(f"speed={speed:.2f} (user {state.rate.value:.2f} syll/s, neutral {cfg.neutral_rate_sps:.2f})")
        pause_scale = 1.0
        if (state.pause_fraction.value or 0.0) > cfg.pausey_user_fraction:
            pause_scale = cfg.pausey_pause_scale
            why.append(f"pause_scale={pause_scale:.1f} (user pauses {state.pause_fraction.value:.0%} of the time)")
        if supportive:
            # Complement, do not mirror: calmer than a fast, upset speaker. A speaker who is already
            # slow is not slowed further, because the cap only ever lowers the speed to 0.95.
            speed = min(speed, cfg.supportive_speed_cap)
            pause_scale = max(pause_scale, cfg.supportive_pause_scale)
            why.append(f"supportive delivery: speed<={cfg.supportive_speed_cap:.2f}, pause_scale={pause_scale:.1f}")
        voice.speed = round(speed, 3)
        voice.pause_scale = pause_scale

    # The safety reply is not an experimental variable. It applies in every arm.
    if state.crisis:
        text.crisis = True
        why.append("crisis wording detected: fixed safety reply")

    return Controls(text=text, voice=voice, rationale=why)
