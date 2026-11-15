import argparse
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from duplex_render import candidate_path, sentences
from voice_check import EmotionModel, pitch_and_level
from adaptive_s2s.audio import load_audio, to_16k
from adaptive_s2s.evals.runner import wer

TARGET_LABEL = {"sad": "sad", "excited": "happy", "frustrated": "angry", "anxious": "fearful", "plain": "neutral"}
GAP_S = {"plain": 0.35, "sad": 0.9, "flat": 0.6, "hesitant": 0.8, "frustrated": 0.3, "excited": 0.2, "anxious": 0.15}
MAX_WER = 0.25
SAMPLE_RATE = 24000


def take_score(delivery, emotion, pitch_sd, words_per_s):
    if delivery in TARGET_LABEL:
        return emotion.get(TARGET_LABEL[delivery], 0.0)
    if delivery == "flat":
        return emotion.get("neutral", 0.0) + emotion.get("sad", 0.0) - (pitch_sd or 5.0) / 4 - emotion.get("happy", 0.0)
    if delivery == "hesitant":
        lively = emotion.get("happy", 0.0) + emotion.get("angry", 0.0) + emotion.get("surprised", 0.0)
        return 1.0 - lively - words_per_s / 10
    raise ValueError(f"No scoring rule for delivery {delivery}")


def measure_take(path, text, asr, emotion):
    audio, sr = load_audio(path)
    audio16k = to_16k(audio, sr)
    segments, _ = asr.transcribe(audio16k, beam_size=5, language="en", vad_filter=False)
    heard = " ".join(segment.text.strip() for segment in segments)
    median_f0, pitch_sd, level = pitch_and_level(audio16k)
    speech = np.flatnonzero(np.abs(audio16k) > 0.01)
    speaking_s = (speech[-1] - speech[0]) / 16000 if len(speech) > 1 else len(audio16k) / 16000
    return {"heard": heard, "wer": wer(text, heard), "emotion": emotion.scores(audio16k),
            "pitch_sd_semitones": pitch_sd, "median_f0_hz": median_f0, "level_dbfs": level,
            "words_per_s": len(text.split()) / max(speaking_s, 0.1)}


def trim(audio, threshold=0.01, margin=1200):
    active = np.flatnonzero(np.abs(audio) > threshold)
    if not len(active):
        raise ValueError("Take is silent")
    return audio[max(0, active[0] - margin): active[-1] + margin]


def assemble(args):
    from faster_whisper import WhisperModel
    from adaptive_s2s.asr import cached_model_path

    spec = yaml.safe_load(args.scenes.read_text())
    asr = WhisperModel(cached_model_path("Systran/faster-whisper-small.en"), device="cpu", compute_type="int8")
    emotion = EmotionModel()
    manifest = []
    for scene in spec["scenes"]:
        for delivery in scene["deliveries"]:
            turns = []
            for turn_index, turn in enumerate(scene["turns"]):
                pieces, chosen = [], []
                for sentence_index, text in enumerate(sentences(turn)):
                    takes = []
                    for take in range(args.takes):
                        path = candidate_path(args.root, scene["id"], delivery, turn_index, sentence_index, take)
                        if not path.exists():
                            continue
                        measured = measure_take(path, text, asr, emotion)
                        measured["score"] = take_score(delivery, measured["emotion"], measured["pitch_sd_semitones"], measured["words_per_s"])
                        takes.append({"take": take, "file": str(path), **measured})
                    if not takes:
                        raise FileNotFoundError(f"No rendered takes for {scene['id']} {delivery} turn {turn_index} sentence {sentence_index}")
                    usable = [t for t in takes if t["wer"] <= MAX_WER] or takes
                    best = max(usable, key=lambda t: t["score"])
                    chosen.append({"text": text, "takes_scored": len(takes), "words_ok": best["wer"] <= MAX_WER, **best})
                    audio, sr = load_audio(best["file"])
                    if sr != SAMPLE_RATE:
                        raise ValueError(f"Expected {SAMPLE_RATE} Hz takes, got {sr}")
                    pieces.append(trim(audio))
                    pieces.append(np.zeros(int(GAP_S[delivery] * SAMPLE_RATE), dtype=np.float32))
                turn_audio = np.concatenate(pieces[:-1])
                out = args.root / "turns" / f"{scene['id']}_{delivery}_t{turn_index}.wav"
                out.parent.mkdir(parents=True, exist_ok=True)
                sf.write(out, turn_audio, SAMPLE_RATE, subtype="PCM_16")
                turns.append({"text": turn, "file": str(out), "duration_s": len(turn_audio) / SAMPLE_RATE, "sentences": chosen})
            manifest.append({"scene": scene["id"], "title": scene["title"], "situation": scene["situation"],
                             "delivery": delivery, "same_words": bool(scene.get("same_words")),
                             "target_label": TARGET_LABEL.get(delivery), "turns": turns})
            print(f"assembled {scene['id']} {delivery}", flush=True)
    (args.root / "manifest.json").write_text(json.dumps(manifest, indent=2))
    report_coverage(manifest)


def report_coverage(manifest):
    for entry in manifest:
        sentence_rows = [s for turn in entry["turns"] for s in turn["sentences"]]
        label = entry["target_label"]
        if label:
            hits = sum(1 for s in sentence_rows if max(s["emotion"], key=s["emotion"].get) == label)
            summary = f"{hits}/{len(sentence_rows)} sentences read as {label}"
        else:
            sds = [s["pitch_sd_semitones"] for s in sentence_rows if s["pitch_sd_semitones"] is not None]
            rates = [s["words_per_s"] for s in sentence_rows]
            summary = f"pitch sd {np.mean(sds):.1f} st, {np.mean(rates):.1f} words/s"
        bad_words = sum(1 for s in sentence_rows if not s["words_ok"])
        print(f"{entry['scene']:10s} {entry['delivery']:10s} {summary}; sentences with wrong words: {bad_words}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenes", type=Path, default=ROOT / "scripts/duplex_scenes.yaml")
    parser.add_argument("--root", type=Path, default=ROOT / "out/duplex-scenes")
    parser.add_argument("--takes", type=int, default=3)
    assemble(parser.parse_args())


if __name__ == "__main__":
    main()
