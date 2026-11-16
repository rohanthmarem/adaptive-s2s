# Plan: your own full-duplex model that adapts to how you sound

Written 2026-11-14. Lead: Fable. Second opinion: Astra (`research/ASTRA_CONSULT_DUPLEX.md`, verbatim).
Research behind it, with sources: `research/MODELS_AND_FINETUNING.md`, `research/DATA_AND_EVAL.md`,
`research/LEARNING_RESOURCES.md`. The background you need is in the primer (`primer.html`).

This replaces the cascade as the goal. The cascade in this repo stays as the baseline, the source of draft
training targets, and the measurement code.

## 1. Decision

**Fine-tune Kyutai's Moshi with your own paired data, and prove the fine-tune taught it to listen.**

- **"Your own model" means:** your own trained weights (a LoRA adapter on Moshi), your own dataset, and a
  controlled experiment showing the new behaviour came from your training.
- **It does not mean** training a full-duplex model from scratch. Moshi was trained on about 7 million hours
  of audio. Rebuilding it is out of reach for one person and would not be new.
- **A tiny from-scratch model is a side track** for learning (section 9). It will not hold a conversation.

Fable and Astra reached this recommendation independently. The research task on open models reached it too.

### Why Moshi

| Reason | Detail |
|---|---|
| It is really full duplex | It models your audio and its own audio at the same time, in 80 ms frames. |
| Public fine-tuning recipe | `kyutai-labs/moshi-finetune` (Apache-2.0): LoRA or full fine-tune, with a documented data format. No other open full-duplex model has an official one. |
| Runs on your Mac | Official MLX inference. Weights are CC-BY-4.0. |
| Recorded files can drive it | A wav can be fed in as the user's stream and the reply saved. That is what makes a controlled experiment possible. |

The strongest argument against it: Moshi's conversation quality is modest, and fine-tuning is known to
disturb its timing. NVIDIA's PersonaPlex (built on Moshi) is a better talker but has no official training
recipe. It becomes a comparison system later, not the base.

## 2. The claim to earn

> With a small, fixed amount of data, fine-tuning Moshi on **delivery-paired** dialogues makes its replies
> depend on **how** the user speaks when the **words are identical**. Blind human raters see this on speakers
> the model never heard. An equal-size fine-tune with the pairing **shuffled** does not show it. Task
> completion and turn-taking do not get worse.

The shuffled fine-tune is the key control. It sees the same audio and the same replies, but which reply
goes with which delivery is scrambled. If it scores like the paired one, the model learned a new speaking
style and did not learn to listen.

**A null result is still worth publishing.** "A small fine-tune could not teach a full-duplex model to use
tone, and here is where it broke" is a real finding if the controls are in place.

### What is already taken, so the claim stays honest

| Published work (checked 2026-11-14) | What it did | What it leaves open |
|---|---|---|
| SteerDuplex, Sept 2026 ([arXiv 2609.12623](https://arxiv.org/abs/2609.12623)) | Fine-tuned Moshi to change tone, persona and speed **when instructed** | Adapting **without** being told |
| Emotion directions in Moshi, Oct 2026 ([arXiv 2610.08887](https://arxiv.org/abs/2610.08887)) | Emotion is readable from Moshi's activations, but steering with it only partly works | Whether **training** can make behaviour use it |
| InteractionBench, Nov 2026 ([arXiv 2611.02430](https://arxiv.org/abs/2611.02430)) | Tested seven voice systems, including Moshi. Only 2 of 35 whispered requests got a reply in a lowered voice. | A model that does adapt |
| StyleTalk, EchoMind | Same words, different delivery, for turn-based models | The same test on a full-duplex model, including cues that arrive while it is talking |
| JoyAI-Talker | Describes an adaptive-empathy design | No weights or code to check |

We did not find the paired-versus-shuffled experiment on a full-duplex model. That search does not prove
nobody has done it.

## 3. What the model should learn

Start with two deliveries that ordinary people can record honestly, then add the emotional one.

| The user sounds | The reply should | When |
|---|---|---|
| Neutral | Answer normally | Experiment 1 |
| Rushed | Be brief and direct, a little faster | Experiment 1 |
| Hesitant or unsure | Slow down, simplify, check understanding | Experiment 1 |
| Low and subdued | Acknowledge first, stay calm, one small next step | Experiment 2, after the method works |

Hesitation comes first on Astra's advice, and Fable agrees. It is easy to record without acting, easy to
rate, and it carries no claim about a person's emotional state. The subdued delivery is the "empathy"
headline, and it comes second because acted sadness is the hardest thing to record and judge fairly.

The substance of the answer stays the same in every row. Only wording, pace and manner change.

## 4. How it will be built

```
scripts ──> user audio in 3 deliveries ─┐                      ┌─> paired data ───> LoRA A ─┐
   │        (TTS voices + real people)  ├─> two-channel files ─┤                            ├─> same-words test
   └──────> target replies ─────────────┘   + word timings     └─> shuffled data ─> LoRA B ─┤   on held-out people
            (cascade drafts, checked by you)                         stock Moshi ───────────┘
```

### Data

- **Format (fixed by the trainer):** stereo wav, assistant on the left channel, user on the right, silences
  and overlaps kept in place, plus a JSON of word timestamps for the assistant channel.
- **One "family" is one script in every delivery.** The user's words are identical across the family. The
  target reply differs by delivery. All versions of a family stay in the same split.
- **User side:** several voices crossed with every delivery, so the model cannot solve the task by
  recognising a voice. Synthetic voices for volume, real recordings mixed in as you collect them.
- **Assistant side:** one fixed voice. Reply wording drafted by this repo's cascade policy and a local LLM,
  then checked by you. Reject anything patronising.
- **Mixed in:** ordinary conversations with no adaptation (DailyTalk), so the model keeps its general
  ability.
- **Amounts:** 20 clips, then 1 to 2 hours, then a 5-hour pilot. Scale past 5 hours only if the held-out
  test improves. No published result says how much is enough.
- **Test set, built first and never trained on:** real people only. You and as many consenting friends as
  you can get, with at least four held out entirely. About 60 families.

### Training

- **Base:** `kyutai/moshiko-pytorch-bf16`. **Trainer:** `moshi-finetune`, LoRA, official settings for the
  first run so there are as few unknowns as possible.
- **Where:** one rented 80 GB GPU. The trainer is CUDA-only. The repo's own number is about 40 GB of GPU
  memory on one H100. Your Mac cannot train it.
- **Before paying for anything:** read trainer issue #24 (a padding bug reported on 2026-11-06) and issue
  #12 (fine-tunes that respond late).
- **First run is an overfit test:** 20 episodes, until the model reproduces them. This proves the data,
  the loss and the checkpoint all connect.
- **Then two runs at the same budget:** paired data and shuffled data. A second seed of each if money allows.
- **Back to the Mac:** Kyutai ships a script that merges a LoRA into the weights and exports them for MLX.
  Test this early.

### Evaluation

The existing harness carries over: stimulus manifests, pace and wording measures, cluster-bootstrap
intervals, the blind rating sheet. Three things are new.

1. **A duplex runner.** It plays a recorded user wav into the model's user stream and saves the model's
   audio and text on the same clock. A first version already works on your Mac (section 7).
2. **No transcript lock.** An audio-in model cannot be handed fixed words. Instead, check with speech
   recognition that the two deliveries really contain the same words.
3. **Full-duplex measures:** time from the user finishing to the model speaking, stopping when interrupted,
   false starts during pauses, and **cues that arrive while the model is already talking**. The last one is
   the test a turn-based system cannot take.

| Compared | Why |
|---|---|
| Stock Moshi | The direct baseline |
| LoRA on paired data | The model under test |
| LoRA on shuffled data | Shows the effect needs the pairing |
| Same words, the other delivery, swapped at test time | The reply must follow the audio actually played |
| Neutral twice | The noise floor |
| The cascade from this repo | A reference point that is known to adapt |
| Full-Duplex-Bench v1.0 and v1.5 | Shows turn-taking did not break |

The headline number stays the same as before: blind raters score each reply against the delivery it was made
for and against the other delivery of the same words. Matched minus swapped is the gain.

## 5. Stages, gates and cost

Nothing is spent until you approve it. The Mac does everything except training.

| Stage | When | What | Gate to pass | Cost |
|---|---|---|---|---|
| **0. Learn and listen** | This weekend | The short study path (9.5 h). Talk to Moshi on your Mac. Record 20 script pairs yourself. | You can draw how one 80 ms frame moves through Moshi | $0 |
| **1. Baseline** | Weeks 1 to 2 | Run stock Moshi through the same-words test with the duplex runner. Compare with the cascade. **Blog post 1: does a full-duplex model hear how you say it?** | The runner gives the same result twice. The measures are stable across seeds. | $0 |
| **2. Prove the loop** | Weeks 2 to 3 | Build the data pipeline at small scale. Overfit 20 episodes on a rented GPU. Export to MLX. | The model reproduces the 20 episodes, still talks sensibly on its own, and survives the export | Up to $30 |
| **3. The experiment** | Weeks 3 to 5 | 5-hour dataset. Paired and shuffled fine-tunes. Held-out human test. Full-Duplex-Bench. | Paired beats stock and shuffled on held-out people, with no loss in task completion | Up to $120 |
| **4. Write up** | Week 6 | Post, demo, and release of the adapter, the data recipe and the test | | $0 |

**If stage 3 fails twice with the controls in place, stop scaling.** Publish the failure analysis, or switch
to one of the fallbacks in section 8.

### Where the cost estimate comes from

- Rental prices read on 2026-11-14: an 80 GB A100 is about $2.00 to $2.10 an hour, an H100 about $2.90 to
  $4.40.
- The trainer's default run (2,000 steps) works out to about 8 GPU-hours, or $32 to $62. That default is
  sized for about 20 hours of data. A 5-hour dataset needs far fewer steps.
- Planning figure: 1.5 to 2 GPU-hours per run, about $5 to $9, and about 8 runs. With storage and mistakes,
  **$150 covers the whole experiment**.
- These are estimates. The first paid hour is a benchmark: measure steps per second, then recompute.
- If your university gives students GPU access, use that first.

## 6. Where Fable and Astra disagreed

| Topic | Fable | Astra | Chosen |
|---|---|---|---|
| Training data | Mostly synthetic voices, because recruiting many speakers is the hardest part for one person | Mostly real recordings from 12 speakers, because synthetic hours do not replace real variety | **Synthetic for volume, real recordings mixed in, and a test set of real people only.** Report real and synthetic results separately. |
| First delivery to teach | Sadness, since empathy is the goal | Hesitation and pace, since they can be recorded and rated honestly | **Astra's.** Sadness is experiment 2. |
| Making the listening visible | Have the model write a short "what I heard" tag on its text stream before it replies | A separate probe on the model's activations. Tags could be spoken aloud or confuse the result. | **Probe first.** The tag becomes an optional experiment 3, because whether an explicit listening step helps is a good question on its own. |
| LoRA settings | The trainer's defaults first | Small rank on the attention layers only | **Defaults first**, then smaller. |
| Budget | About $150 | $20 to $30 first, $150 cap | **Same thing.** $30 to prove the loop, $150 cap. |
| Tiny from-scratch model | Worth doing as a learning side track | A small event predictor is enough for learning | **Optional side track**, cut first if time is short. |

## 7. Checked on your Mac today

- **Installed:** Kyutai's `moshi_mlx` package (0.3.0) in a separate test environment.
- **Read from the code:** the model steps once per 80 ms frame (1,920 samples at 24 kHz), reads 8 tokens of
  user audio and writes one text token and 8 audio tokens. The large transformer has 32 layers and the small
  one has 6.
- **Found a snag:** the packaged offline script (`moshi_mlx.run_inference`) fails on the standard Moshi
  weights, because it expects a `config.json` that those weight repos do not have. A 60-line driver (`docs/duplex/moshi_offline.py`) that
  loads the model the way the live app does gets around it. It is the seed of the duplex runner.
- **First offline run (8-bit weights, two demo clips, each padded with 4 s of silence before and 10 s after):**
  - Speed: 0.7x real time with this simple driver, so about 27 s to process 19 s of audio. Fine for
    offline experiments. Real-time talk needs the live app, which was not measured here.
  - Moshi greets at 0.5 s, before the user speaks, in both runs: "Hey, how was your day?"
  - "I just got laid off this morning and I don't know what to do": **no reply at all** in the 10 s after.
  - "Can we move it to Friday?": after a 4 s gap it said "I'm sorry, but I'm not comfortable with that. We
    discussed this a few weeks ago, and we both agreed to meet on Tuesday."
  - One seed and one run each, so this is an anecdote. It still shows the stage 1 baseline will not be
    flattering, and that the replies will need people to rate them.
  - Audio is in `out/moshi-first-run/` (not in git).

To talk to Moshi yourself (stage 0), with headphones on:

```bash
scripts/moshi-local  # opens http://localhost:8998
```

The launcher creates the repository-local Python environment if needed and uses cached weights
by default. On a new machine, run `HF_HUB_OFFLINE=0 scripts/moshi-local` to download
the weights (about 8.5 GB) and web assets. The missing `config.json` warning is expected
for these weights; Kyutai falls back to its built-in Moshi configuration.

For recorded audio: `HF_HUB_OFFLINE=1 .venv-moshi/bin/python docs/duplex/moshi_offline.py IN.wav OUT.wav`.
Supply silence after the recorded speech to leave time for a response.

## 8. Risks, most likely first

1. **Too little or too narrow data.** The model learns a stock reassuring phrase, or learns the voices,
   and not the delivery. The shuffled control and the held-out speakers expose this.
2. **The targets reward generic politeness.** Then every reply sounds kind and none depends on the voice.
   Matched-minus-swapped ratings and the false-reaction rate on neutral speech expose this.
3. **Fine-tuning damages speech or timing.** Training loss looks fine while free-running speech collapses
   or responds late. Always listen to free-running output, and run Full-Duplex-Bench.
4. **Synthetic shortcuts.** The model keys on artefacts of the TTS voices. Only real people are in the test.
5. **Tooling.** The trainer bug, the export to MLX, or quantisation changes the behaviour.
6. **Too few speakers.** Four test speakers support a pilot. Report per-speaker results.
7. **Moshi itself.** Its replies can be odd, which makes "appropriate" harder to rate.

**Fallbacks if the fine-tune cannot learn it:** more data on one delivery only; the listening-tag
experiment; or a small learned controller around a frozen speech model, described honestly as a learned
duplex policy and not as an end-to-end model.

## 9. Side track: a tiny duplex model from scratch

For understanding, not for results. Train a 10 to 50 million parameter two-stream transformer over frozen
Mimi tokens on about 20 hours of two-channel speech (DailyTalk). The open project `caramel` is a readable
starting point. Expect babble with roughly correct turn-taking. It costs a few dollars of GPU time or a
long run on the Mac, and it makes the Moshi paper concrete.

## 10. Cut in this order if time runs out

The PersonaPlex comparison, the listening-tag experiment, the from-scratch side track, register and slang,
the subdued delivery, a live demo on the Mac.

**Never cut:** stock Moshi as the baseline, the shuffled control, held-out real speakers, task completion,
and measuring the audio the model actually produced. If those do not fit, make the claim smaller.
