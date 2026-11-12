"""Lazy local Whisper recogniser."""
import numpy as np
from .types import Transcript, Word


def cached_model_path(name: str) -> str:
    """Resolve cached revisions even when the cache has no main branch ref."""
    from pathlib import Path
    from huggingface_hub import snapshot_download, scan_cache_dir
    if Path(name).is_dir():
        return name
    try:
        return snapshot_download(name, local_files_only=True)
    except OSError as exc:
        for repo in scan_cache_dir().repos:
            if repo.repo_id == name and repo.revisions:
                revision = max(repo.revisions, key=lambda rev: rev.last_modified)
                return str(revision.snapshot_path)
        raise RuntimeError(f"Model {name} is not cached; run s2s fetch-models") from exc


class WhisperASR:
    def __init__(self, model_name="base.en", device="cpu", compute_type="int8"):
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def transcribe(self, audio16k: np.ndarray) -> Transcript:
        if self._model is None:
            from faster_whisper import WhisperModel
            from faster_whisper.utils import _MODELS
            path = cached_model_path(_MODELS.get(self.model_name, self.model_name))
            self._model = WhisperModel(path, device=self.device,
                                       compute_type=self.compute_type, local_files_only=True)
        segments, _ = self._model.transcribe(
            np.asarray(audio16k, dtype=np.float32), word_timestamps=True, beam_size=5,
            temperature=0.0, language="en", condition_on_previous_text=False)
        segments = list(segments)
        words = [Word(w.word.strip(), w.start, w.end, w.probability)
                 for seg in segments for w in (seg.words or [])]
        return Transcript(" ".join(s.text.strip() for s in segments).strip(), words,
                          model=self.model_name)
