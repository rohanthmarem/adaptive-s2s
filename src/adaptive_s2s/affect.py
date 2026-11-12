"""Optional local speech-emotion readings."""
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import logging
import os
import numpy as np
from .types import AffectReading

LABELS = {"angry", "disgusted", "fearful", "happy", "neutral", "other", "sad", "surprised", "unknown"}


class NullAffect:
    def __init__(self, note="Speech emotion analysis disabled"):
        self.note = note

    def analyze(self, audio16k) -> AffectReading:
        return AffectReading(available=False, note=self.note)


class Emotion2VecAffect:
    def __init__(self, model="emotion2vec/emotion2vec_plus_base"):
        self.model = model
        self._model = None

    def analyze(self, audio16k) -> AffectReading:
        # Resolve only cached snapshots: normal turns must never trigger downloads.
        from .asr import cached_model_path
        previous = logging.root.manager.disable
        root_handlers = list(logging.root.handlers)
        try:
            logging.disable(logging.CRITICAL)
            with open(os.devnull, "w") as sink, redirect_stdout(sink), redirect_stderr(sink):
                if self._model is None:
                    from funasr import AutoModel
                    path = cached_model_path(self.model)
                    self._model = AutoModel(model=path, hub="hf", disable_update=True,
                                            disable_pbar=True, device="cpu")
                rec = self._model.generate(
                    np.asarray(audio16k, dtype=np.float32), granularity="utterance",
                    extract_embedding=False, disable_pbar=True)
        finally:
            # FunASR may install a root handler while stdout/stderr point at the sink.
            # Remove only newly installed handlers; never retain a closed stream.
            for handler in list(logging.root.handlers):
                if handler not in root_handlers:
                    logging.root.removeHandler(handler)
                    handler.close()
            logging.disable(previous)
        scores = {}
        for label, score in zip(rec[0]["labels"], rec[0]["scores"]):
            label = label.rsplit("/", 1)[-1].lower()
            label = {"disgust": "disgusted", "fear": "fearful", "<unk>": "unknown"}.get(label, label)
            if label not in LABELS:
                raise ValueError(f"Unexpected emotion2vec label: {label}")
            scores[label] = float(score)
        top = max(scores, key=scores.get)
        return AffectReading(True, self.model, scores, top, scores[top])


def make_affect(kind: str) -> NullAffect | Emotion2VecAffect:
    if kind == "off":
        return NullAffect()
    if kind not in ("auto", "emotion2vec"):
        raise ValueError(f"Unknown affect backend: {kind}")
    if importlib.util.find_spec("funasr") is None:
        if kind == "emotion2vec":
            raise RuntimeError("emotion2vec requires funasr; install the affect extra")
        return NullAffect("funasr is not installed")
    return Emotion2VecAffect()
