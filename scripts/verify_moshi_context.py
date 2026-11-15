import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import rustymimi
import sphn

from moshi_scenarios import SCENARIOS, DELIVERIES, acting_prompt, tagged_text

root=Path(__file__).resolve().parents[1]
output=root/'out/verify-moshi-context'
output.mkdir(parents=True,exist_ok=True)
try:
    acting_prompt({'script':'I do not understand this.'},'neutral')
except ValueError:
    pass
else:
    raise AssertionError('Ungrounded old-style samples must be rejected')
for scene in SCENARIOS:
    for style in DELIVERIES:
        prompt=acting_prompt(scene,style)
        assert scene['context'] in prompt and scene['script'] in prompt
assert len(set(DELIVERIES.values()))==6
assert '[cry]' in tagged_text(SCENARIOS[0]['script'],'sad')
assert '[long-pause]' in tagged_text(SCENARIOS[0]['script'],'hesitant')
assert tagged_text(SCENARIOS[0]['script'],'hesitant').count('My') >= 2
for name,length in [('user',3211),('context',4321)]:
    rustymimi.write_wav(str(output/f'{name}.wav'),np.zeros(length,dtype=np.float32),sample_rate=24000)
command=[sys.executable,str(root/'docs/duplex/moshi_offline.py'),str(output/'user.wav'),str(output/'output.wav'),
         '--context',str(output/'context.wav'),'--listen-first','--prefix-silence','0.16','--tail-silence','1',
         '--seed','101','--trace',str(output/'trace.json')]
result=subprocess.run(command,capture_output=True,text=True,timeout=120,env={**os.environ,'HF_HUB_OFFLINE':'1'})
(output/'log.txt').write_text(result.stdout+result.stderr)
assert result.returncode==0,result.stderr
trace=json.loads((output/'trace.json').read_text())
assert trace['context_samples']==4321+7680
assert trace['input_samples']==3211+4321+7680
assert trace['frames']==int(np.ceil((trace['input_samples']+3840+24000)/1920))
assert trace['seed']==101 and trace['sampling']=='official' and trace['listen_first']
assert all(t==3 for t in trace['text_tokens'][:trace['listen_frames']]), 'listen-first must hold the text stream on the padding token 3, not the word-start token 0'
audio,_=sphn.read(str(output/'output.wav'),sample_rate=24000)
gate_end=max(1,trace['listen_frames']-2)*1920
assert np.sqrt(np.mean(audio[0,:gate_end]**2))<0.02
print('PASS: context preserved in stream, partial frame retained, explicit seed, official sampling, opening silence forced in diagnostic mode; ungrounded scene rejected')

stop_command=[sys.executable,str(root/'docs/duplex/moshi_offline.py'),str(output/'user.wav'),str(output/'stopped.wav'),
              '--tail-silence','8','--stop-silence','0.8','--seed','0','--trace',str(output/'stopped.json')]
stop_result=subprocess.run(stop_command,capture_output=True,text=True,timeout=120,env={**os.environ,'HF_HUB_OFFLINE':'1'})
(output/'stop-log.txt').write_text(stop_result.stdout+stop_result.stderr)
assert stop_result.returncode==0,stop_result.stderr
stopped=json.loads((output/'stopped.json').read_text())
assert stopped['frames']<stopped['max_frames'] and stopped['words']
print('PASS: response-silence stop ends a real Moshi run before the maximum tail')
