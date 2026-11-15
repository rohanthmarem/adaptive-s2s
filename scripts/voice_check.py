import argparse
import json
import logging
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import numpy as np

from adaptive_s2s.audio import load_audio, to_16k

EMOTION_LABELS = ["angry", "disgusted", "fearful", "happy", "neutral", "other", "sad", "surprised", "unknown"]
MIN_SEGMENT_S = 1.0


def transcribe_sentences(model, audio16k):
    segments, _ = model.transcribe(audio16k, word_timestamps=True, beam_size=5, language="en", vad_filter=False)
    sentences, words = [], []
    for segment in segments:
        for word in segment.words or []:
            words.append(word)
            if word.word.strip().endswith((".", "?", "!")):
                sentences.append(words)
                words = []
    if words:
        sentences.append(words)
    return [
        {"text": "".join(w.word for w in sentence).strip(), "start": sentence[0].start, "end": sentence[-1].end}
        for sentence in sentences
    ]


def merge_short(sentences):
    merged = []
    for sentence in sentences:
        if merged and (sentence["end"] - sentence["start"] < MIN_SEGMENT_S or merged[-1]["end"] - merged[-1]["start"] < MIN_SEGMENT_S):
            merged[-1] = {"text": merged[-1]["text"] + " " + sentence["text"], "start": merged[-1]["start"], "end": sentence["end"]}
        else:
            merged.append(sentence)
    return merged


def pitch_and_level(audio16k):
    import parselmouth

    sound = parselmouth.Sound(audio16k.astype(np.float64), sampling_frequency=16000)
    f0 = sound.to_pitch(time_step=0.01, pitch_floor=70.0, pitch_ceiling=500.0).selected_array["frequency"]
    voiced = f0[f0 > 0]
    level = 20 * np.log10(np.sqrt(np.mean(audio16k**2)) + 1e-9)
    if voiced.size < 10:
        return None, None, float(level)
    semitones = 12 * np.log2(voiced / np.median(voiced))
    return float(np.median(voiced)), float(np.std(semitones)), float(level)


class EmotionModel:
    def __init__(self):
        from funasr import AutoModel
        from adaptive_s2s.asr import cached_model_path

        logging.disable(logging.CRITICAL)
        with open(os.devnull, "w") as sink, redirect_stdout(sink), redirect_stderr(sink):
            self.model = AutoModel(model=cached_model_path("emotion2vec/emotion2vec_plus_base"), hub="hf",
                                   disable_update=True, disable_pbar=True, device="cpu")

    def scores(self, audio16k):
        with open(os.devnull, "w") as sink, redirect_stdout(sink), redirect_stderr(sink):
            result = self.model.generate(audio16k.astype(np.float32), granularity="utterance",
                                         extract_embedding=False, disable_pbar=True)[0]
        return {label.rsplit("/", 1)[-1]: round(float(score), 3) for label, score in zip(result["labels"], result["scores"])}


def analyse(path, asr, emotion):
    audio, sr = load_audio(path)
    audio16k = to_16k(audio, sr)
    sentences = merge_short(transcribe_sentences(asr, audio16k))
    rows = []
    for sentence in sentences:
        clip = audio16k[int(sentence["start"] * 16000): int(sentence["end"] * 16000) + 1]
        median_f0, pitch_sd, level = pitch_and_level(clip)
        words = len(sentence["text"].split())
        rows.append({**sentence, "emotion": emotion.scores(clip), "median_f0_hz": median_f0,
                     "pitch_sd_semitones": pitch_sd, "level_dbfs": level,
                     "words_per_s": words / max(sentence["end"] - sentence["start"], 0.1)})
    whole_f0, whole_sd, whole_level = pitch_and_level(audio16k)
    return {"file": str(path), "duration_s": len(audio16k) / 16000, "transcript": " ".join(r["text"] for r in rows),
            "pitch_sd_semitones": whole_sd, "median_f0_hz": whole_f0, "level_dbfs": whole_level,
            "emotion": emotion.scores(audio16k), "sentences": rows}


def sustained(report, label, threshold):
    shares = [row["emotion"].get(label, 0.0) for row in report["sentences"]]
    return bool(shares) and min(shares) >= threshold, shares


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    from faster_whisper import WhisperModel
    from adaptive_s2s.asr import cached_model_path

    asr = WhisperModel(cached_model_path("Systran/faster-whisper-small.en"), device="cpu", compute_type="int8")
    emotion = EmotionModel()
    reports = [analyse(path, asr, emotion) for path in args.files]
    for report in reports:
        print(Path(report["file"]).name, f"{report['duration_s']:.1f}s", "pitch sd", report["pitch_sd_semitones"])
        for row in report["sentences"]:
            top = max(row["emotion"], key=row["emotion"].get)
            print(f"   {row['start']:5.1f}-{row['end']:5.1f}s  {top:8s} {row['emotion'][top]:.2f}  sad {row['emotion'].get('sad', 0):.2f}  "
                  f"sd {row['pitch_sd_semitones'] or 0:.1f}st  {row['words_per_s']:.1f} w/s  | {row['text']}")
    if args.out:
        args.out.write_text(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
