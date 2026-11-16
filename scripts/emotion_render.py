import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

ROOT = Path(__file__).resolve().parents[1]


def take_path(root, voice, emotion, sentence, take):
    return root / "takes" / f"{voice}_{emotion}_s{sentence}_k{take}.wav"


def instruction(voice, emotion):
    if "speaker" in voice:
        return f"Speak with {emotion['direction']}."
    return f"{voice['description']}, speaking with {emotion['direction']}."


def render(args):
    import mlx.core as mx
    from mlx_audio.tts.utils import load_model

    spec = yaml.safe_load(args.spec.read_text())
    by_model = {}
    for name, voice in spec["voices"].items():
        by_model.setdefault(voice["model"], []).append(name)
    total = len(spec["voices"]) * len(spec["emotions"]) * len(spec["sentences"]) * args.takes
    done = 0
    for model_id, voice_names in by_model.items():
        model = None
        for voice_name in voice_names:
            voice = spec["voices"][voice_name]
            for emotion_name, emotion in spec["emotions"].items():
                for sentence_index, text in enumerate(spec["sentences"]):
                    for take in range(args.takes):
                        done += 1
                        path = take_path(args.root, voice_name, emotion_name, sentence_index, take)
                        request = {"model": model_id, "voice": voice_name, "text": text,
                                   "instruct": instruction(voice, emotion), "seed": 1000 * take + 7 + sentence_index}
                        meta = path.with_suffix(".json")
                        if path.exists() and meta.exists() and json.loads(meta.read_text()) == request:
                            continue
                        if model is None:
                            model = load_model(model_id)
                        mx.random.seed(request["seed"])
                        options = {"voice": voice["speaker"]} if "speaker" in voice else {}
                        audio = np.concatenate([np.array(chunk.audio) for chunk in model.generate(
                            text=text, instruct=request["instruct"], lang_code="english", **options)])
                        path.parent.mkdir(parents=True, exist_ok=True)
                        sf.write(path, audio, model.sample_rate)
                        meta.write_text(json.dumps(request, indent=2))
                        if done % 40 == 0:
                            print(f"rendered {done}/{total}", flush=True)
        del model
    print(f"rendered {total}/{total}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, default=ROOT / "scripts/emotion_set.yaml")
    parser.add_argument("--root", type=Path, default=ROOT / "out/emotions")
    parser.add_argument("--takes", type=int, default=2)
    render(parser.parse_args())


if __name__ == "__main__":
    main()
