import json
import re
from pathlib import Path
import subprocess
import sys

import numpy as np
import rustymimi
import sphn

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'scripts'))
from moshi_matched import speech_request, SCRIPTS
for script in SCRIPTS:
    url, neutral = speech_request('xai', script, 'neutral')
    _, repeat = speech_request('xai', script, 'neutral_repeat')
    _, hesitant = speech_request('xai', script, 'hesitant')
    assert url == 'https://api.x.ai/v1/tts'
    assert neutral == repeat
    assert neutral['voice_id'] == hesitant['voice_id']
    assert re.sub(r'<[^>]+>|\[pause\]', '', hesitant['text']).split() == script.split()
    assert hesitant['output_format'] == {'codec': 'wav', 'sample_rate': 24000}
output = root/'out/verify-moshi-matched'
source = output/'source'
source.mkdir(parents=True, exist_ok=True)
entries = []
for index, samples in enumerate([2400, 4800]):
    path = source/f'{index}.wav'
    signal = 0.1*np.sin(np.arange(samples)*2*np.pi*220/24000)
    rustymimi.write_wav(str(path), signal.astype(np.float32), sample_rate=24000)
    entries.append(dict(id=str(index), file=str(path)))
(source/'manifest.json').write_text(json.dumps(entries))
command = [sys.executable, str(root/'scripts/moshi_matched.py'), 'prepare',
           '--source', str(source), '--output', str(output/'prepared')]
subprocess.run(command, check=True, timeout=30)
prepared = json.loads((output/'prepared/manifest.json').read_text())
assert len({e['speech_end_frame'] for e in prepared}) == 1
lengths = []
for entry in prepared:
    audio, _ = sphn.read(entry['prepared_file'], sample_rate=24000)
    end = entry['speech_end_frame']*1920
    assert audio.shape[-1]-end == 240000
    assert np.count_nonzero(audio[0, end:]) == 0
    assert np.count_nonzero(audio[0, :96000]) == 0
    assert np.max(np.abs(audio)) <= 0.951
    assert np.isfinite(audio).all()
    lengths.append(audio.shape[-1])
assert len(set(lengths)) == 1
(output/'result.json').write_text(json.dumps({'passed': True, 'command': command}))
print('PASS: matched recording preparation CLI, aligned boundaries, silence, finite audio')
