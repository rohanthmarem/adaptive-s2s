"""Turns a run's traces into `summary.json` and a readable `report.md`.

The report leads with the warnings that limit what the run can claim, then the headline question,
then only the sections that apply to this run. Every number carries its n and a confidence interval.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from . import metrics
from .stimuli import read_manifest

Estimate = dict  # {"value", "ci", "n_rows", "n_clusters"}

SPEED_MEASURES = {
    "realised_speed": "Measured reply speed (x neutral) per syll/s of user pace",
    "realised_rate": "Measured reply rate (syll/s) per syll/s of user pace",
    "requested_speed": "Requested speed per syll/s of user pace",
}
REGISTER_MEASURES = {
    "contractions_per_100": "Contractions per 100 words",
    "slang": "Slang and casual words per reply",
    "formal_markers": "Formal markers per reply",
    "mean_sentence_len": "Words per sentence",
}


def collect_warnings(rows: list[dict]) -> list[str]:
    """The limits on what this run can claim. These go at the top of the report."""
    warnings = []
    if any(r.get("llm", {}).get("stub") for r in rows):
        warnings.append("A stub reply model was used. This run checks the wiring only.")
    if rows and all(r["stimulus"]["tier"].startswith("synthetic") for r in rows):
        warnings.append("All stimuli are synthetic voices. This is a smoke run, not a result on human speech.")
    for row in rows:
        model = str(row.get("affect", {}).get("model") or "").lower()
        if any(name.lower() in model for name in row["stimulus"].get("contaminated_for", [])):
            warnings.append("These stimuli are in the emotion model's training data, so its readings here are in-distribution.")
            break
    if len({r["stimulus"]["script_id"] for r in rows}) < 8:
        warnings.append("Fewer than 8 scripts. The confidence intervals are fragile.")
    if not any(r["stimulus"]["split"] == "heldout" for r in rows):
        warnings.append("No held-out stimuli. Nothing here shows generalisation.")
    return warnings


def compute(rows: list[dict]) -> dict:
    """Every metric, as nested dicts of estimates."""
    return {
        "rate_dose_response": metrics.rate_dose_response(rows),
        "register_accommodation": metrics.register_accommodation(rows),
        "support_response": metrics.support_response(rows),
        "task_preservation": metrics.task_preservation(rows),
        "noise_floor": metrics.noise_floor(rows),
        "nuisance_invariance": metrics.nuisance_invariance(rows),
        "latency": metrics.latency(rows),
        "asr_summary": metrics.asr_summary(rows),
        "LSM-lite": metrics.lsm_summary(rows),
    }


# --- formatting -------------------------------------------------------------------------------------


def _is_estimate(value) -> bool:
    return isinstance(value, dict) and "value" in value and "n_rows" in value


def _leaves(value, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Estimate]]:
    """Walk nested dicts and yield (path, estimate) for every estimate that has data."""
    if _is_estimate(value):
        if value["n_rows"] and value["value"] is not None:
            yield path, value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _leaves(child, path + (str(key),))


def _num(x: float | None, digits: int = 2) -> str:
    return "n/a" if x is None else f"{x:.{digits}f}"


def _ci(est: Estimate, digits: int = 2) -> str:
    return "n/a" if est["ci"] is None else f"{_num(est['ci'][0], digits)} to {_num(est['ci'][1], digits)}"


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return lines + [""]


def _generic_section(title: str, note: str, data: dict, digits: int = 2) -> list[str]:
    rows = [
        [" / ".join(path), _num(est["value"], digits), _ci(est, digits), str(est["n_rows"]), str(est["n_clusters"])]
        for path, est in _leaves(data)
    ]
    if not rows:
        return []
    return [f"## {title}", "", note, ""] + _table(["Measure", "Value", "95% CI", "n", "Scripts"], rows)


def _pace_section(data: dict) -> list[str]:
    """The headline: does the reply's speed follow the speaker's pace, and only in the adaptive arms?"""
    # Only measurements of the generated audio count here. A run without synthesis has no headline.
    measured = ("realised_speed", "realised_rate")
    measure = next((m for m in measured if any(_leaves({a: d.get(m, {}).get("slope") for a, d in data.items()}))), None)
    if measure is None:
        return []
    rows, verdicts = [], []
    for arm, per_arm in data.items():
        slope = per_arm.get(measure, {}).get("slope")
        if not slope or slope["value"] is None or not slope["n_rows"]:
            continue
        rows.append([f"`{arm}`", _num(slope["value"], 3), _ci(slope, 3), str(slope["n_rows"]), str(slope["n_clusters"])])
        if slope["ci"] is not None:
            excludes_zero = slope["ci"][0] > 0 or slope["ci"][1] < 0
            verdicts.append(f"- `{arm}`: the interval {'excludes' if excludes_zero else 'includes'} zero.")
    if not rows:
        return []
    return [
        "## Headline: does the reply follow the speaker's pace?",
        "",
        f"Slope of: {SPEED_MEASURES[measure].lower()}. Words are identical across deliveries on the locked track, "
        "so a slope above zero came through the audio. Expected shape: adaptive voice arms above zero, "
        "`static` and `full+shuffled` near zero.",
        "",
    ] + _table(["Arm", "Slope", "95% CI", "n", "Scripts"], rows) + verdicts + [""]


def _register_section(data: dict) -> list[str]:
    rows = []
    for arm, per_arm in data.items():
        for key, label in REGISTER_MEASURES.items():
            est = per_arm.get("casual_minus_formal", {}).get(key)
            if est and est["n_rows"] and est["value"] is not None:
                rows.append([f"`{arm}`", label, _num(est["value"]), _ci(est), str(est["n_rows"]), str(est["n_clusters"])])
    if not rows:
        return []
    lines = [
        "## Register: does the wording follow the user's register?",
        "",
        "Each value is replies to casual wording minus replies to formal wording of the same request. An "
        "arm that ignores register sits near zero. An adaptive arm should show more contractions and fewer "
        "formal markers for casual input.",
        "",
    ] + _table(["Arm", "Measure", "Casual minus formal", "95% CI", "n", "Scripts"], rows)
    caricature = [
        [f"`{arm}`", f"{est['value']:.0%}", str(est["n_rows"])]
        for arm, per_arm in data.items()
        if (est := per_arm.get("caricature_rate")) and est["n_rows"] and est["value"] is not None
    ]
    if caricature:
        lines += ["Caricature rate: share of replies with slang when the user used none. It should stay at zero.", ""]
        lines += _table(["Arm", "Caricature rate", "n"], caricature)
    return lines


def _run_line(run: Path, rows: list[dict], tiers: list[str]) -> str:
    config = {}
    if (run / "config.json").is_file():
        config = json.loads((run / "config.json").read_text(encoding="utf-8"))
    llms = sorted({str(r.get("llm", {}).get("model") or r.get("llm", {}).get("backend")) for r in rows})
    parts = [
        f"{len(rows)} traces",
        f"{len({r['stimulus']['id'] for r in rows})} stimuli from {len({r['stimulus']['script_id'] for r in rows})} scripts",
        f"tiers: {', '.join(tiers)}",
        f"track: {config.get('track', 'unknown')}",
        f"seeds: {config.get('seeds', 'unknown')}",
        f"reply model: {', '.join(llms)}",
        f"commit: {str(config.get('git_commit'))[:8]}",
    ]
    return "**Run:** " + "; ".join(parts) + "."


def build_report(run_dir) -> dict:
    """Compute every metric for a run and write `summary.json` and `report.md`. Returns the summary."""
    run = Path(run_dir)
    rows = read_manifest(run / "traces.jsonl")
    tiers = sorted({r["stimulus"]["tier"] for r in rows})
    result = {"warnings": collect_warnings(rows), "tiers": tiers, **compute(rows)}
    (run / "summary.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")

    lines = [f"# Evaluation report: {run.name}", ""]
    lines += [f"> **Warning:** {w}" for w in result["warnings"]]
    lines += ["", _run_line(run, rows, tiers), ""]
    lines += _pace_section(result["rate_dose_response"])
    lines += _register_section(result["register_accommodation"])
    lines += _generic_section(
        "Support response",
        "By delivery or script: share of turns in supportive mode, share of replies that open with an "
        "acknowledgment, and the requested speed.",
        result["support_response"],
    )
    lines += _generic_section(
        "Nuisance invariance",
        "Change in the controls when only the recording conditions change (gain, leading silence, noise). "
        "Everything here should be near zero.",
        result["nuisance_invariance"],
        digits=3,
    )
    lines += _generic_section(
        "Noise floor",
        "Variation across seeds for identical input: spread of the reply rate, and word overlap between replies.",
        result["noise_floor"],
    )
    lines += _generic_section(
        "On-topic check (crude proxy)",
        "Share of replies that mention a topic word of the request. Human ratings replace this for real results.",
        result["task_preservation"],
    )
    lines += _generic_section(
        "Speech recognition", "Word error rate against the script, end-to-end track only.", result["asr_summary"]
    )
    lines += _generic_section("Latency (seconds)", "Per stage, median and 95th percentile.", result["latency"])
    lines += _generic_section(
        "All pace measures",
        "Slope, intercept and correlation for every pace measure and arm.",
        result["rate_dose_response"],
        digits=3,
    )
    lines += _generic_section(
        "LSM-lite (descriptive only)",
        "Function-word matching between user and reply, from short open word lists. It is not the LIWC "
        "dictionary and it does not measure slang.",
        result["LSM-lite"],
    )
    lines += [
        "## How to read this",
        "",
        "- Single-turn experiments start from an empty state, so turns are independent.",
        "- Intervals are 95% percentile bootstrap intervals over 1000 resamples of whole scripts.",
        "- The human-rated appropriateness gain (`s2s eval ratings-export`) is the headline for real results.",
        "",
    ]
    (run / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return result
