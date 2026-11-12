# Claim check of the preliminary research

Checked 2026-11-12 (UTC) by a research agent that read the primary pages. It covers the claims in
`PRELIM_RESEARCH.md` that the plan depends on. Astra checked a few more claims on its own; those are in
section 6 of `ASTRA_CONSULT.md`.

Verdicts: **confirmed** (read on a primary page), **partly** (some of the claim holds), **unverifiable**
(no primary source found).

| # | Claim | Verdict | Source read | Note |
|---|---|---|---|---|
| 1 | emotion2vec+ exists, is open, has 9 classes | Partly | [HF large](https://huggingface.co/emotion2vec/emotion2vec_plus_large), [GitHub](https://github.com/ddlBoJack/emotion2vec) | Repos exist and are not gated. License is "other" (FunASR model license) on HF but MIT on GitHub. No official ONNX export. |
| 2 | CREMA-D is usable as same-sentence, different-emotion audio | Confirmed | [GitHub](https://github.com/CheyneyComputerScience/CREMA-D) | ODbL. 12 sentences, 6 emotions, 91 actors. Direct wav URLs work (16 kHz mono). |
| 3 | Hume EVI/TTS APIs shut down 2026-11-13 | Partly | [dev.hume.ai changelog](https://dev.hume.ai/voice/changelog) | Not readable on any hume.ai page. Search summaries and competitor blogs agree. Probably true. |
| 4 | Decagon Chord is post-trained, Voice 3 is duplex | Confirmed | [Chord](https://decagon.ai/blog/decagon-chord-voice-model), [Voice 3](https://decagon.ai/blog/voice-3) | "A speech model we post-trained for customer conversations." Both posts dated 2026-10-01. |
| 5 | Block's Dessa is trained from scratch, research preview | Partly | [block.xyz/dessa](https://block.xyz/dessa) | "From scratch" and "full-duplex" confirmed. Page says waitlist, not "research preview". The 2026-10-23 date is not on the page. |
| 6 | LISTEN: audio LLMs show lexical dominance | Confirmed | [arXiv 2510.10444](https://arxiv.org/abs/2510.10444), [EACL 2026](https://aclanthology.org/2026.eacl-long.274/) | "A consistent lexical dominance"; near chance on paralinguistic-only input. |
| 7 | EchoMind: same script, three vocal styles, 12 models | Confirmed | [arXiv 2510.22758](https://arxiv.org/abs/2510.22758) | Dataset on HF under CC-BY-NC-SA-4.0. EmoAlign and Vocal Empathy Score are defined there. |
| 8 | Synchrony-Stability Frontier: bounded mirroring is more stable | Confirmed | [arXiv 2510.00339](https://arxiv.org/abs/2510.00339) | EMA plus cap raises stability from 0.542 to 0.878 for about 17% less synchrony. |
| 9 | LSM formula and nine categories | Partly | [liwc.app](https://www.liwc.app/help/lsm) | Composite and the 0.0001 term confirmed. The formula and category table are images, so the nine names were not read from text. |
| 10 | ElevenLabs v4 Turbo, Expressive mode, audio tags | Confirmed | [Expressive mode](https://elevenlabs.io/docs/eleven-agents/customization/voice/expressive-mode) | "Adapting in real time to how users sound and what they say." Mechanism not disclosed. |
| 11 | GPT-Live-1 costs $0.05/min, GA 2026-09-10 | Partly | [model docs](https://developers.openai.com/api/docs/models/gpt-live-1) | Price confirmed. GA date comes only from news. |
| 12 | Gemini 3.8 Live removed affective dialog | Confirmed | [AI Studio](https://aistudio.google.com/docs/models/gemini-3.8-live) | "Affective dialogue is removed from the API." |
| 13 | JoyAI-Talker weights are available | Unverifiable | [arXiv 2608.01119](https://arxiv.org/abs/2608.01119) | Paper only. No repo found on HF or GitHub. |
| 14 | PersonaPlex-7B is open | Confirmed | [HF](https://huggingface.co/nvidia/personaplex-7b-v1) | Weights under the NVIDIA Open Model License. Code is MIT. |
| 15 | Qwen3-TTS, Fun-CosyVoice 3, Orpheus are open | Confirmed | [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS), [Orpheus](https://github.com/canopyai/Orpheus-TTS) | All three Apache-2.0. |

## What this changes in the plan

- **emotion2vec+ is contaminated for the public acted-emotion sets.** Its seed model is fine-tuned on EmoBox,
  whose table lists CREMA-D, RAVDESS and IEMOCAP. Results on those sets are in-distribution for the analyzer.
  The held-out split must be fresh recordings.
- **emotion2vec+ labels are bilingual** (for example `生气/angry`). Parse the part after the slash. Order in
  the large model: angry, disgusted, fearful, happy, neutral, other, sad, surprised, unknown.
- **Do not build on Hume.** The shutdown is probably real even though the notice was not read directly.
- **Do not cite JoyAI-Talker as something to run.** It is a design reference only.
- **Soften two statements for the blog:** Dessa is a waitlist (not a "research preview"), and the GPT-Live-1
  launch date is unconfirmed.
- **LSM category names** come from Ireland et al. 2011 and were not re-read here. The harness uses open word
  lists for the nine categories and labels the metric "LSM-lite", because it is not the LIWC dictionary.

## CREMA-D details used by the eval harness

- File pattern: `AudioWAV/{ActorID}_{SENT}_{EMO}_{LEVEL}.wav`
- Raw URL pattern:
  `https://media.githubusercontent.com/media/CheyneyComputerScience/CREMA-D/master/AudioWAV/1001_DFA_ANG_XX.wav`
- Emotions: ANG, DIS, FEA, HAP, NEU, SAD. Levels: LO, MD, HI, XX.
- Sentences: IEO "It's eleven o'clock", TIE "That is exactly what happened", IOM "I'm on my way to the
  meeting", IWW "I wonder what this is about", TAI "The airplane is almost full", MTI "Maybe tomorrow it will
  be cold", IWL "I would like a new alarm clock", ITH "I think I have a doctor's appointment", DFA "Don't
  forget a jacket", ITS "I think I've seen this before", TSI "The surface is slick", WSI "We'll stop in a
  couple of minutes".
