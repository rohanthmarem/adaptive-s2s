import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess


def build(root):
    experiment = root/'experiment'
    sources = json.loads((root/'source/manifest.json').read_text())
    prepared = {e['id']: e for e in json.loads((experiment/'manifest.json').read_text())}
    transcripts = json.loads((experiment/'audio-transcripts.json').read_text())
    cache = root/'review-audio'
    cache.mkdir(exist_ok=True)
    media = {}

    def encode(path):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest not in media:
            target = cache/f'{digest}.mp3'
            if not target.exists():
                subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-codec:a', 'libmp3lame',
                                '-b:a', '64k', str(target)], check=True)
            media[digest] = 'data:audio/mpeg;base64,' + base64.b64encode(target.read_bytes()).decode()
        return digest

    for entry in sources:
        entry['raw'] = encode(Path(entry['file']))
        entry['padded'] = encode(Path(prepared[entry['id']]['prepared_file']))
    runs = []
    for path in sorted(experiment.glob('*seed*.json')):
        trace = json.loads(path.read_text())
        name = path.stem
        if 'words' not in trace:
            continue
        family = int(name.split('_')[0])
        seed = int(name.rsplit('seed', 1)[1])
        condition = name.split('_', 1)[1].rsplit('_seed', 1)[0]
        input_style = 'neutral' if condition.startswith('patch_') else condition
        end = prepared[f'{family}_{input_style}']['speech_end_frame']*.08
        offset = (trace['frames']-len(trace['audio_tokens']))*.08
        runs.append(dict(id=name, family=family, seed=seed, condition=condition,
            input_style=input_style, audio=encode(path.with_suffix('.wav')),
            response_start=max(0,end-offset), stream=''.join(w for _,w in trace['words']).strip(),
            transcript=''.join(s['text'] for s in transcripts[name]).strip()))
    assert len(sources)==6 and len(runs)==24
    payload = json.dumps(dict(sources=sources, runs=runs, media=media)).replace('<','\\u003c')
    page = TEMPLATE.replace('DATA_PLACEHOLDER', payload)
    target = root/'review.html'
    target.write_text(page)
    print(f'{target.resolve()} — {len(runs)} runs, {len(sources)} sources, {len(media)} unique audio previews')
    return target


TEMPLATE = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Moshi listening review</title><style>
:root{color-scheme:dark}body{font-family:var(--font-sans,system-ui);color:var(--foreground);margin:0}h2{font-size:19px}h3{font-size:16px;margin:0 0 8px}p{line-height:1.5}small,.muted{color:var(--muted-foreground)}.toolbar{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin:16px 0}.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius,10px);padding:16px;margin:12px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}.grid .card{margin:0}audio{width:100%;margin:8px 0}button,select,textarea{background:var(--secondary);color:var(--foreground);border:1px solid var(--border);border-radius:6px;padding:8px;font:inherit}button{cursor:pointer}textarea{box-sizing:border-box;width:100%;margin-top:8px}summary{cursor:pointer}a{color:var(--primary)}.badge{font-size:12px;color:var(--muted-foreground)}.transcript{white-space:pre-wrap}label{display:inline-flex;align-items:center;gap:6px}
</style></head><body><p>Six synthetic inputs · 24 local Moshi generations. Review the audible response, its relevance, delivery and timing. “Slow + paused” is a delivery proxy, not a verified emotion.</p><div class="toolbar"><label>Script <select id="family"><option value="0">1 — Explain it to me</option><option value="1">2 — Go over that again</option></select></label><label>Seed <select id="seed"><option>0</option><option>1</option></select></label><button id="stop">Stop audio</button><button id="export">Export ratings</button></div><div id="sources"></div><h2>Responses <small id="count"></small></h2><p class="muted">Patches use the neutral input and replace layer 8 for one frame at 9.92 seconds. “Play response” skips the initial greeting and starts near the user’s speech end. All recordings include the complete saved output; a final sentence may be cut off by the recording window.</p><div id="runs" class="grid"></div><p class="muted">Audio previews are 64 kbps MP3 conversions of the saved WAVs. Audio transcripts use local Whisper small.en and may contain recognition errors. The separate Moshi text stream is what the model generated internally, not a transcription. Ratings remain in this page until you export them.</p>
<script type="application/json" id="data">DATA_PLACEHOLDER</script><script>
const data=JSON.parse(document.getElementById('data').textContent);const ratings={};
const names={neutral:'Neutral input',neutral_repeat:'Repeated neutral input',hesitant:'Slow + paused input',patch_neutral:'Self-patch control',patch_neutral_repeat:'Repeated-neutral patch',patch_hesitant:'Slow + paused patch'};
const escapeText=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function stop(){document.querySelectorAll('audio').forEach(a=>a.pause())}
function audio(key,id){return `<audio controls preload="metadata" id="${id}" src="${data.media[key]}"></audio>`}
function render(){stop();const family=Number(document.getElementById('family').value);const seed=Number(document.getElementById('seed').value);const sources=data.sources.filter(s=>s.family===family);document.getElementById('sources').innerHTML=`<h2>Input recordings</h2><p>${escapeText(sources[0].text)}</p><div class="grid">`+sources.map(s=>`<section class="card"><h3>${names[s.style]}</h3><small>xAI · Eve · exact words confirmed by ASR</small>${audio(s.raw,'source-'+s.id)}<details><summary>Input exactly as Moshi heard it</summary><small>Volume normalized, silence padded, speech-end aligned.</small>${audio(s.padded,'padded-'+s.id)}</details></section>`).join('')+'</div>';const order=['neutral','neutral_repeat','hesitant','patch_neutral','patch_neutral_repeat','patch_hesitant'];const runs=data.runs.filter(r=>r.family===family&&r.seed===seed).sort((a,b)=>order.indexOf(a.condition)-order.indexOf(b.condition));document.getElementById('count').textContent='6 of 24 · all conditions';document.getElementById('runs').innerHTML=runs.map(r=>`<section class="card"><h3>${names[r.condition]}</h3><div class="badge">${r.id} · user input: ${names[r.input_style]}</div>${audio(r.audio,r.id)}<button class="response" data-id="${r.id}" data-time="${r.response_start}">Play response</button><p class="transcript"><strong>Audio transcript</strong><br>${escapeText(r.transcript||'[No transcribed speech]')}</p><details><summary>Moshi text stream</summary><p>${escapeText(r.stream)}</p></details><div class="toolbar"><label>Rating <select class="rating" data-id="${r.id}"><option value="">Not rated</option><option>Appropriate</option><option>Mixed</option><option>Inappropriate</option><option>Unintelligible</option></select></label></div><textarea class="notes" data-id="${r.id}" aria-label="Notes for ${r.id}" placeholder="Relevance, tone, timing, interruptions…">${escapeText(ratings[r.id]?.notes||'')}</textarea></section>`).join('');document.querySelectorAll('.rating').forEach(s=>s.value=ratings[s.dataset.id]?.rating||'');document.querySelectorAll('audio').forEach(a=>a.addEventListener('play',()=>document.querySelectorAll('audio').forEach(b=>{if(a!==b)b.pause()})))}
document.getElementById('family').onchange=render;document.getElementById('seed').onchange=render;document.getElementById('stop').onclick=stop;document.addEventListener('click',async e=>{if(e.target.matches('.response')){const a=document.getElementById(e.target.dataset.id);a.currentTime=Number(e.target.dataset.time);try{await a.play()}catch(error){alert('Playback could not start: '+error.message)}}});document.addEventListener('change',e=>{if(e.target.matches('.rating')){const id=e.target.dataset.id;ratings[id]={...ratings[id],rating:e.target.value}}});document.addEventListener('input',e=>{if(e.target.matches('.notes')){const id=e.target.dataset.id;ratings[id]={...ratings[id],notes:e.target.value}}});document.getElementById('export').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify({experiment:'matched-xai',ratings},null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='moshi-ratings.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};render();
</script></body></html>'''

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path('out/matched-xai'))
    build(parser.parse_args().root)
