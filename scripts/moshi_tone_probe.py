import argparse
import json
import re
import sys
import time
from pathlib import Path

import mlx.core as mx
import mlx.nn as nn
import numpy as np
import rustymimi
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from moshi_dialogue import FRAME, SAMPLE_RATE, TEXT_PAD, Moshi, load_turn

LEAD_S = 0.5
TAIL_S = 1.2
CANDIDATE = re.compile(r"^(?P<scene>[a-z_]+)_(?P<delivery>[a-z]+)_t(?P<turn>\d+)_s(?P<sentence>\d+)_k(?P<take>\d+)\.wav$")


class Recorder(nn.Module):
    def __init__(self, inner, slot, sink):
        super().__init__()
        self.inner = inner
        self.slot = slot
        object.__setattr__(self, "sink", sink)

    def __call__(self, xs, *args, **kwargs):
        if self.slot == 0:
            self.sink.record("embed", xs)
        out = self.inner(xs, *args, **kwargs)
        self.sink.record(self.slot, out)
        return out


class TextHead(nn.Module):
    def __init__(self, inner, sink):
        super().__init__()
        self.inner = inner
        object.__setattr__(self, "sink", sink)

    def __call__(self, xs):
        logits = self.inner(xs)
        self.sink.record("text", logits)
        return logits


class NeuronTap(nn.Module):
    def __init__(self, inner, slot, sink):
        super().__init__()
        self.inner = inner
        self.slot = slot
        object.__setattr__(self, "sink", sink)

    def __call__(self, xs):
        projected = self.inner.linear_in(xs)
        b, t, _ = projected.shape
        projected = projected.reshape(b, t, 2, -1)
        neurons = nn.silu(projected[:, :, 0]) * projected[:, :, 1]
        self.sink.record(("mlp", self.slot), neurons)
        return self.inner.linear_out(neurons)


class Sink:
    def __init__(self):
        self.frame = {}
        self.neurons = None

    def record(self, slot, value):
        self.frame[slot] = value

    def take(self, layers):
        values = [self.frame["embed"], *(self.frame[i] for i in range(layers))]
        stacked = mx.concatenate([v.reshape(1, -1).astype(mx.float32) for v in values], axis=0)
        logits = self.frame["text"].reshape(-1).astype(mx.float32)
        neurons = None
        if ("mlp", 0) in self.frame:
            neurons = mx.concatenate([self.frame[("mlp", i)].reshape(1, -1).astype(mx.float32) for i in range(layers)], axis=0)
            mx.eval(neurons)
            neurons = np.array(neurons)
        self.neurons = neurons
        mx.eval(stacked, logits)
        self.frame = {}
        return np.array(stacked), np.array(mx.softmax(logits))


class Listener:
    def __init__(self, repo, neurons=False):
        self.moshi = Moshi(repo)
        model = self.moshi.model
        self.layers = len(model.transformer.layers)
        self.sink = Sink()
        for index in range(self.layers):
            if neurons:
                layer = model.transformer.layers[index]
                layer.gating = NeuronTap(layer.gating, index, self.sink)
            model.transformer.layers[index] = Recorder(model.transformer.layers[index], index, self.sink)
        model.text_linear = TextHead(model.text_linear, self.sink)
        codec = rustymimi.Tokenizer(self.moshi.mimi, num_codebooks=8)
        warm = [np.asarray(codec.encode_step(np.zeros((1, 1, FRAME), dtype=np.float32)))[0, :8, 0] for _ in range(12)]
        self.silence_codes = warm[-1].astype(np.int64)

    def listen(self, audio, seed=0):
        from moshi_mlx import models, utils

        model = self.moshi.model
        mx.random.seed(seed)
        model.warmup()
        codec = rustymimi.Tokenizer(self.moshi.mimi, num_codebooks=8)
        lead = np.zeros(int(LEAD_S * SAMPLE_RATE), dtype=np.float32)
        tail = np.zeros(int(TAIL_S * SAMPLE_RATE), dtype=np.float32)
        stream = np.concatenate([lead, audio, tail])
        stream = np.pad(stream, (0, (-len(stream)) % FRAME))
        frames = stream.reshape(-1, FRAME)
        silence = self.silence_codes

        def keep_quiet_text(tokens):
            tokens[:] = TEXT_PAD

        def keep_quiet_audio(tokens):
            for codebook in range(tokens.shape[1]):
                tokens[:, codebook, 0] = int(silence[codebook])

        gen = models.LmGen(model=model, max_steps=len(frames) + 5, text_sampler=utils.Sampler(top_k=25),
                           audio_sampler=utils.Sampler(top_k=250), check=False,
                           on_text_hook=keep_quiet_text, on_audio_hook=keep_quiet_audio)
        states, speak_probs, top_tokens, emitted, neurons = [], [], [], [], []
        for frame in frames:
            user_tokens = mx.array(codec.encode_step(frame[None, None, :])).transpose(0, 2, 1)[:, :, :8]
            emitted.append(gen.step(user_tokens[0])[0].item())
            hidden, probs = self.sink.take(self.layers)
            states.append(hidden)
            if self.sink.neurons is not None:
                neurons.append(self.sink.neurons.astype(np.float16))
            speak_probs.append(float(1.0 - probs[TEXT_PAD]))
            words = np.argsort(probs)[::-1]
            top_tokens.append(int(next(t for t in words if t not in (TEXT_PAD, 0))))
        lead_frames = len(lead) // FRAME
        speech_frames = int(np.ceil(len(audio) / FRAME))
        return {"states": np.stack(states), "neurons": np.stack(neurons) if neurons else None, "speak_prob": np.array(speak_probs), "top_token": np.array(top_tokens),
                "emitted": np.array(emitted), "speech": (lead_frames, lead_frames + speech_frames)}


def clip_table(scenes_path, candidates):
    spec = yaml.safe_load(scenes_path.read_text())
    by_id = {s["id"]: s for s in spec["scenes"]}
    rows = []
    for path in sorted(candidates.glob("*.wav")):
        match = CANDIDATE.match(path.name)
        if not match or match["scene"] not in by_id:
            continue
        scene = by_id[match["scene"]]
        if match["delivery"] not in scene["deliveries"]:
            continue
        rows.append({"file": str(path), "scene": match["scene"], "delivery": match["delivery"],
                     "turn": int(match["turn"]), "sentence": int(match["sentence"]), "take": int(match["take"]),
                     "same_words": bool(scene.get("same_words")),
                     "text": json.loads(path.with_suffix(".json").read_text())["text"]})
    return rows


def capture(args):
    rows = clip_table(args.scenes, args.root / "candidates")
    if args.only:
        rows = [r for r in rows if r["scene"] in args.only]
    if args.limit:
        rows = rows[: args.limit]
    listener = Listener(args.repo)
    during, after, speak_during, speak_after, first_word = [], [], [], [], []
    started = time.time()
    for index, row in enumerate(rows, 1):
        result = listener.listen(load_turn(row["file"]))
        start, stop = result["speech"]
        if not (result["emitted"] == TEXT_PAD).all():
            raise RuntimeError(f"Moshi's own text was not held silent for {row['file']}")
        during.append(result["states"][start:stop].mean(axis=0).astype(np.float16))
        after.append(result["states"][stop:].mean(axis=0).astype(np.float16))
        speak_during.append(result["speak_prob"][start:stop].mean())
        speak_after.append(result["speak_prob"][stop:].mean())
        peak = stop + int(np.argmax(result["speak_prob"][stop:]))
        first_word.append(listener.moshi.tokenizer.id_to_piece(int(result["top_token"][peak])).replace("▁", ""))
        if index % 20 == 0 or index == len(rows):
            print(f"listened {index}/{len(rows)} in {time.time() - started:.0f}s", flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out / "states.npz", during=np.stack(during), after=np.stack(after),
                        speak_during=np.array(speak_during), speak_after=np.array(speak_after))
    for row, word in zip(rows, first_word):
        row["likely_first_word"] = word
    (args.out / "clips.json").write_text(json.dumps(rows, indent=2))
    print(args.out / "states.npz")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenes", type=Path, default=ROOT / "scripts/duplex_scenes.yaml")
    parser.add_argument("--root", type=Path, default=ROOT / "out/duplex-scenes")
    parser.add_argument("--out", type=Path, default=ROOT / "out/tone-probe")
    parser.add_argument("--repo", default="kyutai/moshiko-mlx-q8")
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--limit", type=int)
    capture(parser.parse_args())


if __name__ == "__main__":
    main()
