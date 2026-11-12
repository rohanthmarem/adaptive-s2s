# Adaptive Speech-to-Speech: Preliminary Research (unverified input)

> **Status:** prepared 2026-11-11 by another assistant, before this repo existed. It is the *input* to
> `docs/PLAN.md`, not a verified source. Claims marked **(vendor-reported)** come from the vendor's own page.
> Claims marked **(unverified)** could not be confirmed from a primary source. See
> `docs/research/CLAIM_CHECK.md` for what was re-checked when the repo was built.

## 0. The idea, restated

Build a voice system that adapts how it talks to whoever it is talking to, live, from the incoming audio. It should shift register (Gen Z slang and contractions vs. structured workplace English), pace, intonation and warmth, and become empathetic when it hears sadness or distress. The differentiator is that adaptation comes from the paralinguistic and lexical cues in the audio stream, updated while the conversation runs, and not from one static system prompt.

## 1. Bottom line

1. **Recommended v1 is a cascaded pipeline with an explicit, running "listener profile"** (path A in section 4). It is the only option where every adaptation is inspectable, ablatable and controllable in a weekend. End-to-end open S2S models are heavy (32B / 30B-class) and, per the 2025-26 evidence, mostly do not use vocal cues well on their own (LISTEN, EchoMind below).
2. **The honest gap in prior art:** I found no product or open model that verifiably does live *register and lexical* mirroring (slang, formality, idioms) from speech. Emotion/tone perception exists in several systems (Gemini Live, ElevenLabs Expressive mode, Hume EVI, Sophon-Realtime, JoyAI-Talker), but register accommodation is not benchmarked anywhere I found. That gap is the project's novelty.
3. **The blog-post-worthy eval is a "text-identical, voice-different" test** (EchoMind-style): same neutral words, different delivery, and measure whether the response changes. This isolates audio-driven adaptation from prompt-driven adaptation and also tests lexical accommodation with Language Style Matching.
4. Decagon did **not** build a speech-to-speech model from scratch; Block's **Dessa** did (research preview only). Details in section 2.1.
5. **Time-sensitive:** Hume's EVI/TTS APIs are reported (third-party sources only) to shut down on **2026-11-13**. Do not build on EVI.

## 2. Landscape

### 2.1 Clarifying what the user mentioned

- **Decagon (Voice 3 + Chord), Oct 1 2026.** Chord is "a speech model we post-trained for customer conversations", built by post-training a *tokenizer-free diffusion model*. It shapes speech phrase by phrase (slows down for a confirmation code, returns to conversational pace) and Decagon says emotion, pace and emphasis are steerable. Voice 3 is a "duplex architecture with two layers in parallel": a low-latency conversational model for listening/speaking and a stronger model for reasoning and tools. So it is post-trained, not from scratch, and the posts do not claim adapting to the caller's speaking style. https://decagon.ai/blog/decagon-chord-voice-model , https://decagon.ai/blog/voice-3 , https://www.unite.ai/decagon-introduces-voice-3-agent-with-chord-speech-model/
- **"Dessa" = Block's Dessa** (announced Oct 23 2026 per press): a full-duplex speech-to-speech model "trained from scratch on nothing but human conversation. No text, no pretrained models", runs locally on a MacBook Pro M4 Max or better, trained on one GB200 NVL72. Claims it hears emotion, sarcasm, laughter. It is a **research preview with waitlist: no weights, API, paper, parameter count or benchmarks** published. The team descends from the Toronto startup Dessa. https://block.xyz/dessa , https://gadgetsnow.indiatimes.com/tech-news/how-the-lab-behind-a-2019-joe-rogan-voice-clone-built-blocks-human-sounding-dessa/articleshow/135212230.cms , https://ai.thesatyajit.com/articles/dessa

### 2.2 Closed / API systems

| System | Access | Duplex / latency | Hears user's emotion/style? | Controls own style | Adapts to user? |
|---|---|---|---|---|---|
| OpenAI GPT-Live-1 | API GA 2026-09-10, $0.05/min voice layer | Full-duplex single model, delegates reasoning to a backend model | Not documented on the launch page (unverified) | Tone, pace, style via system prompt | No documented automatic adaptation |
| Gemini 3.8 Live (`gemini-3.8-live`) | API | Audio-to-audio, proactive audio always on | Cloud doc says it processes prosody, vocal cues, pauses and inflection to adjust vocal tone and pacing (vendor-reported). The older `enable_affective_dialog` flag was removed in 3.8 | Prompt | Vendor says tone/pace adjust to user cues |
| ElevenLabs Eleven v4 Turbo / v3 + Expressive mode | API / ElevenAgents | ~100 ms median TTS latency (vendor-reported) | Expressive mode "adapting in real time to how users sound", e.g. calmer when user sounds worried (vendor-reported; mechanism not disclosed) | Audio tags `[laughs] [whispers] [sighs] [slow] [excited]`, each affecting roughly the next 4-5 words | Tone adapts to user sound (vendor-reported). Register/slang not mentioned |
| Hume EVI 3 / EVI 4 mini | API, **reported shutting down 2026-11-13** | EVI 3 <300 ms on strong hardware, ~1.2 s practical in Hume's own test (2025) | Yes, prosody (tune, rhythm, timbre); beat GPT-4o on 8 of 9 emotions in Hume's own eval (vendor-reported) | Any voice/personality by prompt, emotion/style on command | Implicit emotional adaptation |
| Decagon Voice 3 / Chord | Closed, product | Duplex (conversational + reasoning layers) | Not claimed | Emotion, pace, emphasis steerable | Not claimed |
| Block Dessa | Waitlist research preview | Full-duplex, faster than real time (Block-reported) | Claims emotion, sarcasm, laughter | n/a | n/a, no public detail |
| Thinking Machines "interaction models" | Research preview | 200 ms micro-turns, 276B MoE / 12B active; FD-bench turn-taking latency 0.40 s (self-reported) | Not a stated focus | n/a | n/a |

Sources: https://openai.com/index/introducing-gpt-live-1-in-the-api/ , https://aistudio.google.com/docs/models/gemini-3.8-live , https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/guides/gemini-3-8-live , https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api/configure-gemini-capabilities , https://elevenlabs.io/docs/eleven-agents/customization/voice/expressive-mode , https://elevenlabs.io/docs/help-center/product/core-capabilities/text-to-speech/how-do-audio-tags-work-with-eleven-v3-and-v4 , https://www.hume.ai/blog/introducing-evi-3 , https://burki.dev/blog/hume-api-shutdown-migration-guide (Hume shutdown, third-party, unverified on hume.ai) , https://thinkingmachines.ai/blog/interaction-models/

### 2.3 Open-weight systems

| System | License / weights | Duplex / latency | Hears emotion/style? | Controllable output | Adapts to user? |
|---|---|---|---|---|---|
| Qwen3-Omni-30B-A3B (Alibaba) | Apache 2.0 | Thinker-Talker MoE, 234 ms theoretical cold-start first packet (paper) | Yes; emotion 77.0 on MER2025 refined labels (per JoyAI-Talker table). Captioner variant describes audio | Tone/persona via system prompt | Only via prompt |
| Sophon-Realtime v1 (Adventists AI) | Apache 2.0; Tag build ~42 GB; 1x80 GB GPU | Full-duplex; first audio ~0.6 s (Tag), 0.31 s (Flash), ~0.25 s (E2E) (self-reported) | Yes via DuplexJev "ears"; paralinguistic 48.6 combined vs Gemini 3.8 Flash 46.9, Qwen3-Omni 44.6 (self-reported) | Writes sound tags (laugh, sigh, breathe) and performs them. LoRA-finetunable thinker (persona, tone) on one 80 GB GPU | Hears tone and answers with tone of its own (self-reported). No register adaptation claimed |
| JoyAI-Talker (JD) | Weights availability **unverified** (paper only seen) | Full-duplex via Joy-Duplex gate (1.7B); modular Thinker-Talker | Yes: age 77.3, emotion 79.6, gender 98.2 (self-reported) | NL speaking instructions + 10 paralinguistic tokens (rate, volume, laughter, sigh) | **PAER**: perceives speaker attributes, reasons over them in CoT, emits per-utterance speaking instruction. Closest published architecture to the idea |
| NVIDIA PersonaPlex-7B | Open on HF (check license) | Moshi-based full-duplex; released checkpoint latency 0.17 s smooth turn-taking (paper) | Not an emotion model | Text role prompt + voice-prompt cloning, **fixed at session start** | Static conditioning only |
| Kyutai Moshi | CC-BY 4.0 | 160 ms theoretical, ~200 ms on L4 | Limited; VoiceBench 29.5 (via Sophon table) | Fixed voice | No |
| OpenS2S / V1.5 (CASIA) | Fully open: weights, data, code | Streaming interleaved decoding | Yes (BLSP-Emo style) | Emotional response voice via InstructTTS-made data | Empathetic response; V1.5 uses ~400k bilingual empathetic pairs |
| GLM-4-Voice-9B | Code Apache 2.0, weights under model agreement | 12.5 tokens/s tokenizer, streaming decoder | Partial | Spoken instructions control emotion, tone, speech rate, dialect | Only if told |
| Step-Audio 2 mini | Apache 2.0 | End-to-end audio LLM | **Paralinguistic analysis: emotion, age, timbre, pitch, rhythm, speed, style** | Speech conversation | Not claimed |
| Ultravox v0.6 | Open weights (Llama 3.3 70B / Gemma 3 / Qwen 3 variants) | Audio-in LLM (Whisper-large-v3-turbo encoder, frozen LLM), needs separate TTS | Audio embeddings reach the LLM | Via TTS | No |
| LLaMA-Omni 2 / Mini-Omni(2) | Apache 2.0 (LLaMA-Omni 2) | Streaming speech out | Little | Little | No |
| Sesame CSM-1B | Open | Context-aware speech generator, not a chat LLM | n/a | Conditions on previous text+audio segments | **Hypothesis to test:** feed the user's audio turn as context to induce prosodic entrainment (unverified) |
| Kyutai STT/TTS + Unmute | Open | Streaming STT with semantic VAD, TTS streams from partial LLM text | n/a | n/a | Modular reference stack |
| Fun-CosyVoice 3 (0.5B) | Apache 2.0 | Streaming TTS | n/a | NL instructions: emotion, speed, volume, dialect, style | n/a |
| Qwen3-TTS (1.7B VoiceDesign etc.) | Apache 2.0, released 2026-01-22 | Streaming TTS | n/a | NL voice design + instruction control | n/a |
| Orpheus 3B | Open | ~200 ms streaming (~100 ms with input streaming) | n/a | Inline emotive tags (laugh, sigh, cough, gasp...) | n/a |
| Dia 1.6B | Open | Dialogue TTS | n/a | English, `[S1]/[S2]`, nonverbal tags | n/a |
| Chatterbox | MIT, **retired/unmaintained as of Aug 2026** | n/a | n/a | `exaggeration` / `cfg_weight` | n/a. Avoid for new work |
| emotion2vec+ | Open | Utterance/segment SER, 9 classes + embeddings | Yes | n/a | n/a |
| DuplexJev 4B/32B (Adventists AI) | Open weights | Batched single-token decisions, 80 decisions in ~0.1 s on 8 GPUs | Gender/emotion accuracy ~90% with cross-attention connector (self-reported) | n/a | n/a |

Sources: https://arxiv.org/html/2509.17765 , https://huggingface.co/Qwen/Qwen3-Omni-30B-A3B-Instruct , https://huggingface.co/adventists-ai/Sophon-Realtime-v1 , https://arxiv.org/html/2608.01119 , https://arxiv.org/abs/2602.06053 , https://huggingface.co/nvidia/personaplex-7b-v1 , https://arxiv.org/html/2410.00037 , https://kyutai.org/blog/2024-09-18-moshi-release/ , https://arxiv.org/abs/2507.05177 , https://github.com/zai-org/GLM-4-Voice , https://github.com/stepfun-ai/Step-Audio2/ , https://github.com/fixie-ai/ultravox/ , https://github.com/ictnlp/LLaMA-Omni2 , https://huggingface.co/sesame/csm-1b , https://github.com/kyutai-labs/unmute/ , https://github.com/FunAudioLLM/CosyVoice , https://github.com/QwenLM/Qwen3-TTS/ , https://github.com/canopyai/Orpheus-TTS , https://huggingface.co/nari-labs/Dia-1.6B , https://github.com/resemble-ai/chatterbox , https://github.com/ddlBoJack/emotion2vec , https://paperswithcode.co/paper/2610.02638

Note: all Sophon/JoyAI/DuplexJev numbers are self-reported by lesser-known labs. Treat as leads to reproduce, not facts.

## 3. Research on the capability

### 3.1 Perception is the bottleneck (evidence the cascaded analyzer is justified)

- **LISTEN** (EACL 2026): six audio LLMs show "consistent lexical dominance". They default to "neutral" when the words are neutral or absent, gain little from aligned cues, fail when words and tone conflict, and are near chance on paralinguistic-only input. https://arxiv.org/html/2510.10444 , https://aclanthology.org/2026.eacl-long.274/ . Follow-up: "Text Dominance in Paralinguistic Conflict" https://arxiv.org/pdf/2610.25599 (title only seen).
- **EchoMind** (arXiv 2510.22758): same semantically neutral scripts, 3 vocal-style variants, 39 vocal attributes, 12 SLMs. Finding: models handle content well but "struggle to use expressive vocal cues for empathetic, emotionally aligned responses". Provides metrics reusable for us: EmoAlign (emotion2vec on the response audio vs. reference) and Vocal Empathy Score (a Gemini judge of whether the reply mirrors the user's vocal style). https://arxiv.org/abs/2510.22758 , https://hlt-cuhksz.github.io/EchoMind/ , https://huggingface.co/datasets/hlt-cuhksz/EchoMind
- **VoxDialogue** (ICLR 2025): 4.5K multi-turn dialogues over 12 acoustic attributes. ASR-based systems are better at context, direct speech models better at acoustics. https://proceedings.iclr.cc/paper_files/paper/2025/hash/011df158529ddceb5f2f7a65f2732a5a-Abstract-Conference.html
- Human speech is harder than TTS-generated test speech (EchoMind-Human). Evaluate on his own recorded voice too.

### 3.2 Accommodation / entrainment / style mirroring

- Classic result: spoken dialogue systems that adapt pitch, intensity and rate improve perceived rapport and naturalness. Pitch adaptation helped naturalness and rapport in a learning companion; intensity entrainment raised trust while pitch entrainment did not always. https://doi.org/10.1109/asru.2015.7404781 , https://www.cs.columbia.edu/speech/PaperFiles/2020/Galvez_speech_communication_2020.pdf , https://aclanthology.org/N13-2012.pdf
- **Language Style Matching (LSM)**: function-word similarity metric, per category `1 - |p1 - p2| / (p1 + p2 + 0.0001)`, averaged over nine categories (Ireland et al. 2011). Cheap, text-only, usable on ASR transcripts of both sides. https://www.liwc.app/help/lsm , https://journals.sagepub.com/doi/full/10.1177/0956797610392928
- LLMs accommodate less in style than humans: "LLMs stick to the point, humans to style" (SIGDIAL 2025) https://aclanthology.org/2025.sigdial-1.16/ ; LLMs syntactically adapt to partners https://arxiv.org/html/2503.07457 ; LSM in LLMs https://aclanthology.org/2025.sigdial-1.50/ .
- **Synchrony-Stability Frontier** in adaptive chatbots: mimicry helps rapport but unbounded mirroring risks instability and sycophancy; use bounded adaptation. https://arxiv.org/html/2510.00339v1 . This directly motivates the clamp and hysteresis in the v1 design.

### 3.3 Empathetic speech dialogue models and data

- **StyleTalk** (ACL 2024): speech dialogue dataset with emotion, speed, volume style labels; same text paired with different responses under different styles. MIT. https://github.com/DanielLin94144/StyleTalk , https://arxiv.org/html/2402.12786
- **E-chat200 / E-chat**: 178k synthetic emotion-sensitive spoken dialogues. https://arxiv.org/html/2401.00475
- **OpenS2S**: 50k EN + 50k ZH synthetic empathetic speech instructions (LLM writes the content and tone, voice cloning varies the speaker, instruct-TTS renders the reply); V1.5 ~400k pairs. Reusable recipe for path C. https://arxiv.org/abs/2507.05177 , https://huggingface.co/datasets/CASIA-LM/OpenS2S_Datasets
- **OSUM-EChat**: https://arxiv.org/html/2508.09600 ; **CoT for empathetic spoken dialogue**: https://arxiv.org/html/2501.10937
- **PersonaPlex's recipe**: synthetic LLM-written dialogues rendered with TTS plus 1,217 hours of Fisher for backchannels; the experimental model trained in 6 hours on 8xA100. https://arxiv.org/abs/2602.06053
- **JoyAI-Talker PAER**: audio understanding -> CoT over perceived attributes -> speaking instruction + paralinguistic tokens. Also the only paper I found that lists "interface bottleneck" honestly: symbolic Thinker->Talker interface drops fine acoustic detail. https://arxiv.org/html/2608.01119

### 3.4 Speech emotion recognition, register detection

- SER: emotion2vec+ (9-class, 16 kHz) is the practical open tool. https://huggingface.co/emotion2vec/emotion2vec_plus_large . Step-Audio 2 and Qwen3-Omni can also output paralinguistic descriptions.
- Register / sociolect from speech: I found **no mature open model**. Do it on the transcript instead (slang density, contraction rate, formality via an LLM or small classifier, LSM function-word profile) plus acoustic rate/pitch/energy features. Inferring age or gender from voice is possible (JoyAI-Talker, EchoMind) but I recommend not using demographics as an adaptation input (see section 7).

### 3.5 Benchmarks relevant to the capability

- EchoMind (empathy, vocal cues), VoxDialogue (12 acoustic attributes), LISTEN (lexical vs acoustic emotion), StyleTalk (style-conditioned responses), URO-Bench UnderEmotion subsets (used by OpenS2S).
- Turn-taking / latency: Full-Duplex-Bench family incl. v3 (tool use under disfluency, 100 recordings, 12 speakers) https://arxiv.org/abs/2604.04847 , https://github.com/DanielLin94144/Full-Duplex-Bench/ ; Service-Duplex-Bench in the PersonaPlex paper.
- **None** of these measures register/lexical accommodation or prosodic entrainment of the *agent's* speech to the user. That is the gap to fill.

## 4. Weekend v1 approaches

### Path A: cascaded with a listener profile (RECOMMENDED)

```
mic -> VAD + turn detection -> streaming STT (words + timestamps)
           \-> audio analyzer (parallel, off critical path):
                 emotion2vec+ probs, pitch/energy/rate features,
                 optional Step-Audio-2-mini / Qwen3-Omni paralinguistic caption
        transcript -> register analyzer (slang, contractions, formality, LSM features)
        both -> ListenerProfile (EMA, clamped)  <-- the "memory of how this person talks"
        ListenerProfile + dialogue -> LLM (style brief) -> text with expressive tags + speaking instruction
        -> expressive streaming TTS (tags / instruct / speed) -> speaker
```

Components, all with real, current options:
- Orchestration: Pipecat (Silero VAD + Smart Turn) https://github.com/pipecat-ai/pipecat/ , or Kyutai Unmute as a reference https://github.com/kyutai-labs/unmute/
- STT: Kyutai streaming STT (word timestamps, semantic VAD) via https://github.com/kyutai-labs/delayed-streams-modeling/ , or any streaming Whisper-class ASR.
- Emotion: emotion2vec+ (funasr). Prosody: pitch/energy/speaking-rate from the waveform and STT word timestamps.
- LLM: any fast hosted LLM with low time-to-first-token. Keep it swappable.
- TTS (pick one per run, keep an adapter interface): ElevenLabs Eleven v4 Turbo with audio tags (closed, best expressiveness, also the nearest commercial baseline); Fun-CosyVoice 3 (open, instruction control: emotion/speed/volume); Qwen3-TTS (open, instruct control); Orpheus (open, tags). Avoid Chatterbox (retired).

Latency target (engineering targets I set, not sourced): p50 <= 1.0 s and p95 <= 1.6 s from end of user speech to first agent audio. For reference, Hume measured ~1.2 s (EVI 3 web app), Gemini Live ~1.5 s and GPT-4o Realtime ~2.6 s in its own 2025 test (Hume-run, vendor-reported). Budget: endpointing 200-300 ms, final STT 100-200 ms, LLM TTFT 200-400 ms, TTS first chunk 100-300 ms. The audio analyzer must run while the user is still speaking so it adds ~0 to the critical path.

**ListenerProfile** (suggested schema):
```json
{
  "register":  {"formality": 0.0-1.0, "slang_density": 0.0-1.0, "contraction_rate": 0.0-1.0,
                "avg_sentence_len": float, "lsm_function_words": {"pronouns": p, "articles": p, ...}},
  "prosody":   {"rate_wpm": float, "pitch_st_rel_baseline": float, "pitch_range_st": float, "energy_db": float},
  "affect":    {"emotion_probs": {...9 classes...}, "arousal": float, "valence": float, "distress": 0.0-1.0},
  "confidence": 0.0-1.0, "turns_seen": int
}
```
Update rule: per-utterance EMA (alpha ~0.5 early, ~0.3 later), weighted by analyzer confidence. Adaptation strength lambda in [0, 0.7] so the agent never fully copies (Synchrony-Stability finding). Hysteresis: only change a discrete style bucket after 2 consistent turns, to avoid whiplash.

**Policy** (profile -> controls):
- Register: LLM style brief states target formality, slang allowance (a whitelist so it does not caricature), contraction rate, max sentence length. Gen Z-ish -> casual, contractions, light slang, short; business -> complete sentences, workplace idioms, no slang.
- Prosody: target rate = user rate nudged toward a neutral baseline; map to TTS pace tag or speed parameter; energy/pitch mapped to emotion tag choice (`[calm]`, `[upbeat]` etc. or instruct string).
- Affect: **complement, don't mirror, for distress.** If distress prob > threshold for 2 consecutive chunks, override to a supportive policy: slower than the user, softer, validate first, shorter turns, no jokes, no advice dump.
- Always log profile + chosen controls per turn for the eval.

Pros: inspectable, ablatable, works with any LLM, small GPU needs, fast iteration, easy to evaluate against baselines. Cons: symbolic bottleneck loses fine acoustics (JoyAI-Talker names this explicitly), higher latency than native duplex, no overlapping speech or true backchannels.

### Path B: wrap an existing open S2S model with style conditioning

- Candidates: Sophon-Realtime v1 (hears tone, writes tags; needs one 80 GB GPU, ~42 GB weights), Qwen3-Omni-30B-A3B (persona/tone via system prompt), PersonaPlex-7B (voice + role prompts), GLM-4-Voice (spoken instructions for emotion/speed).
- Idea: re-prompt the system prompt mid-session from the same ListenerProfile ("dynamic prompt injection"). That is exactly the "prompt change" the user wants to differentiate from, so it works as a **baseline**, not the product.
- Pros: native audio perception, lowest latency of the options. Cons: heavy GPUs, PersonaPlex's conditioning is fixed at session start, LISTEN/EchoMind suggest weak use of vocal cues, harder to debug, benchmarks mostly self-reported.

### Path C: light fine-tune with synthetic style-matched dialogues (stretch / v2)

- Recipe (from OpenS2S, PersonaPlex, StyleTalk): an LLM writes dialogue pairs conditioned on (user persona, emotion, register) -> adapted reply with tags/speaking instructions; render *user* audio with expressive/instruct TTS and voice cloning for speaker diversity; render reply with controllable TTS or keep it as text+tags. Train a LoRA on an open omni model: Sophon-Realtime thinker LoRA (documented, one 80 GB GPU, ms-swift, keeps the tag adapter) https://huggingface.co/adventists-ai/Sophon-Realtime-v1 ; Qwen3-Omni-30B-A3B LoRA via ms-swift (documented recipes target 2x48-50 GB GPUs) https://github.com/modelscope/ms-swift/blob/main/examples/models/qwen3_omni/transformers.sh
- Pros: closest to "the model itself adapts". Cons: weekend-hard (data gen + training + debugging), TTS-generated user audio is easier than human speech (EchoMind), risk of learning artifacts of the synthetic TTS.

### Comparison

| | A: cascaded + profile | B: open S2S + dynamic prompt | C: LoRA on omni model |
|---|---|---|---|
| Weekend feasibility | High | Medium (GPU, serving) | Low-Medium |
| GPU | 1x24 GB or API-only | 1x80 GB (Sophon) / 2x48 GB (Qwen3-Omni) | Same as B plus training |
| Latency | ~0.9-1.6 s | ~0.3-0.6 s claimed (Sophon, self-reported) | Same as B |
| Uses audio cues | Explicitly (analyzer) | Implicitly, weak per LISTEN | Learned |
| Debuggable / ablatable | Best | Poor | Poor |
| Novel angle | Profile + policy + eval | Baseline | Full model |

**Recommended path:** build A in two days with TTS and LLM adapters; run B (Sophon-Realtime or Qwen3-Omni with the same profile injected into the prompt) and commercial baselines as comparison arms; leave C as a post-weekend follow-up using the data you generate for the eval.

### Suggested weekend schedule

- Fri night: repo, Pipecat skeleton, STT -> LLM -> TTS working with fixed style. Record 20 min of his own speech in 4 styles for tests.
- Sat AM: audio analyzer (emotion2vec+, pitch/energy/rate), register analyzer, ListenerProfile + policy + logging.
- Sat PM: TTS adapters (ElevenLabs tags; one open model), latency measurement, distress policy. Build the eval persona set.
- Sun AM: run the eval (all arms), compute metrics. Sun PM: plots, write-up, short demo recording.

## 5. Evaluation: "Does it actually listen?" (blog post candidate)

**Core test: text-identical, voice-different.** Take EchoMind-style neutral scripts (e.g. "I got my test results back today."). Render each in several delivery styles (neutral, sad, excited, fast, slow, whispered) and, for register, take the *same intent* in different registers (Gen Z phrasing vs formal phrasing). Feed to each system. If the reply changes only when the words change, it is reading text; if it changes with delivery, it listens. Add LISTEN-style conflicting cues (positive words, sad voice).

**Systems (arms):**
1. Static-prompt cascade (same stack, profile disabled)
2. Profile cascade (the project)
3. Same cascade with profile injected as a prompt only (no TTS control), to separate text-side from voice-side adaptation
4. ElevenLabs Eleven v4 Turbo Expressive mode (nearest commercial analogue)
5. GPT-Live-1 with a "match the user's style" system prompt ($0.05/min voice layer)
6. Gemini 3.8 Live
7. One open E2E model (Sophon-Realtime or Qwen3-Omni)

**Metrics:**
- Lexical accommodation: LSM between user and agent turns; slang density and contraction rate deltas; LLM-judge formality gap. Report as distance to the *target* register, and also over-adaptation (caricature rate: slang used when user used none).
- Prosodic accommodation: agent vs user speech-rate ratio, pitch/energy distance, as in the entrainment literature.
- Emotional appropriateness: EchoMind's EmoAlign (emotion2vec on reply audio vs reference emotion) and a Gemini-based Vocal Empathy Score; for distress cases, check "complement not mirror" (agent slower and calmer than user).
- Audio-dependence (the headline number): response divergence for text-identical, voice-different pairs (embedding distance of replies + judge), per system.
- Guardrails: task correctness unchanged, p50/p95 latency, stability (profile does not flip-flop across turns).
- Human A/B: >= 20 blind raters, pairwise preference on rapport/naturalness, on both TTS-generated and his own recorded speech (EchoMind found human speech harder).
- Report confidence intervals and the number of scripts. Keep a "human-recorded" split separate from "TTS-generated" split.

**Post angle:** "I tested whether voice agents actually listen. Same words, different voice." Related to LISTEN and EchoMind, and ties to the Decagon/Dessa news hook. Note the headline risk: do not claim superiority over closed systems beyond what the eval shows.

## 6. Open questions / verify before building

- Hume EVI shutdown date (only third-party sources; check hume.ai).
- JoyAI-Talker open-weights status and license.
- PersonaPlex license terms.
- Whether ElevenLabs Expressive mode actually uses acoustic cues from the user's audio (docs say "how users sound" but give no mechanism).
- Sophon-Realtime and DuplexJev: benchmarks are self-reported; reproduce one before relying on them.
- Gemini 3.8 Live: Cloud docs describe prosody-based adjustment, but AI Studio docs say affective dialog was removed from the API; behavior is therefore implicit and not configurable.
- Whether a Block Dessa waitlist slot is worth requesting (no weights, no API).

## 7. Risks and ethics

- Do not condition on inferred age, gender or ethnicity; adapt to *how someone talks* (register, pace, affect), not who the system thinks they are. Avoid caricaturing dialects or accents.
- Mirroring distress or anger can escalate; use the complement policy and hand-off wording for real crisis content.
- Voice is biometric-adjacent data: process locally where possible, store nothing by default, get consent for any recorded eval speech.
- Disclose that it is an AI and that it adjusts its speech to the listener.

## 8. Source list (primary)

Decagon: https://decagon.ai/blog/decagon-chord-voice-model , https://decagon.ai/blog/voice-3 · Block Dessa: https://block.xyz/dessa · OpenAI GPT-Live-1: https://openai.com/index/introducing-gpt-live-1-in-the-api/ · Gemini 3.8 Live: https://aistudio.google.com/docs/models/gemini-3.8-live · ElevenLabs Expressive mode: https://elevenlabs.io/docs/eleven-agents/customization/voice/expressive-mode · Hume EVI 3: https://www.hume.ai/blog/introducing-evi-3 · Qwen3-Omni: https://arxiv.org/html/2509.17765 · PersonaPlex: https://arxiv.org/abs/2602.06053 · Moshi: https://arxiv.org/html/2410.00037 · JoyAI-Talker: https://arxiv.org/html/2608.01119 · OpenS2S: https://arxiv.org/abs/2507.05177 · Sophon-Realtime: https://huggingface.co/adventists-ai/Sophon-Realtime-v1 · DuplexJev: https://paperswithcode.co/paper/2610.02638 · EchoMind: https://arxiv.org/abs/2510.22758 · LISTEN: https://arxiv.org/html/2510.10444 · VoxDialogue: https://proceedings.iclr.cc/paper_files/paper/2025/hash/011df158529ddceb5f2f7a65f2732a5a-Abstract-Conference.html · StyleTalk: https://github.com/DanielLin94144/StyleTalk · E-chat: https://arxiv.org/html/2401.00475 · LSM: https://www.liwc.app/help/lsm · Synchrony-Stability: https://arxiv.org/html/2510.00339v1 · Full-Duplex-Bench v3: https://arxiv.org/abs/2604.04847 · Thinking Machines: https://thinkingmachines.ai/blog/interaction-models/ · Pipecat: https://github.com/pipecat-ai/pipecat/ · Kyutai Unmute / DSM: https://github.com/kyutai-labs/unmute/ , https://arxiv.org/html/2509.08753v2 · emotion2vec: https://github.com/ddlBoJack/emotion2vec · Fun-CosyVoice 3: https://github.com/FunAudioLLM/CosyVoice · Qwen3-TTS: https://arxiv.org/html/2601.15621 · GLM-4-Voice: https://arxiv.org/abs/2412.02612 · Step-Audio 2: https://arxiv.org/html/2507.16632 · Ultravox: https://github.com/fixie-ai/ultravox/ · Orpheus: https://github.com/canopyai/Orpheus-TTS · Dia: https://huggingface.co/nari-labs/Dia-1.6B · Sesame CSM: https://huggingface.co/sesame/csm-1b · Entrainment: https://aclanthology.org/N13-2012.pdf , https://www.cs.columbia.edu/speech/PaperFiles/2020/Galvez_speech_communication_2020.pdf
