# Adaptive speech-to-speech

A voice system that changes how it talks based on how you talk. It listens to a spoken turn, measures the
pace and the wording, keeps a running style state, and answers in a matching register and pace. When it
detects distress it switches to supportive wording and slower speech.

This is **v1: turn-adaptive, not live**. It hears a whole turn, then replies. Everything runs locally.

The plan, the two design perspectives (Fable and Astra) and the evaluation design are in
[`docs/PLAN.md`](docs/PLAN.md).

```
user audio ──> ASR ──────────────> words ──> register cues ─┐
     │                                                      ├─> style state ──> policy ─┬─> LLM style brief ──> reply text ─┐
     └──────> pace, pauses, (emotion model) ────────────────┘                            └─> TTS speed and pauses <──────────┴─> reply audio
```

## Quick start (Apple Silicon Mac)

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[mlx,mic,affect,dev]"
.venv/bin/s2s fetch-models          # about 5 GB: Whisper, Kokoro, Qwen2.5-7B, emotion2vec+
.venv/bin/s2s doctor                # shows which models will be used and whether they are present
.venv/bin/s2s demo --compare-static # four-turn scripted conversation, then open out/demo/index.html
```

The demo page plays each user turn and both replies (adaptive and static baseline) and shows why each
decision was made.

## Commands

| Command | What it does |
|---|---|
| `s2s doctor` | Lists the ASR, emotion, LLM and TTS backends and whether their files are present. Exit code 1 if something is missing. |
| `s2s fetch-models` | Downloads the models that are missing. |
| `s2s turn IN.wav` | One turn. Prints what it heard, what it measured, each decision, and the reply. Writes `reply.wav` and `trace.json`. |
| `s2s converse A.wav B.wav ...` | Several turns in one conversation, with the state carried across turns. |
| `s2s talk` | Push-to-talk with the microphone: Enter to start, Enter to stop. |
| `s2s demo [--compare-static]` | The scripted demo (needs macOS `say`). |
| `s2s calibrate-tts` | Measures the speed Kokoro really produces for each setting and saves the table. |
| `s2s eval ...` | The evaluation harness (below). |

Useful options on `turn`, `converse`, `talk` and `demo`:

- `--arm full|static|text-only|voice-only` picks one cell of the ablation.
- `--llm auto|mlx|openai|template` picks the reply model. `template` is a labelled stub for machines without
  a model. It is never chosen automatically.
- `--affect auto|off|emotion2vec` turns the emotion model on or off.
- `--locked-text "..."` gives the reply model fixed words, so only the delivery varies.

## How it adapts

| Signal | Measured from | Changes |
|---|---|---|
| Pace (syllables per second, pauses excluded) | The waveform | Reply speed. It follows 60% of your deviation from a neutral rate, within ±15%. |
| Register (slang, reductions, contractions, formal markers) | The transcript | The style brief: casual, neutral or formal. It may reuse at most two expressions you used. It never invents slang. |
| Distress (distress words, or a confident emotion-model reading) | Transcript, and the optional emotion model | Supportive wording, speed capped at 0.95x, longer pauses. It switches on at once and fades over a few turns. |
| Crisis wording | The transcript | A fixed reply that points to real help. No model is involved. |

The state is conversation-scoped. It holds no demographics and starts empty every time. Every number in the
policy is in [`src/adaptive_s2s/config.py`](src/adaptive_s2s/config.py).

Each turn writes a JSON trace with the measurements, the state before and after, every decision with its
evidence, the reply, the speed that was asked for and the speed that was measured in the reply audio.

## Evaluation harness

The claim to test: **changing only how something is said changes the response, and the change disappears
when the acoustic evidence is shuffled.** The design is in section 5 of the plan.

```bash
# 1. Build stimuli (written under data/, which git ignores)
.venv/bin/s2s eval stimuli --set say      --out data/say            # same words, three speeds, three voices
.venv/bin/s2s eval stimuli --set register --out data/register       # same request in three registers
.venv/bin/s2s eval stimuli --set psola    --source data/say/manifest.jsonl --out data/psola      # stretched copies
.venv/bin/s2s eval stimuli --set nuisance --source data/say/manifest.jsonl --out data/nuisance   # gain, silence, noise
.venv/bin/s2s eval stimuli --set crema    --out data/crema          # acted emotion (downloads CREMA-D clips)
.venv/bin/s2s eval stimuli --set human    --source data/recordings --out data/human    # your own recordings

# 2. Run the arms. `locked` gives every delivery identical words. `--shuffled` adds the negative control.
.venv/bin/s2s eval run --manifest data/say/manifest.jsonl --out runs/say --track locked \
    --arms static full --shuffled --seeds 0,1

# 3. Report: every number comes with its n and a cluster-bootstrap confidence interval
.venv/bin/s2s eval report --run runs/say

# 4. Human ratings: export a blind sheet, collect ratings, score the appropriateness gain
.venv/bin/s2s eval ratings-export --run runs/say --out ratings/say --group-label rate_wpm
.venv/bin/s2s eval ratings-score --sheet ratings/say/ratings_sheet.csv --key ratings/say/ratings_key.json
```

How to record your own stimuli: [`src/adaptive_s2s/evals/RECORDING_GUIDE.md`](src/adaptive_s2s/evals/RECORDING_GUIDE.md).

### Smoke run (synthetic voices, not a result)

`scripts/smoke_eval.sh` runs the whole harness in about 10 minutes. These numbers come from that script
on 2026-11-11. The inputs are macOS voices and acted clips, on dev scripts only. They show that the harness
works and that the wiring is right. **They are not results:** there are no human recordings, no held-out
stimuli and no human ratings yet. Intervals are 95% bootstrap intervals over scripts.

| Check | Stimuli | What came out |
|---|---|---|
| Reply pace follows the speaker | 8 scripts x 5 speeds, identical words, 120 turns | `full`: measured reply speed rises 0.079x per syll/s of user pace (0.061 to 0.103). `full+shuffled`: 0.008 (-0.021 to 0.036). `static`: 0 by construction. |
| Wording follows the register | 4 requests x 3 registers, 2 seeds | `text-only`, casual minus formal: +5.7 contractions per 100 words (0.7 to 12.4), -0.9 formal markers (-1.6 to -0.3), -9.0 words per sentence (-12.6 to -4.1). `static`: every interval includes zero. Caricature rate 0%. |
| The same, through real speech recognition | Same, end-to-end track | Word error rate 5%. The register shift survives. |
| Sad voice, neutral words | 41 CREMA-D clips, which are in the emotion model's training data | `full` switched to supportive wording on 7 of 10 sad clips, 0 of 11 neutral, 0 of 10 angry and 1 of 10 happy (a false reaction). `static`: never. |
| Recording conditions do not move the controls | 4 scripts x gain, silence, noise | Speed changed by 0.000 for ±6 dB gain, 0.003 for leading silence, 0.001 for noise at 30 dB SNR and 0.036 at 20 dB SNR. Register and support never changed. |

One example of the emotion path, and of why it needs human ratings. The words are "I would like a new alarm
clock", spoken in a sad voice:

- `static`: "Sure thing! What kind of features are you looking for in your new alarm clock?"
- `full`: "I'm sorry to hear you're not happy with your alarm clock. Would you like help finding a new one
  that might suit your needs better?"

The reply changed because of the voice alone. Whether that change is appropriate is what the blind rating
sheet measures. The export works on these runs (160 blind trials from the pace run).

## Compute and cost

Everything is local. Cost so far: $0. Measured on an M5 MacBook Pro with 32 GB, over the 120 turns of the pace smoke run.

| Stage | Model | Size | Time per turn (median) |
|---|---|---|---|
| Speech recognition | faster-whisper `base.en`, CPU int8 | 145 MB | 0.47 s |
| Measurements and policy | numpy, Praat (pitch) | none | 0.09 s |
| Emotion (optional) | emotion2vec+ base, needs PyTorch | about 1 GB installed | included above |
| Reply | Qwen2.5-7B-Instruct 4-bit, MLX | 4.3 GB | 1.03 s |
| Speech | Kokoro-82M ONNX | 355 MB | 1.10 s |
| **Whole turn** | | | **2.7 s** (95th percentile 3.7 s) |

The reply audio is synthesised in full before it plays. Streaming it sentence by sentence would cut the wait
to roughly the first three rows plus one sentence.

Nothing here needs a GPU rental or a paid API. Adding a commercial reference system or an expressive paid
voice would cost money. Ask before doing that.

## What is verified

Verified on this Mac on 2026-11-11 with the real models:

- `pytest`: 36 tests pass, including the ones that load Whisper and Kokoro.
- `s2s doctor`, `s2s turn`, `s2s converse`, `s2s demo --compare-static` and `s2s calibrate-tts`.
- `--llm openai` against a local OpenAI-compatible server (`mlx_lm server`), and `--llm template`, which is
  labelled `STUB=True` in the output and in the trace.
- The eval harness end to end: the `say`, `register`, `psola`, `nuisance` and `crema` builders, runs on the
  locked and end-to-end tracks with the shuffled control, the reports, and the rating-sheet export.

Not verified:

- `s2s talk` (microphone) and `--play` (playback). They need a person at the Mac.
- `s2s fetch-models` from an empty cache. It was only run with the models already present.
- The `human` stimulus builder, `ratings-score` and the `full+oracle` arm. They pass unit tests on synthetic
  data. No real recordings or ratings exist yet.
- Any platform other than this Mac.

## Known limits

- **No intonation control.** Kokoro has a speed setting and nothing else. v1 adapts pace and pauses, not
  intonation.
- **The emotion model is unreliable.** On four CREMA-D clips it read acted sadness as "neutral, 1.00". Its
  training data includes the public acted-emotion sets, so only fresh recordings test it fairly.
- **The register rules are a short word list.** They catch "ngl", "lowkey" and "gonna". Real casual speech
  varies far more.
- **Speech recognition changes slang.** In the demo "ngl" became "and gl" and "gotta bail" became "got a
  bail". The register still came out casual from the other cues.
- **Kokoro does not deliver the speed it is asked for.** Asking for 0.90x gives about 0.95x. The adapter
  corrects for this with a measured table (`s2s calibrate-tts`), and every trace records the measured speed.
- **macOS `say` cannot speak slower than about 4.6 syllables per second.** Slower test audio is made by
  stretching.
- **Turn-based.** No streaming, no barge-in, no backchannels.

## Other platforms

The reply model is the only Mac-specific part. On Linux or Windows, run any OpenAI-compatible server
(Ollama, the llama.cpp server, LM Studio) and point the CLI at it:

```bash
export S2S_OPENAI_BASE_URL=http://127.0.0.1:11434/v1
export S2S_OPENAI_MODEL=qwen2.5:7b
.venv/bin/s2s turn in.wav --llm openai
```

The demo and the `say` and `register` stimulus builders need macOS `say`. Everything else is portable.

## Layout

```
docs/PLAN.md                     the plan: approach, both perspectives, evaluation, schedule, risks
docs/research/                   preliminary research, the Astra consult (verbatim), the claim check
scripts/smoke_eval.sh            the smoke evaluation, start to finish
src/adaptive_s2s/
  acoustic.py  register.py       measurements: how it was said, what words were used
  state.py  policy.py  config.py the running style state, the policy, every tunable number
  prompting.py                   style brief, safety reply, reply clean-up
  asr.py  affect.py  llm.py  tts.py  audio.py     model adapters
  pipeline.py  cli.py  demo.py   one turn end to end, the command line, the demo page
  evals/                         stimuli, runner, metrics, ratings, report, scripts.yaml
tests/                           unit tests (fast) and model tests (marked slow)
```

## Tests

```bash
.venv/bin/python -m pytest -q                 # everything, including tests that load the models
.venv/bin/python -m pytest -q -m "not slow"   # fast tests only
```
