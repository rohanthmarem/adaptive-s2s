"""Feed a recorded wav to Moshi as the user's stream and save what Moshi says.

Usage: python moshi_offline.py IN.wav OUT.wav [--repo kyutai/moshiko-mlx-q8] [--seed 0]
Prints Moshi's text stream with the time of each word, and the speed relative to real time.
"""
import argparse, json, time, secrets
import numpy as np
import mlx.core as mx
import mlx.nn as nn
import rustymimi, sentencepiece, sphn
from huggingface_hub import hf_hub_download
from moshi_mlx import models, utils
from moshi_hooks import ResidualHooks
from contextlib import nullcontext

FRAME = 1920

p = argparse.ArgumentParser()
p.add_argument("infile"); p.add_argument("outfile")
p.add_argument("--repo", default="kyutai/moshiko-mlx-q8")
p.add_argument("--seed", type=int, default=None)
p.add_argument("--trace")
p.add_argument("--capture", help="Save residual activations to an NPZ file")
p.add_argument("--layers", default="0,8,24", help="Zero-based temporal layers")
p.add_argument("--start-frame", type=int, default=0)
p.add_argument("--stop-frame", type=int)
p.add_argument("--direction", help="Add a raw residual-space vector from an NPY file")
p.add_argument("--strength", type=float, default=0.0)
p.add_argument("--donor", help="Replace selected activations from a captured NPZ")
p.add_argument("--stop-silence", type=float, help="Stop after this much assistant silence following a response")
p.add_argument("--listen-first", action="store_true", help="Force assistant silence during the initial user input; diagnostic, not unrestricted duplex")
p.add_argument("--context", help="Spoken context WAV, streamed before the user clip without resetting Moshi")
p.add_argument("--prefix-silence", type=float, default=0.0)
p.add_argument("--tail-silence", type=float, default=0.0)
p.add_argument("--sampling", choices=["official", "legacy"], default="official")
args = p.parse_args()
if args.seed is None:
    args.seed = secrets.randbits(32)
if args.prefix_silence < 0 or args.tail_silence < 0 or (args.stop_silence is not None and args.stop_silence <= 0):
    p.error("silence durations must be nonnegative")

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
pcm = pcm.mean(axis=0, keepdims=True)
context_samples = 0
if args.context:
    context, _ = sphn.read(args.context, sample_rate=24000)
    context = context.mean(axis=0, keepdims=True)
    context_samples = context.shape[-1] + 7680
    pcm = np.concatenate([context, np.zeros((1, 7680), dtype=np.float32), pcm], axis=-1)
input_samples = pcm.shape[-1]
if input_samples == 0 or not np.isfinite(pcm).all():
    raise ValueError("Input must contain finite audio samples")
prefix_samples = round(args.prefix_silence * 24000)
pcm = np.pad(pcm, ((0, 0), (prefix_samples, round(args.tail_silence * 24000))))
pcm = np.pad(pcm, ((0, 0), (0, (-pcm.shape[-1]) % FRAME)))
steps = pcm.shape[-1] // FRAME
text_sampler = utils.Sampler(top_k=25) if args.sampling == "official" else utils.Sampler()
audio_sampler = utils.Sampler(top_k=250) if args.sampling == "official" else utils.Sampler()
silence_history = []
silence_codec = rustymimi.Tokenizer(mimi, num_codebooks=8) if args.listen_first else None
listen_frames = (prefix_samples + input_samples + FRAME - 1) // FRAME

def hold_text(tokens):
    if args.listen_first and i < listen_frames:
        tokens[:] = 3

def hold_audio(tokens):
    if args.listen_first and i < listen_frames:
        for codebook, delay in enumerate(cfg.audio_delays[:8]):
            tokens[:, codebook, 0] = int(silence_history[max(0, i-delay)][codebook])

gen = models.LmGen(model=model, on_text_hook=hold_text if args.listen_first else None, on_audio_hook=hold_audio if args.listen_first else None, max_steps=steps + 5, text_sampler=text_sampler, audio_sampler=audio_sampler, check=False)
hooks = None
if args.capture or args.direction or args.donor:
    hooks = ResidualHooks(model, [int(i) for i in args.layers.split(",")],
                          args.start_frame, args.stop_frame, args.direction,
                          args.strength, args.donor, bool(args.capture))
out, words = [], []
all_text_tokens, all_audio_tokens = [], []
response_started = False
quiet_frames = 0
last_text_frame = -1
max_frames = steps
start = time.time()
with hooks if hooks is not None else nullcontext():
    for i in range(steps):
        if hooks is not None:
            hooks.frame = i
        frame = pcm[:, i * FRAME:(i + 1) * FRAME]
        user_tokens = mx.array(codec.encode_step(frame[None, 0:1])).transpose(0, 2, 1)[:, :, :8]
        if args.listen_first and i < listen_frames:
            encoded_silence = silence_codec.encode_step(np.zeros((1, 1, FRAME), dtype=np.float32))
            silence_history.append(np.asarray(encoded_silence)[0, :, 0])
        text_token = gen.step(user_tokens[0])[0].item()
        all_text_tokens.append(text_token)
        audio_tokens = gen.last_audio_tokens()
        if text_token not in (0, 3):
            last_text_frame = i
            words.append((round(i * 0.08, 2), tok.id_to_piece(text_token).replace("▁", " ")))
        if audio_tokens is not None:
            all_audio_tokens.append(np.array(audio_tokens).tolist())
            decoded = codec.decode_step(np.array(audio_tokens[:, :, None]).astype(np.uint32))
            out.append(decoded)
            if i >= listen_frames:
                speaking = float(np.sqrt(np.mean(decoded**2))) > 0.008
                response_started = response_started or speaking
                quiet_frames = 0 if speaking else quiet_frames + 1
                if args.stop_silence and response_started and quiet_frames * 0.08 >= args.stop_silence and (i-last_text_frame)*0.08 >= args.stop_silence:
                    steps = i + 1
                    break
elapsed = time.time() - start
if not out:
    raise ValueError("Input is too short to produce audio")
audio = np.concatenate(out, axis=-1)[0, 0]
rustymimi.write_wav(args.outfile, audio, sample_rate=24000)
print(f"{steps} frames ({steps * 0.08:.1f}s of audio) in {elapsed:.1f}s = {steps * 0.08 / elapsed:.2f}x real time")
print("text stream:", "".join(w for _, w in words))
print("word times:", words[:60])
if args.trace:
    json.dump({"repo": args.repo, "weights_path": weights, "frames": steps, "max_frames": max_frames, "stop_silence_s": args.stop_silence, "elapsed_s": elapsed, "seed": args.seed, "sampling": args.sampling, "listen_first": args.listen_first, "listen_frames": listen_frames if args.listen_first else 0, "input_samples": input_samples, "context_samples": context_samples, "user_end_s": (prefix_samples + input_samples) / 24000, "prefix_silence_s": args.prefix_silence, "tail_silence_s": args.tail_silence, "words": words, "text_tokens": all_text_tokens, "audio_tokens": all_audio_tokens}, open(args.trace, "w"))

if hooks is not None and args.capture:
    hooks.save(args.capture, {"repo": args.repo, "seed": args.seed, "input": args.infile, "frame_seconds": 0.08, "direction": args.direction, "strength": args.strength, "donor": args.donor})
