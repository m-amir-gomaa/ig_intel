"""LLM provider seam.

DirectDeepSeek wired now. OpenRouter reserved for the web-search/RAG phase
(deepseek-v4-pro + web_search tool) — swap the provider, keep the interface.
"""

import abc

import requests

from . import config


class LLMProvider(abc.ABC):
    @abc.abstractmethod
    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        """Return assistant text. json_mode=True requests a JSON object response."""


class DirectDeepSeek(LLMProvider):
    def __init__(self, api_key: str):
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY not set")
        self.api_key = api_key
        self.base = config.DEEPSEEK_BASE_URL
        self.model = config.DEEPSEEK_MODEL

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        resp = requests.post(
            f"{self.base}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


class OpenRouter(LLMProvider):
    """Reserved for RAG phase (deepseek-v4-pro + web_search)."""

    def __init__(self, api_key: str):  # noqa: ARG002
        raise NotImplementedError("OpenRouter lands with the web-search/RAG phase")


def get_provider() -> LLMProvider:
    if config.DEEPSEEK_API_KEY:
        return DirectDeepSeek(config.DEEPSEEK_API_KEY)
    if config.OPENROUTER_API_KEY:
        raise NotImplementedError("OpenRouter not wired yet — set DEEPSEEK_API_KEY")
    raise RuntimeError("no LLM provider configured (need DEEPSEEK_API_KEY)")
