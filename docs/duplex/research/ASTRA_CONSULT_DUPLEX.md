# Astra: independent duplex consultation

2026-11-14. Read `README.md` and `docs/PLAN.md`; checked the sources below today. Recommendations and budgets are proposals, not measured results.

**1. Recommendation: own the adaptation experiment and trained weights.**

Choose **Moshi fine-tuning**, preceded by a small learning exercise. “My own” should mean a reproducible derivative checkpoint, original paired data, and demonstrated behavior attributable to training. Full duplex means incoming audio continues to influence generation while the model speaks; microphone concurrency alone is insufficient.

| Route | Judgment and novelty |
|---|---|
| Full foundation model from scratch | Reject. Moshi used seven million hours of audio before later training stages. Reimplementing it would not itself be novel. A genuinely new learning method could be, but this budget cannot establish foundation-model competitiveness. |
| Fine-tune Moshi or PersonaPlex | Best route. LoRA itself and an empathetic persona are not novel. A controlled finding about learning delivery-dependent behavior could be. |
| Small duplex model from scratch | A 50–100M dual-stream transformer over frozen Mimi tokens is a plausible narrow-domain research prototype; its codec is still pretrained. Expect poor open conversation. A smaller event predictor is a learning exercise, not speech-to-speech. Novelty would require a new mechanism or finding, not small size. |
| Train a controller around frozen speech models | Cheapest fallback and potentially original research. Call it a learned duplex policy, not an end-to-end speech foundation model. |

The training-scale comparison comes from the [Moshi paper](https://arxiv.org/html/2410.00037v2). Keep the cascade as a baseline, data-labeling aid, and debugging oracle. Its current synthetic smoke results establish plumbing, not human benefit.

**2. What is actually available.**

[Moshi](https://github.com/kyutai-labs/moshi) provides official MLX inference, including quantized models, tested upstream on an M3 MacBook Pro. Python code is MIT, Rust Apache-2.0, and weights CC-BY-4.0. The separate [Apache-2.0 trainer](https://github.com/kyutai-labs/moshi-finetune) supports LoRA and reports 39.6 GB peak allocated GPU memory for its single-H100 example. Apple inference does **not** establish Apple training support. M5 throughput, our training memory, and adapter-to-MLX conversion parity remain unverified.

[PersonaPlex](https://github.com/NVIDIA/personaplex) has MIT code; [weights](https://huggingface.co/nvidia/personaplex-7b-v1) use the NVIDIA Open Model License with Moshi attribution information. The [license](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/) permits derivatives subject to its conditions. NVIDIA documents Linux/PyTorch and A100/H100, testing on A100 80 GB; that is not a minimum-memory requirement.

Community [MLX inference](https://github.com/mu-hashmi/personaplex-mlx) and [fine-tuning code](https://github.com/tin-computer/personaplex-finetune) exist. The latter is marked WIP, reports substantial training failures, and lists a single H100 or multiple 24 GB GPUs. I found no official NVIDIA training recipe. PersonaPlex is a possible later comparator, not the lowest-risk starting point.

**3. The claim to test.**

**Under a fixed small-data budget, delivery-paired fine-tuning improves human-rated response appropriateness to identical words spoken neutrally versus hesitantly, including cues received during assistant speech, over base Moshi and equally sized pairing-shuffled training, without degrading task completion.**

Begin with uncertainty and measured pace, not clinical distress. Appropriate support can mean offering clarification, not declaring that someone is sad.

Broad novelty is already gone: [SteerDuplex](https://arxiv.org/abs/2609.12623) studies instructed tone/speed control; [JoyAI-Talker](https://arxiv.org/abs/2608.01119) studies adaptive empathy; [Moshi emotion steering](https://arxiv.org/abs/2610.08887) finds decodable affect does not imply reliable controllability. Our candidate contribution is controlled learning from implicit delivery under overlap. This search does not establish priority. A well-supported null result separating recognition from behavioral use is worth publishing.

**4. Architecture and training.**

Start with `kyutai/moshiko-pytorch-bf16`. Moshi already has concurrent user/assistant audio streams and an assistant text stream; Mimi processes 24 kHz audio at 12.5 frames/second. Its text stream represents assistant speech, not an explanation of its listening. [Architecture](https://github.com/kyutai-labs/moshi#model-architecture).

Freeze Mimi, embeddings, and the depth transformer initially. Train rank-8/16 LoRA on temporal-transformer attention projections using teacher-forced text/audio prediction. Restricting adapters requires inspecting/modifying trainer parameter selection; this is a proposed configuration, not a verified preset. Start with gradient checkpointing, batch one, and accumulation. Audit audio/text loss balance and silence collapse before tuning anything else.

Training pairs must differ in user delivery **and appropriate target behavior**. Repeatedly showing hesitant audio with the same generic target gives no incentive to use it. Mix neutral conversations and retain interruptions/backchannels to limit forgetting.

For inspection, fit a separate causal probe on past-only hidden states for perceived hesitation and pace. Log probe confidence, acoustic measurements, generated text, and audio timestamps. A successful probe shows available information, not that generation uses it; input interventions establish behavioral use. Do not introduce emotion words into the assistant text stream initially: they can leak into speech and conflate supplied labels with listening.

**5. Data: prioritize real paired recordings.**

Aim for 12 consenting speakers: six training, two development, four untouched test. Eight supports only a smaller pilot. Record each speaker saying identical scripts in neutral and hesitant delivery, with independent fast/slow examples. Collect repeated takes; randomize recording order and balance microphones across conditions. Humans verify intelligibility and perceived delivery. Time stretching supplies pace controls, not authentic emotion.

Start with 20 paired episodes to debug. Then target 200–300 pairs of roughly 30-second two-channel conversations: approximately 3–5 hours. This is a feasibility budget, not evidence that enough data exists to teach empathy.

Curate targets with one consenting assistant speaker across both conditions: preserve factual content, vary delivery or offer a brief clarification when appropriate. Have listeners reject patronizing responses. Use local cascade drafts and synthetic neutral replay for augmentation, separately labeled; synthetic hours do not replace speaker diversity. Keep every target speaker/style combination balanced. Never supply delivery labels, revealing filenames, or different system prompts to the model. Voice drift from human targets is a risk to measure.

Keep simultaneous speech and silence on their original timeline. The official trainer expects assistant-left/user-right stereo plus timestamped transcripts. Hold out speakers, script families, sessions, and all transformations of each recording together. Reserve subtle cues, conflicting words/delivery, nuisance noise, and mid-response changes for harder evaluation.

**6. Evaluation: carry the design forward, not its assumptions.**

Reuse manifests, repeated seeds, measured output pace, blind matched-versus-swapped ratings, nuisance tests, and cluster-aware intervals. Keep static/adaptive cascades as contextual baselines; base Moshi is the direct training baseline.

Required model arms: base Moshi, paired LoRA, and equal-budget LoRA with target deliveries shuffled within script and speaker. At inference, swap neutral/hesitant user recordings with identical words; responses should follow the audio actually supplied. Matching scores against the original intended condition should fall. Do not shuffle arbitrary codec tokens: that destroys speech.

There is no drop-in “locked transcript” input for native Moshi. Verify identical spoken words and audit recognition separately; this cannot guarantee identical internal semantic representations. Add a fixed-assistant-text diagnostic to isolate output delivery, labeled as constrained generation.

For overlap trials, replay an identical conversation prefix, then introduce the cue while the assistant speaks. Use events triggered relative to actual assistant onset, log timing, and check that output does not change before the cue arrives. Separate duration-matched tone trials from pace trials.

Measure turn-end-to-audible-response latency, interruption-to-last-audible-output latency, false interruptions during pauses, appropriate versus intrusive overlap, backchannel precision/recall, cue-to-adaptation delay, task completion, and p50/p95 compute latency. Include buffering and audio playback; silent models must fail completion. [Full-Duplex-Bench](https://arxiv.org/abs/2503.04721) supplies established interaction categories.

Use at least 60 held-out pairs with three blind raters each as a pilot, resampling speakers and scripts rather than treating ratings as independent. Report per-speaker effects: four test speakers cannot support population-wide conclusions. Predeclare a useful effect and acceptable task loss on development data. Continuous metrics can saturate too: freeze the core, then version subtler challenges without tuning them to favor your model.

**7. Schedule and decision gates.**

- **First weekend:** learn sampling, codec tokens, causal masking, teacher forcing, and LoRA. Run quantized Moshi locally; measure ten minutes of streaming and overlap behavior with headphones. Collect 20 real pairs and test codec reconstruction. Gate: usable speech, intelligible cues, reproducible timestamps. If streaming falls behind, retain offline experiments and drop the local real-time promise.
- **First two weeks:** learn loss masking, alignment, validation splits, and overfitting. Train the tiny event predictor as an exercise, then overfit 20 episodes with Moshi LoRA after compute approval. Verify free-running speech and checkpoint reload, not merely falling loss. Test merge/conversion before promising Mac deployment. Gate: coherent changed behavior on training examples plus initial generalization to development speakers. If the model cannot overfit the tiny set, fix alignment/loss/inference before buying another training run.
- **First six weeks:** learn paired statistical comparisons and blind rating design. Run paired/shuffled training, a second training seed if affordable, frozen evaluation, and publish checkpoints, manifests, failure audio, and costs. If two controlled attempts fail to generalize, stop scaling. Publish the failure analysis or pivot to the smaller learned controller.

**8. Compute and cost.**

No paid jobs are authorized by this memo. Weekend: Mac, $0 incremental compute. First two weeks: request a capped $20–30 GPU experiment. The event-predictor exercise stays local; scratch speech pretraining is excluded from this budget because no credible six-week quality estimate is verified. Through week six: cap total cloud compute/storage at $150; participant compensation is separate and also requires approval.

[Runpod's current list](https://www.runpod.io/pricing) quotes A100 80 GB PCIe at $2.09/hour on Secure Cloud, from $1.19 on Community; H100 PCIe is $2.89/hour Secure. Budget roughly 40–60 A100 hours plus storage, not guaranteed training throughput. Benchmark one hour, then estimate epochs from measured steps/second. University GPU access, if available, is cheapest. An 80 GB rental avoids spending the project porting training to 32 GB unified memory. Do preprocessing locally and shut rented instances down between runs.

**9. Likely failures, in order.**

1. Too little diverse supervision: LoRA learns canned reassurance or speaker identity, not tone sensitivity. Probe success cannot rescue absent behavioral generalization.
2. Targets reward generic politeness or the wrong behavior. Blind crossed ratings and neutral false-reaction rates expose this.
3. Training damages speech, timing, or voice identity; teacher-forced loss hides free-running collapse.
4. Recording artifacts, target leakage, or synthetic-voice shortcuts explain the apparent effect.
5. MLX conversion, quantization, or buffering erases the trained benefit.
6. Too few speakers or agreeable friends make uncertain results look decisive.

Never label hesitation as a person's true emotional state.

**10. Cut in this order.**

Cut PersonaPlex comparisons; UI polish; register/slang adaptation; extra emotions; custom control tokens and auxiliary training losses; local real-time deployment. Keep inspectable traces, held-out humans, base/shuffled controls, task completion, and actual output-audio measurements. If those cannot fit, reduce the claim rather than remove the evidence.

