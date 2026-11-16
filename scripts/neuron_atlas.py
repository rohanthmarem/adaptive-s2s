import argparse
import base64
import io
import json
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from moshi_tone_analyse import centroid_predict

STRONG = 1.0
MIN_STRENGTH = 0.5
PER_EMOTION_RISE = 15
PER_EMOTION_FALL = 8
TOP_CLIPS = 8
SHUFFLES = 3
AUDIO_RATE = 12000


def held_out(features, labels, groups, classes):
    predicted = np.empty(len(labels), dtype=object)
    for group in np.unique(groups):
        test = groups == group
        predicted[test] = centroid_predict(features[~test], labels[~test], features[test], classes)
    return predicted


def per_voice_effects(x, emotions, voices, emotion_names, voice_names):
    effects = np.zeros((len(voice_names), len(emotion_names), x.shape[1]), dtype=np.float32)
    for v, voice in enumerate(voice_names):
        in_voice = voices == voice
        for e, emotion in enumerate(emotion_names):
            hit, rest = x[in_voice & (emotions == emotion)], x[in_voice & (emotions != emotion)]
            pooled = np.sqrt((hit.var(axis=0, ddof=1) + rest.var(axis=0, ddof=1)) / 2) + 1e-4
            effects[v, e] = (hit.mean(axis=0) - rest.mean(axis=0)) / pooled
    return effects


def robust(effects):
    same_sign = (np.sign(effects) == np.sign(effects[:1])).all(axis=0)
    return np.where(same_sign, np.sign(effects[0]) * np.abs(effects).min(axis=0), 0.0)


def describe(profile, emotion_names, sign):
    ranked = [(emotion_names[i], profile[i]) for i in np.argsort(-sign * profile) if sign * profile[i] >= 0.5]
    verb = "Rises" if sign > 0 else "Falls"
    if not ranked:
        return f"{verb} weakly with tone"
    head = f"{verb} for {ranked[0][0]} voices"
    rest = [name for name, _ in ranked[1:4]]
    return head + (f", also {', '.join(rest)}" if rest else "")


def analyse(args):
    out = args.root / "moshi"
    clips = json.loads((out / "clips.json").read_text())
    neurons = np.load(out / "neurons_mean.npy", mmap_mode="r")
    residual = np.load(out / "residual.npz")
    emotions = np.array([c["emotion"] for c in clips])
    voices = np.array([c["voice"] for c in clips])
    sentences = np.array([c["sentence"] for c in clips])
    emotion_names = [str(e) for e in dict.fromkeys(emotions)]
    voice_names = [str(v) for v in dict.fromkeys(voices)]
    layers = neurons.shape[1]
    rng = np.random.default_rng(0)

    during = residual["during"].astype(np.float64)
    after = residual["after"].astype(np.float64)
    probe = {"by_voice": [], "by_sentence": [], "after_by_voice": [], "floor": []}
    shuffled = emotions.copy()
    for voice in voice_names:
        members = np.flatnonzero(voices == voice)
        shuffled[members] = emotions[rng.permutation(members)]
    for layer in range(during.shape[1]):
        probe["by_voice"].append(float((held_out(during[:, layer], emotions, voices, emotion_names) == emotions).mean()))
        probe["by_sentence"].append(float((held_out(during[:, layer], emotions, sentences, emotion_names) == emotions).mean()))
        probe["after_by_voice"].append(float((held_out(after[:, layer], emotions, voices, emotion_names) == emotions).mean()))
        probe["floor"].append(float((held_out(during[:, layer], shuffled, voices, emotion_names) == shuffled).mean()))
    best = int(np.argmax(probe["by_voice"]))
    predicted = held_out(during[:, best], emotions, voices, emotion_names)
    confusion = [[int(((emotions == a) & (predicted == b)).sum()) for b in emotion_names] for a in emotion_names]

    x = during[:, best]
    scaled = (x - x.mean(axis=0)) / (x.std(axis=0) + 1e-6)
    for sentence in np.unique(sentences):
        scaled[sentences == sentence] -= scaled[sentences == sentence].mean(axis=0)
    centroids = np.stack([scaled[emotions == e].mean(axis=0) for e in emotion_names])
    centred = centroids - centroids.mean(axis=0)
    _, _, vt = np.linalg.svd(centred, full_matrices=False)
    centroid_xy = centred @ vt[:2].T
    clip_xy = (scaled - centroids.mean(axis=0)) @ vt[:2].T
    scale = np.abs(clip_xy).max()
    unit_centroids = centred / np.linalg.norm(centred, axis=1, keepdims=True)
    similarity = (unit_centroids @ unit_centroids.T).round(2).tolist()

    counts, null_counts, poles = [], [], []
    for layer in range(layers):
        x = np.asarray(neurons[:, layer], dtype=np.float32)
        effects = per_voice_effects(x, emotions, voices, emotion_names, voice_names)
        strength = robust(effects)
        counts.append([int((np.abs(strength[e]) >= STRONG).sum()) for e in range(len(emotion_names))])
        layer_null = np.zeros(len(emotion_names))
        for _ in range(SHUFFLES):
            fake = emotions.copy()
            for voice in voice_names:
                members = np.flatnonzero(voices == voice)
                fake[members] = emotions[rng.permutation(members)]
            null_strength = robust(per_voice_effects(x, fake, voices, emotion_names, voice_names))
            layer_null += (np.abs(null_strength) >= STRONG).sum(axis=1)
        null_counts.append((layer_null / SHUFFLES).round(2).tolist())
        for e, emotion in enumerate(emotion_names):
            for sign, keep in ((1, PER_EMOTION_RISE), (-1, PER_EMOTION_FALL)):
                order = np.argsort(-sign * strength[e])[:keep]
                for unit in order:
                    if sign * strength[e, unit] < MIN_STRENGTH:
                        continue
                    poles.append({"layer": layer, "neuron": int(unit), "sign": sign, "emotion": emotion,
                                  "strength": float(sign * strength[e, unit]),
                                  "profile": strength[:, unit].round(2).tolist(),
                                  "per_voice": effects[:, :, unit].round(2).tolist(),
                                  "activation": x[:, unit].round(3).tolist()})
        print(f"layer {layer}: strong neurons per emotion {dict(zip(emotion_names, counts[-1]))} (shuffled {null_counts[-1]})", flush=True)

    chosen_poles = []
    for emotion in emotion_names:
        for sign, keep in ((1, PER_EMOTION_RISE), (-1, PER_EMOTION_FALL)):
            candidates = sorted((p for p in poles if p["emotion"] == emotion and p["sign"] == sign), key=lambda p: -p["strength"])
            chosen_poles.extend(candidates[:keep])
    for pole in chosen_poles:
        profile = np.array(pole["profile"])
        pole["description"] = describe(profile, emotion_names, pole["sign"])
        activation = np.array(pole["activation"])
        pole["top_clips"] = np.argsort(-pole["sign"] * activation)[:TOP_CLIPS].tolist()
    unique = sorted({(p["layer"], p["neuron"]) for p in chosen_poles})
    (out / "chosen_neurons.json").write_text(json.dumps([{"layer": l, "neuron": n} for l, n in unique]))

    summary = {"emotions": emotion_names, "voices": voice_names, "layers": layers, "best_layer": best,
               "probe": probe, "confusion": confusion, "similarity": similarity,
               "centroid_xy": (centroid_xy / scale).round(3).tolist(), "clip_xy": (clip_xy / scale).round(3).tolist(),
               "counts": counts, "null_counts": null_counts, "strong": STRONG, "poles": chosen_poles,
               "chance": 1 / len(emotion_names)}
    (out / "atlas_data.json").write_text(json.dumps(summary))
    print(f"best layer {best - 1 if best else 'input'}: held-out-voice accuracy {probe['by_voice'][best]:.2f}, "
          f"held-out-sentence {probe['by_sentence'][best]:.2f}, floor {probe['floor'][best]:.2f}; {len(chosen_poles)} poles, {len(unique)} neurons")


def encode_wav(path, out):
    from moshi_dialogue import SAMPLE_RATE, load_turn

    audio = load_turn(path)
    step = SAMPLE_RATE // AUDIO_RATE
    audio = audio[: len(audio) // step * step].reshape(-1, step).mean(axis=1)
    pcm = (audio / max(1e-6, np.abs(audio).max()) * 0.9 * 32767).astype(np.int16)
    with wave.open(str(out), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(AUDIO_RATE)
        handle.writeframes(pcm.tobytes())


def embedded_fonts():
    folder = ROOT / "out/tone-probe/fonts"
    css = []
    for family, stem, style in [("Merriweather", "merriweather-latin", "normal"), ("Geist Pixel", "geist-pixel-square", "normal")]:
        data = base64.b64encode(next(folder.glob(f"{stem}.*.woff2")).read_bytes()).decode()
        weight = "font-weight:300 600;" if family == "Merriweather" else ""
        css.append(f'@font-face{{font-family:"{family}";src:url(data:font/woff2;base64,{data}) format("woff2");{weight}font-style:{style};font-display:swap}}')
    return "".join(css)


def build(args):
    out = args.root / "moshi"
    data = json.loads((out / "atlas_data.json").read_text())
    clips = json.loads((out / "clips.json").read_text())
    chosen = json.loads((out / "chosen_neurons.json").read_text())
    index = {(c["layer"], c["neuron"]): i for i, c in enumerate(chosen)}
    trace_file = out / "neuron_traces.npz"
    traces = np.load(trace_file) if trace_file.exists() else None
    site = args.root / "atlas"
    (site / "audio").mkdir(parents=True, exist_ok=True)
    for i, clip in enumerate(clips):
        target = site / "audio" / f"{i}.wav"
        if not target.exists():
            encode_wav(clip["file"], target)
    for pole in data["poles"]:
        row = index[(pole["layer"], pole["neuron"])]
        pole["traces"] = []
        for clip in pole["top_clips"]:
            if traces is None:
                pole["traces"].append({"clip": clip, "speech": [], "values": []})
                continue
            values = traces[f"clip_{clip}"][row]
            speech = traces[f"speech_{clip}"].tolist()
            pole["traces"].append({"clip": clip, "speech": speech, "values": np.round(values, 2).tolist()})
    from moshi_tone_viz import emotion_acoustics

    data["acoustics"] = emotion_acoustics(args.root / "manifest.json", data)
    data["clips"] = [{k: c[k] for k in ("voice", "sex", "emotion", "sentence", "text")} for c in clips]
    data["frame_s"] = 0.08
    data["lead_s"] = 0.5
    page = (ROOT / "scripts/neuron_atlas.html").read_text()
    page = page.replace("__FONTS__", embedded_fonts()).replace("__DATA__", json.dumps(data, separators=(",", ":")))
    (site / "index.html").write_text(page)
    print(site / "index.html", f"{len(page) / 1e6:.1f} MB page, {len(clips)} audio files")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["analyse", "build"])
    parser.add_argument("--root", type=Path, default=ROOT / "out/emotions")
    args = parser.parse_args()
    analyse(args) if args.mode == "analyse" else build(args)


if __name__ == "__main__":
    main()
