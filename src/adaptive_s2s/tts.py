"""Sentence-wise Kokoro synthesis with explicit pauses and a calibrated speed control."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .config import DEFAULT_POLICY, PolicyConfig
from .textutil import sentences
from .types import VoiceControls

CACHE = Path.home() / ".cache/adaptive-s2s/kokoro"

# Kokoro does not deliver the speed it is asked for. Small changes are partly lost (asking for 0.90x
# gives about 0.95x) and large ones overshoot. This table maps the engine's `speed` argument to the
# speed measured in the audio (speaking time against the same words at 1.0x). Measured on this
# project's Mac with the voice `af_heart` and four sentences. Re-measure with `s2s calibrate-tts`.
DEFAULT_SPEED_CALIBRATION: list[tuple[float, float]] = [
    (0.6, 0.585), (0.7, 0.682), (0.8, 0.793), (0.9, 0.946), (1.0, 1.0),
    (1.1, 1.049), (1.2, 1.133), (1.3, 1.208), (1.4, 1.512),
]

CALIBRATION_TEXTS = (
    "Yeah, sure thing. Let's move it to Friday then. I'll send you the new time.",
    "I'm really sorry to hear about that. It's okay to feel overwhelmed right now.",
    "Of course, I can help with that. Could you give me some details about the message?",
    "The library closes at five on Sundays, so you have about two hours left to return the books.",
)


def calibration_path(voice: str) -> Path:
    return CACHE / f"speed_calibration_{voice}.json"


class KokoroTTS:
    def __init__(self, model_path=None, voices_path=None, calibrate: bool = True):
        self.model_path = Path(model_path or CACHE / "kokoro-v1.0.onnx")
        self.voices_path = Path(voices_path or CACHE / "voices-v1.0.bin")
        self.calibrate = calibrate
        self._model = None
        self._tables: dict[str, list[tuple[float, float]]] = {}

    def _table(self, voice: str) -> list[tuple[float, float]]:
        if voice not in self._tables:
            path = calibration_path(voice)
            table = DEFAULT_SPEED_CALIBRATION
            if path.is_file():
                table = [tuple(row) for row in json.loads(path.read_text(encoding="utf-8"))]
            self._tables[voice] = sorted(table, key=lambda row: row[1])
        return self._tables[voice]

    def engine_speed(self, target: float, voice: str = DEFAULT_POLICY.default_voice) -> float:
        """The `speed` argument that makes Kokoro actually speak at `target` times its normal speed."""
        if not self.calibrate or target == 1.0:
            return float(target)
        table = self._table(voice)
        realised = [row[1] for row in table]
        requested = [row[0] for row in table]
        return float(np.interp(target, realised, requested))

    def _load(self):
        for path in (self.model_path, self.voices_path):
            if not path.is_file():
                raise RuntimeError(f"Missing {path}; run s2s fetch-models")
        if self._model is None:
            from kokoro_onnx import Kokoro

            self._model = Kokoro(str(self.model_path), str(self.voices_path))
        return self._model

    def synthesize(self, text: str, voice: VoiceControls, cfg: PolicyConfig = DEFAULT_POLICY) -> tuple[np.ndarray, int]:
        """Speak `text`. `voice.speed` is the speed wanted in the audio, not the raw engine setting."""
        model = self._load()
        speed = self.engine_speed(voice.speed, voice.voice)
        pause = np.zeros(round(24000 * cfg.base_pause_ms * voice.pause_scale / 1000), dtype=np.float32)
        chunks: list[np.ndarray] = []
        sr = 24000
        for sentence in sentences(text):
            samples, rate = model.create(sentence, voice=voice.voice, speed=speed, lang="en-us")
            if rate != sr:
                raise RuntimeError(f"Kokoro returned {rate} Hz, expected {sr} Hz")
            if chunks:
                chunks.append(pause)
            chunks.append(np.asarray(samples, dtype=np.float32).reshape(-1))
        return (np.concatenate(chunks) if chunks else np.empty(0, dtype=np.float32)), sr


def measure_speed_calibration(
    tts: KokoroTTS,
    voice: str = DEFAULT_POLICY.default_voice,
    speeds: tuple[float, ...] = (0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4),
) -> list[tuple[float, float]]:
    """Measure what each engine speed really produces for one voice, averaged over a few sentences."""
    from . import acoustic

    model = tts._load()

    def speaking_time(text: str, speed: float) -> float:
        samples, sr = model.create(text, voice=voice, speed=speed, lang="en-us")
        return acoustic.measure(np.asarray(samples, dtype=np.float32).reshape(-1), sr, text, with_pitch=False).articulation_time_s

    table = []
    for speed in speeds:
        ratios = [speaking_time(text, 1.0) / speaking_time(text, speed) for text in CALIBRATION_TEXTS]
        table.append((speed, round(float(np.mean(ratios)), 3)))
    return table
