"""Shared data types. Everything here is plain data that goes into the per-turn JSON trace."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Register = Literal["casual", "neutral", "formal"]


@dataclass
class Word:
    text: str
    start: float
    end: float
    prob: float = 1.0


@dataclass
class Transcript:
    text: str
    words: list[Word]
    # "asr": text came from the recogniser. "locked": an experiment supplied the canonical text, so
    # every delivery of the same script reaches the generator with identical words.
    source: Literal["asr", "locked"] = "asr"
    model: str | None = None
    asr_text: str | None = None  # what the recogniser heard, kept when source == "locked"


@dataclass
class AcousticFeatures:
    """How the turn was said. Measured from the waveform, never from the words' meaning."""

    duration_s: float
    speech_span_s: float | None  # first to last speech frame
    articulation_time_s: float | None  # speech span minus pauses
    n_words: int
    n_syllables: int
    speech_rate_sps: float | None  # syllables / speech span (pauses included)
    articulation_rate_sps: float | None  # syllables / articulation time (pauses excluded)
    pause_fraction: float | None  # pause time / speech span
    rms_dbfs: float | None  # level of the speech frames; depends on mic gain, so it is not a control input
    f0_median_hz: float | None  # diagnostics only
    f0_iqr_st: float | None  # diagnostics only, in semitones
    valid: bool  # False when there is too little speech to trust the rates
    invalid_reason: str | None = None


@dataclass
class AffectReading:
    """Output of the optional speech-emotion model. `available=False` means unknown, not neutral."""

    available: bool
    model: str | None = None
    scores: dict[str, float] = field(default_factory=dict)
    top_label: str | None = None
    top_score: float | None = None
    note: str | None = None  # why it is unavailable, or a caveat


@dataclass
class RegisterFeatures:
    """What words were used. Measured from the transcript only."""

    n_tokens: int
    n_sentences: int
    mean_sentence_len: float
    contractions_per_100: float
    reductions: list[str]  # gonna, wanna, kinda, ...
    slang_hits: list[str]
    formal_hits: list[str]
    distress_hits: list[str]
    crisis_hits: list[str]
    casual_evidence: float  # 0..1, this turn only
    formal_evidence: float  # 0..1, this turn only


@dataclass
class Tracked:
    """One running estimate with its own evidence count, so reliability is per feature."""

    value: float | None = None
    n_obs: int = 0
    last_obs: float | None = None
    last_valid_turn: int | None = None


@dataclass
class TextControls:
    register: Register = "neutral"
    contractions: Literal["use", "some", "avoid"] = "some"
    slang_allowed: list[str] = field(default_factory=list)  # only expressions the user used
    max_sentences: int = 3
    supportive: bool = False
    crisis: bool = False


@dataclass
class VoiceControls:
    speed: float = 1.0  # requested TTS speed multiplier; the eval measures what was realised
    pause_scale: float = 1.0  # scales the silence inserted between sentences
    voice: str = "af_heart"


@dataclass
class Controls:
    text: TextControls = field(default_factory=TextControls)
    voice: VoiceControls = field(default_factory=VoiceControls)
    rationale: list[str] = field(default_factory=list)  # one line per decision, with its evidence


@dataclass
class StyleState:
    """Conversation-scoped style state (the "listener profile").

    It describes how the last few turns were spoken. It is not a profile of a person: it holds no
    demographics, it starts empty for every conversation, and every field decays or resets.
    """

    turn: int = 0
    rate: Tracked = field(default_factory=Tracked)  # articulation rate, syllables per second
    pause_fraction: Tracked = field(default_factory=Tracked)
    casual: float = 0.0  # accumulated register evidence, 0..1
    formal: float = 0.0
    register: Register = "neutral"
    slang_seen: list[str] = field(default_factory=list)  # most recent first
    support: float = 0.0  # 0..1, fast attack and slow release
    support_evidence: list[str] = field(default_factory=list)
    crisis: bool = False  # set by this turn's words only; never carried over


@dataclass(frozen=True)
class Arm:
    """One cell of the 2x2 ablation: is the text side adaptive, is the voice side adaptive."""

    name: str
    text_adaptive: bool
    voice_adaptive: bool


ARMS: dict[str, Arm] = {
    "static": Arm("static", text_adaptive=False, voice_adaptive=False),
    "text-only": Arm("text-only", text_adaptive=True, voice_adaptive=False),
    "voice-only": Arm("voice-only", text_adaptive=False, voice_adaptive=True),
    "full": Arm("full", text_adaptive=True, voice_adaptive=True),
}


def to_dict(obj: Any) -> Any:
    """Dataclass (or nested structure of them) to plain JSON-ready data."""
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_dict(v) for v in obj]
    return obj
