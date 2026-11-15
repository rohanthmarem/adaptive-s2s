import argparse
import json
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

import mlx.core as mx
import mlx.nn as nn
import numpy as np
import rustymimi
import sentencepiece
import sphn
from huggingface_hub import hf_hub_download
from moshi_mlx import models, utils

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RATE = 24000
FRAME = 1920
FRAME_S = FRAME / SAMPLE_RATE
TEXT_PAD = 3
TEXT_WORD_START = 0
SPEAKING_RMS = 0.01


@dataclass
class Timing:
    greet_max_s: float = 5.0
    greet_quiet_s: float = 0.6
    reply_wait_max_s: float = 8.0
    reply_quiet_s: float = 1.2
    reply_max_s: float = 20.0
    lead_in_s: float = 0.3


@dataclass
class Conversation:
    user_track: list = field(default_factory=list)
    moshi_track: list = field(default_factory=list)
    words: list = field(default_factory=list)
    text_tokens: list = field(default_factory=list)
    events: list = field(default_factory=list)


class Moshi:
    def __init__(self, repo):
        bits = 8 if repo.endswith("q8") else 4 if repo.endswith("q4") else None
        self.repo = repo
        self.weights = hf_hub_download(repo, f"model.q{bits}.safetensors" if bits else "model.safetensors")
        self.mimi = hf_hub_download(repo, "tokenizer-e351c8d8-checkpoint125.safetensors")
        self.tokenizer = sentencepiece.SentencePieceProcessor(hf_hub_download(repo, "tokenizer_spm_32k_3.model"))
        self.config = models.config_v0_1()
        self.model = models.Lm(self.config)
        self.model.set_dtype(mx.bfloat16)
        if bits:
            nn.quantize(self.model, bits=bits, group_size=32 if bits == 4 else 64)
        self.model.load_weights(self.weights, strict=True)

    def converse(self, turns, seed, timing):
        mx.random.seed(seed)
        self.model.warmup()
        codec = rustymimi.Tokenizer(self.mimi, num_codebooks=8)
        max_frames = int((timing.greet_max_s + sum(len(t) / SAMPLE_RATE + timing.reply_max_s for t in turns) + 5) / FRAME_S)
        gen = models.LmGen(model=self.model, max_steps=max_frames + 5, text_sampler=utils.Sampler(top_k=25),
                           audio_sampler=utils.Sampler(top_k=250), check=False)
        talk = Conversation()
        step = {"index": 0}

        def advance(user_frame):
            index = step["index"]
            if index >= max_frames:
                raise RuntimeError("Conversation exceeded its frame budget")
            user_tokens = mx.array(codec.encode_step(user_frame[None, None, :])).transpose(0, 2, 1)[:, :, :8]
            text_token = gen.step(user_tokens[0])[0].item()
            talk.text_tokens.append(text_token)
            talk.user_track.append(user_frame)
            if text_token not in (TEXT_PAD, TEXT_WORD_START):
                talk.words.append((round(index * FRAME_S, 2), self.tokenizer.id_to_piece(text_token).replace("▁", " ")))
            audio_tokens = gen.last_audio_tokens()
            if audio_tokens is None:
                decoded = np.zeros(FRAME, dtype=np.float32)
            else:
                decoded = np.asarray(codec.decode_step(np.array(audio_tokens[:, :, None]).astype(np.uint32)))[0, 0]
            talk.moshi_track.append(decoded)
            step["index"] += 1
            return float(np.sqrt(np.mean(decoded**2))) > SPEAKING_RMS or text_token not in (TEXT_PAD, TEXT_WORD_START)

        silence = np.zeros(FRAME, dtype=np.float32)

        def wait_for_moshi(max_wait_s, quiet_s, total_max_s, phase):
            start = step["index"]
            spoke, quiet = False, 0
            while True:
                speaking = advance(silence)
                spoke = spoke or speaking
                quiet = 0 if speaking else quiet + 1
                elapsed = (step["index"] - start) * FRAME_S
                if spoke and quiet * FRAME_S >= quiet_s:
                    reason = "moshi finished"
                    break
                if not spoke and elapsed >= max_wait_s:
                    reason = "moshi stayed silent"
                    break
                if elapsed >= total_max_s:
                    reason = "time limit"
                    break
            talk.events.append({"phase": phase, "start_s": round(start * FRAME_S, 2),
                                "end_s": round(step["index"] * FRAME_S, 2), "moshi_spoke": spoke, "ended_because": reason})

        wait_for_moshi(timing.greet_max_s, timing.greet_quiet_s, timing.greet_max_s + 3, "greeting")
        for turn_index, turn in enumerate(turns):
            for _ in range(int(timing.lead_in_s / FRAME_S)):
                advance(silence)
            start = step["index"]
            padded = np.pad(turn, (0, (-len(turn)) % FRAME))
            overlapped = sum(advance(frame) for frame in padded.reshape(-1, FRAME))
            talk.events.append({"phase": f"user turn {turn_index + 1}", "start_s": round(start * FRAME_S, 2),
                                "end_s": round(step["index"] * FRAME_S, 2), "moshi_frames_while_user_spoke": int(overlapped)})
            wait_for_moshi(timing.reply_wait_max_s, timing.reply_quiet_s, timing.reply_max_s, f"reply {turn_index + 1}")
        return talk


def load_turn(path):
    pcm, _ = sphn.read(str(path), sample_rate=SAMPLE_RATE)
    audio = pcm.mean(axis=0).astype(np.float32)
    if not len(audio) or not np.isfinite(audio).all():
        raise ValueError(f"Unreadable or empty user turn: {path}")
    return audio


def save(talk, out_dir, meta):
    out_dir.mkdir(parents=True, exist_ok=True)
    moshi = np.concatenate(talk.moshi_track)
    user = np.concatenate(talk.user_track)
    sphn.write_wav(str(out_dir / "moshi.wav"), moshi, SAMPLE_RATE)
    sphn.write_wav(str(out_dir / "conversation.wav"), np.stack([moshi, user]), SAMPLE_RATE)
    sphn.write_wav(str(out_dir / "mix.wav"), np.clip(0.8 * moshi + 0.8 * user, -1, 1), SAMPLE_RATE)
    trace = {**meta, "duration_s": len(moshi) / SAMPLE_RATE, "events": talk.events,
             "moshi_text": "".join(w for _, w in talk.words).strip(), "words": talk.words, "text_tokens": talk.text_tokens}
    (out_dir / "trace.json").write_text(json.dumps(trace, indent=2))
    return trace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=ROOT / "out/duplex-scenes/manifest.json")
    parser.add_argument("--out", type=Path, default=ROOT / "out/duplex-scenes/moshi")
    parser.add_argument("--repo", default="kyutai/moshiko-mlx-q8")
    parser.add_argument("--seeds", type=int, default=2)
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--turns", type=Path, nargs="*", help="Run one conversation from these user-turn wavs instead of a manifest")
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    moshi = Moshi(args.repo)
    timing = Timing()
    if args.turns:
        seed = args.seed if args.seed is not None else secrets.randbits(31)
        trace = save(moshi.converse([load_turn(p) for p in args.turns], seed, timing), args.out,
                     {"repo": args.repo, "seed": seed, "turn_files": [str(p) for p in args.turns]})
        print(json.dumps({k: trace[k] for k in ("seed", "moshi_text", "events")}, indent=2))
        return
    entries = json.loads(args.manifest.read_text())
    seeds = [secrets.randbits(31) for _ in range(args.seeds)] if args.seed is None else [args.seed + i for i in range(args.seeds)]
    for entry in entries:
        if args.only and entry["scene"] not in args.only:
            continue
        turns = [load_turn(t["file"]) for t in entry["turns"]]
        for seed in seeds:
            started = time.time()
            name = f"{entry['scene']}_{entry['delivery']}_seed{seed}"
            trace = save(moshi.converse(turns, seed, timing), args.out / name,
                         {"repo": args.repo, "seed": seed, "scene": entry["scene"], "delivery": entry["delivery"],
                          "turn_texts": [t["text"] for t in entry["turns"]], "timing": timing.__dict__})
            print(f"{name}: {time.time() - started:.0f}s | {trace['moshi_text'][:160]}", flush=True)


if __name__ == "__main__":
    main()
