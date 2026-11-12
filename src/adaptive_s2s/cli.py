"""Command-line entry point for local speech conversations."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import urllib.request
from .audio import load_audio, play, record_until_enter
from .pipeline import build_pipeline, Session
from .types import ARMS, StyleState, to_dict
from .tts import CACHE

DEFAULT_MLX = "mlx-community/Qwen2.5-7B-Instruct-4bit"


def fmt(value, digits: int = 2, unit: str = "") -> str:
    """Format a measurement that may be missing."""
    return "n/a" if value is None else f"{value:.{digits}f}{unit}"


def print_summary(r) -> None:
    a = r.acoustic
    print(f"Turn {r.turn} [{r.arm}] heard: {r.transcript.text}")
    pace = f"{fmt(a.articulation_rate_sps)} syll/s, pauses {fmt(a.pause_fraction and a.pause_fraction * 100, 0)}%"
    print(f"  Pace: {pace}" + ("" if a.valid else f" (not trusted: {a.invalid_reason})"))
    emotion = f"{r.affect.top_label} {fmt(r.affect.top_score)}" if r.affect.available else f"unknown ({r.affect.note})"
    print(f"  Emotion model: {emotion}")
    print(f"  State: register {r.state_after.register}, support {r.state_after.support:.2f}, "
          f"pace estimate {fmt(r.state_after.rate.value)} syll/s")
    for line in r.controls.rationale:
        print(f"  - {line}")
    stub = "  ** STUB reply, not a model **" if r.llm["stub"] else ""
    print(f"  LLM: {r.llm['backend']} model={r.llm['model']} STUB={r.llm['stub']}{stub}")
    print(f"  Reply: {r.reply_text}")
    rate = r.output_acoustic.articulation_rate_sps if r.output_acoustic else None
    realised = r.tts.get("realised_speed")
    print(f"  Speed: requested {r.controls.voice.speed:.2f}x, realised "
          f"{fmt(realised)}{'x' if realised is not None else ''} ({fmt(rate)} syll/s)")
    print("  Timings: " + ", ".join(f"{k}={v:.2f}s" for k, v in r.timings_s.items()))


def cached(repo) -> bool:
    from .asr import cached_model_path
    try:
        cached_model_path(repo)
        return True
    except (OSError, ValueError, RuntimeError):
        return False


def doctor(args) -> int:
    from .llm import make_llm
    from .affect import make_affect, Emotion2VecAffect
    from faster_whisper.utils import _MODELS
    missing = False
    whisper_repo = _MODELS.get(args.asr_model, args.asr_model)
    ready = Path(args.asr_model).is_dir() or cached(whisper_repo)
    print(f"ASR: faster-whisper {args.asr_model}; cached={ready}")
    missing |= not ready
    emotion = make_affect(args.affect)
    if isinstance(emotion, Emotion2VecAffect):
        ready = cached(emotion.model)
        print(f"Affect: emotion2vec {emotion.model}; cached={ready}")
        missing |= not ready
    else:
        print(f"Affect: off ({emotion.note})")
    try:
        chat = make_llm(args.llm, model=args.llm_model)
        model = args.llm_model or getattr(chat, "model", None)
        stub = chat.__class__.__name__ == "TemplateChat"
        ready = (Path(model).is_dir() or cached(model)) if chat.__class__.__name__ == "MLXChat" else True
        print(f"LLM: {chat.__class__.__name__}; model={model}; cached/configured={ready}; STUB={stub}")
        missing |= not ready
    except (RuntimeError, ValueError) as exc:
        print(f"LLM: unavailable: {exc}")
        missing = True
    for name in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
        ready = (CACHE / name).is_file()
        print(f"TTS: Kokoro {CACHE / name}; present={ready}")
        missing |= not ready
    return int(missing)


def fetch_models(args) -> int:
    from huggingface_hub import snapshot_download
    from faster_whisper.utils import download_model
    CACHE.mkdir(parents=True, exist_ok=True)
    for name in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
        dest = CACHE / name
        if not dest.is_file():
            temp = dest.with_suffix(".download")
            urllib.request.urlretrieve(
                "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/" + name, temp)
            temp.replace(dest)
    download_model(args.asr_model)
    snapshot_download(args.llm_model or DEFAULT_MLX)
    if args.affect != "off" and importlib.util.find_spec("funasr"):
        snapshot_download("emotion2vec/emotion2vec_plus_base")
    return 0


def calibrate_tts(args) -> int:
    """Measure the speed Kokoro really produces for each setting and save the table for this voice."""
    from .tts import KokoroTTS, calibration_path, measure_speed_calibration
    table = measure_speed_calibration(KokoroTTS(calibrate=False), args.voice)
    for requested, realised in table:
        print(f"engine speed {requested:.2f} -> measured {realised:.3f}x")
    path = calibration_path(args.voice)
    path.write_text(json.dumps(table), encoding="utf-8")
    print(f"Saved {path}")
    return 0


def run_turn(args) -> int:
    pipeline = build_pipeline(args.asr_model, args.affect, args.llm, args.llm_model)
    pipeline.warm()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    audio, sr = load_audio(args.input)
    result, _ = pipeline.turn(audio, sr, StyleState(), arm=ARMS[args.arm], seed=args.seed,
                              locked_text=args.locked_text, input_path=args.input,
                              out_path=out / "reply.wav", measure_reference=True)
    (out / "trace.json").write_text(json.dumps(to_dict(result), indent=2), encoding="utf-8")
    print_summary(result)
    if args.play:
        play(result.output_path)
    return 0


def converse(args) -> int:
    session = Session(build_pipeline(args.asr_model, args.affect, args.llm, args.llm_model), args.out_dir)
    session.pipeline.warm()
    for path in args.inputs:
        result = session.turn(path, arm=ARMS[args.arm], seed=args.seed, locked_text=args.locked_text,
                              measure_reference=True)
        print_summary(result)
        if args.play:
            play(result.output_path)
    return 0


def talk(args) -> int:
    session = Session(build_pipeline(args.asr_model, args.affect, args.llm, args.llm_model), args.out_dir)
    print("Loading models...")
    session.pipeline.warm()
    try:
        while True:
            input("Press Enter to start (Ctrl-C to end): ")
            audio = record_until_enter()
            result = session.turn(audio, 16000, arm=ARMS[args.arm], seed=args.seed, locked_text=args.locked_text)
            print_summary(result)
            play(result.output_path)
    except (KeyboardInterrupt, EOFError):
        print("\nConversation ended.")
    return 0


def common(parser, out="out/turn"):
    parser.add_argument("--out-dir", default=out)
    parser.add_argument("--arm", choices=list(ARMS), default="full")
    parser.add_argument("--llm", choices=["auto", "mlx", "openai", "template"], default="auto")
    parser.add_argument("--llm-model")
    parser.add_argument("--affect", choices=["auto", "off", "emotion2vec"], default="auto")
    parser.add_argument("--asr-model", default="base.en")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--locked-text")
    parser.add_argument("--play", action="store_true")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="s2s")
    subparsers = parser.add_subparsers(dest="command", required=True)
    p = subparsers.add_parser("doctor")
    common(p)
    p.set_defaults(func=doctor)
    p = subparsers.add_parser("fetch-models")
    common(p)
    p.set_defaults(func=fetch_models)
    p = subparsers.add_parser("turn")
    common(p)
    p.add_argument("input")
    p.set_defaults(func=run_turn)
    p = subparsers.add_parser("converse")
    common(p, "out/session")
    p.add_argument("inputs", nargs="+")
    p.set_defaults(func=converse)
    p = subparsers.add_parser("talk")
    common(p, "out/talk")
    p.set_defaults(func=talk)
    p = subparsers.add_parser("calibrate-tts")
    p.add_argument("--voice", default="af_heart")
    p.set_defaults(func=calibrate_tts)
    from .demo import run_demo
    p = subparsers.add_parser("demo")
    common(p, "out/demo")
    p.add_argument("--compare-static", action="store_true")
    p.set_defaults(func=run_demo)
    try:
        from adaptive_s2s.evals.cli import register as register_evals
        register_evals(subparsers)
    except ImportError:
        pass
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"s2s: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
