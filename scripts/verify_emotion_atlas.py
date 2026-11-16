import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import neuron_atlas
from moshi_dialogue import load_turn
from moshi_tone_probe import Listener

spec = yaml.safe_load((ROOT / "scripts/emotion_set.yaml").read_text())
emotions = list(spec["emotions"])
assert {"sarcastic", "surprised", "bored", "anxious", "disgusted", "sad", "happy", "neutral"} <= set(emotions)
assert len(emotions) >= 10 and len(spec["voices"]) >= 3 and len(spec["sentences"]) >= 8
for name, emotion in spec["emotions"].items():
    assert any(w in emotion["direction"] for w in ("whole", "every word", "throughout", "first word to the last")), \
        f"{name} must be asked for across the whole sentence"
    assert ("classifier" in emotion) != ("acoustic" in emotion), f"{name} needs exactly one way to pick its best take"
print(f"PASS: {len(emotions)} emotions incl. sarcasm, surprise, boredom, anxiety and disgust, each sustained, {len(spec['voices'])} voices")

with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    (root / "moshi").mkdir()
    voices = list(spec["voices"])
    clips = [{"voice": v, "sex": "x", "emotion": e, "sentence": s, "text": "t", "file": "x"}
             for v in voices for e in emotions for s in range(10)]
    (root / "moshi" / "clips.json").write_text(json.dumps(clips))
    rng = np.random.default_rng(0)
    labels = np.array([c["emotion"] for c in clips])
    fake = rng.normal(size=(len(clips), 3, 120)).astype(np.float16)
    fake[labels == "sad", 1, 7] += 3
    fake[labels == "happy", 2, 9] -= 3
    np.save(root / "moshi" / "neurons_mean.npy", fake)
    residual = rng.normal(size=(len(clips), 4, 24))
    np.savez(root / "moshi" / "residual.npz", during=residual, after=residual, speak_after=np.zeros(len(clips)),
             frames=np.zeros((len(clips), 3)))
    neuron_atlas.analyse(type("Args", (), {"root": root})())
    data = json.loads((root / "moshi" / "atlas_data.json").read_text())
    found = {(p["layer"], p["neuron"], p["sign"], p["emotion"]) for p in data["poles"]}
    assert (1, 7, 1, "sad") in found and (2, 9, -1, "happy") in found, "planted sad and happy neurons must be found"
    assert sum(sum(row) for row in data["null_counts"]) <= 1, "shuffled labels must find almost no strong neurons"
    assert all(p["strength"] >= neuron_atlas.MIN_STRENGTH for p in data["poles"])
print("PASS: atlas finds a planted sad neuron that rises and a happy neuron that falls, and shuffled labels find none")

clip = ROOT / "out/duplex-scenes/turns/callback_sad_t0.wav"
plain = Listener("kyutai/moshiko-mlx-q8").listen(load_turn(clip))
tapped = Listener("kyutai/moshiko-mlx-q8", neurons=True).listen(load_turn(clip))
np.testing.assert_array_equal(plain["states"], tapped["states"])
assert tapped["neurons"].shape[1:] == (32, 11264) and np.isfinite(tapped["neurons"].astype(np.float32)).all()
print("PASS: reading Moshi's 360,448 MLP neurons leaves its computation unchanged")

out = ROOT / "out/emotions"
if (out / "moshi" / "atlas_data.json").exists():
    manifest = json.loads((out / "manifest.json").read_text())
    assert len(manifest) == len(spec["voices"]) * len(emotions) * len(spec["sentences"])
    data = json.loads((out / "moshi" / "atlas_data.json").read_text())
    for pole in data["poles"]:
        e = data["emotions"].index(pole["emotion"])
        per_voice = np.array(pole["per_voice"])[:, e] * pole["sign"]
        assert (per_voice > 0).all() and abs(per_voice.min() - pole["strength"]) < 0.02, "every listed pole must agree in all voices"
    atlas = out / "atlas" / "index.html"
    assert atlas.exists() and "__DATA__" not in atlas.read_text()
    assert len(list((out / "atlas" / "audio").glob("*.wav"))) == len(manifest)
    print(f"PASS: real atlas has {len(data['poles'])} poles, each agreeing across all {len(data['voices'])} voices, with audio for all {len(manifest)} clips")
