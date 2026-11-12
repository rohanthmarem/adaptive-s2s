"""Audio I/O; all processing uses mono float32 waveforms."""
from pathlib import Path
import shutil
import subprocess

import numpy as np
import soundfile as sf
import soxr


def load_audio(path) -> tuple[np.ndarray, int]:
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    return x.mean(axis=1, dtype=np.float32), sr


def resample(x, sr: int, target_sr: int) -> np.ndarray:
    if sr <= 0 or target_sr <= 0:
        raise ValueError("Sample rates must be positive")
    x = np.asarray(x, dtype=np.float32)
    return x if sr == target_sr else soxr.resample(x, sr, target_sr).astype(np.float32)


def to_16k(x, sr: int) -> np.ndarray:
    return resample(x, sr, 16000)


def save_wav(path, x, sr: int) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, np.asarray(x, dtype=np.float32), sr, subtype="PCM_16")


def play(path) -> None:
    if shutil.which("afplay"):
        subprocess.run(["afplay", str(path)], check=True)
    else:
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError("Playback needs afplay or sounddevice") from exc
        x, sr = load_audio(path)
        sd.play(x, sr)
        sd.wait()


def record_until_enter(sr: int = 16000) -> np.ndarray:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError("Microphone recording requires sounddevice (install the mic extra)") from exc
    chunks = []
    def callback(indata, frames, time, status):
        chunks.append(indata[:, 0].copy())
    with sd.InputStream(samplerate=sr, channels=1, dtype="float32", callback=callback):
        input("Recording… press Enter to stop: ")
    return np.concatenate(chunks) if chunks else np.empty(0, dtype=np.float32)
