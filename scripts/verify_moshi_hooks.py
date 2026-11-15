import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import rustymimi

root = Path(__file__).resolve().parents[1]
os.chdir(root)
output = root / 'out' / 'verify-moshi-hooks'
output.mkdir(parents=True, exist_ok=True)
input_path = output / 'silence.wav'
rustymimi.write_wav(str(input_path), np.zeros(1920 * 30, dtype=np.float32), sample_rate=24000)
np.save(output / 'direction.npy', np.ones(4096, dtype=np.float32))


def run(name, *options):
    command = [sys.executable, 'docs/duplex/moshi_offline.py', str(input_path),
               str(output / f'{name}.wav'), '--seed', '0', '--trace', str(output / f'{name}.json'), *options]
    result = subprocess.run(command, env={**os.environ, 'HF_HUB_OFFLINE': '1'},
                            capture_output=True, text=True, timeout=180)
    (output / f'{name}.log').write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(result.stderr)
    print(name, result.stdout.split('text stream:')[0].strip(), flush=True)
    return json.loads((output / f'{name}.json').read_text())


baseline = run('baseline')
captured = run('capture', '--capture', str(output / 'capture.npz'))
zero = run('zero', '--direction', str(output / 'direction.npy'), '--strength', '0')
patched = run('identity-patch', '--donor', str(output / 'capture.npz'))
steered = run('steered', '--direction', str(output / 'direction.npy'), '--strength', '2',
              '--start-frame', '8', '--stop-frame', '16')
for name, result in [('capture', captured), ('zero', zero), ('identity-patch', patched)]:
    for key in ['text_tokens', 'audio_tokens']:
        assert baseline[key] == result[key], (name, key)
    assert (output / 'baseline.wav').read_bytes() == (output / f'{name}.wav').read_bytes(), name
with np.load(output / 'capture.npz') as data:
    for layer in [0, 8, 24]:
        assert data[f'layer_{layer}'].shape == (30, 4096)
        assert np.isfinite(data[f'layer_{layer}']).all()
        np.testing.assert_array_equal(data[f'frames_{layer}'], np.arange(30))
assert steered['audio_tokens'] != baseline['audio_tokens']
assert steered['text_tokens'][:8] == baseline['text_tokens'][:8]
(output / 'result.json').write_text(json.dumps({'passed': True, 'frames': 30,
    'checks': ['capture parity', 'zero steering parity', 'identity patch parity',
               'finite activations', 'nonzero intervention changes generation']}))
print(f'PASS: real Moshi CLI capture and intervention checks. Evidence: {output}')
