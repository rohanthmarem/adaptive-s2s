import json
from pathlib import Path
import numpy as np
import pytest
from adaptive_s2s.pipeline import Pipeline, Session
from adaptive_s2s.types import Transcript, AffectReading, StyleState, VoiceControls, to_dict
from adaptive_s2s.acoustic import measure
from adaptive_s2s.llm import TemplateChat


class ASR:
    def transcribe(self, x):
        assert x.dtype == np.float32
        return Transcript("heard words", [], model="fake")


class Affect:
    def analyze(self, x):
        return AffectReading(False)


class TTS:
    def synthesize(self, text, voice, cfg):
        return np.ones(24000, dtype=np.float32) * .1, 24000


def test_turn(tmp_path):
    p = Pipeline(ASR(), Affect(), TemplateChat(), TTS())
    x = np.ones(32000, dtype=np.float32) * .1
    override = measure(x, 16000, "a longer phrase to count the syllables")
    r, s = p.turn(x, 16000, StyleState(), locked_text="Hey bro I kinda wanna chill with you today",
                  feature_override=(override, AffectReading(False, note="override")),
                  feature_source="oracle", out_path=tmp_path / "reply.wav")
    assert r.transcript.source == "locked" and r.transcript.asr_text == "heard words"
    assert r.acoustic.n_words != r.acoustic_used.n_words
    assert r.affect_used.note == "override"
    assert r.llm["stub"] is True and s.turn == 1
    assert Path(r.output_path).is_file()
    assert json.loads(json.dumps(to_dict(r)))["track"] == "locked"
    r, _ = p.turn(x, 16000, s, locked_text="I want to kill myself", synthesize=False)
    assert r.llm["backend"] == "crisis-template" and r.output_acoustic is None
    assert r.tts["sr"] is None
    session = Session(p, tmp_path / "session")
    session.turn((x, 16000))
    session.turn(x, 16000)
    assert len(session.history) == 2 and session.state.turn == 2
    assert (tmp_path / "session/turn_02.trace.json").is_file()


@pytest.mark.slow
def test_real_models(tmp_path):
    from adaptive_s2s.tts import KokoroTTS, CACHE
    from adaptive_s2s.asr import WhisperASR
    from adaptive_s2s.asr import cached_model_path
    if not all((CACHE / n).is_file() for n in ("kokoro-v1.0.onnx", "voices-v1.0.bin")):
        pytest.skip("Kokoro files missing")
    try:
        cached_model_path("Systran/faster-whisper-base.en")
    except (OSError, RuntimeError):
        pytest.skip("Whisper cache missing")
    tts = KokoroTTS()
    x, sr = tts.synthesize("Please help me plan our meeting for Friday afternoon.", VoiceControls())
    p = Pipeline(WhisperASR(), Affect(), TemplateChat(), tts)
    r, _ = p.turn(x, sr, StyleState(), out_path=tmp_path / "reply.wav")
    assert "friday" in r.transcript.text.lower()
    assert r.output_acoustic.valid and r.llm["stub"]


def test_crisis_skips_generator_and_tts():
    class Never:
        def generate(self, *args, **kwargs):
            raise AssertionError("Crisis must bypass the LLM")

        def synthesize(self, *args, **kwargs):
            raise AssertionError("Text-only turn must bypass TTS")

    p = Pipeline(ASR(), Affect(), Never(), Never())
    r, _ = p.turn(np.zeros(24000, dtype=np.float32), 24000, StyleState(),
                  locked_text="I want to end my life", synthesize=False)
    assert r.controls.text.crisis and r.llm["backend"] == "crisis-template"
    assert not r.llm["stub"]  # the fixed safety reply is deliberate, not a stand-in for a model
    assert r.output_path is None


def test_tts_sentence_pauses(tmp_path):
    from adaptive_s2s.tts import KokoroTTS
    from adaptive_s2s.config import DEFAULT_POLICY
    model = tmp_path / "model"
    voices = tmp_path / "voices"
    model.touch()
    voices.touch()
    calls = []

    class Kokoro:
        def create(self, text, **kwargs):
            calls.append((text, kwargs))
            return np.ones(2400, dtype=np.float32), 24000

    tts = KokoroTTS(model, voices)
    tts._model = Kokoro()
    x, sr = tts.synthesize("First sentence. Second sentence.", VoiceControls(speed=.9, pause_scale=1.4))
    pause = round(sr * DEFAULT_POLICY.base_pause_ms * 1.4 / 1000)
    assert x.dtype == np.float32 and len(x) == 4800 + pause
    assert np.all(x[2400:2400 + pause] == 0)
    # The engine setting is calibrated: asking Kokoro for 0.90x only gives about 0.95x in the audio,
    # so a 0.90x target needs a lower engine setting.
    assert len(calls) == 2 and calls[0][1]["speed"] == tts.engine_speed(.9)
    assert 0.8 < calls[0][1]["speed"] < .9

    raw = KokoroTTS(model, voices, calibrate=False)
    raw._model = Kokoro()
    calls.clear()
    raw.synthesize("One sentence.", VoiceControls(speed=.9))
    assert calls[0][1]["speed"] == .9
    assert tts.engine_speed(1.0) == 1.0
