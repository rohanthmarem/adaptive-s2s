# Adaptive speech-to-speech: plan

Written 2026-11-11. Lead: Fable. Second opinion: Astra (`docs/research/ASTRA_CONSULT.md`, verbatim).
Inputs: `docs/research/PRELIM_RESEARCH.md` and its re-check in `docs/research/CLAIM_CHECK.md`.

## 1. Decision

Build a **turn-based cascade with an explicit running style state**, and treat the experiment as the product.

```
user audio ──> ASR ──────────────> words ──> register cues ─┐
     │                                                      ├─> style state ──> policy ─┬─> LLM style brief ──> reply text ─┐
     └──────> pace, pauses, (emotion model) ────────────────┘                            └─> TTS speed and pauses <──────────┴─> reply audio
```

The claim the project has to earn is causal: **changing only how something is said changes the response in
an appropriate way, and that change disappears when the acoustic evidence is removed or shuffled.**
Everything in v1 exists to make that claim testable. The demo comes out of the same code.

v1 is called **turn-adaptive**, not live or full-duplex. It listens to a whole turn, then answers.

## 2. What v1 does for each behaviour you asked for

| Behaviour | Evidence it uses | What changes | In v1 |
|---|---|---|---|
| Picks up slang and contractions | The words (transcript) | LLM style brief goes casual. It may reuse only expressions the user actually said. | Yes |
| Shifts to workplace language | The words | LLM style brief goes formal: full sentences, no contractions, answer first. | Yes |
| Becomes empathetic for sadness or distress | Distress words, or the emotion model when it is confident | Supportive wording, slower speech, longer pauses. Fixed safety reply for crisis wording. | Yes. The voice-only path is the weakest part (section 8). |
| Matches pace | Measured articulation rate | TTS speed follows 60% of the user's deviation from neutral, clamped to ±15%. | Yes |
| Adapts intonation | Nothing yet | Nothing yet | **No.** Kokoro has speed control but no intonation or emotion control. |

Two channels feed the state and they never mix. Words drive register. The waveform drives pace. Fast speech
is not evidence that someone uses slang.

## 3. Architecture and component picks

All of it runs locally on the M5 MacBook Pro (32 GB). Timings are measured on this machine.

| Stage | Pick | Why | Measured |
|---|---|---|---|
| ASR | faster-whisper `base.en`, CPU int8 | Same transcripts as `small.en` on the test clips, 3x faster | 0.4 s for a 5 s clip |
| Pace and pauses | Energy-based speech detector + syllable count (`acoustic.py`) | Does not depend on ASR word timestamps. The same function measures the reply audio. | Instant |
| Emotion (optional) | emotion2vec+ base through FunASR | Only practical open model. Scores are not calibrated (section 8). | 0.2 s per clip |
| Register | Small rule set on the transcript (`register.py`) | Inspectable. Every decision can be traced to a word. | Instant |
| State | `StyleState` (`state.py`), a pure update function | Loggable and replayable turn by turn | Instant |
| Reply | Qwen2.5-7B-Instruct 4-bit through MLX | Apache-2.0, 4.3 GB, follows a style brief. Any OpenAI-compatible server also works. | See README |
| Speech | Kokoro-82M (ONNX), speed control | Natural enough for human ratings, Apache-2.0, 330 MB | 0.18x real time |

### The state (the "listener profile")

`StyleState` describes how the last few turns were spoken. It is not a profile of a person. It holds no
demographics, starts empty for every conversation, and every field decays.

- **Pace:** running average of articulation rate (syllables per second, pauses excluded). A turn with fewer
  than four words or under one second of speech is not trusted, and the estimate drifts back toward neutral.
- **Register:** two evidence levels, casual and formal, each 0 to 1. A short turn moves them less, because
  "no slang in a three-word reply" is not evidence of anything. The label is sticky so it does not flip
  around the threshold.
- **Support:** fast attack, slow release. One credible signal switches it on at once. Without new evidence it
  fades by 40% per turn.
- **Crisis:** set by this turn's words only. It triggers a fixed safety reply and is never an experimental
  variable.

### The policy

- **Text side:** register label, contraction use, the user's own slang (at most two expressions), a
  three-sentence cap, and the supportive brief.
- **Voice side:** `speed = 1 + 0.6 x (user rate / neutral rate - 1)`, clamped to 0.85-1.15. In supportive
  mode the speed is capped at 0.95 and pauses grow by 40%. A speaker who is already slow is not slowed further.
- Each side can be switched off separately. That gives the four arms of the ablation.

Every number above is in `config.py`. Each one is an engineering choice to be tuned on the dev split, not a
research result.

## 4. Two perspectives

### Fable

1. **This is a measurement problem before it is a modelling problem.** A cascade that adapts is easy to
   build and easy to fool yourself with. The hard part, and the part worth hiring someone for, is showing
   that the audio caused the change.
2. **Converge part of the way, never copy.** People accommodate partially. Full mirroring reads as mockery
   for slang and as escalation for anger. The policy follows 60% of the pace deviation and reuses only
   words the user said.
3. **Keep the emotion path in v1, clearly marked as the weakest link.** It is one of the three behaviours
   you asked for, and "same words, sad voice" is the hook of the blog post. It stays behind a confidence
   gate, and the emotion model is never also the judge.
4. **Use a natural voice.** People will rate whether replies sound appropriate. A robotic voice would
   confound those ratings.
5. **Make saturation impossible by construction.** Measure continuous effects (slopes, thresholds, lag),
   not accuracy on a fixed set (section 5).
6. **Add one outside reference system after the internal ablation is clean.** Readers will ask how a
   commercial voice API does on the same test.

### Astra (summary)

1. Cascade, yes, but build a **turn-by-turn adaptation experiment before a streaming agent**. The preliminary
   design bundles too many problems into one weekend.
2. The smallest honest demonstration is pace: identical words at different speeds must change the **actual
   output audio**. Measure the generated audio, not the requested control.
3. Rename the profile to a conversation style state. Do not infer distress from low pitch, low volume or
   slow speech. Drop pitch matching, demographic inference and a single global confidence number.
4. Replace the seven arms with a **2x2 ablation** (text policy x voice policy), a shuffled-features control
   and an oracle. Drop all outside systems this weekend.
5. Replace "response divergence" as the headline. Randomness and irrelevant sympathy both raise it. Use
   **audio-conditioned appropriateness gain**: blind listeners rate each reply against the delivery it was
   made for and against the other delivery of the same words.
6. No fixed benchmark can guarantee it will not saturate. Freeze a core and version harder extensions.
7. Emotion model off by default. eSpeak NG first, Piper as the upgrade.

### Where we agreed

Cascade with an inspectable state. Two separate channels. Bounded adaptation. No demographics. Fresh
recordings as the real test, because the public emotion sets are in the emotion model's training data. A
static baseline, repeated seeds for a noise floor, and nuisance controls. Honest naming: turn-adaptive.

### Where we disagreed, and what was chosen

| Topic | Fable | Astra | Chosen | Why |
|---|---|---|---|---|
| Speech synthesis | Kokoro-82M | eSpeak NG, then Piper | **Kokoro**, with Astra's rule to measure the realised rate | Human ratings need a natural voice. Astra's rule already paid off: a ±15% speed request produced a -10% / +7% change in measured speech rate. |
| Emotion model | In v1, gated | Off by default, try last | **In, optional, gated** | It is one of the three requested behaviours. On four CREMA-D clips it read acted sadness as "neutral, 1.00", so the gate and the caveats stay. |
| Switching support on | (Prelim: after two consistent turns) | At once, release slowly | **Astra's** | Waiting a turn to respond to "I just got laid off" is the wrong failure. |
| Arms | No strong view | 2x2 + shuffled + oracle | **Astra's** | It isolates each half of the system. Seven arms with weak controls prove less. |
| Headline metric | Automatic pace dose-response slope against a shuffled control | Human appropriateness gain | **Both** | The slope needs no raters and is available on day one. The gain answers "you rewarded your own rule". |
| Outside systems | One reference arm once the ablation is clean | Drop all four this weekend | **Dropped for the weekend**, first follow-up | Costs money and needs your approval. The internal result has to stand first. |
| Language style matching | Keep as a secondary metric | Cut it | **Cut from the controller, kept as a labelled descriptive metric** ("LSM-lite") | It measures function-word matching, not slang. It is cheap to report. It decides nothing. |
| Name | Listener profile | ConversationStyleState | **`StyleState`** | "Profile" invites treating one turn as a trait. "Listener profile" stays only as the informal name. |
| Live demo | Push-to-talk on the Mac is in scope | Files first, microphone later | **Files first, then push-to-talk** | Same code path. It is still labelled turn-adaptive. |
| Reply model | Qwen2.5-7B on the Mac | 0.5B on the VM, 1.5B on a laptop | **7B** | The hardware changed (see below). |

**Hardware note.** This plan began on a small VM (2 vCPU, 3.8 GB, no GPU). The VM rebooted twice while
benchmarking models, so the work moved to the Mac. Astra's "this server" column no longer applies.

## 5. Evaluation

### Two experiments, kept apart

1. **Acoustic adaptation:** identical words, different delivery. Tests the audio path.
2. **Lexical accommodation:** the same request in casual, neutral and formal wording, with voice and pace
   held fixed. Tests the word path.

### Arms

| Arm | Text side | Voice side |
|---|---|---|
| `static` | fixed | fixed |
| `text-only` | adaptive | fixed |
| `voice-only` | fixed | adaptive |
| `full` | adaptive | adaptive |
| `full+shuffled` | adaptive, but fed another stimulus's acoustic features | same |
| `full+oracle` | adaptive, fed human labels (subset) | same |

Same reply model, same voice, same decoding settings in every arm. `static` still sees the transcript, so it
is an ordinary cascade and a fair baseline. `shuffled` is the negative control: if it scores like `full`,
the audio is not doing the work.

### Two tracks

- **Transcript-locked:** every delivery of a script reaches the reply model with identical canonical words.
  Any difference in the reply came through the acoustic path.
- **End-to-end:** real ASR output, with word error rate reported. This is what a user would get.

### Metrics

| Metric | What it answers | Needs raters |
|---|---|---|
| **Pace dose-response slope:** realised reply rate against the user's rate, per arm, with a cluster bootstrap CI | Does the output audio actually follow the input audio? `static` and `shuffled` must sit near zero. | No |
| **Audio-conditioned appropriateness gain:** matched rating minus swapped rating | Is the change appropriate for that delivery, beyond generic niceness? | Yes |
| Register shift: contractions, slang and formal markers in replies, casual minus formal | Does wording follow the user's register? | No |
| **Caricature rate:** slang in the reply when the user used none | Is it overdoing it? | No |
| Support response by delivery, and false reactions on neutral speech | Does it react to distress, and only to distress? | No |
| Task preservation: reply stays on the script's topic | Did style change the substance? | No (crude) |
| Nuisance invariance: gain ±6 dB, leading silence, noise | Does it react to the microphone instead of the speaker? | No |
| Noise floor across seeds | How much of any difference is just sampling? | No |
| Latency per stage, p50 and p95 | Is it usable? | No |

Every number is reported with its n, its number of clusters and a confidence interval that resamples scripts
or speakers, not rows.

### Stimuli, in four tiers

| Tier | What | Use |
|---|---|---|
| `synthetic-say` | macOS voices at set rates | Debugging only. Reported separately. |
| `psola` | Any recording stretched by 0.8 to 1.25 without changing pitch | The parametric "dose" for pace |
| `crema-d` | Actors saying the same sentence in different emotions | Emotion path, **in-distribution for the emotion model**, so labelled as such |
| `human` | Your own recordings and a few friends' | The only tier that counts for claims |

Scripts are split into dev and held-out in `scripts.yaml` now, before any tuning.

### Why this does not saturate

- The headline numbers are **continuous effects**, not accuracy. A slope, an appropriateness gain and a
  false-reaction rate keep discriminating between systems as they improve.
- The pace test is **parametric**. When a system handles a 25% rate change, test 10%, then 5%. The quantity
  of interest becomes the smallest delivery difference that produces an appropriate change.
- **Versioned harder sets** on top of a frozen core: subtler deliveries, conflicting cues (cheerful words in
  a flat voice), unfamiliar speakers, noise, and style changes in the middle of a conversation (measure the
  lag in turns and the overshoot).
- The difficulty is not tuned after seeing which system wins.

### What the harness does today, and what it cannot claim

It builds the stimuli, runs the arms, computes every automatic metric and exports a blind rating sheet. Runs
in this repo so far use synthetic voices. They show that the apparatus works. They are not results.

## 6. Weekend schedule

The code skeleton exists. The weekend goes to recordings, calibration and the first real run.

| When | Do | Done when |
|---|---|---|
| **Friday evening** | Run `s2s demo` and `s2s talk`. Record the scripts yourself: 12 neutral scripts in three deliveries (plain, subdued, energised), a fast and slow subset, and the register triples. Send `RECORDING_GUIDE.md` to three friends. Write down what you expect to see. | About 30 minutes of your own audio is in `data/recordings/` |
| **Saturday morning** | Calibrate the neutral rate and the speed-to-realised-rate mapping on dev recordings. Run the nuisance set. Fix what breaks. | Pace slope is above zero on dev and flat for `static` and `shuffled` |
| **Saturday afternoon** | Run the 2x2 plus shuffled on dev, both tracks. Read the failures. Decide whether the emotion gate stays. | Thresholds chosen on dev only |
| **Sunday morning** | Freeze the config (commit hash). Run held-out. Export the rating sheet and get three raters on about 40 trials each. | Held-out report and scored ratings exist |
| **Sunday afternoon** | Write post 1 with the failures included. Record a 60-second demo. | Post drafted |

**Cut in this order if time runs out:** expressive TTS experiments, the outside reference arm, the emotion
model, push-to-talk polish, register scoring refinements.

**Never cut:** the static baseline, the shuffled control, measuring the realised audio, the held-out split.

## 7. Compute and cost

Everything in v1 is local. Cost so far: $0.

| Item | Size | Cost |
|---|---|---|
| Whisper `base.en` | 145 MB | $0 |
| Kokoro-82M ONNX + voices | 355 MB | $0 |
| Qwen2.5-7B-Instruct 4-bit (MLX) | 4.3 GB | $0 |
| emotion2vec+ base (optional, pulls in PyTorch) | about 1 GB installed | $0 |

Things that would cost money and need your approval first: a commercial reference arm (GPT-Live-1 is
$0.05 per minute, so a 200-clip run is a few dollars), ElevenLabs v4 for expressive speech, or a GPU rental
for a larger open speech model.

## 8. Risks

1. **The emotion model is the weakest link.** Its scores are not calibrated and its training data includes
   the public acted-emotion sets. It can miss real sadness and can fire on neutral speech. Mitigation: a
   confidence gate, fresh recordings, a reported false-reaction rate, and never using it as its own judge.
2. **No intonation control.** v1 adapts pace and pauses only. Do not claim intonation until an expressive
   TTS is in.
3. **A 7B model may ignore or overdo the style brief.** Mitigation: the caricature rate, a whitelist of the
   user's own expressions, and an adapter that accepts any stronger model.
4. **The register rules are a small, stereotyped word list.** Real casual speech varies far more than
   "ngl" and "lowkey". Treat the list as a placeholder and report its misses.
5. **ASR may mangle slang.** The end-to-end track measures this instead of hiding it.
6. **The pace measure is simple.** The syllable count is a heuristic and the speech detector is energy-based,
   so heavy noise will hurt it. The nuisance set shows how much.
7. **"You rewarded your own rule."** A slope only shows the system does what it was told. Human
   appropriateness ratings and task preservation are what answer this.
8. **Small n.** Four speakers support a pilot, not a claim about people in general. Publish per-speaker
   results and rater disagreement.
9. **People.** Do not adapt to who the system thinks someone is, only to how they talk. Get consent for
   recordings and store nothing by default. Say that it is an AI. Crisis wording gets a fixed reply that
   points to real help.

## 9. After the weekend

1. One outside reference arm on the same stimuli (post 2).
2. Expressive speech for intonation: Qwen3-TTS or Orpheus locally, or ElevenLabs v4 with approval (post 3).
3. Streaming and barge-in, once the turn-based result holds.
4. The model itself adapts: a LoRA on an open omni model trained on style-matched dialogue made with this
   harness's stimuli (post 4).
