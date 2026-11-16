import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from moshi_dialogue import TEXT_PAD, load_turn
from moshi_tone_probe import Listener


def capture(args):
    manifest = json.loads((args.root / "manifest.json").read_text())
    if args.limit:
        manifest = manifest[: args.limit]
    listener = Listener(args.repo, neurons=True)
    neurons, during, after, speak_after, frames = [], [], [], [], []
    started = time.time()
    for index, clip in enumerate(manifest, 1):
        result = listener.listen(load_turn(clip["file"]))
        if not (result["emitted"] == TEXT_PAD).all():
            raise RuntimeError(f"Moshi's own text was not held silent for {clip['file']}")
        start, stop = result["speech"]
        speech = result["neurons"][start:stop].astype(np.float32)
        neurons.append(speech.mean(axis=0).astype(np.float16))
        during.append(result["states"][start:stop].mean(axis=0).astype(np.float16))
        after.append(result["states"][stop:].mean(axis=0).astype(np.float16))
        speak_after.append(float(result["speak_prob"][stop:].mean()))
        frames.append([int(start), int(stop), int(len(result["states"]))])
        if index % 20 == 0 or index == len(manifest):
            print(f"listened {index}/{len(manifest)} in {time.time() - started:.0f}s", flush=True)
    out = args.root / "moshi"
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "neurons_mean.npy", np.stack(neurons))
    np.savez_compressed(out / "residual.npz", during=np.stack(during), after=np.stack(after),
                        speak_after=np.array(speak_after), frames=np.array(frames))
    (out / "clips.json").write_text(json.dumps([{k: clip[k] for k in ("voice", "sex", "emotion", "sentence", "text", "file")}
                                                for clip in manifest], indent=2))
    print(out)


def trace(args):
    clips = json.loads((args.root / "moshi" / "clips.json").read_text())
    chosen = json.loads((args.root / "moshi" / "chosen_neurons.json").read_text())
    layers = np.array([c["layer"] for c in chosen])
    units = np.array([c["neuron"] for c in chosen])
    listener = Listener(args.repo, neurons=True)
    poles = json.loads((args.root / "moshi" / "atlas_data.json").read_text())["poles"]
    needed = sorted({clip for pole in poles for clip in pole["top_clips"]})
    traces = {}
    for count, index in enumerate(needed, 1):
        result = listener.listen(load_turn(clips[index]["file"]))
        traces[f"clip_{index}"] = result["neurons"][:, layers, units].astype(np.float16).T
        traces[f"speech_{index}"] = np.array(result["speech"])
        if count % 40 == 0 or count == len(needed):
            print(f"traced {count}/{len(needed)}", flush=True)
    np.savez_compressed(args.root / "moshi" / "neuron_traces.npz", **traces)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["capture", "trace"])
    parser.add_argument("--root", type=Path, default=ROOT / "out/emotions")
    parser.add_argument("--repo", default="kyutai/moshiko-mlx-q8")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    capture(args) if args.mode == "capture" else trace(args)


if __name__ == "__main__":
    main()
