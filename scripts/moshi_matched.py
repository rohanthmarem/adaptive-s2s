import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request

import numpy as np
import rustymimi
import sphn

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ['I do not understand this. Can you explain it to me?',
           'Can we go over that again? I want to make sure I understand.']
STYLES = {
    'neutral': 'Speak naturally and matter-of-factly at a conversational pace.',
    'neutral_repeat': 'Speak naturally and matter-of-factly at a conversational pace.',
    'hesitant': 'Sound uncertain and hesitant, with natural pauses, but remain clearly intelligible. Do not add fillers, repeat words, or change the text.'}


def speech_request(provider, script, style):
    if provider == 'xai':
        text = script
        if style == 'hesitant':
            text = '<slow>' + script.replace('. ', '. [pause] ').replace('? ', '? [pause] ') + '</slow>'
        return 'https://api.x.ai/v1/tts', dict(text=text, voice_id='eve', language='en',
            output_format={'codec': 'wav', 'sample_rate': 24000})
    return 'https://api.openai.com/v1/audio/speech', dict(model='gpt-4o-mini-tts',
        voice='coral', input=script, instructions='Say exactly the supplied text. '+STYLES[style],
        response_format='wav')


def generate(destination, key_file, provider):
    key = Path(key_file).read_text().strip() if key_file else os.environ.get('XAI_API_KEY' if provider == 'xai' else 'OPENAI_API_KEY')
    if not key:
        raise ValueError('Provider API key or --key-file is required for generation')
    destination.mkdir(parents=True, exist_ok=True)
    manifest = []
    for index, script in enumerate(SCRIPTS):
        for style, instruction in STYLES.items():
            name = f'{index}_{style}'
            target = destination / f'{name}.wav'
            endpoint, payload = speech_request(provider, script, style)
            provenance = destination / f'{name}.request.json'
            if target.exists():
                if not provenance.exists() or json.loads(provenance.read_text()) != payload:
                    raise ValueError(f'Existing recording has mismatched provenance: {name}')
            else:
                request = urllib.request.Request(endpoint,
                    data=json.dumps(payload).encode(),
                    headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
                try:
                    with urllib.request.urlopen(request, timeout=120) as response:
                        audio = response.read()
                except urllib.error.HTTPError as error:
                    raise RuntimeError(f'Speech API returned HTTP {error.code}; check account access and credits') from None
                target.write_bytes(audio)
                provenance.write_text(json.dumps(payload, indent=2))
            manifest.append(dict(id=name, family=index, style=style, text=script, provider=provider,
                                 file=str(target.resolve()), sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
            print(f'Generated {name}', flush=True)
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2))


def prepare(source, destination):
    entries = json.loads((source / 'manifest.json').read_text())
    destination.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        audio, _ = sphn.read(entry['file'], sample_rate=24000)
        audio = audio.mean(axis=0)
        if not len(audio) or not np.isfinite(audio).all():
            raise ValueError('Invalid source audio')
        active = np.flatnonzero(np.abs(audio) > 0.005)
        if not len(active):
            raise ValueError('Source audio is silent')
        audio = audio[max(0, active[0]-240):min(len(audio), active[-1]+241)]
        rms = np.sqrt(np.mean(audio**2))
        audio = audio * min(0.06 / rms, 0.95 / np.max(np.abs(audio)))
        entry['samples'] = len(audio)
        entry['audio'] = audio
    boundary = max(entry['samples'] for entry in entries) + 4 * 24000
    boundary = ((boundary + 1919) // 1920) * 1920
    for entry in entries:
        audio = entry.pop('audio')
        padded = np.pad(audio, (boundary-len(audio), 10*24000)).astype(np.float32)
        path = destination / (entry['id'] + '.wav')
        rustymimi.write_wav(str(path), padded, sample_rate=24000)
        entry['prepared_file'] = str(path.resolve())
        entry['speech_end_frame'] = boundary // 1920
    (destination / 'manifest.json').write_text(json.dumps(entries, indent=2))
    return entries


def run(source, destination):
    entries = prepare(source, destination)
    results = []
    for seed in [0, 1]:
        for entry in entries:
            name = f'{entry["id"]}_seed{seed}'
            execute(entry, name, seed, destination, [])
        for family in sorted({entry['family'] for entry in entries}):
            neutral = next(e for e in entries if e['family'] == family and e['style'] == 'neutral')
            boundary = neutral['speech_end_frame']
            for donor_style in ['neutral', 'neutral_repeat', 'hesitant']:
                donor = destination / f'{family}_{donor_style}_seed{seed}.npz'
                name = f'{family}_patch_{donor_style}_seed{seed}'
                execute(neutral, name, seed, destination,
                        ['--donor', str(donor), '--start-frame', str(boundary), '--stop-frame', str(boundary+1)])
        for trace in sorted(destination.glob(f'*seed{seed}.json')):
            data = json.loads(trace.read_text())
            if 'words' in data:
                results.append({'run': trace.stem, 'words': data['words'], 'elapsed_s': data['elapsed_s']})
    (destination / 'results.json').write_text(json.dumps(results, indent=2))
    print(f'Experiment outputs: {destination}', flush=True)


def execute(entry, name, seed, destination, options):
    command = [sys.executable, str(ROOT/'docs/duplex/moshi_offline.py'),
        entry['prepared_file'], str(destination/f'{name}.wav'), '--seed', str(seed),
        '--layers', '8', '--trace', str(destination/f'{name}.json')]
    if not options:
        command += ['--capture', str(destination/f'{name}.npz')]
    result = subprocess.run(command+options, capture_output=True, text=True, timeout=240,
                            env={**os.environ, 'HF_HUB_OFFLINE': '1'})
    (destination/f'{name}.log').write_text(result.stdout+result.stderr)
    if result.returncode:
        raise RuntimeError(f'{name} failed; see log')
    print(f'Finished {name}', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['generate', 'run', 'prepare'])
    parser.add_argument('--source', type=Path, default=ROOT/'out/matched-voice/source')
    parser.add_argument('--output', type=Path, default=ROOT/'out/matched-voice/experiment')
    parser.add_argument('--key-file')
    parser.add_argument('--provider', choices=['openai', 'xai'], default='openai')
    args = parser.parse_args()
    if args.action == 'generate':
        generate(args.source, args.key_file, args.provider)
    elif args.action == 'prepare':
        prepare(args.source, args.output)
    else:
        run(args.source, args.output)


if __name__ == '__main__':
    main()
