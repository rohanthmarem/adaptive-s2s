import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import soundfile as sf
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from duplex_render import sentences

spec = yaml.safe_load((ROOT / "scripts/duplex_scenes.yaml").read_text())
for scene in spec["scenes"]:
    assert scene["situation"] and len(scene["turns"]) >= 2, scene["id"]
    assert set(scene["deliveries"]) <= set(spec["deliveries"]), scene["id"]
    assert "plain" in scene["deliveries"], f"{scene['id']} needs a plain reading of the same words as its control"
    emotional = [d for d in scene["deliveries"] if d != "plain"]
    if not scene.get("same_words"):
        assert len(emotional) == 1, f"{scene['id']} must test one emotion that its story is about, got {emotional}"
for delivery, direction in spec["deliveries"].items():
    if delivery != "plain":
        assert any(word in direction for word in ("whole", "every sentence", "throughout", "never", "last word")), \
            f"{delivery} direction must ask for the emotion across the whole utterance"
print("PASS: every scene tests one emotion its story supports, plus a plain control; directions ask for sustained emotion")

manifest = json.loads((ROOT / "out/duplex-scenes/manifest.json").read_text())
expected = {(s["id"], d) for s in spec["scenes"] for d in s["deliveries"]}
assert {(e["scene"], e["delivery"]) for e in manifest} == expected, "manifest must cover every scene and delivery"
for entry in manifest:
    scene = next(s for s in spec["scenes"] if s["id"] == entry["scene"])
    for turn, text in zip(entry["turns"], scene["turns"]):
        assert len(turn["sentences"]) == len(sentences(text)), f"each sentence must be rendered and scored on its own: {turn['file']}"
        assert all(s["takes_scored"] >= 1 and s["emotion"] for s in turn["sentences"])
        audio, sr = sf.read(turn["file"])
        assert sr == 24000 and len(audio) / sr == turn["duration_s"] and len(audio) > sr // 2
print(f"PASS: {len(manifest)} scene readings, every sentence rendered and emotion-scored separately")

out = ROOT / "out/verify-duplex"
turns = [entry["turns"][i]["file"] for entry in manifest[:1] for i in range(2)]
result = subprocess.run([str(ROOT / ".venv-moshi/bin/python"), str(ROOT / "scripts/moshi_dialogue.py"), "--turns", *turns,
                         "--out", str(out), "--seed", "11"], capture_output=True, text=True, timeout=400,
                        env={**os.environ, "HF_HUB_OFFLINE": "1"})
assert result.returncode == 0, result.stderr[-2000:]
trace = json.loads((out / "trace.json").read_text())
phases = [e["phase"] for e in trace["events"]]
assert phases == ["greeting", "user turn 1", "reply 1", "user turn 2", "reply 2"], phases
for previous, current in zip(trace["events"], trace["events"][1:]):
    assert current["start_s"] >= previous["end_s"], "a user turn must start only after the previous phase ended"
stereo, sr = sf.read(out / "conversation.wav")
assert sr == 24000 and stereo.ndim == 2 and stereo.shape[1] == 2, "conversation.wav must be stereo: Moshi left, user right"
assert abs(len(stereo) / sr - trace["duration_s"]) < 0.01
user_rms = np.sqrt(np.mean(stereo[:, 1] ** 2))
assert user_rms > 0.005, "the user channel must contain the user's speech"
assert any(e.get("moshi_spoke") for e in trace["events"] if e["phase"].startswith("reply")), "Moshi must speak in at least one reply window"
print("PASS: real Moshi call: greeting, then each user turn after Moshi goes quiet, replies captured, stereo aligned")
