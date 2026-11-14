"""Feed a recorded wav to Moshi as the user's stream and save what Moshi says.

Usage: python moshi_offline.py IN.wav OUT.wav [--repo kyutai/moshiko-mlx-q8] [--seed 0]
Prints Moshi's text stream with the time of each word, and the speed relative to real time.
"""
import argparse, json, time
import numpy as np
import mlx.core as mx
import mlx.nn as nn
import rustymimi, sentencepiece, sphn
from huggingface_hub import hf_hub_download
from moshi_mlx import models, utils

FRAME = 1920  # samples per 80 ms frame at 24 kHz

p = argparse.ArgumentParser()
p.add_argument("infile"); p.add_argument("outfile")
p.add_argument("--repo", default="kyutai/moshiko-mlx-q8")
p.add_argument("--seed", type=int, default=0)
p.add_argument("--trace")
args = p.parse_args()

bits = 8 if args.repo.endswith("q8") else 4 if args.repo.endswith("q4") else None
weights = hf_hub_download(args.repo, f"model.q{bits}.safetensors" if bits else "model.safetensors")
mimi = hf_hub_download(args.repo, "tokenizer-e351c8d8-checkpoint125.safetensors")
spm = hf_hub_download(args.repo, "tokenizer_spm_32k_3.model")

mx.random.seed(args.seed)
cfg = models.config_v0_1()
model = models.Lm(cfg)
model.set_dtype(mx.bfloat16)
if bits:
    nn.quantize(model, bits=bits, group_size=32 if bits == 4 else 64)
t0 = time.time(); model.load_weights(weights, strict=True); model.warmup()
print(f"model loaded and warmed up in {time.time() - t0:.1f}s")
tok = sentencepiece.SentencePieceProcessor(spm)
codec = rustymimi.Tokenizer(mimi, num_codebooks=8)

pcm, _ = sphn.read(args.infile, sample_rate=24000)
steps = pcm.shape[-1] // FRAME
gen = models.LmGen(model=model, max_steps=steps + 5, text_sampler=utils.Sampler(), audio_sampler=utils.Sampler(), check=False)
out, words = [], []
start = time.time()
for i in range(steps):
    frame = pcm[:, i * FRAME:(i + 1) * FRAME]
    user_tokens = mx.array(codec.encode_step(frame[None, 0:1])).transpose(0, 2, 1)[:, :, :8]
    text_token = gen.step(user_tokens[0])[0].item()
    audio_tokens = gen.last_audio_tokens()
    if text_token not in (0, 3):
        words.append((round(i * 0.08, 2), tok.id_to_piece(text_token).replace("▁", " ")))
    if audio_tokens is not None:
        out.append(codec.decode_step(np.array(audio_tokens[:, :, None]).astype(np.uint32)))
elapsed = time.time() - start
audio = np.concatenate(out, axis=-1)[0, 0]
rustymimi.write_wav(args.outfile, audio, sample_rate=24000)
print(f"{steps} frames ({steps * 0.08:.1f}s of audio) in {elapsed:.1f}s = {steps * 0.08 / elapsed:.2f}x real time")
print("text stream:", "".join(w for _, w in words))
print("word times:", words[:60])
if args.trace:
    json.dump({"frames": steps, "elapsed_s": elapsed, "words": words}, open(args.trace, "w"))
