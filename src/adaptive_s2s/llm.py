"""Explicit local, compatible HTTP, and labelled template backends."""
from dataclasses import dataclass
import importlib.util
import json
import os
import platform
import time
import urllib.request
from .types import TextControls


@dataclass
class LLMResult:
    text: str
    backend: str
    model: str | None
    stub: bool
    seed: int
    latency_s: float


class MLXChat:
    def __init__(self, model="mlx-community/Qwen2.5-7B-Instruct-4bit"):
        self.model = model
        self._loaded = None

    def generate(self, messages, *, max_tokens=160, temperature=0.6, top_p=0.9, seed=0, controls=None) -> LLMResult:
        start = time.perf_counter()
        import mlx.core as mx
        from mlx_lm import load, generate
        from mlx_lm.sample_utils import make_sampler
        from .asr import cached_model_path
        if self._loaded is None:
            path = self.model if os.path.isdir(self.model) else cached_model_path(self.model)
            self._loaded = load(path)
        model, tokenizer = self._loaded
        mx.random.seed(seed)
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        text = generate(model, tokenizer, prompt=prompt, max_tokens=max_tokens,
                        sampler=make_sampler(temp=temperature, top_p=top_p), verbose=False)
        return LLMResult(text, "mlx", self.model, False, seed, time.perf_counter() - start)


class OpenAIChat:
    def __init__(self, base_url=None, model=None, api_key=None):
        self.base_url = (base_url or os.environ.get("S2S_OPENAI_BASE_URL", "")).rstrip("/")
        self.model = model or os.environ.get("S2S_OPENAI_MODEL")
        self.api_key = api_key or os.environ.get("S2S_OPENAI_API_KEY")
        if not self.base_url or not self.model:
            raise ValueError("Set S2S_OPENAI_BASE_URL and S2S_OPENAI_MODEL for the OpenAI-compatible backend")

    def generate(self, messages, *, max_tokens=160, temperature=0.6, top_p=0.9, seed=0, controls=None) -> LLMResult:
        start = time.perf_counter()
        payload = dict(model=self.model, messages=messages, max_tokens=max_tokens,
                       temperature=temperature, top_p=top_p, seed=seed)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(self.base_url + "/chat/completions",
                                         data=json.dumps(payload).encode(), headers=headers)
        with urllib.request.urlopen(request, timeout=120) as response:
            text = json.load(response)["choices"][0]["message"]["content"]
        return LLMResult(text, "openai", self.model, False, seed, time.perf_counter() - start)


class TemplateChat:
    def generate(self, messages, *, max_tokens=160, temperature=0.6, top_p=0.9, seed=0, controls=None) -> LLMResult:
        tc = controls or TextControls()
        replies = {
            "casual": "Yeah, we can work through it. What's the next thing you want to try?",
            "neutral": "We can work through this together. What would you like to do next?",
            "formal": "I can assist with that request. Please describe the next step you would like to take.",
        }
        text = ("That sounds really difficult. Would it help to take one small step together?"
                if tc.supportive else replies[tc.register])
        return LLMResult(text, "template", None, True, seed, 0.0)


def make_llm(kind: str, model: str | None = None) -> MLXChat | OpenAIChat | TemplateChat:
    if kind == "auto":
        if platform.system() == "Darwin" and platform.machine() == "arm64" and importlib.util.find_spec("mlx_lm"):
            kind = "mlx"
        elif os.environ.get("S2S_OPENAI_BASE_URL"):
            kind = "openai"
        else:
            raise RuntimeError("No model backend available; pass --llm template explicitly to use a stub")
    if kind == "mlx":
        return MLXChat(model or "mlx-community/Qwen2.5-7B-Instruct-4bit")
    if kind == "openai":
        return OpenAIChat(model=model)
    if kind == "template":
        return TemplateChat()
    raise ValueError(f"Unknown LLM backend: {kind}")
