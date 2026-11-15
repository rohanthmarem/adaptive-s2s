import argparse
import base64
import hashlib
import html
import json
from pathlib import Path
import subprocess

import numpy as np
import soundfile as sf

from moshi_review import TEMPLATE


def build(root):
    entries=json.loads((root/'experiment/manifest.json').read_text())
    validations=json.loads((root/'source/validation.json').read_text())
    transcripts=json.loads((root/'experiment/audio-transcripts.json').read_text())
    cache=root/'review-audio'
    cache.mkdir(exist_ok=True)
    media={}
    def encode(path):
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest not in media:
            target=cache/(digest+'.mp3')
            if not target.exists():
                subprocess.run(['ffmpeg','-v','error','-i',str(path),'-codec:a','libmp3lame','-b:a','64k',str(target)],check=True)
            media[digest]='data:audio/mpeg;base64,'+base64.b64encode(target.read_bytes()).decode()
        return digest
    sources=[]
    runs=[]
    for entry in entries:
        name=entry['id']
        trace=json.loads((root/'experiment'/(name+'.json')).read_text())
        family=0 if entry['scene']['id']=='interview' else 1
        user,rate=sf.read(entry['input'],dtype='float32')
        assistant,_=sf.read(entry['output'],dtype='float32')
        prefix=round(trace['prefix_silence_s']*rate)
        offset=(trace['frames']-len(trace['audio_tokens']))*1920
        timeline=np.zeros(trace['frames']*1920,dtype=np.float32)
        timeline[prefix:prefix+len(user)]=user
        padded=cache/(name+'_user.wav')
        sf.write(padded,timeline,rate)
        timeline[offset:offset+len(assistant)]+=assistant
        if np.max(np.abs(timeline))>0.98:
            timeline*=0.98/np.max(np.abs(timeline))
        conversation=cache/(name+'_conversation.wav')
        sf.write(conversation,timeline,rate)
        sources.append(dict(id=name,family=family,style=entry['requested_delivery'],text=entry['scene']['script'],
            raw=encode(Path(entry['file'])),padded=encode(padded),validation=validations[name],
            method=entry.get('acoustic_transform',{}).get('method','xAI TTS expressive tags'),
            input_transcript=validations[name]['transcript']))
        runs.append(dict(id=name,family=family,seed=101,condition=entry['requested_delivery'],
            input_style=entry['requested_delivery'],audio=encode(Path(entry['output'])),
            conversation=encode(conversation),response_start=max(0,trace['user_end_s']-offset/rate),
            transcript=transcripts[name]['transcript'],stream=''.join(w for _,w in trace['words']).strip()))
    control=root/'free-duplex-control'
    control_trace=json.loads((control/'interview_neutral.json').read_text())
    control_transcripts=json.loads((control/'audio-transcripts.json').read_text())
    control_audio=encode(control/'interview_neutral.wav')
    control_text=control_transcripts['interview_neutral']['transcript']
    assert len(sources)==12 and len(runs)==12
    page=TEMPLATE.replace('DATA_PLACEHOLDER',json.dumps(dict(sources=sources,runs=runs,media=media)).replace('<','\\u003c'))
    page=page.replace('Six synthetic inputs · 24 local Moshi generations. Review the audible response, its relevance, delivery and timing. “Slow + paused” is a delivery proxy, not a verified emotion.',
        'Twelve contextual voice tests · same Moshi checkpoint, seed 101. Requested emotions are not verified labels. Hesitation includes word repetitions; flat samples use disclosed pitch flattening. Judge both the input performance and the response.')
    page=page.replace('1 — Explain it to me','1 — Junior developer interview').replace('2 — Go over that again','2 — Pepper died yesterday')
    page=page.replace('<option>0</option><option>1</option>','<option>101</option>')
    page=page.replace("const names={neutral:'Neutral input',neutral_repeat:'Repeated neutral input',hesitant:'Slow + paused input',patch_neutral:'Self-patch control',patch_neutral_repeat:'Repeated-neutral patch',patch_hesitant:'Slow + paused patch'};", "const names={neutral:'Neutral',sad:'Sad / crying requested',flat:'Pitch-flattened / bored requested',hesitant:'Hesitation with repetitions',frustrated:'Frustrated / emphatic requested',excited:'Excited / animated requested'};")
    page=page.replace("['neutral','neutral_repeat','hesitant','patch_neutral','patch_neutral_repeat','patch_hesitant']", "['neutral','sad','flat','hesitant','frustrated','excited']")
    page=page.replace('6 of 24 · all conditions','6 of 12 · all deliveries')
    start=page.index('Patches use the neutral input')
    end=page.index('</p>',start)
    page=page[:start]+'Listen-first diagnostic: the assistant stream is forced silent while the opening user turn plays. Generation is released afterward, with a 20-second maximum tail and a 1.6-second silence stop. This is not unrestricted full-duplex performance. No activation patches or weight edits are used in this batch.'+page[end:]
    page=page.replace('xAI · Eve · exact words confirmed by ASR', "${escapeText(s.method)}<br>Script match: ${s.validation.exact_words?'yes':'variation — inspect transcript'}")
    page=page.replace("${audio(s.raw,'source-'+s.id)}", "${audio(s.raw,'source-'+s.id)}<details><summary>Input audio transcript</summary><p>${escapeText(s.input_transcript)}</p></details>")
    page=page.replace('Volume normalized, silence padded, speech-end aligned.','Original delivery level retained; 160 ms startup padding. End times vary with delivery.')
    page=page.replace('${audio(r.audio,r.id)}', '${audio(r.audio,r.id)}<details><summary>Hear the full exchange</summary>${audio(r.conversation,r.id+\'-conversation\')}</details>')
    page=page.replace("experiment:'matched-xai'", "experiment:'contextual-extreme'")
    control_markup='<details class="card"><summary>Free-duplex control: same neutral interview input and seed, listening gate off</summary><p>The stock opening remains audible here. This is a control, not one of the twelve listen-first runs.</p><audio controls preload="metadata" src="'+media[control_audio]+'"></audio><p>Audio transcript: '+html.escape(control_text)+'</p><details><summary>Moshi text stream</summary><p>'+html.escape(''.join(w for _,w in control_trace['words']))+'</p></details></details>'
    page=page.replace('<script type="application/json"',control_markup+'<script type="application/json"',1)
    target=root/'review.html' 
    target.write_text(page)
    print(target.resolve())
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path('out/contextual-extreme'))
    build(parser.parse_args().root)
