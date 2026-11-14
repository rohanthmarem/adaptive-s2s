# From Python to an empathetic full-duplex speech model

Researched and links checked on **2026-11-14**. For a CS student who knows Python and uses LLMs, but has never trained an audio model.

Take the stages in order. There are **30 resources**, of which **10 are marked ESSENTIAL**. The full route is roughly **55–70 hours**, including the small local exercises but excluding substantial model training. Paper and course times are suggested study budgets, not publisher promises; video runtimes are rounded.

All main-curriculum URLs were opened and their contents or resource identities checked. YouTube sometimes returned only a shell or a fetch error through the research browser; direct HTTP requests to all three watch pages returned 200 with matching titles, and YouTube's official oEmbed endpoint confirmed the uploaders. Playback was not tested. This is resource research, not a claim that the exercises or repositories were executed.

## Minimum path: 9 hours 28 minutes to a first Moshi reading

This is a first-pass comprehension route, not preparation to train a production model. Use the assigned portions and leave installation problems, full exercises, and implementation replay for the longer curriculum.

| Order | Resource | Budget | What to do |
| --- | --- | --- | --- |
| 1 | [Introduction to audio data](https://huggingface.co/learn/audio-course/en/chapter1/audio_data) | 60 min | Read sampling, waveforms, STFT, and mel spectrograms; run one plot. |
| 2 | [Let's build GPT: from scratch, in code, spelled out](https://www.youtube.com/watch?v=kCc8FmEb1nY) | 116 min | Watch for batches, targets, loss, causal attention, optimization, and sampling. |
| 3 | [Hugging Face Audio Course](https://huggingface.co/learn/audio-course/en/chapter0/introduction) | 75 min | Skim Units 2–3 and the Unit 6 introduction: ASR, CTC, Whisper, and TTS. |
| 4 | [Neural audio codecs: how to get audio into LLMs](https://kyutai.org/codec-explainer/) | 75 min | Follow the quantization and RVQ animations, then the Mimi and semantic-token sections. |
| 5 | [MusicGen documentation](https://github.com/facebookresearch/audiocraft/blob/main/docs/MUSICGEN.md) | 25 min | Understand why codebooks are delayed and predicted in parallel. |
| 6 | [Conversational speech generation / CSM](https://www.sesame.com/journal/crossing-the-uncanny-valley-of-voice) | 25 min | Read the technical half: the backbone, small audio decoder, and conversation context. |
| 7 | [Moshi author talk — Alexandre Défossez](https://www.youtube.com/watch?v=0_c3bw_x6uU) | 72 min | Watch the explanation of Mimi and multiple synchronized streams. |
| 8 | [Moshi paper](https://arxiv.org/abs/2410.00037) | 90 min | Read the introduction, §3.1, §3.3–3.4, and the training-stage overview; postpone detailed results. |
| 9 | [Moshi official repository](https://github.com/kyutai-labs/moshi) | 30 min | Read the architecture summary and Mac/MLX instructions; locate codec loading and generation code. |

You should now be able to explain the difference between waveform samples, codec frames, codebooks, text tokens, and user/assistant streams. If you cannot draw how one 80 ms audio frame moves through Moshi, repeat steps 4, 7, and 8 before proceeding to fine-tuning.

## Stage 1 — Digital audio, from arrays to spectrograms

**Time: 2–3 hours.** Learn just enough signal processing to inspect data and avoid sample-rate mistakes.

### 1. ESSENTIAL — Introduction to audio data

**Author:** Hugging Face Audio Course team. **Type:** course lesson with executable Python examples. **Effort:** 60–90 minutes. **Level:** beginner.

**URL:** https://huggingface.co/learn/audio-course/en/chapter1/audio_data

Learn waveform amplitude, sampling rate, frequency spectra, short-time Fourier transforms (STFT), and mel filterbanks with NumPy and librosa. This is the most direct starting point because it assumes no audio background and puts each representation beside code and a picture.

**Mac exercise, 30–45 minutes:** Record five seconds of your voice as a WAV. In a notebook, print its shape, duration, and sample rate, then plot its waveform, STFT magnitude, and log-mel spectrogram. Change the STFT window and hop sizes and describe the time/frequency tradeoff; resample properly rather than changing the sample-rate label.

**Checkpoint:** A waveform is a sequence of amplitude measurements; a spectrogram summarizes local frequency content. A mel spectrogram is a continuous feature array, not a sequence of discrete codec IDs.

## Stage 2 — Refresh transformers and actual training

**Time: 4–5 hours.** These are the only two general transformer refreshers in the curriculum.

### 2. Attention in transformers, step-by-step — Deep Learning Chapter 6

**Author:** Grant Sanderson / 3Blue1Brown. **Type:** video, YouTube. **Length:** 26 minutes. **Level:** beginner.

**URL:** https://www.youtube.com/watch?v=eMlx5fFNoYc

Build a visual understanding of queries, keys, values, and attention heads. Watch before Karpathy if the matrix operations still feel abstract; it supplies intuition rather than a training recipe.

### 3. ESSENTIAL — Let's build GPT: from scratch, in code, spelled out

**Author:** Andrej Karpathy. **Type:** video and coding lecture, YouTube. **Length:** 1 hour 56 minutes; allow another 1–2 hours to reproduce selected code. **Level:** beginner to intermediate.

**URL:** https://www.youtube.com/watch?v=kCc8FmEb1nY

Build next-token prediction from data batches through loss, gradient updates, causal attention, and autoregressive sampling. This closes the gap between knowing what fine-tuning means as a user and understanding what a speech-token training loop actually optimizes.

**Mac exercise, 45–60 minutes:** Run a very small character model on CPU using a short text file. Print input/target shifts, training and held-out loss, and samples before and after training; keep the model small enough that observing the loop matters more than output quality.

**Checkpoint:** Explain teacher forcing, cross-entropy, the causal mask, and why lower training loss alone does not establish conversational quality.

## Stage 3 — Understand the speech ML landscape

**Time: 9–12 hours for selected material.** Do not complete every assignment in both courses.

### 4. ESSENTIAL — Hugging Face Audio Course: applications, architectures, ASR, and TTS

**Author:** Sanchit Gandhi, Matthijs Hollemans, Maria Khalusova, Vaibhav Srivastav / Hugging Face. **Type:** course with Python examples and notebook workflows. **Effort:** 5–7 hours for Units 2–3 and selected sections of Units 5–6. **Level:** beginner to intermediate.

**URL:** https://huggingface.co/learn/audio-course/en/chapter0/introduction

Learn the roles of automatic speech recognition (ASR), text-to-speech (TTS), encoder-only CTC models such as wav2vec 2.0 and HuBERT, and encoder-decoder models such as Whisper. Follow the CTC and Seq2Seq pages in Unit 3, then run one ASR example and inspect one TTS example before attempting fine-tuning.

### 5. CS224S: Spoken Language Processing — Spring 2025 syllabus

**Author:** Andrew Maas and the Stanford CS224S teaching team. **Type:** course syllabus, public slides, readings, and assignments. **Effort:** 2–3 hours for selected slides; the whole course is a quarter. **Level:** intermediate.

**URL:** https://web.stanford.edu/class/cs224s/semesters/2025-spring/syllabus

Use the acoustic phonetics, TTS/prosody, recognition, and dialogue material to connect the ML tasks to human speech. Public slides are useful, but the lecture recordings are restricted to registered students; this is not a freely watchable video course.

### 6. WavLM: Large-Scale Self-Supervised Pre-Training for Full Stack Speech Processing

**Author:** Sanyuan Chen and colleagues / Microsoft. **Type:** paper. **Effort:** 60–90 minutes for the introduction, related work, HuBERT background, and method. **Level:** intermediate to advanced.

**URL:** https://arxiv.org/html/2110.13900v5

Use its background sections to compare wav2vec 2.0's contrastive learning, HuBERT's masked prediction of clustered targets, and WavLM's masked prediction with denoising. WavLM matters later because Mimi distills semantic information from it; these speech encoders learn representations rather than directly serving as waveform reconstruction codecs.

**Mac exercise, 45–60 minutes:** Run a small pretrained Whisper checkpoint on CPU on two short recordings of the same sentence, one calm and one frustrated. Compare the transcripts, listen again, and write down what the transcript discards. Then extract hidden states from a small pretrained wav2vec 2.0 or HuBERT model and print their shape; do not train either model from scratch.

**Checkpoint:** Distinguish unlabeled-audio pretraining from supervised ASR fine-tuning. Whisper's speech-to-text objective and HuBERT/WavLM representation learning solve different problems from audio reconstruction.

## Stage 4 — Neural codecs and residual vector quantization

**Time: 6–8 hours.** Read the explainer first, then use the older systems to understand the design choices.

### 7. ESSENTIAL — Neural audio codecs: how to get audio into LLMs

**Author:** Václav Volhejn / Kyutai, October 2025. **Type:** interactive blog with audio, animations, pseudocode, and linked experimental code. **Effort:** 75–120 minutes. **Level:** beginner to intermediate.

**URL:** https://kyutai.org/codec-explainer/

Yes, Kyutai published precisely this explainer: it builds from raw samples through vector quantization and RVQ to Mimi and audio-token language modeling. It is the strongest bridge in this curriculum because it shows why reconstruction quality, token rate, and semantic information all matter.

The article's linked `nanoGPTaudio` code includes codec and RVQ notebooks. Its README explicitly warns about hardcoded paths and describes H100-scale experiments: use it for code reading, not as a ready-to-run Mac training tutorial.

### 8. SoundStream: An End-to-End Neural Audio Codec

**Author:** Neil Zeghidour, Alejandro Luebs, Ahmed Omran, Jan Skoglund, Marco Tagliasacchi / Google. **Type:** paper. **Effort:** 45–60 minutes, focusing on architecture and quantizer dropout. **Level:** intermediate.

**URL:** https://arxiv.org/abs/2107.03312

Understand the encoder–RVQ–decoder structure and why dropping quantizer layers during training permits different bitrates. It is the foundational codec design to recognize beneath later systems; you do not need to reproduce its adversarial training.

### 9. EnCodec: High Fidelity Neural Audio Compression — official implementation

**Author:** Alexandre Défossez and colleagues / Meta AI. **Type:** repo with encode/decode examples. **Effort:** 60–90 minutes. **Level:** intermediate.

**URL:** https://github.com/facebookresearch/encodec

Turn a waveform into integer codebook indices and reconstruct it with a real open codec. The README includes direct encoding/decoding examples and distinguishes the causal 24 kHz model from the noncausal 48 kHz model, making it useful for understanding streaming constraints.

### 10. Descript Audio Codec: High-Fidelity Audio Compression with Improved RVQGAN

**Author:** Rithesh Kumar and colleagues / Descript. **Type:** repo with training and inference code. **Effort:** 45–60 minutes for the README and quantizer implementation. **Level:** intermediate.

**URL:** https://github.com/descriptinc/descript-audio-codec

Compare another widely used RVQ codec and inspect its programmatic `encode`/`decode` interface. DAC is a useful reference for codec quality and codebook design, but its reconstruction capability alone does not make a dialogue system full-duplex.

**Mac exercise, 60–90 minutes:** Use EnCodec's 24 kHz model on CPU to encode and decode a two-second mono WAV. Print the code tensor shape and count integer IDs per second at two bandwidth settings, then listen to both reconstructions. Afterward, read Mimi's description in resource 18: distinguish its 24,000 waveform samples/second from 12.5 codec frames/second and multiple codebooks per frame.

**Checkpoint:** In RVQ, later codebooks encode residual errors in latent space. A codebook index is not a word, and the number of frames per second is not the total number of IDs across all codebooks.

## Stage 5 — Language models over audio tokens

**Time: 4–5 hours.** Trace the transition from audio continuation and TTS to context-aware speech generation.

### 11. AudioLM: a Language Modeling Approach to Audio Generation

**Author:** Zalán Borsos, Neil Zeghidour, and the Google Research team. **Type:** research blog with architecture diagrams and audio examples. **Effort:** 30–45 minutes. **Level:** intermediate.

**URL:** https://research.google/blog/audiolm-a-language-modeling-approach-to-audio-generation/

Learn how semantic and acoustic token streams let language-model methods generate coherent audio continuations. Read this before VALL-E so unconditional/prompted continuation and text-conditioned synthesis remain distinct in your mental model.

### 12. VALL-E — Neural codec language models for speech synthesis

**Author:** Chengyi Wang and colleagues / Microsoft Research. **Type:** official research demo and model explainer. **Effort:** 30–45 minutes. **Level:** intermediate.

**URL:** https://www.microsoft.com/en-us/research/project/vall-e-x/vall-e/

Study TTS as conditional prediction of codec IDs from phonemes and an acoustic prompt. The official diagrams and samples explain voice conditioning clearly; this page is a research demonstration, not an open fine-tuning package.

### 13. MusicGen: Simple and Controllable Music Generation — documentation

**Author:** Jade Copet and colleagues / Meta AI AudioCraft team. **Type:** repo documentation with Python examples and notebook links. **Effort:** 45–60 minutes. **Level:** intermediate.

**URL:** https://github.com/facebookresearch/audiocraft/blob/main/docs/MUSICGEN.md

Learn the delayed-codebook pattern that predicts several RVQ levels in parallel while preserving selected dependencies. The point here is sequence organization and compute cost, not learning music generation; this is a useful precursor to Moshi's acoustic delays and depth decoder.

### 14. Crossing the uncanny valley of conversational voice — technical section: Conversational speech generation

**Author:** Johan Schalkwyk, Ankit Kumar, Dan Lyth, Sefik Emre Eskimez, Zack Hodari, Cinjon Resnick, Ramon Sanabria, Raven Jiang / Sesame. **Type:** technical blog with audio and architecture animations. **Effort:** 30–45 minutes. **Level:** intermediate.

**URL:** https://www.sesame.com/journal/crossing-the-uncanny-valley-of-voice

Study CSM's large backbone, smaller audio decoder, Mimi tokens, and conditioning on conversation history to choose appropriate prosody. Sesame explicitly identifies conversation structure and full-duplex interaction as further work: the released CSM concept should not be confused with a complete simultaneous listening-and-speaking agent.

**Mac exercise, 30–45 minutes:** In NumPy, create a toy tensor with four codebooks and six time frames. Write flattening, parallel, and delayed layouts; print each layout and implement the inverse mapping. Explain which tokens from one frame can condition each prediction and how many backbone steps are needed before the first complete frame is available.

## Stage 6 — Full-duplex dialogue and a guided Moshi reading

**Time: 12–15 hours.** This is the central stage. The older systems supply useful contrasts; Moshi is the implementation target.

### 15. Generative Spoken Dialogue Language Modeling — dGSLM

**Author:** Tu Anh Nguyen, Eugene Kharitonov, and colleagues / Meta AI and collaborators. **Type:** paper, 2022 preprint / TACL 2023. **Effort:** 45–60 minutes. **Level:** intermediate to advanced.

**URL:** https://arxiv.org/abs/2203.16502

See how two-channel conversational audio and coupled transformer towers model overlap, laughter, and turn-taking without text. This is an important ancestor of duplex modeling, rather than an instruction-following assistant you can immediately deploy.

### 16. ESSENTIAL — Moshi: a speech-text foundation model for real-time dialogue — author talk

**Author:** Alexandre Défossez / Kyutai, hosted by the Conversational AI Reading Group, March 2025. **Type:** video talk, YouTube. **Length:** 72 minutes. **Level:** intermediate.

**URL:** https://www.youtube.com/watch?v=0_c3bw_x6uU

Hear a model author explain Mimi and efficient modeling of multiple audio streams before tackling the dense paper. The presentation also discusses Hibiki, so use the Moshi/Mimi material as the conceptual preparation rather than expecting a fine-tuning tutorial.

### 17. ESSENTIAL — Moshi: a speech-text foundation model for real-time dialogue

**Author:** Alexandre Défossez, Laurent Mazaré, Manu Orsini, Amélie Royer, Patrick Pérez, Hervé Jégou, Edouard Grave, Neil Zeghidour / Kyutai. **Type:** paper, 2024. **Effort:** 3–4 hours over two passes. **Level:** advanced.

**URL:** https://arxiv.org/abs/2410.00037

Learn Mimi's split semantic/acoustic RVQ, the temporal and depth transformers, separate user/assistant audio streams, and time-aligned text generation called Inner Monologue. First read §3.1, §3.3–3.4 and §4; on the second pass inspect the ablations that justify the architecture instead of trying to absorb every table at once.

### 18. ESSENTIAL — Moshi and Mimi: official code and Mac inference

**Author:** Kyutai. **Type:** repo and implementation documentation. **Effort:** 2–3 hours for code reading and a small inference attempt. **Level:** advanced.

**URL:** https://github.com/kyutai-labs/moshi

Use this as an architecture-to-code walkthrough: follow model loading, codec encoding, streaming generation, and waveform decoding while keeping the paper's diagrams beside you. The official MLX backend and quantized checkpoints provide a real Apple Silicon entry point; inference support does not establish Mac training support.

### 19. SyncLLM: Synchronous LLMs as Full-Duplex Dialogue Agents

**Author:** Bandhav Veluri, Benjamin N. Peloquin, Bokai Yu, Hongyu Gong, Shyam Gollakota / Meta AI and University of Washington. **Type:** official project explainer with paper and examples, EMNLP 2024. **Effort:** 45–60 minutes. **Level:** advanced.

**URL:** https://syncllm.cs.washington.edu/

Understand how chunk interleaving and explicit synchronization give a pretrained text LLM a relationship to wall-clock time. Compare this with Moshi's parallel streams, especially what the model knows about incoming audio when generating the next chunk.

### 20. PersonaPlex: Voice and Role Control for Full Duplex Conversational Speech Models

**Author:** NVIDIA ADLR. **Type:** official repo and inference documentation, 2026. **Effort:** 45–60 minutes. **Level:** advanced.

**URL:** https://github.com/NVIDIA/personaplex

Study a Moshi-derived model that combines text role prompts and audio voice conditioning while retaining duplex interaction. It is relevant to controlling your model's persona and delivery, but role/voice prompting is not evidence of reliable emotion perception or empathy; the linked release documents inference rather than a verified end-to-end training recipe.

### 21. A Survey of Full-Duplex Spoken Dialogue Systems: Architectural Hierarchy, Interaction Ontology, and Decision State Machine

**Author:** Jingyu Lu and colleagues. **Type:** survey paper, June 2026. **Effort:** 60–90 minutes for the taxonomy and comparison tables. **Level:** intermediate to advanced.

**URL:** https://arxiv.org/abs/2606.19453

Learn to distinguish where listening/speaking decisions are made and which interaction behaviors a system actually supports. Read after the concrete architectures so labels such as full-duplex do not hide differences between streaming capability, turn management, and observed behavior.

### 22. Voice AI's Big Moment: Why Everything Is Changing Now

**Author:** Matt Turck interviewing Neil Zeghidour, a Moshi and SoundStream coauthor; The MAD Podcast, February 2026. **Type:** podcast/interview with a public transcript and video link. **Length:** 83 minutes; a focused pass through the codec, Kyutai, evaluation, and architecture chapters takes about 30 minutes. **Level:** beginner to intermediate.

**URL:** https://www.mattturck.com/podcast/voice-ais-big-moment-why-everything-is-changing-now-ft-neil-zeghidour-gradium-ai

Hear the builder's account of the path from codecs to audio LMs and full-duplex interaction, including data and real-world noise problems. Use it for research judgment and context; the papers and code remain the specification.

**Mac exercise, 60–90 minutes:** Follow the official MLX instructions with a quantized Moshi checkpoint if your memory budget permits. Try a long mid-sentence pause, a brief “mm-hmm,” and an interruption; record what happened and the machine configuration. If the full model does not fit, run only a short Mimi encode/decode on CPU and build a Python replay of two synchronized WAV channels in 80 ms chunks; both paths should produce a time-indexed table of incoming and outgoing frames.

**Reading checkpoint:** Draw Mimi → temporal transformer → depth transformer → Mimi decoder. Mark the user stream, assistant stream, assistant text, silence/padding, causal boundaries, and the distinction between codec delay, computation time, and conversational response timing.

## Stage 7 — Fine-tuning an open full-duplex model

**Time: 6–8 hours of preparation, then a separately budgeted GPU experiment.** Use Moshi's official recipe for the first attempt.

### 23. LoRA — conceptual guide

**Author:** Hugging Face PEFT maintainers, explaining Low-Rank Adaptation. **Type:** documentation / explainer. **Effort:** 30–45 minutes. **Level:** intermediate.

**URL:** https://huggingface.co/docs/peft/main/en/conceptual_guides/lora

Learn how frozen base weights and small trainable update matrices reduce trainable parameter count, and what rank controls. This gives the intuition needed for Moshi's LoRA settings; Moshi uses its own training implementation, so PEFT examples are not a drop-in Moshi trainer.

### 24. ESSENTIAL — Moshi-Finetune: official data preparation, LoRA training, and inference guide

**Author:** Kyutai. **Type:** repo and official fine-tuning documentation. **Effort:** 2–3 hours to read and prepare a tiny dataset; training time depends on hardware and configuration. **Level:** advanced.

**URL:** https://github.com/kyutai-labs/moshi-finetune/blob/main/README.md

Learn the actual stereo dialogue format, timestamped transcript sidecars, JSONL manifests, configuration, LoRA training, and checkpoint inference. The README reports about 39.6 GB peak allocated GPU memory for its example on one H100, so prepare and validate data on your Mac and plan the documented training run on a suitable CUDA machine rather than assuming MLX inference implies MLX fine-tuning.

**Mac exercise, 60–90 minutes:** Create three short synchronized stereo examples: left channel is the target assistant and right channel is the user, exactly as the README specifies. Include silence, one backchannel, and one overlap; write the duration manifest and timestamped transcript sidecars, then validate duration, channel order, timestamps, and clipping locally. Do not concatenate alternating turns after deleting silences: you would remove the timing behavior you want to learn.

**First fine-tuning experiment:** On suitable GPU hardware, first overfit a few examples to establish that data, loss, checkpoint loading, and inference connect correctly. Then use a small speaker-disjoint train/dev/test split and compare the base model with the adapter on the same recordings, including pauses and interruptions. Keep a manifest of source data, licenses/permissions, sample rates, roles, timing annotations, model revision, and training settings.

**Completion criterion:** Save an adapter, reload it through the documented inference path, and demonstrate one intended behavioral change on held-out speakers while checking intelligibility and turn-taking. A loss curve or a training-set voice imitation alone is not this milestone.

## Stage 8 — Prosody, emotion, and empathy

**Time: 6–8 hours.** Separate hearing emotion, choosing an appropriate response, and delivering that response appropriately. Prosody includes pitch movement, rhythm, stress, timing, and loudness; none is a universal emotion label.

### 25. Detecting Empathy in Speech

**Author:** Run Chen, Haozhe Chen, Anushka Kulkarni, Eleanor Lin, Linda Pang, Divya Tadimeti, Jun Shin, Julia Hirschberg / Columbia University. **Type:** paper, Interspeech 2024. **Effort:** 45–60 minutes. **Level:** intermediate.

**URL:** https://www.cs.columbia.edu/speech/PaperFiles/2024/interspeech24_empathy_paper.pdf

Learn how researchers collect empathy judgments and examine interpretable acoustic/prosodic features. It grounds “empathetic voice” in a measurable perception task while helping you avoid treating one pitch or speaking-rate rule as an empathy solution.

### 26. ESSENTIAL — Do Audio LLMs Really LISTEN, or Just Transcribe? Measuring Lexical vs. Acoustic Emotion Cues Reliance

**Author:** Jingyi Chen, Zhimeng Guo, Jiyun Chun, Pichao Wang, Andrew Perrault, Micha Elsner. **Type:** paper and benchmark proposal, 2025. **Effort:** 60–75 minutes. **Level:** intermediate to advanced.

**URL:** https://arxiv.org/abs/2510.10444

Learn to test whether a model uses tone when the words are emotionally neutral or conflict with delivery. This is essential for your specific goal: an apparently empathetic answer can come from transcript clues while ignoring the speaker's voice.

### 27. EchoMind: An Interrelated Multi-level Benchmark for Evaluating Empathetic Speech Language Models

**Author:** Li Zhou, Lutong Yu, You Lyu, Yihang Lin, Zefeng Zhao, Junyi Ao, Yuhao Zhang, Benyou Wang, Haizhou Li. **Type:** paper and benchmark, 2025; revised March 2026. **Effort:** 60–90 minutes. **Level:** advanced.

**URL:** https://arxiv.org/abs/2510.22758

Study the linked progression from spoken-content understanding through vocal-cue perception and reasoning to empathetic response generation. Its controlled delivery changes help you design evaluations that test both what the model understands and what it says or sounds like afterward.

### 28. Advancing Large Language Models to Capture Varied Speaking Styles and Respond Properly in Spoken Conversations — StyleTalk / Spoken-LLM

**Author:** Guan-Ting Lin, Cheng-Han Chiang, Hung-yi Lee / National Taiwan University. **Type:** paper with dataset and implementation links, ACL 2024. **Effort:** 60–90 minutes. **Level:** advanced.

**URL:** https://arxiv.org/html/2402.12786v2

Learn a concrete data-construction and training approach in which identical words spoken in different styles should receive different responses. This is the speech-dialogue StyleTalk dataset and Spoken-LLM work, not the unrelated talking-head animation project with the same name; its style conditioning is useful inspiration, not an established full-duplex empathy recipe.

**Mac exercise, 60–90 minutes:** Record six identical, emotionally neutral sentences in two contrasting deliveries. Randomize the twelve clips and build a small evaluation sheet with separate ratings for perceived emotion, response content, response vocal delivery, and timing. Compare audio-conditioned outputs with a transcript-only baseline; split by speaker when expanding the set, and preserve disagreements rather than presenting your intended emotion as unquestionable ground truth.

**Design implication:** Build matched-content/different-delivery pairs and speaker-disjoint tests before collecting a large fine-tuning corpus. Treat a style-matching objective, an emotion-recognition objective, and human-rated appropriate empathy as separate measurements; automatically copying a distressed speaker's tone is not necessarily a good response.

## Stage 9 — Evaluate duplex interaction and regressions

**Time: 3–4 hours.** Measure interaction behavior alongside speech and empathy quality.

### 29. ESSENTIAL — Full-Duplex-Bench: official benchmark suite

**Author:** Guan-Ting Lin and collaborators. **Type:** repo, evaluation code, datasets, and linked papers, 2025–2026. **Effort:** 90–120 minutes for protocols and a small offline subset. **Level:** advanced.

**URL:** https://github.com/DanielLin94144/Full-Duplex-Bench

Start with v1's pauses, backchannels, turn-taking, and interruptions, then v1.5's overlap scenarios; the repository also contains v2 real-time multi-turn evaluation and v3 disfluent speech with tool use. These versions answer different questions, so report the exact protocol and avoid treating a later version as the same score with more examples.

### 30. TurnBench: measuring the timing of conversation

**Author:** Sefik Emre Eskimez, Ankit Kumar, Françoise Beaufays, Freeman Jiang, Ramon Sanabria, Soham Deshmukh, Bandhav Veluri, Satyapriya Krishna / Sesame, August 2026. **Type:** technical blog and benchmark explainer. **Effort:** 45–60 minutes. **Level:** intermediate to advanced.

**URL:** https://www.sesame.com/journal/turnbench

Learn event-based end-of-turn and interruption evaluation using recall, false positives, and signed latency rather than judging speed alone. Its stated limitation matters: the interruption track does not yet directly evaluate full-duplex models' simultaneous generated speech, so use it alongside Full-Duplex-Bench rather than as a complete replacement.

**Mac exercise, 45–60 minutes:** Create a ten-case offline set covering a pause inside a sentence, a true turn end, a backchannel, a real interruption, and background speech, with two cases each. Annotate expected behavior and event times in JSON, replay WAVs in fixed chunks, and score a saved base-model response and adapter response for false takeovers, missed interruptions, stop delay, and response onset. CPU waveform inspection is enough for this exercise; a complete benchmark run may need a GPU inference endpoint and additional ASR/judge services.

**Report the result in four separate groups:** intelligibility/content, audio/prosodic quality, emotion/empathy, and interaction timing. Include paired listening judgments, the benchmark version, hardware, real-time factor, and latency percentiles. Retain neutral and conflicting-cue cases so improved style does not hide damaged comprehension or interruption handling. This reporting plan is a proposed capstone protocol, not a claim that the listed papers validate one combined empathy score.

## Could not verify / access limits

- **Les géants de la tech s'appuient sur cette IA parisienne — Neil Zeghidour**, Underscore_, November 9, 2026. **Type:** podcast/interview, French. **Length:** 46 minutes according to indexed metadata. **Level:** intermediate. **URL:** https://podcasts.apple.com/tn/podcast/les-g%C3%A9ants-de-la-tech-sappuient-sur-cette-ia/id1556250107?i=1000800708295 — Search metadata identifies a Moshi interview, but opening the episode failed; excluded from the curriculum. The verified English MAD interview above fills the builder-interview role.
- **CS224S lecture recordings:** the public course states recordings are available only to registered students. Public syllabus/slides were verified; do not plan on public YouTube access to the 2025 lectures.
- **Official PersonaPlex fine-tuning instructions:** I verified the NVIDIA inference repository, but did not verify a published official fine-tuning recipe. Use the verified Kyutai Moshi-Finetune instructions for the first training project; do not assume they apply unchanged to PersonaPlex.
- **Local execution:** no package installation, model download, notebook execution, Mac performance test, or training run was performed during this research. The Mac exercises are deliberately small CPU/MLX tasks, and the documented CUDA fine-tuning milestone is separate.
