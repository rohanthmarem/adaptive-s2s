Record consenting adults reading the neutral scripts verbatim in contrasting deliveries (ordinary,
slow, fast, happy, sad). Keep microphone position and gain fixed. Also record the register triples
with the same delivery. Save mono WAV files as `{speaker}_{script_id}_{delivery}.wav`, for example
`p01_n09_sad.wav`. Use anonymous speaker IDs; avoid names or identifying speech.

Reserve new speakers AND heldout script IDs for the final evaluation. Freeze policy settings on dev
recordings first. Pass heldout speaker IDs to the human manifest builder; inspect both the manifest script `split` and `labels.speaker_split`. Final human results must
use rows where both are heldout. The script split always comes from scripts.yaml.
Obtain explicit consent for recording, local model processing, and any sharing. Keep consent records
separate. Do not publish recordings without permission. Synthetic smoke checks are debugging only.
