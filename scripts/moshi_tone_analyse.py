import argparse
import html
import json
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TONES = ["excited", "sad", "plain"]
TRANSFER = [("sad", "dog"), ("excited", "offer")]
PERMUTATIONS = 30


def layer_names(count):
    return ["embed", *(str(i) for i in range(count - 1))]


def centroid_predict(train_x, train_y, test_x, classes):
    mean, scale = train_x.mean(axis=0), train_x.std(axis=0) + 1e-6
    train_z, test_z = (train_x - mean) / scale, (test_x - mean) / scale
    centroids = np.stack([train_z[train_y == c].mean(axis=0) for c in classes])
    centroids /= np.linalg.norm(centroids, axis=1, keepdims=True)
    test_z = test_z / np.linalg.norm(test_z, axis=1, keepdims=True)
    return np.array(classes)[np.argmax(test_z @ centroids.T, axis=1)]


def held_out_accuracy(features, labels, groups, classes):
    correct = 0
    for group in np.unique(groups):
        test = groups == group
        correct += (centroid_predict(features[~test], labels[~test], features[test], classes) == labels[test]).sum()
    return correct / len(labels)


def shuffle_within(labels, groups, rng):
    shuffled = labels.copy()
    for group in np.unique(groups):
        members = np.flatnonzero(groups == group)
        shuffled[members] = labels[rng.permutation(members)]
    return shuffled


def auc(positive, negative):
    wins = (positive[:, None] > negative[None, :]).sum() + 0.5 * (positive[:, None] == negative[None, :]).sum()
    return wins / (len(positive) * len(negative))


def separation(features, labels, groups):
    centred = features - features.mean(axis=0)
    unit = centred / np.linalg.norm(centred, axis=1, keepdims=True)
    between, within = [], []
    for group in np.unique(groups):
        members = np.flatnonzero(groups == group)
        distance = 1 - unit[members] @ unit[members].T
        same = labels[members][:, None] == labels[members][None, :]
        off_diagonal = ~np.eye(len(members), dtype=bool)
        between.append(distance[~same].mean())
        within.append(distance[same & off_diagonal].mean())
    return float(np.mean(between) / np.mean(within))


def cohens_d(a, b):
    pooled = np.sqrt((a.var(axis=0, ddof=1) + b.var(axis=0, ddof=1)) / 2) + 1e-6
    return (a.mean(axis=0) - b.mean(axis=0)) / pooled


def speech_seconds(path):
    with wave.open(path) as audio:
        return audio.getnframes() / audio.getframerate()


def analyse(args):
    clips = json.loads((args.root / "clips.json").read_text())
    data = np.load(args.root / "states.npz")
    windows = {"during": data["during"].astype(np.float64), "after": data["after"].astype(np.float64)}
    names = layer_names(windows["during"].shape[1])
    scene = np.array([c["scene"] for c in clips])
    tone = np.array([c["delivery"] for c in clips])
    sentence = np.array([f"{c['scene']}/{c['turn']}/{c['sentence']}" for c in clips])
    same = np.array([c["same_words"] for c in clips]) & np.isin(tone, TONES)
    rng = np.random.default_rng(0)

    seconds = np.array([speech_seconds(c["file"]) for c in clips])
    duration_only = held_out_accuracy(seconds[same, None], tone[same], sentence[same], TONES)

    decode, floor, ratio = {}, {}, {}
    for window, states in windows.items():
        x = states[same]
        decode[window] = [held_out_accuracy(x[:, i], tone[same], sentence[same], TONES) for i in range(len(names))]
        shuffled = [shuffle_within(tone[same], sentence[same], rng) for _ in range(PERMUTATIONS)]
        floor[window] = [float(np.percentile([held_out_accuracy(x[:, i], s, sentence[same], TONES) for s in shuffled], 95))
                         for i in range(len(names))]
        ratio[window] = [separation(x[:, i], tone[same], sentence[same]) for i in range(len(names))]

    transfer = {}
    for emotion, target in TRANSFER:
        source = same & np.isin(tone, [emotion, "plain"])
        test_emotion = (scene == target) & (tone == emotion)
        test_plain = (scene == target) & (tone == "plain")
        scores = []
        for i in range(len(names)):
            x = windows["during"][:, i]
            direction = x[source & (tone == emotion)].mean(axis=0) - x[source & (tone == "plain")].mean(axis=0)
            scores.append(float(auc(x[test_emotion] @ direction, x[test_plain] @ direction)))
        transfer[f"{emotion}: job/grade calls -> {target} scene"] = scores

    consistency = []
    for i in range(len(names)):
        x = windows["during"][:, i]
        directions = []
        for scene_id in ("callback", "grades"):
            pick = same & (scene == scene_id)
            directions.append(x[pick & (tone == "sad")].mean(axis=0) - x[pick & (tone == "excited")].mean(axis=0))
        consistency.append(float(directions[0] @ directions[1] / np.linalg.norm(directions[0]) / np.linalg.norm(directions[1])))

    best = int(np.argmax(decode["during"]))
    x = windows["during"][:, best]
    effects = {s: cohens_d(x[same & (scene == s) & (tone == "sad")], x[same & (scene == s) & (tone == "excited")])
               for s in ("callback", "grades")}
    agree = np.sign(effects["callback"]) == np.sign(effects["grades"])
    strength = np.where(agree, np.minimum(np.abs(effects["callback"]), np.abs(effects["grades"])), 0)
    neurons = [{"unit": int(u), "d_callback": float(effects["callback"][u]), "d_grades": float(effects["grades"][u])}
               for u in np.argsort(strength)[::-1][:10]]
    strong_agree = int(((np.abs(effects["callback"]) > 1) & (np.abs(effects["grades"]) > 1) & agree).sum())
    strong_disagree = int(((np.abs(effects["callback"]) > 1) & (np.abs(effects["grades"]) > 1) & ~agree).sum())

    behaviour = []
    for t in TONES:
        pick = same & (tone == t)
        words = {}
        for c in np.array(clips)[pick]:
            words[c["likely_first_word"]] = words.get(c["likely_first_word"], 0) + 1
        behaviour.append({"tone": t, "clips": int(pick.sum()), "speak_prob_after": float(data["speak_after"][pick].mean()),
                          "seconds": float(seconds[pick].mean()),
                          "first_words": sorted(words.items(), key=lambda kv: -kv[1])[:5]})

    result = {"layers": names, "clips": len(clips), "same_word_clips": int(same.sum()),
              "sentences": int(len(np.unique(sentence[same]))), "duration_only_accuracy": float(duration_only),
              "decode": decode, "shuffled_95th": floor, "separation_ratio": ratio, "transfer_auc": transfer,
              "sad_minus_excited_cosine_across_scenes": consistency, "best_layer": names[best],
              "neurons": neurons, "neurons_strong_agree": strong_agree, "neurons_strong_disagree": strong_disagree,
              "behaviour": behaviour}
    (args.root / "results.json").write_text(json.dumps(result, indent=2))
    (args.root / "report.html").write_text(report(result))
    print(json.dumps({k: result[k] for k in ("clips", "same_word_clips", "duration_only_accuracy", "best_layer",
                                              "neurons_strong_agree", "neurons_strong_disagree")}))
    for i, name in enumerate(names):
        print(f"layer {name:>5}: decode during {decode['during'][i]:.2f} (floor {floor['during'][i]:.2f}) "
              f"after {decode['after'][i]:.2f} (floor {floor['after'][i]:.2f}) sep {ratio['during'][i]:.2f} "
              f"cos {consistency[i]:+.2f} " + " ".join(f"{v[i]:.2f}" for v in transfer.values()))
    for row in behaviour:
        print(row)


def line_chart(title, subtitle, layers, series, y_min, y_max, reference=None, y_format="{:.0%}"):
    width, height, left, right, top, bottom = 760, 280, 52, 16, 16, 34
    plot_w, plot_h = width - left - right, height - top - bottom

    def px(i):
        return left + plot_w * i / (len(layers) - 1)

    def py(v):
        return top + plot_h * (1 - (v - y_min) / (y_max - y_min))

    ticks = np.linspace(y_min, y_max, 5)
    grid = "".join(f'<line x1="{left}" x2="{width - right}" y1="{py(t):.1f}" y2="{py(t):.1f}" class="grid"/>'
                   f'<text x="{left - 8}" y="{py(t) + 4:.1f}" class="axis" text-anchor="end">{y_format.format(t)}</text>' for t in ticks)
    xticks = "".join(f'<text x="{px(i):.1f}" y="{height - 12}" class="axis" text-anchor="middle">{html.escape(layers[i])}</text>'
                     for i in range(len(layers)) if i == 0 or i % 4 == 0 or i == len(layers) - 1)
    ref = ""
    if reference is not None:
        label, value = reference
        ref = (f'<line x1="{left}" x2="{width - right}" y1="{py(value):.1f}" y2="{py(value):.1f}" class="ref"/>'
               f'<text x="{width - right}" y="{py(value) - 6:.1f}" class="axis" text-anchor="end">{html.escape(label)}</text>')
    paths, legend, payload = "", "", []
    for index, (name, values, style) in enumerate(series):
        points = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(values))
        cls = "floor" if style == "floor" else f"s{index + 1}"
        paths += f'<polyline points="{points}" class="line {cls}"/>'
        if style != "floor":
            last = len(values) - 1
            paths += f'<circle cx="{px(last):.1f}" cy="{py(values[last]):.1f}" r="4" class="dot {cls}"/>'
        legend += f'<span class="key"><i class="swatch {cls}"></i>{html.escape(name)}</span>'
        payload.append({"name": name, "values": values})
    data = html.escape(json.dumps({"layers": layers, "series": payload, "fmt": "pct" if "%" in y_format else "num",
                                   "geom": [left, top, plot_w, plot_h]}))
    return (f'<figure class="chart" data-chart="{data}"><figcaption><b>{html.escape(title)}</b><span>{html.escape(subtitle)}</span></figcaption>'
            f'<div class="legend">{legend}</div><div class="plot"><svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">'
            f'{grid}{ref}{paths}{xticks}<line class="cross" y1="{top}" y2="{top + plot_h}" x1="-10" x2="-10"/>'
            f'<rect class="hit" x="{left}" y="{top}" width="{plot_w}" height="{plot_h}"/></svg><div class="tip" hidden></div></div></figure>')


def report(r):
    layers = r["layers"]
    chance = 1 / 3
    decode_chart = line_chart(
        "Can a simple probe read the tone out of each layer?",
        f"Same words, three tones ({r['same_word_clips']} clips). Each sentence is held out in turn, so the probe never sees the test sentence.",
        layers, [("While the user speaks", r["decode"]["during"], "line"),
                 ("In the 1.2 s after they stop", r["decode"]["after"], "line"),
                 ("Shuffled labels, 95th percentile", r["shuffled_95th"]["during"], "floor")],
        0, 1, reference=("chance 33%", chance))
    transfer_chart = line_chart(
        "Does the 'sad' and 'excited' axis carry over to a different story?",
        "Direction learned from the job and grade calls, tested on the dog scene (sad vs plain) and the job-offer scene (excited vs plain). 50% = no transfer.",
        layers, [(name, values, "line") for name, values in r["transfer_auc"].items()], 0, 1, reference=("no transfer", 0.5))
    separation_chart = line_chart(
        "How far does the tone move the representation, compared with take-to-take noise?",
        "Distance between tones divided by distance between takes of the same tone, same sentence. Above 1 = tone moves it more than noise.",
        layers, [("Between-tone / within-tone distance", r["separation_ratio"]["during"], "line")],
        min(0.9, min(r["separation_ratio"]["during"])), max(r["separation_ratio"]["during"]) * 1.05,
        reference=("noise level", 1.0), y_format="{:.2f}")
    neuron_rows = "".join(f'<tr><td>{n["unit"]}</td><td>{n["d_callback"]:+.2f}</td><td>{n["d_grades"]:+.2f}</td></tr>' for n in r["neurons"])
    behaviour_rows = "".join(
        f'<tr><td>{b["tone"]}</td><td>{b["clips"]}</td><td>{b["seconds"]:.2f} s</td><td>{b["speak_prob_after"]:.3f}</td>'
        f'<td>{html.escape(", ".join(f"{w} ({n})" for w, n in b["first_words"]))}</td></tr>' for b in r["behaviour"])
    cos = r["sad_minus_excited_cosine_across_scenes"]
    body = f"""
<header><h1>Does Moshi hear tone?</h1>
<p class="lede">Each rendered sentence was played into Moshi on its own while Moshi was held silent, so the only thing that changed between runs was the user's voice. The output of every layer of the 32-layer temporal transformer was recorded and averaged over the speech, and again over the 1.2 s after it.</p>
<div class="tiles"><div class="tile"><span>Probe from duration alone</span><b>{r['duration_only_accuracy']:.0%}</b></div>
<div class="tile"><span>Best layer for tone</span><b>{html.escape(r['best_layer'])}</b></div>
<div class="tile"><span>Best accuracy</span><b>{max(r['decode']['during']):.0%}</b></div>
<div class="tile"><span>Sad-vs-excited axis, job vs grade calls</span><b>cos {max(cos):.2f}</b></div></div></header>
{decode_chart}{transfer_chart}{separation_chart}
<section class="card"><h2>Units that move most with sad vs excited, at layer {html.escape(r['best_layer'])}</h2>
<p class="dim">Cohen's d (sad minus excited), computed separately in the two scenes. Units with |d| above 1 in both scenes: {r['neurons_strong_agree']} agree in sign, {r['neurons_strong_disagree']} disagree.</p>
<table><thead><tr><th>Unit</th><th>d, job call</th><th>d, grade</th></tr></thead><tbody>{neuron_rows}</tbody></table></section>
<section class="card"><h2>What Moshi would say next</h2>
<p class="dim">Moshi was held silent, but its text head still gives a probability that it would start talking, and its top word at the most likely moment.</p>
<table><thead><tr><th>Tone</th><th>Clips</th><th>Mean length</th><th>P(start talking) after</th><th>Top first words</th></tr></thead><tbody>{behaviour_rows}</tbody></table></section>"""
    return TEMPLATE.replace("__BODY__", body)


TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Moshi Tone Probe</title><style>
:root{--surface:#fcfcfb;--card:#ffffff;--ink:#0b0b0b;--ink2:#52514e;--line:#e4e3df;--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--floor:#a3a29b}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--surface:#141413;--card:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--line:#2e2d2a;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--floor:#6b6a64}}
:root[data-theme="dark"]{--surface:#141413;--card:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--line:#2e2d2a;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--floor:#6b6a64}
*{box-sizing:border-box}body{margin:0;background:var(--surface);color:var(--ink);font:15px/1.5 system-ui,sans-serif;padding:24px 16px}
main{max-width:860px;margin:0 auto;display:flex;flex-direction:column;gap:20px}h1{margin:0 0 6px;font-size:26px}h2{margin:0 0 6px;font-size:17px}
.lede,.dim{color:var(--ink2)}.dim{font-size:13px}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-top:12px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}.tile span{display:block;font-size:12px;color:var(--ink2)}.tile b{font-size:24px}
.chart,.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:0}
figcaption b{display:block;font-size:16px}figcaption span{display:block;color:var(--ink2);font-size:13px}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin:10px 0 4px;font-size:13px;color:var(--ink2)}.key{display:inline-flex;align-items:center;gap:6px}
.swatch{width:14px;height:3px;border-radius:2px;display:inline-block}.swatch.s1{background:var(--s1)}.swatch.s2{background:var(--s2)}.swatch.s3{background:var(--s3)}
.swatch.floor{background:none;border-top:2px dashed var(--floor)}
.plot{position:relative}svg{width:100%;height:auto;display:block}.grid{stroke:var(--line);stroke-width:1}.axis{fill:var(--ink2);font-size:11px}
.ref{stroke:var(--ink2);stroke-width:1;stroke-dasharray:2 4}.line{fill:none;stroke-width:2;stroke-linejoin:round}
.line.s1{stroke:var(--s1)}.line.s2{stroke:var(--s2)}.line.s3{stroke:var(--s3)}.line.floor{stroke:var(--floor);stroke-dasharray:5 4}
.dot{stroke:var(--card);stroke-width:2}.dot.s1{fill:var(--s1)}.dot.s2{fill:var(--s2)}.dot.s3{fill:var(--s3)}
.cross{stroke:var(--ink2);stroke-width:1}.hit{fill:transparent;cursor:crosshair}
.tip{position:absolute;pointer-events:none;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px 9px;font-size:12px;box-shadow:0 2px 8px rgba(0,0,0,.12);white-space:nowrap}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}th{color:var(--ink2);font-weight:600}
td:not(:first-child),th:not(:first-child){font-variant-numeric:tabular-nums}
</style></head><body><main>__BODY__</main><script>
document.querySelectorAll('figure[data-chart]').forEach(fig=>{
const d=JSON.parse(fig.dataset.chart),svg=fig.querySelector('svg'),tip=fig.querySelector('.tip'),cross=fig.querySelector('.cross');
const [l,t,w,h]=d.geom,n=d.layers.length,fmt=v=>d.fmt==='pct'?Math.round(v*100)+'%':v.toFixed(3);
fig.querySelector('.hit').addEventListener('pointermove',e=>{const r=svg.getBoundingClientRect(),sx=(e.clientX-r.left)*svg.viewBox.baseVal.width/r.width;
const i=Math.max(0,Math.min(n-1,Math.round((sx-l)/w*(n-1)))),x=l+w*i/(n-1);cross.setAttribute('x1',x);cross.setAttribute('x2',x);
tip.hidden=false;tip.innerHTML='<b>Layer '+d.layers[i]+'</b><br>'+d.series.map(s=>s.name+': '+fmt(s.values[i])).join('<br>');
const px=x*r.width/svg.viewBox.baseVal.width;tip.style.left=Math.min(px+12,r.width-tip.offsetWidth)+'px';tip.style.top='8px'});
fig.querySelector('.hit').addEventListener('pointerleave',()=>{tip.hidden=true;cross.setAttribute('x1',-10);cross.setAttribute('x2',-10)});});
</script></body></html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT / "out/tone-probe")
    analyse(parser.parse_args())


if __name__ == "__main__":
    main()
