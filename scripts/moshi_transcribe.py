import argparse
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import parselmouth
import soundfile as sf
import soxr
from faster_whisper import WhisperModel


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('directory',type=Path)
    parser.add_argument('--source',action='store_true')
    args=parser.parse_args()
    entries=json.loads((args.directory/'manifest.json').read_text())
    model=WhisperModel('small.en',device='cpu',compute_type='int8',local_files_only=True)
    results={}
    cache={}
    for entry in entries:
        file=entry['file'] if args.source else entry['output']
        samples,rate=sf.read(file,dtype='float32')
        if samples.ndim>1:
            samples=samples.mean(axis=1)
        digest=hashlib.sha256(Path(file).read_bytes()).hexdigest()
        if digest not in cache:
            segments,_=model.transcribe(soxr.resample(samples,rate,16000),language='en',beam_size=5,vad_filter=not args.source)
            cache[digest]=[dict(start=s.start,end=s.end,text=s.text) for s in segments]
        segments=cache[digest]
        text=''.join(s['text'] for s in segments).strip()
        row=dict(transcript=text,segments=segments,duration_s=len(samples)/rate)
        if args.source:
            pitch=parselmouth.Sound(samples,rate).to_pitch(pitch_floor=75,pitch_ceiling=500).selected_array['frequency']
            voiced=pitch[pitch>0]
            row['pitch_sd_semitones']=float(np.std(12*np.log2(voiced/np.median(voiced)))) if len(voiced) else None
            normalize=lambda t:re.findall('[a-z]+',t.lower().replace('12','twelve').replace('2','two'))
            row['exact_words']=normalize(text)==normalize(entry['scene']['script'])
            row['delivery_verified']=False
        results[entry['id']]=row
        print(entry['id'],text,flush=True)
    target=args.directory/('validation.json' if args.source else 'audio-transcripts.json')
    target.write_text(json.dumps(results,indent=2))


if __name__=='__main__':
    main()
