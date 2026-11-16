import argparse
import base64
import io
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from moshi_tone_analyse import TONES

TOP_UNITS = 6
AUDIO_RATE = 12000
QWEN_TRACES = [("callback", 1), ("grades", 1)]
GROK_SCRIPTS = ["interview", "pepper"]
GROK_TONES = {"neutral": "plain", "sad": "sad", "excited": "excited", "flat": "flat", "hesitant": "hesitant",
              "frustrated": "frustrated"}
GROK_FULL = {"plain", "sad", "excited"}


def same_word_clips(root):
    clips = json.loads((root / "clips.json").read_text())
    data = np.load(root / "states.npz")
    tone = np.array([c["delivery"] for c in clips])
    keep = np.array([c["same_words"] for c in clips]) & np.isin(tone, TONES)
    picked = [c for c, k in zip(clips, keep) if k]
    return picked, data["during"][keep].astype(np.float64), data["after"][keep].astype(np.float64)


def directions(during, tones):
    centre, spread = during.mean(axis=0), during.std(axis=0) + 1e-6
    scaled = (during - centre) / spread
    means = {t: scaled[tones == t].mean(axis=0) for t in TONES}
    result = {}
    for name, a, b in [("sad_vs_excited", "sad", "excited"), ("sad_vs_plain", "sad", "plain"),
                       ("excited_vs_plain", "excited", "plain")]:
        vector = means[a] - means[b]
        result[name] = {"unit": vector / np.linalg.norm(vector, axis=1, keepdims=True), "origin": (means[a] + means[b]) / 2,
                        "centre": centre, "spread": spread}
    return result


def project(states, d):
    return np.einsum("fld,ld->lf", (states - d["centre"][None]) / d["spread"][None] - d["origin"][None], d["unit"])


def unit_effects(during, tones):
    sad, excited = during[tones == "sad"], during[tones == "excited"]
    pooled = np.sqrt((sad.var(axis=0, ddof=1) + excited.var(axis=0, ddof=1)) / 2) + 1e-6
    return (sad.mean(axis=0) - excited.mean(axis=0)) / pooled


def word_free_map(states, sentences):
    coords = []
    for layer in range(states.shape[1]):
        x = states[:, layer].copy()
        for s in np.unique(sentences):
            x[sentences == s] -= x[sentences == s].mean(axis=0)
        x /= x.std(axis=0) + 1e-6
        _, _, vt = np.linalg.svd(x - x.mean(axis=0), full_matrices=False)
        xy = x @ vt[:2].T
        xy /= np.abs(xy).max()
        coords.append(np.round(xy, 3).tolist())
    return coords


def encode_audio(audio):
    import wave

    pcm = audio[: len(audio) // 2 * 2].reshape(-1, 2).mean(axis=1)
    pcm = (pcm / max(1e-6, np.abs(pcm).max()) * 0.9 * 32767).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(AUDIO_RATE)
        out.writeframes(pcm.tobytes())
    return "data:audio/wav;base64," + base64.b64encode(buffer.getvalue()).decode()


def envelope(audio, frames, lead):
    from moshi_dialogue import FRAME

    padded = np.concatenate([np.zeros(lead * FRAME), audio, np.zeros(max(0, frames * FRAME - lead * FRAME - len(audio)))])
    return np.round(np.sqrt((padded[: frames * FRAME].reshape(frames, FRAME) ** 2).mean(axis=1)), 4).tolist()


def trace(listener, path, dirs, top_units=None):
    from moshi_dialogue import load_turn
    from moshi_tone_probe import LEAD_S
    from moshi_dialogue import FRAME_S

    audio = load_turn(path)
    result = listener.listen(audio)
    states = result["states"].astype(np.float64)
    projections = {name: project(states, d) for name, d in dirs.items()}
    start, stop = result["speech"]
    summary = {name: np.round(p[:, start:stop].mean(axis=1), 2).tolist() for name, p in projections.items()}
    projections = {name: np.round(p, 1).tolist() for name, p in projections.items()}
    units = {} if top_units is None else {str(layer): {str(u): np.round(states[:, layer, u], 2).tolist() for u in top_units[layer]}
                                          for layer in range(states.shape[1])}
    lead = int(round(LEAD_S / FRAME_S))
    return {"projection": projections, "summary": summary, "units": units, "speech": list(result["speech"]),
            "speak_prob": np.round(result["speak_prob"], 4).tolist(), "envelope": envelope(audio, len(states), lead),
            "audio": encode_audio(audio), "frame_s": FRAME_S, "lead_s": LEAD_S}


def live_versus_memory(during, after, tones):
    def axis(states, layer):
        scaled = (states[:, layer] - states[:, layer].mean(axis=0)) / (states[:, layer].std(axis=0) + 1e-6)
        vector = scaled[tones == "sad"].mean(axis=0) - scaled[tones == "excited"].mean(axis=0)
        return vector / np.linalg.norm(vector)
    return [round(float(axis(during, layer) @ axis(after, layer)), 3) for layer in range(during.shape[1])]


def emotion_summary(path):
    data = json.loads(path.read_text())
    clips = json.loads((path.parent / "clips.json").read_text())
    examples = {}
    for emotion in ("sad", "happy"):
        rises = [p for p in data["poles"] if p["emotion"] == emotion and p["sign"] > 0]
        if rises:
            best = max(rises, key=lambda p: p["strength"])
            examples[emotion] = {k: best[k] for k in ("layer", "neuron", "sign", "strength", "profile", "per_voice", "description")}
    keep = ("emotions", "voices", "best_layer", "probe", "confusion", "centroid_xy", "clip_xy", "counts", "null_counts",
            "strong", "chance")
    return {**{k: data[k] for k in keep}, "clip_emotions": [c["emotion"] for c in clips], "examples": examples,
            "pole_count": len(data["poles"]), "acoustics": emotion_acoustics(ROOT / "out/emotions/manifest.json", data)}


def emotion_acoustics(manifest_path, data):
    manifest = json.loads(manifest_path.read_text())
    axis = np.array([xy[1] for xy in data["centroid_xy"]])
    rows = {}
    for emotion in data["emotions"]:
        clips = [m for m in manifest if m["emotion"] == emotion]
        rows[emotion] = {"pitch_hz": float(np.mean([m["median_f0_hz"] or 0 for m in clips])),
                         "pitch_movement": float(np.mean([m["pitch_sd_semitones"] or 0 for m in clips])),
                         "words_per_s": float(np.mean([m["words_per_s"] for m in clips])),
                         "level_db": float(np.mean([m["level_dbfs"] for m in clips]))}
    correlations = {key: float(np.corrcoef(axis, [rows[e][key] for e in data["emotions"]])[0, 1])
                    for key in ("pitch_hz", "pitch_movement", "words_per_s", "level_db")}
    return {"by_emotion": rows, "correlation_with_axis": correlations}


def embedded_fonts(folder):
    faces = [("Merriweather", "merriweather-latin", "normal"), ("Merriweather", "merriweather-italic-latin", "italic"),
             ("Geist Pixel", "geist-pixel-square", "normal")]
    css = []
    for family, stem, style in faces:
        path = next(folder.glob(f"{stem}.*.woff2"))
        data = base64.b64encode(path.read_bytes()).decode()
        weight = "font-weight:300 600;" if family == "Merriweather" else ""
        css.append(f'@font-face{{font-family:"{family}";src:url(data:font/woff2;base64,{data}) format("woff2");{weight}font-style:{style};font-display:swap}}')
    return "".join(css)


def text_head_readout(model, after, tones, sentences):
    import mlx.core as mx
    from moshi_tone_analyse import held_out_accuracy

    logits = np.array(model.text_linear(model.out_norm(mx.array(after[:, -1].astype(np.float32))[:, None, :]))[:, 0].astype(mx.float32))
    logits = logits.astype(np.float64)
    shifted = logits - logits.max(axis=1, keepdims=True)
    log_probs = shifted - np.log(np.exp(shifted).sum(axis=1, keepdims=True))
    return float(held_out_accuracy(log_probs, tones, sentences, TONES))


def build(args):
    from moshi_tone_probe import Listener

    root = args.root
    clips, during, after = same_word_clips(root)
    tones = np.array([c["delivery"] for c in clips])
    sentences = np.array([f"{c['scene']}/{c['turn']}/{c['sentence']}" for c in clips])
    results = json.loads((root / "results.json").read_text())
    dirs = directions(during, tones)
    effects = unit_effects(during, tones)
    top_units = [np.argsort(-np.abs(effects[layer]))[:TOP_UNITS].tolist() for layer in range(effects.shape[0])]

    listener = Listener(args.repo)
    text_head = text_head_readout(listener.moshi.model, after, tones, sentences)
    cache = root / "traces.json"
    if cache.exists() and not args.retrace:
        traces = json.loads(cache.read_text())
    else:
        manifest = {(e["scene"], e["delivery"]): e for e in json.loads((ROOT / "out/duplex-scenes/manifest.json").read_text())}
        traces = {"qwen": [], "grok": []}
        for scene, turn in QWEN_TRACES:
            for tone in TONES:
                entry = manifest[(scene, tone)]
                traces["qwen"].append({"scene": scene, "tone": tone, "text": entry["turns"][turn]["text"],
                                       **trace(listener, entry["turns"][turn]["file"], dirs, top_units)})
                print(f"traced {scene} {tone}", flush=True)
        grok_root = ROOT / "out/contextual-extreme/source"
        grok_manifest = {m["id"]: m for m in json.loads((grok_root / "manifest.json").read_text())}
        for script in GROK_SCRIPTS:
            for grok_tone, tone in GROK_TONES.items():
                item = grok_manifest[f"{script}_{grok_tone}"]
                traced = trace(listener, grok_root / f"{script}_{grok_tone}.wav", dirs)
                record = {"scene": script, "tone": tone, "text": item["scene"]["script"], **traced}
                if tone in GROK_FULL:
                    traces["grok"].append(record)
                traces.setdefault("grok_summary", []).append({k: record[k] for k in ("scene", "tone", "summary")})
                print(f"traced grok {script} {grok_tone}", flush=True)
        cache.write_text(json.dumps(traces))

    payload = {
        "layers": results["layers"],
        "decode_during": results["decode"]["during"], "decode_after": results["decode"]["after"],
        "floor": results["shuffled_95th"]["during"], "transfer": results["transfer_auc"],
        "effects": [np.clip(np.round(effects[layer] * 20), -127, 127).astype(int).tolist() for layer in range(effects.shape[0])],
        "top_units": top_units,
        "map_during": word_free_map(during, sentences), "map_after": word_free_map(after, sentences),
        "map_points": [{"tone": c["delivery"], "text": c["text"], "scene": c["scene"], "take": c["take"]} for c in clips],
        "traces": traces,
        "text_head_decode": text_head,
        "duration_only": results["duration_only_accuracy"],
        "separation": results["separation_ratio"]["during"],
        "consistency": results["sad_minus_excited_cosine_across_scenes"],
        "strong_agree": results["neurons_strong_agree"], "strong_disagree": results["neurons_strong_disagree"],
        "behaviour": results["behaviour"], "clip_count": results["clips"],
        "live_vs_memory": live_versus_memory(during, after, tones),
        "emo": emotion_summary(ROOT / "out/emotions/moshi/atlas_data.json"),
    }
    data = json.dumps(payload, separators=(",", ":"))
    for template, name in [("moshi_tone_viz.html", "explainer.html"), ("moshi_tone_post.html", "post.html")]:
        page = (ROOT / "scripts" / template).read_text().replace("__DATA__", data)
        if "__FONTS__" in page:
            page = page.replace("__FONTS__", embedded_fonts(root / "fonts"))
        (root / name).write_text(page)
        print(root / name, f"{len(page) / 1e6:.1f} MB")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT / "out/tone-probe")
    parser.add_argument("--repo", default="kyutai/moshiko-mlx-q8")
    parser.add_argument("--retrace", action="store_true")
    build(parser.parse_args())


if __name__ == "__main__":
    main()
