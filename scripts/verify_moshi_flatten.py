from pathlib import Path
import numpy as np
import soundfile as sf
from moshi_flatten_pitch import flatten

output=Path('out/verify-moshi-flat')
output.mkdir(parents=True,exist_ok=True)
time=np.arange(24000*2)/24000
frequency=180+40*np.sin(2*np.pi*2*time)
phase=2*np.pi*np.cumsum(frequency)/24000
signal=(0.3*np.sin(phase)+0.15*np.sin(2*phase)+0.1*np.sin(3*phase))*np.minimum(1,np.minimum(time,2-time)*20)
sf.write(output/'varying.wav',signal,24000)
result=flatten(output/'varying.wav',output/'flat.wav')
assert result['original_pitch_sd_semitones']>1
assert result['output_pitch_sd_semitones']<0.4
print('PASS: pitch-flattening visibly varying source produces a measured flat acoustic control')
