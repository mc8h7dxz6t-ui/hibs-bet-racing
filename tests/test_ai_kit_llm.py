"""AI Kit LLM client tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ai_kit.llm import OpenAICompatibleClient


def test_llm_not_configured_without_key():
    client = OpenAICompatibleClient(api_key="")
    assert not client.configured
    resp = client.chat_json(system="s", user="u")
    assert not resp.ok
    assert "OPENAI_API_KEY" in (resp.error or "")


def test_llm_chat_json_parses_response():
    client = OpenAICompatibleClient(api_key="test-key")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": '{"ok": true, "summary": "ready"}'}}],
        "usage": {"total_tokens": 12},
    }
    with patch("ai_kit.llm.httpx.post", return_value=mock_resp):
        resp = client.chat_json(system="sys", user="hi", max_tokens=50)
    assert resp.ok
    assert resp.parsed == {"ok": True, "summary": "ready"}
