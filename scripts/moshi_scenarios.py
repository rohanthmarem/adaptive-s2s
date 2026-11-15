import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import aiohttp
import numpy as np
import rustymimi
import sphn

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = [
    dict(id='interview', title='Preparing for an interview',
         context='You have an interview tomorrow for your first junior software developer job. You are speaking with a supportive friend who can help you prepare.',
         script='My name is Alex. Tomorrow I have an interview for a junior developer job. I built a budgeting app in Python. Please give me a two sentence introduction using those facts.'),
    dict(id='pepper', title='Losing a companion',
         context='Your cat Pepper died yesterday after twelve years together. You are speaking with a caring friend. You want company and one small practical way to get through the evening.',
         script='My cat Pepper died yesterday. We were together for twelve years. The house feels empty tonight. Please suggest one small thing I can do to get through tonight.')]
DELIVERIES = {
    'neutral': 'Speak naturally, conversationally and matter-of-factly.',
    'sad': 'Perform unmistakable deep sadness: a fragile trembling voice, close to tears, breath catches and subdued energy. Sound devastated, not cheerful or merely slow.',
    'flat': 'Perform profound disengagement and boredom. Use a nearly monotone voice, very little pitch variation, flat emphasis and drained energy. Do not sound warmly helpful.',
    'hesitant': 'Perform strong uncertainty: audible false starts, breath catches and searching pauses within phrases. You may repeat a word once but must preserve the meaning. Do not merely slow down smoothly.',
    'frustrated': 'Perform intense frustration: tense emphatic stress, clipped phrases and audible exasperation. Do not shout so hard that words become unclear.',
    'excited': 'Perform extreme excitement: bright animated pitch changes, energetic emphasis and a quick lively pace. This is deliberately emotionally incongruent in the grief scene.'}


def acting_prompt(scene, delivery):
    if not scene.get('context') or not scene.get('script') or delivery not in DELIVERIES:
        raise ValueError('Every sample needs explicit scene context, spoken facts and a supported requested delivery')
    return (f"You are a voice actor performing the USER in a fictional scene, not answering their question. "
            f"Scene: {scene['context']} Acting direction: {DELIVERIES[delivery]} "
            f"Say only the following scripted lines as the character. No introduction, commentary, stage directions, or assistant response. "
            f"Spoken lines: {scene['script']}")


def tagged_text(script, delivery):
    if delivery == 'neutral':
        return script
    if delivery == 'sad':
        return '[cry] <soft><slow><lower-pitch>' + script.replace('. ', '. [sigh] ') + '</lower-pitch></slow></soft>'
    if delivery == 'flat':
        return '<lower-pitch><slow>' + script + '</slow></lower-pitch>'
    if delivery == 'hesitant':
        first, rest = script.split(' ', 1)
        return first + '... [long-pause] ' + first + ' ' + rest.replace('. ', '. [long-pause] ').replace('Please ', 'Please... [pause] please ')
    if delivery == 'frustrated':
        return '[sigh] <loud><emphasis>' + script + '</emphasis></loud>'
    if delivery == 'excited':
        return '[laugh] <higher-pitch><fast><sing-song>' + script + '</sing-song></fast></higher-pitch>'
    raise ValueError('Unknown delivery')


async def generate_tagged(scene, delivery, directory, key):
    name = scene['id']+'_'+delivery
    path = directory/(name+'.wav')
    request = dict(text=tagged_text(scene['script'], delivery), voice_id='eve', language='en',
                   output_format={'codec':'wav','sample_rate':24000})
    provenance = path.with_suffix('.request.json')
    if path.exists():
        if not provenance.exists() or json.loads(provenance.read_text()) != request:
            raise ValueError('Existing source request differs: '+name)
    else:
        async with aiohttp.ClientSession() as session:
            async with session.post('https://api.x.ai/v1/tts',json=request,
                headers={'Authorization':'Bearer '+key},timeout=aiohttp.ClientTimeout(total=90)) as response:
                if response.status != 200:
                    raise RuntimeError('xAI TTS HTTP '+str(response.status))
                path.write_bytes(await response.read())
        provenance.write_text(json.dumps(request,indent=2))
    return dict(id=name,scene=scene,requested_delivery=delivery,delivery_verified=False,
                renderer='xai-tts-tags', word_repetitions=delivery=='hesitant',
                file=str(path.resolve()),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


async def generate_one(scene, delivery, directory, key):
    name = scene['id']+'_'+delivery
    path = directory/(name+'.wav')
    prompt = acting_prompt(scene, delivery)
    request_path = directory/(name+'.request.json')
    request = {'model':'grok-voice-latest','voice':'eve','instructions':prompt,'requested_delivery':delivery,'scene':scene}
    if path.exists():
        if not request_path.exists() or json.loads(request_path.read_text()) != request:
            raise ValueError(f'Existing audio provenance differs: {name}')
    else:
        chunks=[]
        transcript=[]
        async with asyncio.timeout(90):
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect('wss://api.x.ai/v1/realtime?model=grok-voice-latest',
                    headers={'Authorization':'Bearer '+key}) as ws:
                    await ws.send_json({'type':'session.update','session':{'voice':'eve',
                        'instructions':prompt,'turn_detection':None,
                        'audio':{'output':{'format':{'type':'audio/pcm','rate':24000}}}}})
                    async for message in ws:
                        if message.type != aiohttp.WSMsgType.TEXT:
                            continue
                        event=json.loads(message.data)
                        kind=event.get('type','')
                        if kind=='error':
                            raise RuntimeError('xAI voice error: '+str(event.get('error',{}).get('code','unknown')))
                        if kind=='session.updated':
                            await ws.send_json({'type':'conversation.item.create','item':{'type':'message',
                                'role':'user','content':[{'type':'input_text','text':'Perform the scripted user lines now.'}]}})
                            await ws.send_json({'type':'response.create'})
                        elif kind in ['response.audio.delta','response.output_audio.delta']:
                            chunks.append(base64.b64decode(event['delta']))
                        elif kind in ['response.audio_transcript.delta','response.output_audio_transcript.delta']:
                            transcript.append(event['delta'])
                        elif kind=='response.done':
                            if event.get('response',{}).get('status') not in [None,'completed']:
                                raise RuntimeError('xAI response did not complete')
                            break
        if not chunks:
            raise RuntimeError('Voice actor returned no audio')
        pcm=np.frombuffer(b''.join(chunks),dtype='<i2').astype(np.float32)/32768
        rustymimi.write_wav(str(path),pcm,sample_rate=24000)
        request_path.write_text(json.dumps(request,indent=2))
        path.with_suffix('.actor.json').write_text(json.dumps({'transcript':''.join(transcript)}))
    return dict(id=name,scene=scene,requested_delivery=delivery,delivery_verified=False,
                file=str(path.resolve()),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


async def generate(args):
    key=Path(args.key_file).read_text().strip() if args.key_file else os.environ.get('XAI_API_KEY')
    if not key:
        raise ValueError('xAI key required')
    source=args.root/'source'
    source.mkdir(parents=True,exist_ok=True)
    manifest=[]
    for scene in SCENARIOS:
        for delivery in DELIVERIES:
            renderer = generate_tagged if args.renderer == 'tts' else generate_one
            manifest.append(await renderer(scene,delivery,source,key))
            print('Generated',manifest[-1]['id'],flush=True)
            (source/'manifest.json').write_text(json.dumps(manifest,indent=2))
            if args.limit and len(manifest)>=args.limit:
                return


def run(args):
    source=args.root/'source'
    output=args.output or args.root/'experiment'
    output.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((source/'manifest.json').read_text())
    if args.limit:
        manifest=manifest[:args.limit]
    results=[]
    for entry in manifest:
        pcm,_=sphn.read(entry['file'],sample_rate=24000)
        active=np.flatnonzero(np.abs(pcm.mean(axis=0))>0.005)
        if not len(active):
            raise ValueError('Actor recording is silent')
        onset=max(0,active[0]-480)
        end=min(pcm.shape[-1],active[-1]+481)
        prepared=output/(entry['id']+'_input.wav')
        rustymimi.write_wav(str(prepared),pcm.mean(axis=0)[onset:end],sample_rate=24000)
        name=entry['id']
        command=[sys.executable,str(ROOT/'docs/duplex/moshi_offline.py'),str(prepared),str(output/(name+'.wav')),
                 '--stop-silence','1.6','--prefix-silence','0.16','--tail-silence','20','--seed','101',
                 '--trace',str(output/(name+'.json')),'--capture',str(output/(name+'.npz')),'--layers','8']
        if not args.free_duplex:
            command.append('--listen-first')
        completed=subprocess.run(command,capture_output=True,text=True,timeout=240,env={**os.environ,'HF_HUB_OFFLINE':'1'})
        (output/(name+'.log')).write_text(completed.stdout+completed.stderr)
        if completed.returncode:
            raise RuntimeError(name+' failed; see log')
        results.append({**entry,'input':str(prepared.resolve()),'output':str((output/(name+'.wav')).resolve())})
        (output/'manifest.json').write_text(json.dumps(results,indent=2))
        print('Finished',name,flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['generate','run'])
    parser.add_argument('--root',type=Path,default=ROOT/'out/contextual-voice')
    parser.add_argument('--key-file')
    parser.add_argument('--renderer',choices=['voice','tts'],default='voice')
    parser.add_argument('--limit',type=int)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--free-duplex',action='store_true')
    args=parser.parse_args()
    if args.action=='generate':
        asyncio.run(generate(args))
    else:
        run(args)


if __name__=='__main__':
    main()
