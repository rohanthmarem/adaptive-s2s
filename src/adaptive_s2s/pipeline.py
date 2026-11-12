"""One inspectable cascade turn and conversation-scoped sessions."""
from dataclasses import dataclass, replace
import copy
import json
from pathlib import Path
import time
import numpy as np
from . import acoustic, register
from .audio import load_audio, save_wav, to_16k
from .config import DEFAULT_POLICY
from .types import (ARMS, Transcript, AcousticFeatures, AffectReading, RegisterFeatures,
                    StyleState, Controls, VoiceControls, to_dict)
from .state import update_state
from .policy import decide
from .prompting import build_messages, clean_reply, CRISIS_REPLY


@dataclass
class TurnResult:
    turn: int
    input_path: str | None
    arm: str
    track: str
    feature_source: str
    transcript: Transcript
    acoustic: AcousticFeatures
    affect: AffectReading
    register: RegisterFeatures
    acoustic_used: AcousticFeatures
    affect_used: AffectReading
    state_before: StyleState
    state_after: StyleState
    controls: Controls
    reply_text: str
    llm: dict
    tts: dict
    output_path: str | None
    output_acoustic: AcousticFeatures | None
    timings_s: dict[str, float]
    meta: dict


class Pipeline:
    def __init__(self, asr, affect, llm, tts, cfg=DEFAULT_POLICY):
        self.asr, self.affect, self.llm, self.tts, self.cfg = asr, affect, llm, tts, cfg

    def warm(self) -> None:
        """Load every model once, so the first real turn is not timed with model loading."""
        silence = np.zeros(16000, dtype=np.float32)
        self.asr.transcribe(silence)
        self.affect.analyze(silence)
        self.llm.generate([{"role": "user", "content": "Hi"}], max_tokens=1, seed=0)
        self.tts.synthesize("Hello.", VoiceControls(voice=self.cfg.default_voice), self.cfg)

    def _realised_speed(self, reply: str, voice: VoiceControls, output: AcousticFeatures) -> dict:
        """Compare the reply audio with the same words synthesised at neutral speed.

        Replies differ between arms, so raw syllables per second is a noisy way to compare them.
        The ratio of speaking time for identical words isolates what the speed control really did.
        Above 1 means faster than neutral. Pauses are excluded, so `pause_scale` does not move it.
        """
        if voice.speed == 1.0 and voice.pause_scale == 1.0:
            reference = output
        else:
            samples, sr = self.tts.synthesize(reply, VoiceControls(voice=voice.voice), self.cfg)
            reference = acoustic.measure(samples, sr, reply, self.cfg, with_pitch=False)
        speed = duration_ratio = None
        if reference.articulation_time_s and output.articulation_time_s:
            speed = reference.articulation_time_s / output.articulation_time_s
        if reference.duration_s and output.duration_s:
            duration_ratio = reference.duration_s / output.duration_s
        return dict(realised_speed=speed, realised_duration_ratio=duration_ratio,
                    reference_articulation_time_s=reference.articulation_time_s)

    def turn(self, audio, sr, state, *, arm=ARMS["full"], history=(), locked_text=None,
             feature_override=None, feature_source="measured", seed=0, out_path=None,
             input_path=None, synthesize=True, measure_reference=False) -> tuple[TurnResult, StyleState]:
        if isinstance(arm, str):
            arm = ARMS[arm]
        if feature_source not in ("measured", "shuffled", "oracle"):
            raise ValueError("feature_source must be measured, shuffled or oracle")
        start = time.perf_counter()
        audio16k = to_16k(audio, sr)
        transcript = self.asr.transcribe(audio16k)
        if locked_text is not None:
            transcript = replace(transcript, text=locked_text, source="locked", asr_text=transcript.text)
        timings = {"asr": time.perf_counter() - start}
        tick = time.perf_counter()
        measured = acoustic.measure(audio, sr, transcript.text, self.cfg)
        affect = self.affect.analyze(audio16k)
        lexical = register.analyze(transcript.text)
        used, affect_used = feature_override if feature_override is not None else (measured, affect)
        after = update_state(state, used, affect_used, lexical, self.cfg)
        controls = decide(after, arm, self.cfg)
        timings["analyze"] = time.perf_counter() - tick
        tick = time.perf_counter()
        if controls.text.crisis:
            reply = CRISIS_REPLY
            llm_info = dict(backend="crisis-template", model=None, stub=False, seed=seed, latency_s=0.0)
        else:
            result = self.llm.generate(build_messages(list(history), transcript.text, controls.text),
                                       seed=seed, controls=controls.text)
            reply = clean_reply(result.text, controls.text.max_sentences)
            llm_info = {k: getattr(result, k) for k in ("backend", "model", "stub", "seed", "latency_s")}
        timings["llm"] = time.perf_counter() - tick
        tick = time.perf_counter()
        output = None
        output_path = None
        tts_info = dict(voice=controls.voice.voice, requested_speed=controls.voice.speed,
                        pause_scale=controls.voice.pause_scale, sr=None, duration_s=None,
                        engine_speed=None, realised_speed=None, realised_duration_ratio=None,
                        reference_articulation_time_s=None)
        if synthesize:
            samples, output_sr = self.tts.synthesize(reply, controls.voice, self.cfg)
            output = acoustic.measure(samples, output_sr, reply, self.cfg)
            engine_speed = getattr(self.tts, "engine_speed", None)
            tts_info.update(sr=output_sr, duration_s=len(samples) / output_sr,
                            engine_speed=engine_speed(controls.voice.speed, controls.voice.voice)
                            if engine_speed else controls.voice.speed)
            if out_path is not None:
                save_wav(out_path, samples, output_sr)
                output_path = str(out_path)
        timings["tts"] = time.perf_counter() - tick
        if synthesize and measure_reference:
            tick = time.perf_counter()
            tts_info.update(self._realised_speed(reply, controls.voice, output))
            timings["tts_reference"] = time.perf_counter() - tick  # measurement only, not part of a live turn
        timings["total"] = sum(timings[k] for k in ("asr", "analyze", "llm", "tts"))
        from importlib.metadata import version
        trace = TurnResult(after.turn, str(input_path) if input_path is not None else None,
                           arm.name, "locked" if locked_text is not None else "e2e", feature_source,
                           transcript, measured, affect, lexical, used, affect_used,
                           copy.deepcopy(state), after, controls, reply, llm_info, tts_info,
                           output_path, output, timings,
                           dict(package_version=version("adaptive-s2s"), asr_model=transcript.model,
                                policy=to_dict(self.cfg)))
        return trace, after


class Session:
    def __init__(self, pipeline, out_dir="out/session", state=None):
        self.pipeline = pipeline
        self.state = state or StyleState()
        self.history = []
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def turn(self, path_or_audio, sr=None, **kwargs) -> TurnResult:
        if isinstance(path_or_audio, (str, Path)):
            audio, sr = load_audio(path_or_audio)
            kwargs.setdefault("input_path", str(path_or_audio))
        elif isinstance(path_or_audio, tuple):
            audio, sr = path_or_audio
        else:
            audio = np.asarray(path_or_audio, dtype=np.float32)
            if sr is None:
                raise ValueError("Pass sr for an audio array")
        stem = self.out_dir / f"turn_{self.state.turn + 1:02d}"
        kwargs.setdefault("out_path", str(stem) + ".reply.wav")
        result, state = self.pipeline.turn(audio, sr, self.state, history=self.history, **kwargs)
        self.state = state
        self.history.append((result.transcript.text, result.reply_text))
        Path(str(stem) + ".trace.json").write_text(json.dumps(to_dict(result), indent=2), encoding="utf-8")
        return result


def build_pipeline(asr_model="base.en", affect="auto", llm="auto", llm_model=None) -> Pipeline:
    from .asr import WhisperASR
    from .affect import make_affect
    from .llm import make_llm
    from .tts import KokoroTTS
    chat = make_llm(llm, model=llm_model)
    return Pipeline(WhisperASR(asr_model), make_affect(affect), chat, KokoroTTS())
