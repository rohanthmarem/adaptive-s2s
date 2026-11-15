import argparse
import html
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from adaptive_s2s.audio import load_audio, to_16k

DELIVERY_ORDER = ["plain", "sad", "flat", "hesitant", "frustrated", "excited", "anxious"]


def transcribe_replies(asr, conversation_dir, trace):
    audio, sr = load_audio(conversation_dir / "moshi.wav")
    audio16k = to_16k(audio, sr)
    replies = []
    for event in trace["events"]:
        if not (event["phase"].startswith("reply") or event["phase"] == "greeting"):
            continue
        clip = audio16k[int(event["start_s"] * 16000): int(event["end_s"] * 16000)]
        segments, _ = asr.transcribe(clip, beam_size=5, language="en", vad_filter=True) if len(clip) > 1600 else ([], None)
        replies.append({**event, "heard": " ".join(s.text.strip() for s in segments).strip()})
    return replies


def rel(path, base):
    return html.escape(os.path.relpath(path, base))


def emotion_cell(sentence, target):
    emotion = sentence["emotion"]
    top = max(emotion, key=emotion.get)
    mark = "hit" if target and top == target else ("miss" if target else "")
    extra = f"pitch sd {sentence['pitch_sd_semitones']:.1f} st, " if sentence.get("pitch_sd_semitones") else ""
    words = "" if sentence["words_ok"] else ' <span class="miss">words changed: ' + html.escape(sentence["heard"]) + "</span>"
    return (f'<li><span class="said">{html.escape(sentence["text"])}</span> '
            f'<span class="tag {mark}">{top} {emotion[top]:.2f}</span> '
            f'<span class="dim">{extra}{sentence["words_per_s"]:.1f} words/s, best of {sentence["takes_scored"]}</span>{words}</li>')


def build(args):
    from faster_whisper import WhisperModel
    from adaptive_s2s.asr import cached_model_path

    asr = WhisperModel(cached_model_path("Systran/faster-whisper-small.en"), device="cpu", compute_type="int8")
    root = args.root
    manifest = json.loads((root / "manifest.json").read_text())
    conversations = {}
    for trace_path in sorted((root / "moshi").glob("*/trace.json")):
        trace = json.loads(trace_path.read_text())
        trace["replies"] = transcribe_replies(asr, trace_path.parent, trace)
        trace["dir"] = trace_path.parent
        conversations.setdefault((trace["scene"], trace["delivery"]), []).append(trace)

    scenes = {}
    for entry in manifest:
        scenes.setdefault(entry["scene"], []).append(entry)

    sections = []
    for scene_id, entries in scenes.items():
        entries.sort(key=lambda e: DELIVERY_ORDER.index(e["delivery"]))
        first = entries[0]
        columns = []
        for entry in entries:
            target = entry["target_label"]
            user_blocks = []
            for index, turn in enumerate(entry["turns"]):
                sentences = "".join(emotion_cell(s, target) for s in turn["sentences"])
                user_blocks.append(f'<div class="turn"><div class="label">User turn {index + 1}</div>'
                                   f'<audio controls preload="none" src="{rel(turn["file"], root)}"></audio><ul>{sentences}</ul></div>')
            runs = []
            for trace in conversations.get((scene_id, entry["delivery"]), []):
                replies = "".join(
                    f'<li><b>{html.escape(r["phase"])}</b> <span class="dim">{r["start_s"]:.1f}-{r["end_s"]:.1f}s, {html.escape(r["ended_because"])}</span><br>'
                    f'{html.escape(r["heard"]) or "<i>(nothing audible)</i>"}</li>' for r in trace["replies"])
                key = html.escape(trace["dir"].name)
                runs.append(f'<div class="run"><div class="label">Moshi, seed {trace["seed"]}</div>'
                            f'<audio controls preload="none" src="{rel(trace["dir"] / "mix.wav", root)}"></audio>'
                            f'<ol class="replies">{replies}</ol>'
                            f'<details><summary>Moshi text stream</summary><p class="dim">{html.escape(trace["moshi_text"])}</p></details>'
                            f'<label class="rate">Fits the voice? <select data-key="{key}"><option value=""></option>'
                            f'<option>yes</option><option>partly</option><option>no</option><option>no reply</option></select></label></div>')
            columns.append(f'<section class="col"><h3>{html.escape(entry["delivery"])}</h3>{"".join(user_blocks)}'
                           f'{"".join(runs) or "<p class=dim>No Moshi runs yet.</p>"}</section>')
        badge = '<span class="badge">same words, only the voice differs</span>' if first["same_words"] else ""
        sections.append(f'<article><h2>{html.escape(first["title"])} {badge}</h2>'
                        f'<p class="situation">{html.escape(first["situation"])}</p>'
                        f'<div class="cols">{"".join(columns)}</div></article>')

    page = TEMPLATE.replace("__BODY__", "".join(sections))
    (root / "review.html").write_text(page)
    print(root / "review.html")


TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Moshi Voice Review</title>
<style>
:root{--bg:#f5f6f8;--card:#fff;--ink:#17202b;--dim:#5d6875;--line:#dde1e6;--hit:#1d7a46;--miss:#b4361d;--accent:#2952a3}
@media (prefers-color-scheme:dark){:root{--bg:#11151a;--card:#1a2028;--ink:#e6e9ed;--dim:#9aa5b1;--line:#2b333d;--hit:#5fd18f;--miss:#ff8a6b;--accent:#8fb0ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif;padding:24px max(16px,env(safe-area-inset-left))}
main{max-width:1300px;margin:0 auto;display:flex;flex-direction:column;gap:24px}
h1{margin:0;font-size:26px}h2{margin:0 0 6px;font-size:19px}h3{margin:0 0 8px;font-size:15px;text-transform:uppercase;letter-spacing:.06em;color:var(--accent)}
article{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px}
.situation{color:var(--dim);margin:0 0 14px;max-width:80ch}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:16px}.col{min-width:0}
.turn,.run{border-top:1px solid var(--line);padding:10px 0}.label{font-size:12px;font-weight:600;color:var(--dim);text-transform:uppercase;letter-spacing:.05em}
audio{width:100%;height:34px;margin:4px 0}ul,ol{margin:4px 0;padding-left:18px}li{margin:3px 0}
.tag{font:12px ui-monospace,monospace;padding:1px 6px;border-radius:999px;border:1px solid var(--line)}.tag.hit{color:var(--hit);border-color:var(--hit)}.tag.miss,.miss{color:var(--miss)}
.dim{color:var(--dim);font-size:13px}.badge{font-size:12px;font-weight:500;color:var(--accent);border:1px solid var(--accent);border-radius:999px;padding:2px 8px;vertical-align:middle}
.rate{display:block;margin-top:6px;font-size:13px}button{font:inherit;padding:6px 12px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
textarea{width:100%;min-height:80px;font:12px ui-monospace,monospace;background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:8px}
</style></head><body><main>
<header><h1>Moshi voice review</h1><p class="dim">Each scene's user turns were rendered locally with Qwen3-TTS, one emotion direction applied to every sentence, best of three takes per sentence. The tag after each sentence is what the emotion model heard in that sentence alone. Moshi hears the turns in a simulated call: it greets, each user turn starts after Moshi goes quiet, and Moshi replies freely. Reply text is a Whisper transcript of Moshi's audio.</p>
<p><button id="export">Export ratings</button></p><textarea id="out" hidden readonly></textarea></header>
__BODY__
</main><script>
const KEY='moshi-voice-review';let saved={};try{saved=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
document.querySelectorAll('select[data-key]').forEach(s=>{s.value=saved[s.dataset.key]||'';s.addEventListener('change',()=>{saved[s.dataset.key]=s.value;try{localStorage.setItem(KEY,JSON.stringify(saved))}catch(e){}})});
document.getElementById('export').onclick=()=>{const t=document.getElementById('out');t.hidden=false;t.value=JSON.stringify(saved,null,2);t.select()};
</script></body></html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT / "out/duplex-scenes")
    build(parser.parse_args())


if __name__ == "__main__":
    main()
