"""Acoustic measurements: how a turn was said.

Rates come from an energy-based speech detector plus a syllable count, so they do not depend on the
recogniser's word timestamps. The same function measures the user's audio and the agent's generated
audio, which is how the evaluation checks what the synthesiser actually produced.
"""

from __future__ import annotations

import numpy as np

from .config import DEFAULT_POLICY, PolicyConfig
from .textutil import count_syllables_text, tokens
from .types import AcousticFeatures

FRAME_MS = 25
HOP_MS = 10
SPEECH_REL_DB = 30.0  # a frame is speech when it is within this range of the loud frames
SILENCE_FLOOR_DB = -60.0
MIN_PAUSE_S = 0.2  # shorter gaps are stop closures, not pauses


def frame_levels_db(audio: np.ndarray, sr: int) -> np.ndarray:
    """RMS level in dBFS for each 25 ms frame (10 ms hop)."""
    frame = max(1, int(sr * FRAME_MS / 1000))
    hop = max(1, int(sr * HOP_MS / 1000))
    x = np.asarray(audio, dtype=np.float64)
    if x.size < frame:
        x = np.pad(x, (0, frame - x.size))
    n = 1 + (x.size - frame) // hop
    idx = np.arange(frame)[None, :] + hop * np.arange(n)[:, None]
    power = np.mean(x[idx] ** 2, axis=1)
    return 10.0 * np.log10(np.maximum(power, 1e-12))


def speech_mask(levels_db: np.ndarray) -> np.ndarray:
    """True for frames that count as speech."""
    if levels_db.size == 0:
        return np.zeros(0, dtype=bool)
    reference = float(np.percentile(levels_db, 95))
    threshold = max(reference - SPEECH_REL_DB, SILENCE_FLOOR_DB)
    return levels_db > threshold


def _pauses(mask: np.ndarray, hop_s: float) -> tuple[int, int, float]:
    """First speech frame, last speech frame, and total pause time between them."""
    on = np.flatnonzero(mask)
    first, last = int(on[0]), int(on[-1])
    pause_time = 0.0
    run = 0
    for is_speech in mask[first : last + 1]:
        if is_speech:
            if run * hop_s >= MIN_PAUSE_S:
                pause_time += run * hop_s
            run = 0
        else:
            run += 1
    return first, last, pause_time


def _pitch_stats(audio: np.ndarray, sr: int) -> tuple[float | None, float | None]:
    """Median F0 in Hz and its interquartile range in semitones. Diagnostics only."""
    try:
        import parselmouth

        pitch = parselmouth.Sound(np.asarray(audio, dtype=np.float64), sampling_frequency=sr).to_pitch(
            time_step=0.01, pitch_floor=75.0, pitch_ceiling=500.0
        )
        f0 = pitch.selected_array["frequency"]
        f0 = f0[f0 > 0]
        if f0.size < 10:
            return None, None
        q25, q50, q75 = np.percentile(f0, [25, 50, 75])
        return float(q50), float(12.0 * np.log2(q75 / q25))
    except Exception:  # pitch is optional; a failure here must not stop a turn
        return None, None


def measure(
    audio: np.ndarray,
    sr: int,
    text: str,
    cfg: PolicyConfig = DEFAULT_POLICY,
    *,
    with_pitch: bool = True,
) -> AcousticFeatures:
    """Measure pace, pauses and level of one utterance.

    `text` is the words that were spoken (the recogniser's output, or the canonical script in a
    transcript-locked experiment). It only supplies the word and syllable counts.
    """
    audio = np.asarray(audio, dtype=np.float32)
    duration = audio.size / sr if sr else 0.0
    n_words = len(tokens(text))
    n_syll = count_syllables_text(text)

    def invalid(reason: str) -> AcousticFeatures:
        return AcousticFeatures(
            duration_s=duration, speech_span_s=None, articulation_time_s=None, n_words=n_words,
            n_syllables=n_syll, speech_rate_sps=None, articulation_rate_sps=None, pause_fraction=None,
            rms_dbfs=None, f0_median_hz=None, f0_iqr_st=None, valid=False, invalid_reason=reason,
        )

    if audio.size == 0:
        return invalid("empty audio")
    levels = frame_levels_db(audio, sr)
    if float(levels.max()) <= SILENCE_FLOOR_DB:
        return invalid("silence")
    mask = speech_mask(levels)
    if not mask.any():
        return invalid("no speech frames")

    hop_s = HOP_MS / 1000
    first, last, pause_time = _pauses(mask, hop_s)
    span = (last - first) * hop_s + FRAME_MS / 1000
    articulation = max(span - pause_time, 1e-6)
    power = np.mean(10.0 ** (levels[first : last + 1][mask[first : last + 1]] / 10.0))
    f0_median, f0_iqr = _pitch_stats(audio, sr) if with_pitch else (None, None)

    reason = None
    if n_words < cfg.min_words_for_rate:
        reason = f"only {n_words} words"
    elif articulation < cfg.min_articulation_s:
        reason = f"only {articulation:.2f} s of speech"

    return AcousticFeatures(
        duration_s=duration,
        speech_span_s=span,
        articulation_time_s=articulation,
        n_words=n_words,
        n_syllables=n_syll,
        speech_rate_sps=n_syll / span if n_syll else None,
        articulation_rate_sps=n_syll / articulation if n_syll else None,
        pause_fraction=pause_time / span,
        rms_dbfs=float(10.0 * np.log10(max(power, 1e-12))),
        f0_median_hz=f0_median,
        f0_iqr_st=f0_iqr,
        valid=reason is None,
        invalid_reason=reason,
    )
