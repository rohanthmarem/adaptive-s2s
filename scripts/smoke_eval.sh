#!/usr/bin/env bash
# Smoke evaluation on synthetic voices and acted clips. It checks that the harness and the wiring
# work. It is not a result. It uses dev scripts only, so the held-out scripts stay untouched.
# Takes about 10 minutes on an M5 MacBook Pro. Run from the repo root.
set -euo pipefail
export HF_HUB_OFFLINE=1
S=.venv/bin/s2s

$S eval stimuli --set say --out data/smoke-say --voices Samantha --rates 185 --split dev
$S eval stimuli --set psola --source data/smoke-say/manifest.jsonl --out data/smoke-psola
$S eval stimuli --set register --out data/smoke-register --split dev
$S eval stimuli --set nuisance --source data/smoke-say/manifest.jsonl --out data/smoke-nuisance --limit 4
$S eval stimuli --set crema --out data/smoke-crema --actors 1001,1002

# Pace: identical words at five speeds. The shuffled arm is the negative control.
$S eval run --manifest data/smoke-psola/manifest.jsonl --out runs/smoke-pace \
    --arms static full --shuffled --track locked
# Register: the same request in three registers, with and without real speech recognition.
$S eval run --manifest data/smoke-register/manifest.jsonl --out runs/smoke-register \
    --arms static text-only --no-tts --seeds 0,1 --track locked
$S eval run --manifest data/smoke-register/manifest.jsonl --out runs/smoke-register-e2e \
    --arms static text-only --no-tts --track e2e
# Emotion: acted clips with neutral words. These are in the emotion model's training data.
$S eval run --manifest data/smoke-crema/manifest.jsonl --out runs/smoke-emotion \
    --arms static full --no-tts --track locked
# Nuisance: gain, leading silence and noise must not change the controls.
$S eval run --manifest data/smoke-nuisance/manifest.jsonl --out runs/smoke-nuisance \
    --arms full --no-tts --track locked

for run in smoke-pace smoke-register smoke-register-e2e smoke-emotion smoke-nuisance; do
    $S eval report --run "runs/$run"
done
