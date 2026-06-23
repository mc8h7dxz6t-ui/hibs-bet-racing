"""OpenAI-compatible LLM client — optional live inference (not NeMo safety)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx

_DEFAULT_BASE = "https://api.openai.com/v1"
_DEFAULT_MODEL = "gpt-4o-mini"
_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


@dataclass
class LLMResponse:
    ok: bool
    content: str
    parsed: dict[str, Any] | None
    model: str
    usage: dict[str, Any] | None
    error: str | None = None


class OpenAICompatibleClient:
    """
    Minimal chat-completions client for any OpenAI-compatible API.

    Env: ``OPENAI_API_KEY`` (required for live), ``AI_KIT_LLM_BASE_URL``,
    ``AI_KIT_LLM_MODEL``.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
        self.base_url = (base_url or os.getenv("AI_KIT_LLM_BASE_URL", _DEFAULT_BASE)).rstrip("/")
        self.model = model or os.getenv("AI_KIT_LLM_MODEL", _DEFAULT_MODEL)

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def chat_json(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 256,
    ) -> LLMResponse:
        if not self.api_key:
            return LLMResponse(
                ok=False,
                content="",
                parsed=None,
                model=self.model,
                usage=None,
                error="OPENAI_API_KEY not configured",
            )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            body = resp.json()
            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError("LLM response is not a JSON object")
            return LLMResponse(
                ok=True,
                content=content,
                parsed=parsed,
                model=self.model,
                usage=body.get("usage"),
            )
        except Exception as exc:
            return LLMResponse(
                ok=False,
                content="",
                parsed=None,
                model=self.model,
                usage=None,
                error=str(exc),
            )
