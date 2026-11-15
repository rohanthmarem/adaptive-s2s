import base64
import json
from pathlib import Path
import re
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
subprocess.run([sys.executable,str(root/'scripts/moshi_context_review.py'),'--root',str(root/'out/contextual-extreme')],check=True)
page=(root/'out/contextual-extreme/review.html').read_text()
data=json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>',page,re.S).group(1))
assert len(data['sources'])==12 and len(data['runs'])==12
for family in [0,1]:
    assert len([r for r in data['runs'] if r['family']==family])==6
for source in data['sources']:
    assert not source['validation']['delivery_verified']
    assert source['input_transcript']
for run in data['runs']:
    assert run['conversation'] in data['media'] and run['audio'] in data['media']
for uri in data['media'].values():
    audio=base64.b64decode(uri.split(',',1)[1],validate=True)
    assert len(audio)>1000 and audio[:3]==b'ID3'
assert 'Patches use the neutral input' not in page
assert 'Pitch-flattened' in page and 'not unrestricted full-duplex' in page
print('PASS: twelve contextual inputs and outputs, honest delivery labels, complete exchange audio, independent transcripts')
