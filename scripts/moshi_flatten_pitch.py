import argparse
import json
from pathlib import Path

import numpy as np
import parselmouth
from parselmouth.praat import call
import soundfile as sf


def flatten(source, destination):
    samples,rate=sf.read(source,dtype='float64')
    sound=parselmouth.Sound(samples,sampling_frequency=rate)
    pitch=sound.to_pitch(pitch_floor=75,pitch_ceiling=500)
    values=pitch.selected_array['frequency']
    voiced=values[values>0]
    if len(voiced)<5:
        raise ValueError('Too little voiced audio to flatten')
    frequency=float(np.median(voiced))
    manipulation=call(sound,'To Manipulation',0.01,75,500)
    tier=call(manipulation,'Extract pitch tier')
    call(tier,'Remove points between',0,sound.xmax)
    call(tier,'Add point',sound.xmax/2,frequency)
    call([tier,manipulation],'Replace pitch tier')
    flattened=call(manipulation,'Get resynthesis (overlap-add)')
    sf.write(destination,flattened.values.T,round(flattened.sampling_frequency))
    measured=flattened.to_pitch(pitch_floor=75,pitch_ceiling=500).selected_array['frequency']
    measured=measured[measured>0]
    result=dict(method='Praat PSOLA constant pitch, synthetic acoustic control; not validated boredom',
        target_hz=frequency,original_pitch_sd_semitones=float(np.std(12*np.log2(voiced/np.median(voiced)))),
        output_pitch_sd_semitones=float(np.std(12*np.log2(measured/np.median(measured)))))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args()
    source=args.root/'source'
    manifest=json.loads((source/'manifest.json').read_text())
    for entry in manifest:
        if entry['requested_delivery']=='flat':
            original=Path(entry.get('original_file',entry['file']))
            destination=source/(entry['id']+'_flattened.wav')
            entry['acoustic_transform']=flatten(original,destination)
            entry['original_file']=str(original)
            entry['file']=str(destination.resolve())
            entry['sha256']=__import__('hashlib').sha256(destination.read_bytes()).hexdigest()
            print(entry['id'],entry['acoustic_transform'],flush=True)
    (source/'manifest.json').write_text(json.dumps(manifest,indent=2))
