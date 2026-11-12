"""Standalone and embeddable evaluation CLI."""

import argparse
import json
from pathlib import Path
from collections.abc import Sequence
from . import stimuli


def _csv(value: str) -> list[str]:
    return value.split(",")


def _integers(value: str) -> tuple[int, ...]:
    return tuple(map(int, value.split(",")))


def _floats(value: str) -> tuple[float, ...]:
    return tuple(map(float, value.split(",")))


def _stimuli(args: argparse.Namespace) -> int:
    out = args.out or f"data/{args.set}"
    if args.set in ("say", "register"):
        is_register = args.set == "register"
        voices = args.voices or (("Samantha",) if is_register else ("Samantha", "Daniel", "Karen"))
        rates = args.rates or ((185,) if is_register else (150, 185, 220))
        path = stimuli.build_say(
            out, voices=voices, rates=rates, register=is_register, limit=args.limit, split=args.split
        )
    elif args.set in ("psola", "nuisance"):
        if not args.source:
            raise ValueError("--source manifest required")
        path = stimuli.build_derived(args.source, out, kind=args.set, limit=args.limit, factors=args.factors)
    elif args.set == "crema":
        path = stimuli.build_crema(out, actors=args.actors)
    else:
        if not args.source:
            raise ValueError("--source recording directory required")
        path = stimuli.build_human(args.source, out, heldout_speakers=args.heldout_speakers)
    print(path)
    return 0


def _run(args: argparse.Namespace) -> int:
    from ..pipeline import build_pipeline
    from .runner import run_eval

    pipeline = build_pipeline(
        asr_model=args.asr_model, affect=args.affect, llm=args.llm, llm_model=args.llm_model
    )
    rows = run_eval(
        args.manifest,
        args.out,
        pipeline,
        arms=args.arms,
        track=args.track,
        seeds=args.seeds,
        shuffled=args.shuffled,
        oracle=args.oracle,
        synthesize=not args.no_tts,
        limit=args.limit,
    )
    print(f"{len(rows)} traces in {args.out}")
    return 0


def _report(args: argparse.Namespace) -> int:
    from .report import build_report

    build_report(args.run)
    print(Path(args.run) / "report.md")
    return 0


def _export(args: argparse.Namespace) -> int:
    from .ratings import export_sheet

    rows = stimuli.read_manifest(Path(args.run) / "traces.jsonl")
    key = export_sheet(rows, args.out, args.seed, args.group_label, args.arms)
    print(f"{len(key)} blinded trials in {args.out}")
    return 0


def _score(args: argparse.Namespace) -> int:
    from .ratings import score_sheet

    print(json.dumps(score_sheet(args.sheet, args.key), indent=2))
    return 0


def register(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register evaluation subcommands and return their root parser."""
    root = subparsers.add_parser("eval", help="Local causal evaluation harness")
    sub = root.add_subparsers(dest="eval_command", required=True)
    s = sub.add_parser("stimuli")
    s.set_defaults(func=_stimuli)
    s.add_argument(
        "--set",
        required=True,
        choices=["say", "register", "psola", "nuisance", "crema", "human"],
        help="Stimulus collection to build",
    )
    s.add_argument("--source", help="Source manifest or human recording directory")
    s.add_argument("--out", help="Directory for generated stimuli")
    s.add_argument("--limit", type=int, help="Maximum number of source scripts or recordings")
    s.add_argument("--voices", type=_csv, help="Comma-separated macOS voice names")
    s.add_argument("--rates", type=_integers, help="Comma-separated speaking rates in words per minute")
    s.add_argument(
        "--factors",
        type=_floats,
        default=(0.8, 0.9, 1, 1.1, 1.25),
        help="Comma-separated duration factors for PSOLA",
    )
    s.add_argument(
        "--actors", type=_integers, default=tuple(range(1001, 1005)), help="Comma-separated CREMA-D actor IDs"
    )
    s.add_argument("--heldout-speakers", type=_csv, default=(), help="Comma-separated held-out speaker IDs")
    s.add_argument("--split", choices=["dev", "heldout"], help="Canonical script split to include")
    r = sub.add_parser("run")
    r.set_defaults(func=_run)
    r.add_argument("--manifest", required=True, help="Input stimulus JSONL manifest")
    r.add_argument("--out", required=True, help="Directory for traces and reply audio")
    r.add_argument(
        "--arms",
        nargs="+",
        default=["static", "text-only", "voice-only", "full"],
        help="Evaluation arms to run",
    )
    r.add_argument("--track", choices=["locked", "e2e"], default="locked", help="Transcript evaluation track")
    r.add_argument("--seeds", type=_integers, default=(0,), help="Comma-separated generation seeds")
    r.add_argument("--shuffled", action="store_true", help="Include the shuffled-feature full arm")
    r.add_argument("--oracle", action="store_true", help="Include the emotion-label oracle full arm")
    r.add_argument("--no-tts", action="store_true", help="Skip reply speech synthesis")
    r.add_argument("--limit", type=int, help="Maximum number of input stimuli")
    r.add_argument("--asr-model", default="base.en", help="Whisper model name")
    r.add_argument("--llm", default="auto", help="Language model backend")
    r.add_argument("--llm-model", help="Language model name or path")
    r.add_argument("--affect", default="auto", help="Affect analysis backend")
    p = sub.add_parser("report")
    p.set_defaults(func=_report)
    p.add_argument("--run", required=True, help="Run directory to summarize")
    p = sub.add_parser("ratings-export")
    p.set_defaults(func=_export)
    p.add_argument("--run", required=True, help="Run directory containing traces")
    p.add_argument("--out", required=True, help="Directory for the blinded sheet and key")
    p.add_argument("--seed", type=int, default=0, help="Seed for trial ordering and IDs")
    p.add_argument(
        "--group-label",
        choices=["emotion", "stretch", "rate_wpm"],
        default="emotion",
        help="Delivery label used to match and swap replies",
    )
    p.add_argument("--arms", nargs="+", help="Arm labels to include in trials")
    p = sub.add_parser("ratings-score")
    p.set_defaults(func=_score)
    p.add_argument("--sheet", required=True, help="Completed ratings CSV")
    p.add_argument("--key", required=True, help="Blinded trial key JSON")
    return root


def main(argv: Sequence[str] | None = None) -> int:
    """Parse evaluation arguments, run the selected command and return its exit code."""
    parser = argparse.ArgumentParser()
    register(parser.add_subparsers(required=True))
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
