"""The scripted demo: four spoken user turns, the adaptive system next to a static baseline.

The user turns are spoken by a macOS voice, so this is a demonstration of the pipeline, not a result.
The output is one self-contained HTML page with relative audio paths. It opens from `file://`.
"""

from __future__ import annotations

import html
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import yaml

from .audio import load_audio, save_wav
from .pipeline import Session, TurnResult, build_pipeline
from .types import ARMS

ARM_TITLES = {
    "full": "Adaptive",
    "static": "Static baseline",
    "text-only": "Adaptive words only",
    "voice-only": "Adaptive voice only",
}


def render_user_audio(script: dict, wav: Path) -> None:
    """Speak one scripted user turn with macOS `say`, then optionally slow it down without changing pitch."""
    aiff = wav.with_suffix(".aiff")
    subprocess.run(["say", "-v", script["voice"], "-r", str(script["rate"]), "-o", str(aiff), script["text"]], check=True)
    subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(wav)], check=True)
    aiff.unlink()
    stretch = float(script.get("stretch", 1.0))
    if stretch != 1.0:
        import parselmouth
        from parselmouth.praat import call

        audio, sr = load_audio(wav)
        sound = parselmouth.Sound(audio.astype("float64"), sampling_frequency=sr)
        slowed = call(sound, "Lengthen (overlap-add)", 75, 600, stretch)
        save_wav(wav, slowed.values[0], int(slowed.sampling_frequency))


def run_demo(args) -> int:
    if not shutil.which("say") or not shutil.which("afconvert"):
        raise RuntimeError("The demo needs macOS `say` and `afconvert`. On other systems use `s2s converse` with your own wavs.")
    out = Path(args.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    scripts = yaml.safe_load((Path(__file__).parent / "evals/scripts.yaml").read_text(encoding="utf-8"))["demo"]
    pipeline = build_pipeline(args.asr_model, args.affect, args.llm, args.llm_model)
    print("Loading models...")
    pipeline.warm()
    arms = [args.arm] + (["static"] if args.compare_static and args.arm != "static" else [])
    sessions = {arm: Session(pipeline, out / arm) for arm in arms}

    from .cli import print_summary

    turns: list[dict] = []
    for i, script in enumerate(scripts, 1):
        wav = out / f"user_{i:02d}.wav"
        render_user_audio(script, wav)
        results = {}
        for arm, session in sessions.items():
            results[arm] = session.turn(wav, arm=ARMS[arm], seed=args.seed, measure_reference=True)
            print_summary(results[arm])
        turns.append({"index": i, "script": script, "wav": wav.name, "results": results})

    (out / "index.html").write_text(build_page(turns, arms), encoding="utf-8")
    print(f"Demo page: {out / 'index.html'}")
    return 0


# --- page -------------------------------------------------------------------------------------------


def _e(value) -> str:
    return html.escape(str(value))


def _num(value, digits: int = 2, unit: str = "") -> str:
    return "n/a" if value is None else f"{value:.{digits}f}{unit}"


def _chip(label: str, value: str, tone: str = "") -> str:
    return f'<span class="chip {tone}"><b>{_e(label)}</b> {_e(value)}</span>'


def _user_block(turn: dict, r: TurnResult) -> str:
    a, reg = r.acoustic, r.register
    pace = _num(a.articulation_rate_sps, 2, " syll/s") + ("" if a.valid else " (too short to trust)")
    chips = [_chip("Pace", pace)]
    if reg.slang_hits or reg.reductions:
        chips.append(_chip("Casual words", ", ".join(reg.slang_hits + reg.reductions), "casual"))
    if reg.formal_hits:
        chips.append(_chip("Formal words", ", ".join(reg.formal_hits), "formal"))
    if reg.distress_hits:
        chips.append(_chip("Distress words", ", ".join(reg.distress_hits), "support"))
    if r.affect.available:
        chips.append(_chip("Emotion model", f"{r.affect.top_label} {_num(r.affect.top_score)}"))
    else:
        chips.append(_chip("Emotion model", "off"))
    return (
        f'<div class="user"><div class="who">User says</div>'
        f'<audio controls preload="none" src="{_e(turn["wav"])}"></audio>'
        f'<p class="heard">{_e(r.transcript.text)}</p>'
        f'<p class="script">Script: {_e(turn["script"]["text"])}</p>'
        f'<div class="chips">{"".join(chips)}</div></div>'
    )


def _reply_block(arm: str, index: int, r: TurnResult) -> str:
    realised = r.tts.get("realised_speed")
    rate = r.output_acoustic.articulation_rate_sps if r.output_acoustic else None
    stub = '<p class="warn">Stub reply. No language model was used.</p>' if r.llm["stub"] else ""
    why = "".join(f"<li>{_e(line)}</li>" for line in r.controls.rationale if not line.startswith("arm="))
    why = f"<ul>{why}</ul>" if why else '<p class="muted">No adaptation. Fixed style and fixed speed.</p>'
    return (
        f'<section class="reply {_e(arm)}"><div class="who">{_e(ARM_TITLES.get(arm, arm))}</div>'
        f'<audio controls preload="none" src="{_e(arm)}/turn_{index:02d}.reply.wav"></audio>'
        f'<p class="said">{_e(r.reply_text)}</p>{stub}'
        f'<div class="chips">{_chip("Speed asked", _num(r.controls.voice.speed, 2, "x"))}'
        f'{_chip("Speed measured", _num(realised, 2, "x"))}{_chip("Rate", _num(rate, 2, " syll/s"))}'
        f'{_chip("Pauses", _num(r.controls.voice.pause_scale, 1, "x"))}</div>'
        f'<div class="why"><div class="label">Why</div>{why}</div></section>'
    )


def _summary_table(turns: list[dict], arms: list[str]) -> str:
    head = "<tr><th>Turn</th><th>User pace</th><th>Register</th><th>Support</th>" + "".join(
        f"<th>{_e(ARM_TITLES.get(arm, arm))}: speed asked / measured</th>" for arm in arms
    ) + "</tr>"
    rows = []
    for turn in turns:
        first = turn["results"][arms[0]]
        cells = "".join(
            f'<td>{_num(turn["results"][arm].controls.voice.speed, 2, "x")} / '
            f'{_num(turn["results"][arm].tts.get("realised_speed"), 2, "x")}</td>'
            for arm in arms
        )
        rows.append(
            f'<tr><td>{turn["index"]}</td><td>{_num(first.acoustic.articulation_rate_sps, 2, " syll/s")}</td>'
            f"<td>{_e(first.state_after.register)}</td><td>{first.state_after.support:.2f}</td>{cells}</tr>"
        )
    return f'<table><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table>'


_CSS = """
:root{--bg:#f6f6f3;--card:#fff;--ink:#1c2230;--muted:#667085;--line:#e3e3dd;--accent:#2f5fd0;
--casual:#fff1d6;--formal:#e2ecff;--support:#fde4e1;--chip:#f0f0ec}
@media (prefers-color-scheme:dark){:root{--bg:#14161b;--card:#1d2028;--ink:#e8eaf0;--muted:#98a2b3;
--line:#2c303a;--accent:#8fb0ff;--casual:#4a3a14;--formal:#1d2f57;--support:#522924;--chip:#272b35}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1080px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:28px;line-height:1.2;margin:0 0 8px}h2{font-size:18px;margin:0 0 12px}
.lede{color:var(--muted);max-width:70ch;margin:0 0 8px}.meta{color:var(--muted);font-size:14px;margin:0 0 24px}
.notice{border:1px solid var(--line);border-left:4px solid var(--accent);background:var(--card);
padding:12px 16px;border-radius:8px;margin:0 0 24px;max-width:80ch}
.tablewrap{overflow-x:auto;margin:0 0 32px}table{border-collapse:collapse;width:100%;font-size:14px;
font-variant-numeric:tabular-nums;background:var(--card);border:1px solid var(--line);border-radius:8px}
th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--muted);font-weight:600}tr:last-child td{border-bottom:0}
article{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;margin:0 0 20px}
.who,.label{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:600;margin:0 0 8px}
audio{width:100%;height:36px;margin:0 0 8px}.heard,.said{font-size:18px;margin:0 0 8px}
.script{color:var(--muted);font-size:14px;margin:0 0 8px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 4px}
.chip{background:var(--chip);border-radius:999px;padding:2px 10px;font-size:13px;font-variant-numeric:tabular-nums}
.chip b{font-weight:600;color:var(--muted);margin-right:4px}
.chip.casual{background:var(--casual)}.chip.formal{background:var(--formal)}.chip.support{background:var(--support)}
.replies{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;margin-top:16px;
padding-top:16px;border-top:1px solid var(--line)}
.reply{min-width:0}.reply.full .who,.reply.text-only .who,.reply.voice-only .who{color:var(--accent)}
.why{margin-top:12px}.why ul{margin:0;padding-left:18px;font-size:14px;color:var(--muted)}
.muted{color:var(--muted);font-size:14px;margin:0}.warn{color:#b42318;font-weight:600;margin:0 0 8px}
"""


def build_page(turns: list[dict], arms: list[str]) -> str:
    """The whole demo page as one HTML string."""
    first = turns[0]["results"][arms[0]]
    emotion = first.affect.model if first.affect.available else "off"
    models = (
        f"Speech recognition: faster-whisper {_e(first.transcript.model)}. "
        f"Replies: {_e(first.llm['model'] or first.llm['backend'])}. "
        f"Speech: Kokoro ({_e(first.tts['voice'])}). Emotion model: {_e(emotion)}."
    )
    articles = []
    for turn in turns:
        any_result = turn["results"][arms[0]]
        replies = "".join(_reply_block(arm, turn["index"], turn["results"][arm]) for arm in arms)
        articles.append(
            f'<article><h2>Turn {turn["index"]}</h2>{_user_block(turn, any_result)}'
            f'<div class="replies">{replies}</div></article>'
        )
    compare = (
        "The same audio goes through the adaptive system and through a static baseline that uses the same models."
        if len(arms) > 1
        else "The audio goes through one arm of the system."
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Adaptive speech demo</title><style>{_CSS}</style></head><body><main>"
        "<h1>Adaptive speech-to-speech: demo conversation</h1>"
        f'<p class="lede">Four scripted user turns in one conversation. {compare} '
        "Listen for the reply's wording and its pace.</p>"
        f'<p class="meta">{models} Made {datetime.now():%Y-%m-%d %H:%M}.</p>'
        '<p class="notice">The user turns are spoken by a macOS voice at set speeds. This page shows that the '
        "pipeline works end to end. It is not an evaluation result. \"Speed measured\" compares the reply with "
        "the same words synthesised at neutral speed.</p>"
        f'<div class="tablewrap">{_summary_table(turns, arms)}</div>'
        + "".join(articles)
        + "</main></body></html>"
    )
