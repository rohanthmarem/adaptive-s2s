"""Blinded audio-conditioned appropriateness gain trials and scoring."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
from collections.abc import Sequence
import numpy as np
from .metrics import estimate, group, avg


def _trial_group(row: dict) -> tuple:
    stimulus = row["stimulus"]
    return (row["arm_label"], stimulus["script_id"], stimulus["text"], stimulus["speaker"], row["seed"])


def export_sheet(
    rows: list[dict],
    out_dir: str | Path,
    seed: int,
    group_label: str = "emotion",
    arms: Sequence[str] | None = None,
) -> dict:
    """Export balanced blinded audio trials and return the private trial key."""
    if group_label not in ("emotion", "stretch", "rate_wpm"):
        raise ValueError("Unsupported delivery label")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "audio").mkdir(exist_ok=True)
    eligible = []
    for row in rows:
        if row.get("track") != "locked" or not row.get("output_path"):
            continue
        if group_label not in row["stimulus"]["labels"]:
            continue
        if arms is None or row["arm_label"] in arms:
            eligible.append(row)
    trials = []
    for subset in group(eligible, _trial_group).values():
        # Every delivery is balanced as user, matched reply and swapped reply.
        subset = sorted(subset, key=lambda row: str(row["stimulus"]["labels"][group_label]))
        for index, user in enumerate(subset):
            delivery = user["stimulus"]["labels"][group_label]
            alternatives = [row for row in subset if row["stimulus"]["labels"][group_label] != delivery]
            if not alternatives:
                continue
            swapped = alternatives[index % len(alternatives)]
            trials.append((user, user, "matched"))
            trials.append((user, swapped, "swapped"))
    rng = np.random.default_rng(seed)
    rng.shuffle(trials)
    key = {}
    with (out / "ratings_sheet.csv").open("w", newline="") as stream:
        fields = ["trial_id", "user_audio", "reply_audio", "reply_text", "rating", "rater"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for user, reply, kind in trials:
            trial = rng.bytes(12).hex()
            paths = {}
            for name, source in [("user", user["input_path"]), ("reply", reply["output_path"])]:
                target = out / "audio" / f"{trial}_{name}.wav"
                shutil.copyfile(source, target)
                paths[name] = str(target.relative_to(out))
            writer.writerow(
                dict(
                    trial_id=trial,
                    user_audio=paths["user"],
                    reply_audio=paths["reply"],
                    reply_text=reply["reply_text"],
                    rating="",
                    rater="",
                )
            )
            key[trial] = dict(
                arm=user["arm_label"],
                kind=kind,
                script=user["stimulus"]["script_id"],
                user_delivery=user["stimulus"]["labels"][group_label],
                reply_delivery=reply["stimulus"]["labels"][group_label],
            )
    (out / "ratings_key.json").write_text(json.dumps(key, indent=2))
    return key


def _rating_mean(rows: list[dict]) -> float | None:
    return avg(rows, lambda row: row["rating"])


def _kind_mean(rows: list[dict], kind: str) -> float | None:
    return _rating_mean([row for row in rows if row["kind"] == kind])


def _gain(rows: list[dict]) -> float | None:
    matched = _kind_mean(rows, "matched")
    swapped = _kind_mean(rows, "swapped")
    return matched - swapped if matched is not None and swapped is not None else None


def score_sheet(sheet_csv: str | Path, key_json: str | Path) -> dict:
    """Score completed trials and return per-arm ratings, gain estimates and warnings."""
    key = json.loads(Path(key_json).read_text())
    rows = []
    with Path(sheet_csv).open(newline="") as stream:
        for row in csv.DictReader(stream):
            if not row["rating"].strip():
                continue
            rating = float(row["rating"])
            if not 1 <= rating <= 7 or not row["rater"].strip():
                raise ValueError("Ratings need a rater and a score from 1 to 7")
            trial = key[row["trial_id"]]
            rows.append(
                dict(
                    trial,
                    trial_id=row["trial_id"],
                    rating=rating,
                    rater=row["rater"],
                    stimulus={"script_id": trial["script"]},
                )
            )
    if len({(row["trial_id"], row["rater"]) for row in rows}) != len(rows):
        raise ValueError("Duplicate rating by the same rater on one trial")
    result = {}
    for arm in sorted({trial["arm"] for trial in key.values()}):
        subset = [row for row in rows if row["arm"] == arm]
        counts = {}
        for trial_id, trial in key.items():
            if trial["arm"] == arm:
                counts[trial_id] = sum(row["trial_id"] == trial_id for row in subset)
        matched = [row for row in subset if row["kind"] == "matched"]
        swapped = [row for row in subset if row["kind"] == "swapped"]
        warnings = ["Fewer than 3 ratings per trial"] if any(n < 3 for n in counts.values()) else []
        result[arm] = dict(
            matched=estimate(matched, _rating_mean),
            swapped=estimate(swapped, _rating_mean),
            gain=estimate(subset, _gain),
            n_ratings=len(subset),
            n_raters=len({row["rater"] for row in subset}),
            warnings=warnings,
        )
    return result
