import argparse
import json
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from duplex_assemble import MAX_WER, measure_take
from emotion_render import take_path


def take_score(emotion, measured):
    if "classifier" in emotion:
        return measured["emotion"].get(emotion["classifier"], 0.0)
    if emotion["acoustic"] == "low_energy":
        return -(measured["pitch_sd_semitones"] or 5.0) / 4 - (measured["level_dbfs"] + 20) / 10 - measured["words_per_s"] / 3
    return 1.0 - measured["emotion"].get("neutral", 0.0)


def select(args):
    from faster_whisper import WhisperModel
    from adaptive_s2s.asr import cached_model_path
    from voice_check import EmotionModel

    spec = yaml.safe_load(args.spec.read_text())
    asr = WhisperModel(cached_model_path("Systran/faster-whisper-small.en"), device="cpu", compute_type="int8")
    classifier = EmotionModel()
    manifest = []
    for voice in spec["voices"]:
        for emotion_name, emotion in spec["emotions"].items():
            for sentence_index, text in enumerate(spec["sentences"]):
                takes = []
                for take in range(args.takes):
                    path = take_path(args.root, voice, emotion_name, sentence_index, take)
                    if not path.exists():
                        raise FileNotFoundError(path)
                    measured = measure_take(path, text, asr, classifier)
                    measured["classifier_scores"] = measured.pop("emotion")
                    takes.append({"take": take, "file": str(path), "score": take_score(emotion, {**measured, "emotion": measured["classifier_scores"]}), **measured})
                usable = [t for t in takes if t["wer"] <= MAX_WER] or takes
                best = max(usable, key=lambda t: t["score"])
                manifest.append({"voice": voice, "sex": spec["voices"][voice]["sex"], "emotion": emotion_name,
                                 "sentence": sentence_index, "text": text, "words_ok": best["wer"] <= MAX_WER,
                                 "classifier_target": emotion.get("classifier"), **best})
            print(f"scored {voice} {emotion_name}", flush=True)
    (args.root / "manifest.json").write_text(json.dumps(manifest, indent=2))
    report(manifest)


def report(manifest):
    for emotion in dict.fromkeys(m["emotion"] for m in manifest):
        rows = [m for m in manifest if m["emotion"] == emotion]
        top = [max(m["classifier_scores"], key=m["classifier_scores"].get) for m in rows]
        heard = {}
        for label in top:
            heard[label] = heard.get(label, 0) + 1
        target = rows[0]["classifier_target"]
        hits = f"{sum(1 for t in top if t == target)}/{len(rows)} heard as {target}" if target else "no classifier label"
        print(f"{emotion:13s} {hits:28s} top labels {sorted(heard.items(), key=lambda kv: -kv[1])[:3]} "
              f"pitch sd {np.mean([m['pitch_sd_semitones'] or 0 for m in rows]):.1f} st, "
              f"{np.mean([m['words_per_s'] for m in rows]):.1f} words/s, {np.mean([m['level_dbfs'] for m in rows]):.1f} dB, "
              f"wrong words {sum(1 for m in rows if not m['words_ok'])}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, default=ROOT / "scripts/emotion_set.yaml")
    parser.add_argument("--root", type=Path, default=ROOT / "out/emotions")
    parser.add_argument("--takes", type=int, default=2)
    select(parser.parse_args())


if __name__ == "__main__":
    main()
