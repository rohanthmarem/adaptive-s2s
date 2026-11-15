import base64
import json
from pathlib import Path
import re
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
subprocess.run([sys.executable,str(root/'scripts/moshi_review.py'),'--root',str(root/'out/matched-xai')],check=True)
page=(root/'out/matched-xai/review.html').read_text()
data=json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>',page,re.S).group(1))
assert len(data['sources'])==6 and len(data['runs'])==24
assert len({run['id'] for run in data['runs']})==24
for family in [0,1]:
 for seed in [0,1]:
  assert len([r for r in data['runs'] if r['family']==family and r['seed']==seed])==6
for item in data['sources']:
 assert item['raw'] in data['media'] and item['padded'] in data['media']
for run in data['runs']:
 assert run['audio'] in data['media'] and isinstance(run['transcript'],str)
for uri in data['media'].values():
 payload=base64.b64decode(uri.split(',',1)[1],validate=True)
 assert len(payload)>1000 and payload[:3]==b'ID3'
assert 'DATA_PLACEHOLDER' not in page
print('PASS: review built with all six source clips, six padded inputs and 24 transcribed outputs; embedded MP3 assets validated')
