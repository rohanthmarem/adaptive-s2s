import argparse
import json
import re
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

ROOT = Path(__file__).resolve().parents[1]
MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit"


def sentences(text):
    return [part.strip() for part in re.findall(r"[^.!?]+[.!?]+|[^.!?]+$", text) if part.strip()]


def load_scenes(path):
    return yaml.safe_load(Path(path).read_text())


def candidate_path(root, scene_id, delivery, turn, sentence, take):
    return root / "candidates" / f"{scene_id}_{delivery}_t{turn}_s{sentence}_k{take}.wav"


def render(args):
    from mlx_audio.tts.utils import load_model
    import mlx.core as mx

    spec = load_scenes(args.scenes)
    model = load_model(MODEL)
    jobs = []
    for scene in spec["scenes"]:
        if args.only and scene["id"] not in args.only:
            continue
        for delivery in scene["deliveries"]:
            instruct = f"{spec['deliveries'][delivery]} Situation: {scene['situation']}"
            for turn_index, turn in enumerate(scene["turns"]):
                for sentence_index, sentence in enumerate(sentences(turn)):
                    for take in range(args.takes):
                        jobs.append((scene["id"], delivery, turn_index, sentence_index, take, sentence, instruct))
    print(f"{len(jobs)} takes to render", flush=True)
    for done, (scene_id, delivery, turn_index, sentence_index, take, sentence, instruct) in enumerate(jobs, 1):
        path = candidate_path(args.root, scene_id, delivery, turn_index, sentence_index, take)
        meta = path.with_suffix(".json")
        request = {"model": MODEL, "speaker": spec["speaker"], "text": sentence, "instruct": instruct, "seed": take}
        if path.exists() and meta.exists() and json.loads(meta.read_text()) == request:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        mx.random.seed(1000 * take + 7)
        audio = np.concatenate([np.array(chunk.audio) for chunk in model.generate(
            text=sentence, voice=spec["speaker"].lower(), instruct=instruct, lang_code="english")])
        sf.write(path, audio, model.sample_rate)
        meta.write_text(json.dumps(request, indent=2))
        if done % 10 == 0:
            print(f"rendered {done}/{len(jobs)}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenes", type=Path, default=ROOT / "scripts/duplex_scenes.yaml")
    parser.add_argument("--root", type=Path, default=ROOT / "out/duplex-scenes")
    parser.add_argument("--takes", type=int, default=3)
    parser.add_argument("--only", nargs="*")
    render(parser.parse_args())


if __name__ == "__main__":
    main()
