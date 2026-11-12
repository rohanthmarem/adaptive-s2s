"""Local stimulus builders and portable JSONL manifests."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Sequence
from pathlib import Path
import subprocess
import tempfile
from urllib.error import HTTPError
from urllib.request import urlopen

import numpy as np
import soundfile as sf
import yaml

SCRIPTS = Path(__file__).with_name("scripts.yaml")
CREMA = {
    "IEO": "It's eleven o'clock",
    "ITH": "I think I have a doctor's appointment",
    "IOM": "I'm on my way to the meeting",
    "IWL": "I would like a new alarm clock",
    "TIE": "That is exactly what happened",
    "DFA": "Don't forget a jacket",
}
EMOTIONS = {
    "NEU": "neutral",
    "SAD": "sad",
    "ANG": "angry",
    "HAP": "happy",
    "FEA": "fearful",
    "DIS": "disgusted",
}


def scripts() -> dict:
    """Return the bundled canonical stimulus scripts."""
    return yaml.safe_load(SCRIPTS.read_text())


def read_manifest(path: str | Path) -> list[dict]:
    """Read a JSONL manifest and return its nonempty rows."""
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_manifest(out: str | Path, rows: list[dict]) -> Path:
    """Write rows to a portable JSONL manifest and return its path."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "manifest.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def _row(ident: str, script: dict, tier: str, speaker: str, labels: dict, license: str) -> dict:
    return dict(
        id=ident,
        path=ident + ".wav",
        script_id=script["id"],
        text=script["text"],
        tier=tier,
        speaker=speaker,
        split=script["split"],
        labels=labels,
        source_id=None,
        license=license,
        contaminated_for=[],
        topic=script.get("topic", []),
    )


def build_say(
    out: str | Path,
    *,
    voices: Sequence[str] = ("Samantha", "Daniel", "Karen"),
    rates: Sequence[int] = (150, 185, 220),
    register: bool = False,
    limit: int | None = None,
    split: str | None = None,
) -> Path:
    """Synthesize macOS voice and delivery variants and return their manifest path."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    selected = [
        s for s in scripts()["register" if register else "neutral"] if split is None or s["split"] == split
    ]
    if limit is not None:
        selected = selected[:limit]
    rows = []
    for s in selected:
        deliveries = ("casual", "neutral", "formal") if register else (None,)
        for delivery in deliveries:
            for voice in voices:
                for rate in rates:
                    text = s[delivery] if delivery else s["text"]
                    ident = f"{s['id']}_{voice}_{rate}" + (f"_{delivery}" if delivery else "")
                    labels = {"rate_wpm": rate}
                    if delivery:
                        labels["register"] = delivery
                    row = _row(
                        ident,
                        dict(s, text=text),
                        "synthetic-register" if register else "synthetic-say",
                        voice,
                        labels,
                        "macOS synthesized; debug use",
                    )
                    with tempfile.TemporaryDirectory() as tmp:
                        aiff = str(Path(tmp) / "speech.aiff")
                        subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", aiff, text], check=True)
                        subprocess.run(
                            [
                                "afconvert",
                                "-f",
                                "WAVE",
                                "-d",
                                "LEI16@16000",
                                "-c",
                                "1",
                                aiff,
                                str(out / row["path"]),
                            ],
                            check=True,
                        )
                    rows.append(row)
    return write_manifest(out, rows)


def build_derived(
    source: str | Path,
    out: str | Path,
    *,
    kind: str,
    factors: Sequence[float] = (0.8, 0.9, 1.0, 1.1, 1.25),
    limit: int | None = None,
    seed: int = 0,
) -> Path:
    """Write timing or nuisance variants and return their manifest path."""
    source, out = Path(source), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows, rng = [], np.random.default_rng(seed)
    for original in read_manifest(source)[:limit]:
        x, sr = sf.read(source.parent / original["path"], dtype="float32")
        if x.ndim > 1:
            x = x.mean(axis=1)
        variants = (
            factors
            if kind == "psola"
            else ("clean", "gain+6", "gain-6", "leading-silence", "noise30", "noise20")
        )
        for variant in variants:
            if kind == "psola":
                import parselmouth
                from parselmouth.praat import call

                if variant == 1:
                    y = x.copy()
                else:
                    y = call(
                        parselmouth.Sound(x, sampling_frequency=sr),
                        "Lengthen (overlap-add)",
                        75,
                        600,
                        float(variant),
                    ).values[0]
            elif variant == "clean":
                y = x.copy()
            elif str(variant).startswith("gain"):
                y = x * 10 ** (float(str(variant)[4:]) / 20)
            elif variant == "leading-silence":
                y = np.concatenate([np.zeros(round(sr * 0.5)), x])
            else:
                noise = rng.normal(size=len(x))
                noise *= (
                    np.sqrt(np.mean(x**2))
                    / max(np.sqrt(np.mean(noise**2)), 1e-12)
                    / 10 ** (int(str(variant)[5:]) / 20)
                )
                y = x + noise
            row = dict(
                original,
                id=f"{original['id']}_{kind}_{variant}",
                source_id=original["id"],
                labels=dict(original["labels"], **{("stretch" if kind == "psola" else "nuisance"): variant}),
            )
            row["path"] = row["id"] + ".wav"
            # Float WAV preserves gain without introducing clipping as a second nuisance.
            if kind == "nuisance" and variant == "clean":
                shutil.copyfile(source.parent / original["path"], out / row["path"])
            else:
                sf.write(out / row["path"], y, sr, subtype="FLOAT")
            rows.append(row)
    return write_manifest(out, rows)


def build_crema(
    out: str | Path,
    *,
    actors: Sequence[int] = range(1001, 1005),
    sentences: Sequence[str] = tuple(CREMA),
    emotions: Sequence[str] = ("NEU", "SAD", "ANG", "HAP"),
) -> Path:
    """Download labelled CREMA-D examples and return their manifest path."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for actor in actors:
        for sent in sentences:
            for emotion in emotions:
                ident = f"{actor}_{sent}_{emotion}_XX"
                path = out / (ident + ".wav")
                try:
                    if not path.exists():
                        with urlopen(
                            "https://media.githubusercontent.com/media/"
                            f"CheyneyComputerScience/CREMA-D/master/AudioWAV/{ident}.wav",
                            timeout=60,
                        ) as response:
                            path.write_bytes(response.read())
                except HTTPError as exc:
                    if exc.code == 404:
                        continue
                    raise
                row = _row(
                    ident,
                    dict(id=sent, text=CREMA[sent], split="dev" if actor < 1004 else "heldout"),
                    "crema-d",
                    str(actor),
                    {"emotion": EMOTIONS[emotion]},
                    "ODbL",
                )
                row["contaminated_for"] = ["emotion2vec"]
                rows.append(row)
    return write_manifest(out, rows)


def build_human(source: str | Path, out: str | Path, *, heldout_speakers: Sequence[str] = ()) -> Path:
    """Index private recordings with canonical text and return the manifest path."""
    source, out = Path(source), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    index = {}
    catalog = scripts()
    for category in ("neutral", "register", "distress"):
        for script in catalog[category]:
            index[script["id"]] = script
    rows = []
    for path in sorted(source.glob("*.wav")):
        speaker, script_id, delivery = path.stem.rsplit("_", 2)
        script = index[script_id]
        text = script.get("text", script.get(delivery))
        if text is None:
            raise ValueError(f"No canonical text for {path.name}")
        row = _row(
            path.stem,
            dict(script, text=text),
            "human",
            speaker,
            {"delivery": delivery},
            "consent required; private recording",
        )
        if delivery in ("casual", "neutral", "formal"):
            row["labels"]["register"] = delivery
        if delivery in EMOTIONS.values():
            row["labels"]["emotion"] = delivery
        row["labels"]["speaker_split"] = "heldout" if speaker in heldout_speakers else "dev"
        row["path"] = os.path.relpath(path.resolve(), out.resolve())
        rows.append(row)
    return write_manifest(out, rows)
