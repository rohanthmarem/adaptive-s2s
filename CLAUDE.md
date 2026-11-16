# Adaptive speech-to-speech

Context for any agent working in this repo. Read this first, then `docs/duplex/PLAN.md`.

## What this is

Rohanth's project to build a voice model that changes how it responds based on *how* the user sounds (tone, pace, hesitation, emotion), not only on the words. It started as the "Adaptive Speech-to-Speech" entry in his Notion weekend-project list, inspired by Block's Dessa and Decagon. The output is a blog series (rohanth.com and X) aimed at landing an ML co-op, so every claim has to survive a skeptical ML engineer: controls, held-out speakers, no overclaiming.

## Where it has been (2026-11-11 to 2026-11-15)

1. **v1 cascade (done, kept as baseline).** Whisper ASR, pace and register measurements, a running style state, a policy, Qwen2.5-7B (MLX) reply with a style brief, Kokoro TTS at an adapted speed. CLI `s2s`, eval harness with static and shuffled-control arms. Code in `src/adaptive_s2s/`, plan in `docs/PLAN.md`, usage in `README.md`.
2. **Pivot to full duplex.** Rohanth decided a cascade is not novel. New goal: his own full-duplex speech-to-speech model with adaptive tone and empathy. Decision (Fable and Astra independently): fine-tune Kyutai's **Moshi** (LoRA SFT) on paired data, and prove with a scrambled-pairing control and held-out speakers that the fine-tune made it *listen*. Training from scratch is out of reach (Moshi used ~7M hours). Plan: `docs/duplex/PLAN.md`; primer for someone with no audio-ML background: `docs/duplex/primer.html` (published at https://claude.ai/artifact/MJu8GiYAPoBHD5aYTDgq5p); research with sources: `docs/duplex/research/`.
3. **Moshi running locally** on the Mac via MLX (Moshiko q8). `scripts/moshi-local` starts the web UI at http://localhost:8998. Offline runner: `docs/duplex/moshi_offline.py`.
4. **Activation hooks** (`docs/duplex/moshi_hooks.py`): capture, additive steering and activation patching at temporal-transformer layer outputs. Self-patch reproduces outputs exactly.
5. **Test stimuli.** OpenAI TTS was blocked (no credits). xAI Grok TTS (voice "Eve") was used for the first matched and extreme sets; Rohanth judged them unrealistic, with emotion that did not persist. Switched to local **Qwen3-TTS** (voice "Ryan"), generated sentence by sentence with the same emotion direction, best of N takes, each sentence scored by emotion2vec. Scenes must logically fit the emotion being tested, and each has a calm same-words control.
6. **Call-style Moshi harness**: Moshi greets first, user turn starts once Moshi is quiet, reply ends after 1.2 s of silence; saves stereo, mix and timeline.
7. **Interpretability findings** (synthetic single voice, single sentences):
   - Tone is linearly readable in every one of Moshi's 32 layers (84-88% on 3-way same-words; 79% already in input embeddings, since the Mimi codec carries it). One shared sad/excited direction transfers across scenes (AUC 0.98-1.0 on an unseen scene).
   - At the text output head the tone mostly vanishes: same chance of speaking, same first word ("Yeah"). **Moshi hears tone but barely uses it when deciding what to say.** So fine-tuning only has to connect an existing signal to the response.
   - 12-emotion run (12 emotions x 10 sentences x 4 voices, 480 clips): probe gets 38% on an unseen voice (chance 8%, shuffled 5%). Angry, amused, happy are easy; sarcastic, contemptuous, anxious, bored are hard. The main emotion axis tracks pitch height and movement (r 0.81, 0.75), not loudness (0.07). Only 86 of 360,448 MLP neurons pass the strict cross-voice bar (0 with shuffled labels): 52 anger, 15 sad, none sarcasm, mostly layers 0-10.
   - Behaviourally: sad-voiced "they called me back about the job" still often got congratulations. Greeting is fixed per seed.

## Viewable outputs (generated, in `out/`, not in git)

- `out/tone-probe/post.html`: the write-up in rohanth.com style (fonts and audio embedded).
- `out/emotions/atlas/index.html`: Goodfire-style neuron atlas, 253 neuron poles with per-frame traces.
- `out/tone-probe/explainer.html`, `out/tone-probe/report.html`, `out/duplex-scenes/review.html`, `out/matched-xai/review.html`, `out/demo/index.html`.

Builders: `scripts/moshi_tone_viz.py` with `scripts/moshi_tone_post.html`; `scripts/neuron_atlas.py` with `scripts/neuron_atlas.html`. Pipeline: `scripts/emotion_render.py` then `scripts/emotion_select.py` then `scripts/moshi_neurons.py` (capture, analyse, trace) then `scripts/neuron_atlas.py build`. Chain long steps with `set -o pipefail`.

## Open next steps

- Causal test: add the learned "sad" direction to Moshi's layers while it hears a plain reading, and see whether replies change (steering vs. fine-tuning).
- Real-speech validation: Rohanth's and friends' recordings; the "sad" direction may partly be "Qwen Ryan's sad style".
- Paired training data: scenario + intended response policy written together; generated audio checked against what was requested. Check TTS licences before training on generated audio.
- Stage 2 LoRA fine-tune on a rented 80 GB GPU (budget approved only up to the stated amounts; ask before spending). The official Moshi fine-tune recipe does not run on a Mac.
- Human ratings for appropriateness; automatic metrics are not enough.

## Environment

- Apple Silicon Mac, MLX. Three venvs, all uv / Python 3.12: `.venv` (cascade, tests), `.venv-moshi` (moshi_mlx, hooks, probes), `.venv-tts` (Qwen3-TTS). Run Moshi with `HF_HUB_OFFLINE=1`; weights are cached (~8.5 GB).
- API keys are not stored in the repo; ask via secure input when needed (xAI worked, OpenAI account had no credits).
- Only one Moshi process at a time: two at once swaps memory and crawls.

## Working rules

- `agentkit verify` (checks in `.agent/agentkit.toml`) must pass before calling anything done; `full` needs the GPU and takes several minutes.
- No code comments; no new Markdown docs unless asked.
- Label generated emotions as *requested* until measured; keep content accuracy and emotional appropriateness separate; never reroll seeds to hide a bad result.

## History

- Full transcript of the build thread: `docs/history/build-thread.md`.
- T3 thread: "Build Adaptive Speech-to-Speech Pipeline" (febc58a2-fa35-4026-9ae1-d303f1fee8f9).
- Earlier docs: `docs/research/` (prelim research, Astra consult, claim check).
