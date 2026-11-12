# Astra consult (verbatim)

> Independent second opinion from Astra (Codex provider, `gpt-6-astra`, high reasoning effort), requested by
> Fable on 2026-11-11 before the plan was settled. Astra was given the idea, the hard constraints of this
> server and `PRELIM_RESEARCH.md`, and was told not to guess Fable's view. This is its reply, unedited.
> The reconciliation is in `docs/PLAN.md`.

**1. Architecture verdict**

Use a cascade, but build a **turn-by-turn adaptation experiment before a streaming voice agent**. The preliminary design bundles too many problems into one weekend: streaming, emotion recognition, conversational quality, expressive synthesis, and seven-system evaluation.

The smallest honest demonstration is:

`recorded WAV → ASR + measured speaking rate → bounded adaptation policy → reply text → rate-controlled speech`

Feed identical words spoken at different speeds; hold the transcript constant experimentally; demonstrate that the **actual output audio** changes appropriately. This establishes an acoustic causal pathway. It does not establish empathy, natural intonation, or full-duplex interaction.

Keep register adaptation as a separate transcript-driven pathway. Slang is lexical evidence; fast speech is not evidence that someone is Gen Z.

One conceptual correction: **audio-derived prompt changes are legitimate audio-driven adaptation**. Path A already uses them. The distinction is whether acoustic evidence causally changes behavior, not whether the implementation contains a prompt.

**2. Listener profile and policy**

I would rename it `ConversationStyleState`: "listener profile" encourages treating transient observations as stable personal traits.

Keep only:

- **Register:** neutral/casual/formal, observed reusable expressions, evidence count.
- **Timing:** speech rate, pause fraction, measurement validity.
- **Affect:** optional SER scores and an explicit unknown state.
- **State:** previous controls, turn index, evidence provenance and per-feature reliability.

Do not infer distress from low pitch, low volume, or slow speech alone. Microphone gain, fatigue, individual voice differences, and recording conditions confound those measurements.

For valid timing measurements, start with an EMA such as `state ← 0.7 × state + 0.3 × observation`. Treat this as a tunable engineering choice, not a research-backed optimum. Insufficient speech means retain or gradually relax toward neutral. Reset between speakers; manually identify sessions instead of building diarization.

Map controls separately:

- **LLM:** register, permission for contractions, observed slang allowance, response-length preference. Preserve factual content and task completion.
- **TTS:** bounded speed multiplier, pause budget, and a supported delivery instruction. Start with modest speed changes, perhaps ±15%; measure what the synthesizer actually produces.
- **Distress:** supportive wording and restrained delivery, with prompt response to credible evidence and slower release afterward. Do not require two turns before responding supportively. Do not automatically slow an already slow speaker further.

Cut LSM state, nine-category linguistic bookkeeping, continuous valence/arousal inference, demographic inference, and pitch matching. A single global "confidence" is particularly misleading: ASR confidence and emotion uncertainty are different quantities.

**3. Component picks**

These are recommended configurations, not measurements from this machine.

| This server: 2 vCPU, approximately 2 GB free | Rohanth's weekend setup |
|---|---|
| **Orchestration:** plain Python CLI, WAV input/output, JSON traces. Sequential inference avoids resource contention. | Same core, then microphone capture and turn detection. Add a streaming framework only after the file pipeline works. |
| **ASR:** `faster-whisper`, `tiny.en`, CPU INT8, two threads, batch size one. CPU INT8 is documented; speed here remains unmeasured. [Source](https://github.com/SYSTRAN/faster-whisper) | Start with `base.en`; try `small.en` if hardware permits. Benchmark before choosing. |
| **Acoustics:** NumPy measurements of duration, pauses and RMS; ASR word counts for rate. Distinguish rate including pauses from articulation rate excluding them. | Same measurements. Optional pitch extraction for diagnostics, not emotion labels. |
| **Affect:** disabled/unknown by default. Optional isolated emotion2vec+ base experiment; do not make PyTorch/FunASR a prerequisite. | Try **emotion2vec+ base**, approximately 90M parameters, through FunASR. Its nine scores are not calibrated distress probabilities. [Source](https://github.com/ddlBoJack/emotion2vec) |
| **Reply generator:** **Qwen2.5-0.5B-Instruct GGUF Q4**, through llama.cpp, short context and replies. This is a constrained local baseline. Deterministic templates remain an explicitly labelled fallback. [Model](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF) | **Qwen2.5-1.5B-Instruct GGUF** initially; an approved hosted model can replace it. [Model](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF) |
| **TTS:** eSpeak NG first: lightweight, audible rate/pitch controls, robotic quality. Piper is the naturalness upgrade, not an assumed expressive-emotion engine. [eSpeak](https://github.com/espeak-ng/espeak-ng), [Piper](https://github.com/OHF-Voice/piper1-gpl) | Piper without GPU; with approved GPU access, **Qwen3-TTS-12Hz-1.7B-CustomVoice** offers documented instruction control. [Source](https://github.com/QwenLM/Qwen3-TTS) |

Load heavy stages sequentially or isolate their processes if memory requires it. Measure peak RSS and real-time factor. Keep GPU/API adapters disabled without their prerequisites; never silently substitute a stub and count it as model performance.

**4. Evaluation design**

**Replace "response divergence" as the headline.** Randomness, irrelevant sympathy, and degraded answers all increase divergence.

Use two distinct experiments:

- **Acoustic adaptation:** identical words, different delivery.
- **Lexical accommodation:** equivalent task content, different register, with delivery balanced across conditions.

For a weekend pilot, collect roughly **four speakers × eight scripts × three deliveries**: neutral, subdued, energized. Add a small independently varied fast/slow subset. These are acted deliveries, not verified psychological states. Collect independent listener ratings of the stimuli before scoring responses.

Reserve scripts and speakers for evaluation before tuning. Fresh human recordings reduce known training-set overlap; published SER datasets may already appear in the analyzer's training. Synthetic speech is useful for debugging and controlled perturbations, but report it separately from humans.

Replace the seven arms with a **2×2 ablation**:

1. Fixed text policy, fixed TTS.
2. Adaptive text policy, fixed TTS.
3. Fixed text policy, adaptive TTS.
4. Adaptive text policy, adaptive TTS.

Use the same generator, voice, task instructions and decoding settings. Add shuffled acoustic features as a negative control and human-labelled features as an oracle diagnostic on a subset. Drop all four external-system arms this weekend.

Run two tracks:

- **Transcript-locked:** identical canonical text reaches the generator for each delivery; audio features remain measured separately. This isolates the acoustic pathway.
- **End-to-end:** actual ASR outputs, with WER and delivery-dependent transcript differences reported. This measures deployed behavior.

The headline should be **audio-conditioned appropriateness gain**. Blind listeners score each response paired with its originating delivery and with the alternate delivery of the same words. Compute matched-minus-swapped appropriateness, then compare that contrast against the static baseline. Generic reassurance should earn little delivery-specific gain. Report absolute appropriateness and task correctness alongside it so a bad swapped response cannot manufacture success.

Necessary controls:

- Repeat identical inputs to estimate generation and synthesis noise; use several seeds where stochasticity remains.
- Shuffle delivery labels to estimate the experimental null.
- Include gain changes, added silence and mild noise as nuisance controls.
- Keep voices fixed; randomize playback order and system labels.
- Measure response speed from generated audio, not requested controls.
- Score response text and audio separately to locate failures.
- Never use the same SER model as both controller and sole judge.

Use at least three independent ratings per evaluated comparison where feasible. Report paired effects with confidence intervals respecting speaker and script clustering. Four speakers support a pilot, not population-level claims; publish per-speaker results and rater disagreement.

**No fixed benchmark can guarantee non-saturation.** Preserve a frozen core, then version harder extensions: subtler delivery differences, conflicting lexical/acoustic cues, unfamiliar speakers, noise, and mid-conversation style changes. Measure adaptation delay, false reactions and overshoot continuously. Do not tune difficulty after seeing which system wins.

The skeptical reader's first attack will be: "You rewarded your own prescribed behavior." Independent appropriateness ratings, task preservation, and nuisance invariance answer that better than another automatic similarity metric.

**5. Weekend schedule and cut lines**

- **Friday evening:** WAV→ASR→reply→WAV works locally; record resource usage. Freeze the evaluation protocol and recruit recordings/raters.
- **Saturday:** implement rate adaptation, minimal register state, traces and four ablations. Collect recordings. Attempt SER only after those work.
- **Sunday:** freeze thresholds; evaluate held-out material; inspect failures; publish reproducible configuration, uncertainty and a short demonstration.

Drop, in order: commercial comparisons, streaming infrastructure, expressive neural TTS, SER, pitch analysis, elaborate register scoring. Preserve real acoustic measurements, the static baseline, generated audio and held-out evaluation.

If only prerecorded turns work, call it **offline, turn-adaptive speech-to-speech**, not live streaming.

**6. Verified claims and overclaims**

- **Chatterbox retirement is supported.** The maintainer's README update explicitly says retired/unmaintained as of August 2026. [Primary source](https://github.com/resemble-ai/chatterbox/commit/ab55923)
- **emotion2vec+ exists.** Base/large variants and FunASR inference are documented. Availability does not establish Python 3.12 compatibility or memory suitability here; those remain untested. [Repository](https://github.com/ddlBoJack/emotion2vec)
- **JoyAI-Talker's paper exists**, including PAER and instruction-controlled speech. I did not verify downloadable weights. [Paper](https://arxiv.org/html/2608.01119)
- **Sophon exists**, with current documentation specifying an 80 GB GPU. Its repository labels evaluations self-run and reports best-of-several runs for one benchmark; those figures are not independent evidence. [Repository](https://github.com/adventists-ai/sophon-realtime)
- **Hume's exact November 13 cutoff remains unverified from a primary notice in this check.** Current documentation redirects to Audio Decisions; that alone does not establish the shutdown date. [Current documentation](https://dev.hume.ai/audio-decisions/docs/overview)

The larger overclaims are methodological: absence of discovered prior art does not prove novelty; LSM does not measure slang understanding; sadness similarity does not measure empathy; parallel analysis does not become free on two CPU cores. The proposed subsecond latency budget is an aspiration, not a credible commitment for this server.

**7. The result worth blogging**

"Changing only a speaker's delivery caused appropriate, measurable changes in the agent's response; those gains disappeared when acoustic evidence was removed or shuffled." Publish the failures and uncertainty alongside the demonstration—that is stronger hiring evidence than a seven-vendor leaderboard with weak controls.
