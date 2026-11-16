import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from moshi_dialogue import TEXT_PAD, load_turn
from moshi_tone_analyse import held_out_accuracy, shuffle_within
from moshi_tone_probe import Listener, clip_table

rng = np.random.default_rng(1)
groups = np.repeat(np.arange(6), 9)
labels = np.tile(np.repeat(np.array(["a", "b", "c"]), 3), 6)
tone_code = (labels[:, None] == np.array(["a", "b", "c"])[None, :]).astype(float)
signal = rng.normal(size=(len(labels), 64)) + 3 * np.pad(tone_code.repeat(8, axis=1), ((0, 0), (0, 40)))
assert held_out_accuracy(signal, labels, groups, ["a", "b", "c"]) > 0.9, "probe must find a real tone signal"
sentence_only = rng.normal(size=(len(labels), 64)) + 5 * np.pad(np.eye(6)[groups].repeat(8, axis=1), ((0, 0), (0, 16)))
assert held_out_accuracy(sentence_only, labels, groups, ["a", "b", "c"]) < 0.6, "probe must not score from sentence identity"
shuffled = shuffle_within(labels, groups, rng)
for group in range(6):
    assert sorted(shuffled[groups == group]) == sorted(labels[groups == group])
print("PASS: probe finds planted tone, cannot score from sentence identity, shuffles keep each sentence's label mix")

clips = [c for c in clip_table(ROOT / "scripts/duplex_scenes.yaml", ROOT / "out/duplex-scenes/candidates")
         if c["scene"] == "callback" and c["turn"] == 0 and c["take"] == 0]
sad = next(c for c in clips if c["delivery"] == "sad")
excited = next(c for c in clips if c["delivery"] == "excited")
listener = Listener("kyutai/moshiko-mlx-q8")
first = listener.listen(load_turn(sad["file"]))
again = listener.listen(load_turn(sad["file"]))
other = listener.listen(load_turn(excited["file"]))
for run in (first, again, other):
    assert (run["emitted"] == TEXT_PAD).all(), "Moshi must be held silent so only the user's voice varies"
    assert run["states"].shape[1:] == (33, 4096) and np.isfinite(run["states"]).all()
np.testing.assert_array_equal(first["states"], again["states"])
lead = first["speech"][0]
np.testing.assert_allclose(first["states"][:lead], other["states"][:lead], atol=1e-3)
shared_speech = min(first["speech"][1], other["speech"][1])
assert np.abs(first["states"][lead + 2:shared_speech] - other["states"][lead + 2:shared_speech]).max() > 1
print("PASS: real Moshi listen: held silent, repeatable, identical before the user speaks, different once the tone differs")

results = ROOT / "out/tone-probe/results.json"
if results.exists():
    result = json.loads(results.read_text())
    assert result["clips"] == len(clip_table(ROOT / "scripts/duplex_scenes.yaml", ROOT / "out/duplex-scenes/candidates"))
    assert len(result["layers"]) == 33 and all(0 <= v <= 1 for v in result["decode"]["during"])
    print(f"PASS: saved probe covers all {result['clips']} rendered takes")

from moshi_tone_viz import directions, project

rng = np.random.default_rng(2)
planted = np.zeros((3, 4096))
planted[:, :64] = rng.normal(size=(1, 64))
tone_sign = {"sad": 1.0, "plain": 0.0, "excited": -1.0}
fake_tones = np.array(["sad", "plain", "excited"] * 10)
fake = rng.normal(size=(30, 3, 4096)) + np.array([tone_sign[t] for t in fake_tones])[:, None, None] * planted[None]
fake_dirs = directions(fake, fake_tones)
fresh_sad = rng.normal(size=(5, 3, 4096)) + planted[None]
fresh_excited = rng.normal(size=(5, 3, 4096)) - planted[None]
assert (project(fresh_sad, fake_dirs["sad_vs_excited"]) > project(fresh_excited, fake_dirs["sad_vs_excited"])).all()
print("PASS: the explainer's tone axis puts unseen sad-like states on the sad side at every layer")

explainer = ROOT / "out/tone-probe/explainer.html"
if explainer.exists():
    page = explainer.read_text()
    assert "__DATA__" not in page
    payload = json.loads(page.split("const D=", 1)[1].split(";\nconst L=", 1)[0])
    assert len(payload["effects"]) == 33 and all(len(e) == 4096 for e in payload["effects"])
    assert len(payload["map_points"]) == 81 and len(payload["traces"]["qwen"]) == 6
    assert {r["tone"] for r in payload["traces"]["grok_summary"]} >= {"sad", "excited", "plain", "flat", "hesitant"}
    print("PASS: explainer page carries all layers, units, clips and Grok traces")

post = ROOT / "out/tone-probe/post.html"
if post.exists():
    page = post.read_text()
    assert "__DATA__" not in page and "__FONTS__" not in page
    assert page.count("font/woff2;base64,") == 3, "the post must carry its own Merriweather and Geist Pixel fonts"
    assert "100vh" not in page, "the post must not size itself to the viewport height"
    assert "—" not in page.split('id="prose"', 1)[1].split("</article>", 1)[0], "post prose must not use em dashes"
    payload = json.loads(page.split("const D=", 1)[1].split(";\nconst L=", 1)[0])
    assert len(payload["live_vs_memory"]) == 33 and len(payload["behaviour"]) == 3
    assert all(f'id="{name}"' in page for name in ("archsvg", "decodesvg", "grid", "lsvg", "msvg", "transfersvg", "gsvg", "gstrip", "bars"))
    emo = payload["emo"]
    assert len(emo["emotions"]) >= 10 and len(emo["confusion"]) == len(emo["emotions"]) and len(emo["probe"]["by_voice"]) == 33
    assert all(f'id="{name}"' in page for name in ("emoprobesvg", "confsvg", "emomapsvg", "heatsvg", "examples"))
    assert "../emotions/atlas/index.html" in page, "the post must link to the neuron atlas"
    print("PASS: site-styled post carries its fonts, data, all thirteen figures and the atlas link")
