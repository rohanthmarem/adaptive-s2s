"""Pure trace metrics with uncertainty from a cluster bootstrap.

Clusters are resampled with replacement, whole clusters at a time, 1000 times
using a seeded random generator. The interval runs from the 2.5th to the 97.5th
percentile of the finite bootstrap statistics.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterator
from functools import lru_cache, partial
from itertools import combinations

import numpy as np

from ..register import style_counts as _style_counts
from ..textutil import sentences, tokens

# Replies repeat across bootstrap draws; cache only the pure lexical measurement.
style_counts = lru_cache(maxsize=8192)(_style_counts)


def group(rows: list[dict], key: Callable) -> dict:
    """Group rows by key and return a dictionary of row lists."""
    result = defaultdict(list)
    for row in rows:
        result[key(row)].append(row)
    return dict(result)


def _cluster_id(row: dict, cluster: str) -> str:
    return row.get("stimulus", {}).get(cluster, row.get(cluster, "unknown"))


def cluster_samples(
    rows: list[dict], *, cluster: str = "script_id", seed: int = 0, n_boot: int = 1000
) -> Iterator[list[dict]]:
    """Yield seeded bootstrap samples, preserving every row in each drawn cluster."""
    groups = group(rows, partial(_cluster_id, cluster=cluster))
    values = list(groups.values())
    rng = np.random.default_rng(seed)
    for _ in range(n_boot):
        sample = []
        if values:
            for index in rng.integers(0, len(values), len(values)):
                sample.extend(values[index])
        yield sample


def estimate(rows: list[dict], statistic: Callable, *, cluster: str = "script_id", seed: int = 0) -> dict:
    """Return the statistic, bootstrap interval, row count and cluster count."""
    value = statistic(rows) if rows else None
    samples = []
    if rows:
        for sample in cluster_samples(rows, cluster=cluster, seed=seed):
            measured = statistic(sample)
            if measured is not None and np.isfinite(measured):
                samples.append(measured)
    interval = list(map(float, np.percentile(samples, [2.5, 97.5]))) if samples else None
    clusters = {_cluster_id(row, cluster) for row in rows}
    return dict(value=value, ci=interval, n_rows=len(rows), n_clusters=len(clusters))


def avg(rows: list[dict], fn: Callable) -> float | None:
    """Return the mean of a row measurement, or None for an empty list."""
    return float(np.mean([fn(row) for row in rows])) if rows else None


def _arm_label(row: dict) -> str:
    return row.get("arm_label", row.get("arm", "unknown"))


def arms(rows: list[dict]) -> dict:
    """Return rows grouped by evaluation arm label."""
    return group(rows, _arm_label)


def speed(row: dict) -> float:
    """Return the requested voice speed in a trace."""
    return row["controls"]["voice"]["speed"]


def _realised_speed(row: dict) -> float | None:
    return row.get("tts", {}).get("realised_speed")


def _realised_rate(row: dict) -> float | None:
    output = row.get("output_acoustic") or {}
    return output.get("articulation_rate_sps") if output.get("valid") else None


def _fit(rows: list[dict], y: Callable) -> tuple:
    x = np.array([row["acoustic"]["articulation_rate_sps"] for row in rows])
    values = np.array([y(row) for row in rows])
    if len(x) < 2 or np.ptp(x) == 0:
        return None, None, None
    centered_x = x - x.mean()
    slope = float(np.sum(centered_x * (values - values.mean())) / np.sum(centered_x**2))
    intercept = float(values.mean() - slope * x.mean())
    correlation = float(np.corrcoef(x, values)[0, 1]) if np.ptp(values) else None
    return slope, intercept, correlation


def _fit_component(rows: list[dict], y: Callable, component: int) -> float | None:
    return _fit(rows, y)[component]


def rate_dose_response(rows: list[dict], *, cluster: str = "script_id") -> dict:
    """Return three response regressions against input articulation rate for each arm."""
    result = {}
    measures = [("realised_speed", _realised_speed), ("realised_rate", _realised_rate)]
    measures.append(("requested_speed", speed))
    for arm, arm_rows in arms(rows).items():
        result[arm] = {}
        for name, measure in measures:
            valid = []
            for row in arm_rows:
                acoustic = row.get("acoustic", {})
                if not acoustic.get("valid") or acoustic.get("articulation_rate_sps") is None:
                    continue
                if measure(row) is not None:
                    valid.append(row)
            fits = {}
            for component, label in enumerate(("slope", "intercept", "pearson_r")):
                statistic = partial(_fit_component, y=measure, component=component)
                fits[label] = estimate(valid, statistic, cluster=cluster)
            result[arm][name] = fits
    return result


def _style_mean(rows: list[dict], metric: str) -> float | None:
    return avg(rows, lambda row: style_counts(row["reply_text"])[metric])


def _register_diff(rows: list[dict], metric: str) -> float | None:
    casual = []
    formal = []
    for row in rows:
        label = row["stimulus"]["labels"]["register"]
        if label == "casual":
            casual.append(row)
        elif label == "formal":
            formal.append(row)
    if not casual or not formal:
        return None
    return _style_mean(casual, metric) - _style_mean(formal, metric)


def _has_slang(text: str) -> bool:
    counts = style_counts(text)
    return any(counts[metric] for metric in ("slang", "reductions"))


def _caricature(row: dict) -> float:
    return float(_has_slang(row["reply_text"]))


def register_accommodation(rows: list[dict], *, cluster: str = "script_id") -> dict:
    """Return lexical style estimates, register contrasts and caricature rates per arm."""
    result = {}
    metrics = ("contractions_per_100", "slang", "formal_markers", "mean_sentence_len")
    for arm, arm_rows in arms(rows).items():
        labelled = [row for row in arm_rows if "register" in row["stimulus"]["labels"]]
        by_label = group(labelled, lambda row: row["stimulus"]["labels"]["register"])
        summaries = {}
        for label, subset in by_label.items():
            summaries[label] = {}
            for metric in metrics:
                statistic = partial(_style_mean, metric=metric)
                summaries[label][metric] = estimate(subset, statistic, cluster=cluster)
        both = by_label.get("casual", []) + by_label.get("formal", [])
        differences = {}
        for metric in metrics:
            statistic = partial(_register_diff, metric=metric)
            differences[metric] = estimate(both, statistic, cluster=cluster)
        eligible = [row for row in arm_rows if not _has_slang(row["stimulus"]["text"])]
        result[arm] = dict(
            by_register=summaries,
            casual_minus_formal=differences,
            caricature_rate=estimate(eligible, partial(avg, fn=_caricature), cluster=cluster),
        )
    return result


FUNCTION_WORDS = [
    "i me my mine we us our ours you your yours he him his she her hers they them their theirs",
    "it its this that these those something anything everything nothing",
    "a an the",
    "am is are was were be been being have has had do does did can could will "
    "would shall should may might must",
    "very really quite just also too so now then often always never here there",
    "in on at to from with by for of about over under through between into without",
    "and or but because if while although nor yet",
    "no not never neither nobody cannot don't can't won't isn't aren't didn't",
    "all some any many much few several most each every both enough more less",
]


def lsm_lite(user_text: str, reply_text: str) -> float:
    """Return lexical style similarity using nine open word lists rather than LIWC."""
    user_words, reply_words = tokens(user_text), tokens(reply_text)
    scores = []
    for category in FUNCTION_WORDS:
        words = set(category.split())
        p = sum(word in words for word in user_words) / max(len(user_words), 1)
        q = sum(word in words for word in reply_words) / max(len(reply_words), 1)
        scores.append(1 - abs(p - q) / (p + q + 0.0001))
    return float(np.mean(scores))


def _lsm(row: dict) -> float:
    return lsm_lite(row["stimulus"]["text"], row["reply_text"])


def lsm_summary(rows: list[dict], *, cluster: str = "script_id") -> dict:
    """Return bootstrap lexical style similarity estimates for each arm."""
    result = {}
    for arm, arm_rows in arms(rows).items():
        result[arm] = estimate(arm_rows, partial(avg, fn=_lsm), cluster=cluster)
    return result


ACKNOWLEDGMENT_CUES = [
    "sorry",
    "that sounds",
    "it sounds",
    "sounds like",
    "i hear",
    "i understand",
    "that must",
    "hard",
    "tough",
    "difficult",
    "here for you",
    "rough",
]
# Retain the old exported name for callers that imported it.
ACK = tuple(ACKNOWLEDGMENT_CUES)


def _acknowledgment(row: dict) -> float:
    reply_sentences = sentences(row["reply_text"])
    first = reply_sentences[0].lower() if reply_sentences else ""
    return float(any(cue in first for cue in ACKNOWLEDGMENT_CUES))


def _supportive(row: dict) -> float:
    return float(row["controls"]["text"]["supportive"])


def support_response(rows: list[dict], *, cluster: str = "script_id") -> dict:
    """Return support, first-sentence acknowledgment and speed estimates by delivery."""
    eligible = []
    for row in rows:
        stimulus = row["stimulus"]
        if (
            "emotion" in stimulus["labels"]
            or stimulus["script_id"].startswith("d")
            or row.get("register", {}).get("distress_hits")
        ):
            eligible.append(row)
    result = {}
    measures = [("supportive", _supportive), ("acknowledgment", _acknowledgment)]
    measures.append(("requested_speed", speed))
    for arm, arm_rows in arms(eligible).items():
        by_delivery = group(
            arm_rows, lambda row: row["stimulus"]["labels"].get("emotion", row["stimulus"]["script_id"])
        )
        result[arm] = {}
        for label, subset in by_delivery.items():
            result[arm][label] = {}
            for name, measure in measures:
                result[arm][label][name] = estimate(subset, partial(avg, fn=measure), cluster=cluster)
    return result


def _topic_preserved(row: dict) -> float:
    for token in tokens(row["reply_text"]):
        for stem in row["stimulus"].get("topic", []):
            if token.startswith(stem):
                return 1.0
    return 0.0


def task_preservation(rows: list[dict], *, cluster: str = "script_id") -> dict:
    """Return each arm's share of replies retaining a topic stem."""
    result = {}
    for arm, arm_rows in arms(rows).items():
        eligible = [row for row in arm_rows if row["stimulus"].get("topic", [])]
        result[arm] = estimate(eligible, partial(avg, fn=_topic_preserved), cluster=cluster)
    return result


def _field_mean(rows: list[dict], field: str) -> float | None:
    return avg(rows, lambda row: row[field])


def noise_floor(rows: list[dict], *, cluster: str = "script_id") -> dict:
    """Return repeated-seed rate variation and reply token overlap per arm."""
    pairs = []
    grouped = group(rows, lambda row: (row["stimulus"]["id"], row["arm_label"]))
    for (_, arm), subset in grouped.items():
        if len({row["seed"] for row in subset}) < 2:
            continue
        rates = []
        for row in subset:
            rate = _realised_rate(row)
            if rate is not None:
                rates.append(rate)
        word_sets = [set(tokens(row["reply_text"])) for row in subset]
        overlaps = []
        for a, b in combinations(word_sets, 2):
            overlaps.append(len(a & b) / len(a | b) if a | b else 1.0)
        pairs.append(
            dict(
                stimulus=subset[0]["stimulus"],
                arm_label=arm,
                seed=0,
                rate_sd=float(np.std(rates, ddof=1)) if len(rates) > 1 else None,
                jaccard=float(np.mean(overlaps)),
            )
        )
    result = {}
    for arm, arm_rows in arms(pairs).items():
        result[arm] = {}
        for metric in ("rate_sd", "jaccard"):
            valid = [row for row in arm_rows if row[metric] is not None]
            result[arm][metric] = estimate(valid, partial(_field_mean, field=metric), cluster=cluster)
    return result


def _field_max(rows: list[dict], field: str) -> float:
    return float(max(row[field] for row in rows))


def nuisance_invariance(rows: list[dict], *, cluster: str = "script_id") -> dict:
    """Return control changes against clean rows matched by source, arm and seed."""
    clean = {}
    for row in rows:
        stimulus = row["stimulus"]
        if stimulus["labels"].get("nuisance") == "clean":
            clean[(stimulus.get("source_id"), _arm_label(row), row["seed"])] = row
    differences = []
    for row in rows:
        stimulus = row["stimulus"]
        nuisance = stimulus["labels"].get("nuisance")
        if not nuisance or nuisance == "clean":
            continue
        source = clean.get((stimulus.get("source_id"), _arm_label(row), row["seed"]))
        if source is None:
            continue
        text, reference = row["controls"]["text"], source["controls"]["text"]
        differences.append(
            dict(
                stimulus=stimulus,
                arm_label=_arm_label(row),
                nuisance=nuisance,
                speed_delta=abs(speed(row) - speed(source)),
                register_changed=float(text["register"] != reference["register"]),
                supportive_changed=float(text["supportive"] != reference["supportive"]),
            )
        )
    result = {}
    for arm, arm_rows in arms(differences).items():
        result[arm] = {}
        for label, subset in group(arm_rows, lambda row: row["nuisance"]).items():
            result[arm][label] = {}
            for metric in ("speed_delta", "register_changed", "supportive_changed"):
                operations = {}
                for name, reducer in [("mean", _field_mean), ("max", _field_max)]:
                    operations[name] = estimate(subset, partial(reducer, field=metric), cluster=cluster)
                result[arm][label][metric] = operations
    return result


def _timing_percentile(rows: list[dict], stage: str, percentile: int) -> float:
    return float(np.percentile([row["timings_s"][stage] for row in rows], percentile))


def latency(rows: list[dict], *, cluster: str = "script_id") -> dict:
    """Return median and 95th percentile latency estimates for each timed stage."""
    stages = set()
    for row in rows:
        stages.update(row.get("timings_s", {}))
    result = {}
    for stage in sorted(stages):
        eligible = [row for row in rows if stage in row.get("timings_s", {})]
        result[stage] = {}
        for percentile in (50, 95):
            statistic = partial(_timing_percentile, stage=stage, percentile=percentile)
            result[stage][f"p{percentile}"] = estimate(eligible, statistic, cluster=cluster)
    return result


def asr_summary(rows: list[dict], *, cluster: str = "script_id") -> dict:
    """Return end-to-end word error rate estimates grouped by stimulus tier."""
    eligible = [row for row in rows if row.get("track") == "e2e" and row.get("wer") is not None]
    result = {}
    for tier, subset in group(eligible, lambda row: row["stimulus"]["tier"]).items():
        result[tier] = estimate(subset, partial(_field_mean, field="wer"), cluster=cluster)
    return result
