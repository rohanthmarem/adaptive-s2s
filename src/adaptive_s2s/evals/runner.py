"""Independent-turn ablations with append-only, resumable traces."""

from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Sequence
import numpy as np
from ..audio import load_audio, resample
from ..acoustic import measure
from ..config import DEFAULT_POLICY
from ..textutil import tokens
from ..types import ARMS, AffectReading, StyleState, to_dict
from .stimuli import read_manifest


def wer(reference: str, hypothesis: str) -> float:
    """Return word error rate using token edit distance."""
    a, b = tokens(reference), tokens(hypothesis)
    previous = list(range(len(b) + 1))
    for i, word in enumerate(a, 1):
        current = [i]
        for j, other in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (word != other)))
        previous = current
    return previous[-1] / max(len(a), 1)


def derangement(n: int, seed: int = 0) -> list[int]:
    """Return a seeded permutation with no unchanged positions."""
    if n < 2:
        raise ValueError("Shuffling needs at least two stimuli")
    rng = np.random.default_rng(seed)
    order = rng.permutation(n)
    result = np.empty(n, dtype=int)
    result[order] = np.roll(order, 1)
    return result.tolist()


def _oracle(row, acoustic):
    # Only explicit emotion labels provide an oracle. Pace labels are manipulations,
    # not ground-truth articulation rates; never invent rates from say WPM.
    emotion = row["labels"].get("emotion")
    if emotion not in {"sad", "fearful", "neutral", "happy", "angry", "disgusted"}:
        return None
    return acoustic, AffectReading(
        True, "oracle-label", {emotion: 1.0}, emotion, 1.0, "Label oracle; not a model reading"
    )


def _model_info(pipeline) -> dict:
    result = {}
    for name in ("asr", "affect", "llm", "tts"):
        backend = getattr(pipeline, name, None)
        model = getattr(
            backend, "model", getattr(backend, "model_name", getattr(backend, "model_path", None))
        )
        result[name] = {"backend": type(backend).__name__, "model": str(model) if model is not None else None}
        if hasattr(backend, "voices_path"):
            result[name]["voices_path"] = str(backend.voices_path)
    return result


def run_eval(
    manifest_path: str | Path,
    out_dir: str | Path,
    pipeline: Any,
    *,
    arms: Sequence[str] = ("static", "text-only", "voice-only", "full"),
    track: str = "locked",
    seeds: Sequence[int] = (0,),
    shuffled: bool = False,
    oracle: bool = False,
    synthesize: bool = True,
    limit: int | None = None,
) -> list[dict]:
    """Run independent evaluation turns and return existing and newly appended traces."""
    if track not in ("locked", "e2e"):
        raise ValueError("track must be locked or e2e")
    manifest_path, out_dir = Path(manifest_path).resolve(), Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "audio").mkdir(exist_ok=True)
    stimuli = read_manifest(manifest_path)[:limit]
    if len({s["id"] for s in stimuli}) != len(stimuli):
        raise ValueError("Stimulus IDs must be unique")
    labels = list(arms) + (["full+shuffled"] if shuffled else []) + (["full+oracle"] if oracle else [])
    for arm in arms:
        if arm not in ARMS:
            raise ValueError(f"Unknown arm {arm}")
    trace_path = out_dir / "traces.jsonl"
    existing = read_manifest(trace_path) if trace_path.exists() else []
    done = {(r["stimulus"]["id"], r["arm_label"], r["seed"]) for r in existing}
    cfg = dict(
        manifest=str(manifest_path),
        manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        arms=labels,
        track=track,
        seeds=list(seeds),
        synthesize=synthesize,
        limit=limit,
        policy=to_dict(getattr(pipeline, "cfg", DEFAULT_POLICY)),
        models=_model_info(pipeline),
    )
    config_path = out_dir / "config.json"
    if config_path.exists():
        old = json.loads(config_path.read_text())
        if any(
            old.get(k) != cfg.get(k)
            for k in ("manifest_sha256", "track", "seeds", "arms", "synthesize", "limit", "policy", "models")
        ):
            raise ValueError("Resume configuration changed; use a new output directory")
    try:
        cfg["git_commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except subprocess.CalledProcessError:
        cfg["git_commit"] = None
    cfg["timestamp"] = datetime.now(timezone.utc).isoformat()
    cfg["counts"] = {"stimuli": len(stimuli), "traces": len(existing)}
    config_path.write_text(json.dumps(cfg, indent=2, default=str))
    trace_path.touch(exist_ok=True)
    cache = {}

    def features(i):
        if i not in cache:
            s = stimuli[i]
            x, sr = load_audio(manifest_path.parent / s["path"])
            analyser = getattr(pipeline, "affect", None)
            aff = (
                analyser.analyze(resample(x, sr, 16000))
                if analyser
                else AffectReading(False, note="No affect analyser")
            )
            cache[i] = measure(x, sr, s["text"], getattr(pipeline, "cfg", DEFAULT_POLICY)), aff
        return cache[i]

    if hasattr(pipeline, "warm"):
        pipeline.warm()
    for seed in seeds:
        permutation = derangement(len(stimuli), seed) if shuffled else None
        for i, stimulus in enumerate(stimuli):
            input_path = (manifest_path.parent / stimulus["path"]).resolve()
            for label in labels:
                if (stimulus["id"], label, seed) in done:
                    continue
                override, source = None, "measured"
                if label == "full+shuffled":
                    override, source = features(permutation[i]), "shuffled"
                elif label == "full+oracle":
                    override = _oracle(stimulus, features(i)[0])
                    if override is None:
                        continue
                    source = "oracle"
                x, sr = load_audio(input_path)
                ident = hashlib.sha256(f"{stimulus['id']}|{label}|{seed}".encode()).hexdigest()[:24]
                result, _ = pipeline.turn(
                    x,
                    sr,
                    StyleState(),
                    arm=ARMS[label.split("+")[0]],
                    history=(),
                    locked_text=stimulus["text"] if track == "locked" else None,
                    feature_override=override,
                    feature_source=source,
                    seed=seed,
                    out_path=out_dir / "audio" / f"{ident}.wav" if synthesize else None,
                    input_path=str(input_path),
                    synthesize=synthesize,
                    measure_reference=synthesize,
                )
                row = dict(to_dict(result), stimulus=stimulus, arm_label=label, seed=seed, track=track)
                if track == "e2e":
                    row["wer"] = wer(stimulus["text"], row["transcript"]["text"])
                # Make paths usable by rating exports from any working directory.
                row["input_path"] = str(input_path)
                if row.get("output_path"):
                    row["output_path"] = str(Path(row["output_path"]).resolve())
                with trace_path.open("a") as stream:
                    stream.write(json.dumps(row, default=str) + "\n")
                existing.append(row)
                done.add((stimulus["id"], label, seed))
    cfg["counts"]["traces"] = len(existing)
    observed = set()
    for row in existing:
        llm = row.get("llm", {})
        observed.add((llm.get("backend", ""), str(llm.get("model", "")), bool(llm.get("stub"))))
    cfg["observed_llms"] = []
    for backend, model, stub in sorted(observed):
        cfg["observed_llms"].append(dict(backend=backend, model=model, stub=stub))
    config_path.write_text(json.dumps(cfg, indent=2, default=str))
    return existing
