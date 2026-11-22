"""Minimal LLM / embedding clients for a local Ollama server or any OpenAI-compatible server (e.g. vLLM)."""
from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Protocol

import httpx

Message = dict[str, str]


class ChatModel(Protocol):
    name: str

    def chat(self, messages: list[Message]) -> str: ...


class OllamaChat:
    """POST /api/chat on an Ollama server; deterministic decoding (temperature 0)."""

    def __init__(self, model: str, base_url: str = "http://127.0.0.1:11434", timeout_s: float = 180.0,
                 num_ctx: int = 8192, client: httpx.Client | None = None):
        self.name = f"ollama:{model}"
        self.model, self.num_ctx = model, num_ctx
        self.client = client or httpx.Client(base_url=base_url, timeout=timeout_s)

    def chat(self, messages: list[Message]) -> str:
        resp = self.client.post("/api/chat", json={
            "model": self.model, "messages": messages, "stream": False,
            "options": {"temperature": 0, "seed": 0, "num_ctx": self.num_ctx},
        })
        resp.raise_for_status()
        return resp.json()["message"]["content"]


class OpenAICompatibleChat:
    """POST /v1/chat/completions — works with vLLM, LiteLLM, llama.cpp server, etc."""

    def __init__(self, model: str, base_url: str, api_key: str | None = None, timeout_s: float = 180.0,
                 client: httpx.Client | None = None):
        self.name = f"openai-compatible:{model}"
        self.model = model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.client = client or httpx.Client(base_url=base_url, timeout=timeout_s, headers=headers)

    def chat(self, messages: list[Message]) -> str:
        resp = self.client.post("/v1/chat/completions", json={
            "model": self.model, "messages": messages, "temperature": 0,
        })
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


class ScriptedChat:
    """Returns pre-written replies in order; used by tests and by the evaluation 'oracle' baseline."""

    def __init__(self, replies: Iterable[str], name: str = "scripted"):
        self.name = name
        self._replies = list(replies)
        self.calls: list[list[Message]] = []

    def chat(self, messages: list[Message]) -> str:
        self.calls.append(messages)
        if not self._replies:
            raise RuntimeError("ScriptedChat has no replies left")
        return self._replies.pop(0)


class OllamaEmbedder:
    def __init__(self, model: str = "bge-m3", base_url: str = "http://127.0.0.1:11434", timeout_s: float = 120.0,
                 client: httpx.Client | None = None):
        self.name = f"ollama:{model}"
        self.model = model
        self.client = client or httpx.Client(base_url=base_url, timeout=timeout_s)

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self.client.post("/api/embed", json={"model": self.model, "input": texts})
        resp.raise_for_status()
        return resp.json()["embeddings"]


def make_chat(provider: str, model: str, base_url: str) -> ChatModel | None:
    if provider == "ollama":
        return OllamaChat(model, base_url)
    if provider == "openai":
        return OpenAICompatibleChat(model, base_url, api_key=os.environ.get("LLM_API_KEY"))
    if provider == "none":
        return None
    raise ValueError(f"unknown LLM_PROVIDER: {provider}")
