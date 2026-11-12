import copy
import csv
import json
import numpy as np
import pytest
import soundfile as sf
from adaptive_s2s.evals import metrics as m
from adaptive_s2s.evals.stimuli import build_derived, write_manifest, read_manifest
from adaptive_s2s.evals.runner import wer, derangement, run_eval
from adaptive_s2s.evals.ratings import export_sheet, score_sheet
from adaptive_s2s.evals.report import build_report


def row(i=0, arm="full", seed=0):
    return dict(
        stimulus=dict(
            id=f"s{i}",
            script_id=f"n{i}",
            text="I have the package for you",
            speaker="p1",
            split="dev",
            tier="synthetic-say",
            labels={"rate_wpm": 150},
            topic=["package"],
            contaminated_for=[],
        ),
        arm_label=arm,
        seed=seed,
        track="locked",
        acoustic=dict(valid=True, articulation_rate_sps=2 + i),
        output_acoustic=dict(valid=True, articulation_rate_sps=4 + 2 * i),
        controls=dict(voice=dict(speed=1 + i / 100), text=dict(register="neutral", supportive=False)),
        reply_text="The package is here.",
        tts={"realised_speed": 1 + i / 10},
        llm={"stub": True},
        affect={},
        timings_s={"total": 1.0},
    )


def test_slope_and_cluster_bootstrap():
    rows = [row(i) for i in range(12)]
    fit = m.rate_dose_response(rows)["full"]["realised_rate"]["slope"]
    assert fit["value"] == pytest.approx(2)
    assert fit["ci"][0] <= 2 <= fit["ci"][1]
    assert fit["n_clusters"] == 12
    clustered = [dict(row(i), stimulus=dict(row(i)["stimulus"], script_id=str(i // 2))) for i in range(8)]
    for sample in m.cluster_samples(clustered, n_boot=30):
        for rs in m.group(sample, lambda r: r["stimulus"]["script_id"]).values():
            assert len(rs) % 2 == 0
            assert sum(r["stimulus"]["id"] == rs[0]["stimulus"]["id"] for r in rs) == len(rs) // 2


def test_text_metrics():
    r = row()
    r["reply_text"] = "Bro, gonna get that package."
    assert m.register_accommodation([r])["full"]["caricature_rate"]["value"] == 1
    assert m.lsm_lite("I am in the house", "I am in the house") == 1
    assert m.lsm_lite("I am in the house", "packages arrive tomorrow") < 1
    assert m.task_preservation([r])["full"]["value"] == 1
    assert wer("one two three", "one four three five") == pytest.approx(2 / 3)
    assert wer("", "") == 0


def test_noise_and_nuisance():
    a, b = row(), row(seed=1)
    b["output_acoustic"]["articulation_rate_sps"] = 6
    noise = m.noise_floor([a, b])["full"]
    assert noise["rate_sd"]["value"] == pytest.approx(np.sqrt(2))
    assert noise["jaccard"]["value"] == 1
    a["stimulus"].update(id="s0_nuisance_clean", source_id="s0", labels={"nuisance": "clean"})
    v = copy.deepcopy(a)
    v["stimulus"].update(id="variant", source_id="s0", labels={"nuisance": "gain+6"})
    v["controls"]["voice"]["speed"] = 1.1
    result = m.nuisance_invariance([a, v])["full"]["gain+6"]
    assert result["speed_delta"]["max"]["value"] == pytest.approx(0.1)
    assert result["register_changed"]["mean"]["value"] == 0


def test_derangement():
    for n in range(2, 20):
        p = derangement(n)
        assert sorted(p) == list(range(n))
        assert all(i != v for i, v in enumerate(p))
    with pytest.raises(ValueError):
        derangement(1)


def tone(tmp_path):
    sr = 16000
    x = (0.1 * np.sin(2 * np.pi * 180 * np.arange(sr * 2) / sr)).astype("float32")
    x[12000:16000] = 0
    sf.write(tmp_path / "tone.wav", x, sr, subtype="FLOAT")
    r = row()["stimulus"]
    r.update(path="tone.wav")
    return write_manifest(tmp_path, [r]), x, sr


def test_builders(tmp_path):
    manifest, x, sr = tone(tmp_path)
    p = build_derived(manifest, tmp_path / "psola", kind="psola")
    for r in read_manifest(p):
        y, rate = sf.read(p.parent / r["path"])
        assert len(y) / rate == pytest.approx(len(x) / sr * r["labels"]["stretch"], abs=0.06)
        assert r["source_id"] == "s0"
    p = build_derived(manifest, tmp_path / "nuisance", kind="nuisance")
    for r in read_manifest(p):
        y, _ = sf.read(p.parent / r["path"])
        label = r["labels"]["nuisance"]
        if label.startswith("gain"):
            assert 20 * np.log10(np.linalg.norm(y) / np.linalg.norm(x)) == pytest.approx(
                float(label[4:]), abs=0.01
            )
        elif label.startswith("noise"):
            assert 20 * np.log10(np.linalg.norm(x) / np.linalg.norm(y - x)) == pytest.approx(
                float(label[5:]), abs=0.01
            )
        elif label == "clean":
            assert r["id"] == "s0_nuisance_clean"
            assert r["source_id"] == "s0"
            np.testing.assert_array_equal(y, x)
        else:
            assert len(y) == len(x) + sr // 2
    assert len(read_manifest(p)) == 6


class FakePipeline:
    def __init__(self):
        self.calls = []

    def turn(self, x, sr, state, *, measure_reference=False, **kw):
        kw["measure_reference"] = measure_reference
        assert state.turn == 0
        self.calls.append(kw)
        r = row()
        r["transcript"] = {"text": "I have the package for you"}
        return r, state


def test_resume(tmp_path):
    manifest, _, _ = tone(tmp_path)
    pipe = FakePipeline()
    rows = run_eval(manifest, tmp_path / "run", pipe, arms=("static", "full"), synthesize=False, track="e2e")
    assert len(rows) == 2 and len(pipe.calls) == 2
    assert all(r["wer"] == 0 for r in rows)
    assert all(call["measure_reference"] is False for call in pipe.calls)
    run_eval(manifest, tmp_path / "run", pipe, arms=("static", "full"), synthesize=False, track="e2e")
    assert len(pipe.calls) == 2
    with pytest.raises(ValueError):
        run_eval(manifest, tmp_path / "run", pipe, arms=("static", "full"), synthesize=False, track="locked")


def test_ratings_and_report(tmp_path):
    manifest, _, _ = tone(tmp_path)
    rows = []
    for i in range(8):
        for rate in (150, 220):
            r = row(i)
            r["stimulus"]["labels"]["rate_wpm"] = rate
            r["input_path"] = r["output_path"] = str(tmp_path / "tone.wav")
            rows.append(r)
    out = tmp_path / "ratings"
    key = export_sheet(rows, out, 7, "rate_wpm")
    with (out / "ratings_sheet.csv").open() as f:
        sheet = list(csv.DictReader(f))
    assert len(sheet) == 32
    assert set(sheet[0]) == {"trial_id", "user_audio", "reply_audio", "reply_text", "rating", "rater"}
    assert all("full" not in r["reply_audio"] and "matched" not in r["reply_audio"] for r in sheet)
    for r in sheet:
        r["rating"] = 6 if key[r["trial_id"]]["kind"] == "matched" else 3
        r["rater"] = "r1"
    with (out / "ratings_sheet.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=sheet[0])
        w.writeheader()
        w.writerows(sheet)
    score = score_sheet(out / "ratings_sheet.csv", out / "ratings_key.json")["full"]
    assert score["gain"]["value"] == 3
    assert score["gain"]["ci"] == [3, 3]
    assert score["warnings"]
    rows[0]["stimulus"]["contaminated_for"] = ["emotion2vec"]
    rows[0]["affect"] = {"model": "emotion2vec/base"}
    run = tmp_path / "report"
    run.mkdir()
    (run / "traces.jsonl").write_text(json.dumps(rows[0]) + "\n")
    result = build_report(run)
    assert len(result["warnings"]) == 5
    assert "synthetic" in (run / "report.md").read_text()


def test_shuffled_oracle_and_locked(tmp_path):
    manifest, _, _ = tone(tmp_path)
    a = read_manifest(manifest)[0]
    b = dict(a, id="s1", labels={"emotion": "sad"})
    manifest = write_manifest(tmp_path, [a, b])

    class Affect:
        calls = 0

        def analyze(self, x):
            from adaptive_s2s.types import AffectReading

            self.calls += 1
            return AffectReading(False)

    pipeline = FakePipeline()
    pipeline.affect = Affect()
    rows = run_eval(
        manifest, tmp_path / "run", pipeline, arms=("static",), shuffled=True, oracle=True, synthesize=False
    )
    assert len(rows) == 5
    assert pipeline.affect.calls == 2
    assert all(k["locked_text"] == a["text"] for k in pipeline.calls)
    assert sum(k["feature_source"] == "shuffled" for k in pipeline.calls) == 2
    assert sum(k["feature_source"] == "oracle" for k in pipeline.calls) == 1
    assert (
        next(k for k in pipeline.calls if k["feature_source"] == "oracle")["feature_override"][1].top_label
        == "sad"
    )


def test_human_splits(tmp_path):
    from adaptive_s2s.evals.stimuli import build_human

    source = tmp_path / "human"
    source.mkdir()
    sf.write(source / "p01_n09_sad.wav", np.zeros(100), 16000)
    sf.write(source / "p01_n01_happy.wav", np.zeros(100), 16000)
    manifest = build_human(source, tmp_path / "index", heldout_speakers=("p01",))
    rows = read_manifest(manifest)
    assert {r["script_id"]: r["split"] for r in rows} == {"n01": "dev", "n09": "heldout"}
    assert all(r["labels"]["speaker_split"] == "heldout" for r in rows)
    assert all((manifest.parent / r["path"]).exists() for r in rows)


def test_realised_speed_dose_response():
    rows = [row(i) for i in range(4)]
    rows.append(row(10))
    rows[-1]["tts"]["realised_speed"] = None
    rows[0]["output_acoustic"] = None
    response = m.rate_dose_response(rows)["full"]
    assert list(response) == ["realised_speed", "realised_rate", "requested_speed"]
    fit = response["realised_speed"]
    assert fit["slope"]["value"] == pytest.approx(0.1)
    assert fit["intercept"]["value"] == pytest.approx(0.8)
    assert fit["pearson_r"]["value"] == pytest.approx(1)
    assert fit["slope"]["n_rows"] == 4
    assert response["requested_speed"]["slope"]["n_rows"] == 5
    for trace in rows:
        trace.pop("tts")
    empty = m.rate_dose_response(rows)["full"]["realised_speed"]["slope"]
    assert empty == dict(value=None, ci=None, n_rows=0, n_clusters=0)


@pytest.mark.parametrize(
    "reply, expected",
    [
        ("I'm really sorry to hear that. Let's make a plan.", 1),
        ("Well, that sounds DIFFICULT. We can work on it.", 1),
        ("I am HERE FOR YOU.", 1),
        ("Sounds like a rough day.", 1),
        ("Here is the plan. I am sorry about that.", 0),
        ("The package is here.", 0),
        ("", 0),
    ],
)
def test_first_sentence_acknowledgment(reply, expected):
    trace = row()
    trace["stimulus"]["labels"]["emotion"] = "sad"
    trace["reply_text"] = reply
    result = m.support_response([trace])["full"]["sad"]
    assert result["acknowledgment"]["value"] == expected
    assert "sorry" in m.ACKNOWLEDGMENT_CUES


def test_nuisance_pairs_source_arm_and_seed():
    rows = []
    for arm in ("full", "static"):
        for seed in (0, 1):
            clean = row(arm=arm, seed=seed)
            clean["stimulus"].update(id="s0_nuisance_clean", source_id="s0", labels={"nuisance": "clean"})
            clean["controls"]["voice"]["speed"] = 1 + seed + (arm == "static")
            variant = copy.deepcopy(clean)
            variant["stimulus"]["id"] = "s0_nuisance_gain+6"
            variant["stimulus"]["labels"]["nuisance"] = "gain+6"
            variant["controls"]["voice"]["speed"] += 0.1 * (seed + 1)
            variant["controls"]["text"]["register"] = "formal" if seed else "neutral"
            variant["controls"]["text"]["supportive"] = bool(seed)
            rows.extend([variant, clean])
    # Neither an original source row nor a different source is a valid reference.
    rows.append(row())
    unmatched = copy.deepcopy(rows[0])
    unmatched["stimulus"]["source_id"] = "absent"
    rows.append(unmatched)
    result = m.nuisance_invariance(rows)
    for arm in ("full", "static"):
        assert list(result[arm]) == ["gain+6"]
        measured = result[arm]["gain+6"]
        assert measured["speed_delta"]["mean"]["value"] == pytest.approx(0.15)
        assert measured["speed_delta"]["max"]["value"] == pytest.approx(0.2)
        assert measured["speed_delta"]["mean"]["n_rows"] == 2
        assert measured["register_changed"]["mean"]["value"] == 0.5
        assert measured["supportive_changed"]["mean"]["value"] == 0.5
    assert m.nuisance_invariance([row(), unmatched]) == {}


def test_runner_warms_before_turn_and_measures_reference(tmp_path):
    manifest, _, _ = tone(tmp_path)

    class WarmPipeline(FakePipeline):
        def __init__(self):
            super().__init__()
            self.warmed = False

        def warm(self):
            self.warmed = True

        def turn(self, *args, measure_reference=False, **kwargs):
            assert self.warmed
            assert measure_reference is True
            return super().turn(*args, measure_reference=measure_reference, **kwargs)

    pipeline = WarmPipeline()
    result = run_eval(manifest, tmp_path / "warm-run", pipeline, arms=("full",))
    assert len(result) == 1
    assert pipeline.calls[0]["measure_reference"] is True


def test_nuisance_clean_preserves_source_file(tmp_path):
    manifest, samples, sr = tone(tmp_path)
    stereo = np.column_stack([samples, samples / 2])
    source_audio = tmp_path / "tone.wav"
    sf.write(source_audio, stereo, sr, subtype="PCM_16")
    derived = build_derived(manifest, tmp_path / "nuisance", kind="nuisance")
    clean = next(r for r in read_manifest(derived) if r["labels"]["nuisance"] == "clean")
    assert (derived.parent / clean["path"]).read_bytes() == source_audio.read_bytes()
