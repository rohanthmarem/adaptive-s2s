"""Builds docs/duplex/primer.html: the primer page (also published as an Artifact).

Usage: python build.py OUT.html
The page is written without <html>/<head>/<body> tags because the Artifact host wraps it.
"""

import sys
from pathlib import Path

import figures as fig

HERE = Path(__file__).parent

HEAD = """<title>Full-Duplex Speech Primer</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;600;700&display=swap">
<style>
{css}
</style>
"""


def res(title: str, url: str, meta: str, why: str, must: bool = False) -> str:
    badge = '<span class="must">essential</span>' if must else ""
    return (
        f'<li><span><a href="{url}">{title}</a>{badge}</span>'
        f'<span class="meta">{meta}</span><span class="why">{why}</span></li>'
    )


def stage(n: int, title: str, time: str, items: list[str], exercise: str) -> str:
    return (
        f'<div class="stage"><div class="stage-head"><h3>Stage {n}. {title}</h3><span class="time">{time}</span></div>'
        f'<ul class="res">{"".join(items)}</ul><p class="try"><b>Try it on your Mac</b>{exercise}</p></div>'
    )


STUDY = "".join([
    stage(1, "Sound as data, and how a model is trained", "about 3 hours", [
        res("Introduction to audio data", "https://huggingface.co/learn/audio-course/en/chapter1/audio_data",
            "Hugging Face Audio Course · lesson with code · 60 min",
            "Waveforms, sample rate and spectrograms, each beside a picture and a few lines of Python. It assumes no audio background.", True),
        res("Attention in transformers, step by step", "https://www.youtube.com/watch?v=eMlx5fFNoYc",
            "3Blue1Brown · video · 26 min",
            "Optional. Watch it first if attention still feels abstract."),
        res("Let's build GPT: from scratch, in code, spelled out", "https://www.youtube.com/watch?v=kCc8FmEb1nY",
            "Andrej Karpathy · coding lecture · 1 h 56 min",
            "Batches, targets, loss, the causal mask and sampling. A speech-token model is trained with exactly this loop.", True),
    ], "Record five seconds of your voice. Print its shape, length and sample rate, then plot the waveform and a mel spectrogram."),
    stage(2, "Speech models in general", "about 1.5 hours", [
        res("Hugging Face Audio Course, units 2 and 3", "https://huggingface.co/learn/audio-course/en/chapter0/introduction",
            "Hugging Face · course · skim in 75 min",
            "What speech recognition and text-to-speech models are, and how Whisper differs from wav2vec 2.0 and HuBERT. You need the vocabulary more than the detail.", True),
    ], "Run a small Whisper model on the same sentence said calmly and said in frustration. The two transcripts match. Write down what the transcript threw away."),
    stage(3, "Audio as tokens", "about 2 hours", [
        res("Neural audio codecs: how to get audio into LLMs", "https://kyutai.org/codec-explainer/",
            "Kyutai · interactive article with audio and animations · 75 min",
            "The best single explanation of codecs, residual vector quantization and Mimi, written by the team that built Moshi.", True),
        res("MusicGen documentation", "https://github.com/facebookresearch/audiocraft/blob/main/docs/MUSICGEN.md",
            "Meta AudioCraft · docs · 25 min",
            "Why the several tokens of one frame are predicted with small delays between them. Moshi uses the same idea."),
        res("Crossing the uncanny valley of conversational voice", "https://www.sesame.com/journal/crossing-the-uncanny-valley-of-voice",
            "Sesame · technical article with audio · 25 min",
            "A large backbone plus a small audio decoder over Mimi tokens, explained with examples. Read the technical half."),
    ], "Encode a two-second wav with an open codec such as EnCodec, print the grid of integers, decode it and listen. Then drop the later codebooks and listen again."),
    stage(4, "Moshi, the model this project builds on", "about 3.5 hours", [
        res("Moshi author talk", "https://www.youtube.com/watch?v=0_c3bw_x6uU",
            "Alexandre Défossez, Kyutai · video · 72 min",
            "One of the authors explains Mimi and the synchronised streams. Watch it before the paper.", True),
        res("Moshi: a speech-text foundation model for real-time dialogue", "https://arxiv.org/abs/2410.00037",
            "Kyutai · paper · 90 min for a first pass",
            "Read the introduction, sections 3.1, 3.3 and 3.4, and the training overview. Leave the result tables for later.", True),
        res("Moshi and Mimi: official code", "https://github.com/kyutai-labs/moshi",
            "Kyutai · repository · 30 min to read, longer to run",
            "The architecture summary and the Mac instructions. Find where the codec is loaded and where one frame is generated.", True),
        res("Voice AI's big moment", "https://www.mattturck.com/podcast/voice-ais-big-moment-why-everything-is-changing-now-ft-neil-zeghidour-gradium-ai",
            "The MAD Podcast with Neil Zeghidour · interview · 83 min",
            "Optional listening. A Moshi and SoundStream author on the path from codecs to full-duplex models."),
    ], "Run Moshi on your Mac and talk to it with headphones. Try a long pause in the middle of a sentence, a short \"mm-hm\", and an interruption. Note what it does each time."),
    stage(5, "Fine-tuning", "about 3 hours of reading, then a GPU experiment", [
        res("LoRA conceptual guide", "https://huggingface.co/docs/peft/main/en/conceptual_guides/lora",
            "Hugging Face PEFT · docs · 30 min",
            "How a frozen model plus small trainable add-ons can be fine-tuned on one GPU, and what the rank setting controls."),
        res("Moshi-Finetune: data preparation, LoRA training and inference", "https://github.com/kyutai-labs/moshi-finetune/blob/main/README.md",
            "Kyutai · official guide · 2 to 3 hours",
            "The exact data format and the training commands. This is the recipe the project will follow.", True),
    ], "Make three short stereo files in the format the guide asks for: the assistant on the left channel, the user on the right. Include a silence, a backchannel and an overlap."),
    stage(6, "Tone, emotion and empathy", "about 3.5 hours", [
        res("Do Audio LLMs Really LISTEN, or Just Transcribe?", "https://arxiv.org/abs/2510.10444",
            "Chen and colleagues · paper · 60 min",
            "How to test whether a model uses the voice when the words are neutral. This is the idea behind the project's evaluation.", True),
        res("EchoMind", "https://arxiv.org/abs/2510.22758",
            "Zhou and colleagues · paper and benchmark · 60 min",
            "A benchmark that goes from hearing vocal cues to answering with empathy, using controlled changes in delivery."),
        res("StyleTalk and Spoken-LLM", "https://arxiv.org/html/2402.12786v2",
            "Lin, Chiang and Lee · paper with dataset · 60 min",
            "A dataset where the same words, said in different styles, should get different replies. The closest published data design to ours."),
    ], "Record six neutral sentences in two different deliveries. Shuffle the twelve clips and ask a friend to rate what they hear. Keep the disagreements."),
    stage(7, "Measuring a full-duplex model", "about 2.5 hours", [
        res("Full-Duplex-Bench", "https://github.com/DanielLin94144/Full-Duplex-Bench",
            "Lin and collaborators · benchmark and code · 90 min",
            "Pauses, backchannels, turn-taking and interruptions. We run it to show that fine-tuning did not break the conversation skills.", True),
        res("TurnBench: measuring the timing of conversation", "https://www.sesame.com/journal/turnbench",
            "Sesame · technical article · 45 min",
            "How to score turn timing with events, false alarms and delays, and where that scoring still falls short for full-duplex models."),
    ], "Write ten test cases by hand: a pause inside a sentence, a true end of turn, a backchannel, an interruption and background speech, two of each."),
])

BODY = """
<main class="page">

<header>
  <p class="step">Primer · adaptive speech-to-speech project</p>
  <h1>How full-duplex speech models work</h1>
  <p class="lede">A path from "sound is a list of numbers" to fine-tuning a model that listens and speaks at the same time. Written for one project: a speech model that changes its tone to suit the person talking to it.</p>
  <p>You need Python and a user's understanding of LLMs: tokens, prompts, fine-tuning as an idea. You do not need any signal processing. Reading this page takes about 20 minutes. The study path at the end takes about 9.5 hours for the short route.</p>
  <nav class="contents" aria-label="Contents">
    <ol>
      <li><a href="#idea">The whole idea in six sentences</a></li>
      <li><a href="#sound">Sound is a long list of numbers</a></li>
      <li><a href="#codec">A codec turns sound into tokens</a></li>
      <li><a href="#lm">A language model over audio tokens</a></li>
      <li><a href="#text">The model writes what it is about to say</a></li>
      <li><a href="#duplex">Full duplex: two streams, one clock</a></li>
      <li><a href="#training">How these models are trained</a></li>
      <li><a href="#tone">Why tone is the hard part</a></li>
      <li><a href="#own">What "your own model" can mean</a></li>
      <li><a href="#study">Study path</a></li>
      <li><a href="#words">Words you will meet</a></li>
    </ol>
  </nav>
</header>

<section id="idea">
  <p class="step">Start here</p>
  <h2>The whole idea in six sentences</h2>
  <ol>
    <li>Sound is a very long list of numbers.</li>
    <li>A codec compresses it to about 100 tokens per second.</li>
    <li>A transformer predicts the next audio token the way an LLM predicts the next word.</li>
    <li>The model also writes the words it is about to say, which keeps its language sensible.</li>
    <li>Full duplex means the model reads one slice of your audio and writes one slice of its own every 80 milliseconds, with no turns.</li>
    <li>Tone lives in the tokens that are easiest to ignore, and teaching a model to use them is this project.</li>
  </ol>
</section>

<section id="sound">
  <p class="step">Step 1</p>
  <h2>Sound is a long list of numbers</h2>
  <p>A microphone measures air pressure thousands of times a second. Each measurement is a <strong>sample</strong>. Speech models usually work at 16,000 or 24,000 samples per second, so one second of speech is 24,000 numbers and a ten-second reply is 240,000.</p>
  <p>That is the first problem. A text model reads a few tokens per word. If every sample were a token, one sentence would be longer than a book chapter, and the model would spend all its effort on the shape of the wave and none on meaning.</p>
  <p>You will also meet the <strong>spectrogram</strong>: a picture of which pitches are present at each moment. Whisper reads one. It is a useful way to look at audio, but the models in this project do not use it. They use learned tokens.</p>
</section>

<section id="codec">
  <p class="step">Step 2</p>
  <h2>A codec turns sound into tokens</h2>
  <p>A <strong>neural audio codec</strong> is two networks trained together. The encoder squeezes audio into a short sequence of vectors. The decoder rebuilds the audio from them. In the middle, each vector is replaced by the closest entry in a fixed list called a <strong>codebook</strong>, so a slice of sound becomes an integer. That integer is a token.</p>
  __FIG_CODEC__
  <p>One codebook is too coarse to sound good. Codecs fix this with <strong>residual vector quantization</strong>. The first codebook stores its closest match. The second stores the closest match to whatever the first got wrong. The third corrects the second, and so on.</p>
  __FIG_RVQ__
  <p>Moshi's codec is called <strong>Mimi</strong>. It cuts 24,000 samples per second into 12.5 frames per second and writes 8 tokens for each frame. Each token picks one of 2,048 entries. So speech becomes 100 small integers per second, a 240-fold reduction in count.</p>
  <p>The eight tokens are not equal. Mimi trains the first one to agree with a speech-understanding model, so it mostly carries <strong>what was said</strong>. The other seven carry the rest: who is speaking, pitch, loudness, mood, the room. Remember this split. It comes back in step 7.</p>
</section>

<section id="lm">
  <p class="step">Step 3</p>
  <h2>A language model over audio tokens</h2>
  <p>Once audio is tokens, the LLM recipe applies: train a transformer to predict the next token, then generate by sampling one token after another. Decode the tokens and you hear speech.</p>
  <p>There is one snag. Each frame has several tokens, and a transformer step is expensive. Predicting 100 tokens a second in one long row is slow, and the row gets long quickly. Moshi splits the job between two transformers.</p>
  __FIG_TWO__
  <p>The <strong>temporal transformer</strong> is the big one: 32 layers. It takes one step per frame and reads the whole conversation so far. The <strong>depth transformer</strong> is small: 6 layers. It takes the big model's summary and writes the tokens of the next frame one at a time. The big model only runs 12.5 times a second, which keeps it fast enough to talk in real time.</p>
</section>

<section id="text">
  <p class="step">Step 4</p>
  <h2>The model writes what it is about to say</h2>
  <p>Models that predict only audio tokens speak fluently and reason badly. They sound like speech and drift in meaning. Moshi's fix is called the <strong>inner monologue</strong>. Alongside its audio, the model predicts a stream of text tokens that is lined up in time with its own speech. The text for a word appears just before the audio for that word, and padding tokens fill the gaps.</p>
  <p>In effect the model writes each word and then says it. This keeps the language quality of a text LLM. It also gives us a window: the text stream is something we can read, time-stamp and measure while the model talks.</p>
</section>

<section id="duplex">
  <p class="step">Step 5</p>
  <h2>Full duplex: two streams, one clock</h2>
  <p>A cascade takes turns. It waits for you to stop, thinks, then talks. A full-duplex model has no turns. Time is cut into 80 millisecond frames, and at every frame the model does the same thing: it reads the 8 tokens of <span class="user">your audio</span> for that frame, and writes one text token and 8 tokens of <span class="model">its own audio</span>. Often the audio it writes is silence.</p>
  __FIG_DUPLEX__
  <p>Nothing in the model says "now it is my turn". Starting early, murmuring agreement and stopping when interrupted are all the same act: predicting the next frame given both streams. The model learns when to speak from recordings of real conversations where each person is on a separate channel.</p>
  <p>This is also why a full-duplex model can react to how you sound while it is still talking. Your audio keeps arriving, frame after frame, the whole time.</p>
</section>

<section id="training">
  <p class="step">Step 6</p>
  <h2>How these models are trained</h2>
  <p>The training signal is the same at every stage: hide the next token, ask the model to predict it, and nudge the weights when it is wrong. What changes is the data.</p>
  <div class="tablewrap"><table>
    <thead><tr><th>Stage</th><th>Data</th><th>What the model learns</th><th>Who can do it</th></tr></thead>
    <tbody>
      <tr><td>Text pre-training</td><td>A large text corpus</td><td>Language and knowledge</td><td>Labs</td></tr>
      <tr><td>Audio pre-training</td><td>About 7 million hours of speech</td><td>To speak and to hear</td><td>Labs</td></tr>
      <tr><td>Duplex training</td><td>About 2,000 hours of two-channel phone calls, then about 20,000 hours of synthetic dialogue</td><td>Timing, overlap, and an assistant's voice and manner</td><td>Labs</td></tr>
      <tr><td>Fine-tuning</td><td>A few hours to a few tens of hours of your own dialogues</td><td>One new behaviour</td><td>You, on one rented GPU</td></tr>
    </tbody>
  </table></div>
  <p>The first three rows are the Moshi recipe and are out of reach for one person. The last row is where this project lives.</p>
  <p><strong>Fine-tuning</strong> starts from the released weights and continues training on a small dataset. <strong>LoRA</strong> makes that cheap: the original weights are frozen, and small extra matrices are trained beside them. Far fewer numbers change, so it fits on one GPU and the model is less likely to forget what it already knew.</p>
  <p>The data for a Moshi fine-tune is plain: stereo audio files with the assistant on the left channel and the user on the right, plus a file of word timestamps for the assistant's side. Silences and overlaps stay exactly where they happened, because the timing is part of what is being taught.</p>
  <div class="note">
    <h3>Two things that surprise people</h3>
    <p>A falling loss does not mean the model got better at conversation. During training the model always sees the true past. When it runs freely it sees its own output, and small errors can compound into silence or babble. Always listen to free-running output.</p>
    <p>The model learns exactly what the data rewards. If the right answer never depends on how the user sounded, the model has no reason to listen to that.</p>
  </div>
</section>

<section id="tone">
  <p class="step">Step 7</p>
  <h2>Why tone is the hard part</h2>
  <p>Say one sentence in a plain voice, then in a low, slow voice. The words are the same, so the first token row keeps its pattern. Almost everything that changed is in the other seven rows and in the timing.</p>
  __FIG_SAME__
  <p>Three things make this hard for a model.</p>
  <ul>
    <li><strong>The words are usually enough.</strong> In most training data the best reply can be guessed from the words alone, so a model reaches a low loss without using the voice. Researchers call this lexical dominance. The LISTEN paper measured it in six audio models.</li>
    <li><strong>The right data is rare.</strong> A model only learns to use tone from examples where the same words, said differently, get different replies. Ordinary speech corpora and most synthetic dialogues do not contain such pairs.</li>
    <li><strong>Knowing is not doing.</strong> A 2026 study of Moshi found that emotion can be read out of the model's internal activity, yet using that to steer how it speaks only partly worked. A separate 2026 benchmark played whispered requests to seven voice systems, and only 2 of 35 replies came back in a lowered voice.</li>
  </ul>
  <p>So the project needs two things that the earlier cascade work already started: paired data where delivery changes the right answer, and a test that holds the words fixed and changes only the voice.</p>
</section>

<section id="own">
  <p class="step">Step 8</p>
  <h2>What "your own model" can mean</h2>
  <div class="tablewrap"><table>
    <thead><tr><th>Route</th><th>What it takes</th><th>What you get</th></tr></thead>
    <tbody>
      <tr><td>Train a foundation model from scratch</td><td>Millions of hours of audio and a rack of GPUs</td><td>Not possible for one person. Rebuilding Moshi would not be new either.</td></tr>
      <tr><td>Fine-tune an open full-duplex model</td><td>Your own paired data, one rented GPU for a few hours per run, a small budget</td><td>Your own weights with a behaviour that came from your data, and an experiment that shows it. <strong>This is the main route.</strong></td></tr>
      <tr><td>Train a tiny duplex model from scratch</td><td>A laptop or one GPU, a small corpus, frozen Mimi tokens</td><td>Poor conversation, excellent understanding. A good learning exercise and a good blog post.</td></tr>
    </tbody>
  </table></div>
  <p>What makes the fine-tune yours is an experiment we did not find in published work: showing that a model learns to respond to how something is said, without being told to, and that the effect disappears when the pairing in the training data is shuffled.</p>
</section>

<section id="study">
  <p class="step">Step 9</p>
  <h2>Study path</h2>
  <p>Every link was opened and checked on 14 November 2026. Items marked essential make up the short route, about 9.5 hours, after which you can read the Moshi paper. The full list of 30 resources is in the project at <code>docs/duplex/research/LEARNING_RESOURCES.md</code>.</p>
  __STUDY__
</section>

<section id="words">
  <p class="step">Reference</p>
  <h2>Words you will meet</h2>
  <dl>
    <dt>Sample rate</dt><dd>How many measurements of the sound wave are stored per second. Mimi uses 24,000.</dd>
    <dt>Frame</dt><dd>One slice of time for the model. In Moshi a frame is 80 milliseconds, so there are 12.5 per second.</dd>
    <dt>Codec</dt><dd>An encoder and decoder that turn audio into tokens and back.</dd>
    <dt>Codebook</dt><dd>A fixed list of vectors. A token is the position of the closest one.</dd>
    <dt>RVQ</dt><dd>Residual vector quantization. Several codebooks in a row, each one encoding the error left by the one before.</dd>
    <dt>Semantic token</dt><dd>The first token of a frame, trained to carry mostly the words.</dd>
    <dt>Acoustic tokens</dt><dd>The remaining tokens of a frame. Voice, pitch, mood and room.</dd>
    <dt>Temporal transformer</dt><dd>The large model that steps once per frame.</dd>
    <dt>Depth transformer</dt><dd>The small model that writes the tokens inside one frame.</dd>
    <dt>Inner monologue</dt><dd>The text stream Moshi writes just ahead of its own speech.</dd>
    <dt>Full duplex</dt><dd>Listening and speaking at the same time, with incoming audio able to change what the model is saying.</dd>
    <dt>Backchannel</dt><dd>A short sound such as "mm-hm" that shows you are listening without taking the turn.</dd>
    <dt>Prosody</dt><dd>The melody and rhythm of speech: pitch movement, stress, pauses, pace, loudness.</dd>
    <dt>Teacher forcing</dt><dd>Training on the true past rather than on the model's own output.</dd>
    <dt>LoRA</dt><dd>Fine-tuning by training small added matrices while the original weights stay frozen.</dd>
    <dt>Lexical dominance</dt><dd>A model answering from the words and ignoring how they were said.</dd>
  </dl>
</section>

<footer>Figures are schematic. The numbers for Moshi and Mimi come from the Moshi paper and from Kyutai's released code.</footer>

</main>
"""


def build() -> str:
    css = (HERE / "style.css").read_text(encoding="utf-8")
    body = (
        BODY.replace("__FIG_CODEC__", fig.fig_codec())
        .replace("__FIG_RVQ__", fig.fig_rvq())
        .replace("__FIG_TWO__", fig.fig_two_transformers())
        .replace("__FIG_DUPLEX__", fig.fig_duplex())
        .replace("__FIG_SAME__", fig.fig_same_words())
        .replace("__STUDY__", STUDY)
    )
    assert "__" not in body.replace("__FIG", ""), "unreplaced placeholder"
    return HEAD.format(css=css) + body


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")
