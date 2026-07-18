import json
import os

os.environ.setdefault("BOT_TOKEN", "123456:TEST-token")
os.environ.setdefault("DATABASE_URL", "postgresql://test")

import httpx
import pytest
import respx

from app.db.enums import CostUnit, ModelCategory, ModelProvider, ModelTier
from app.db.models import AiModel
from app.services.ai import openrouter_service
from app.services.ai.base import AIError
from app.services.ai.openrouter_service import OpenRouterProvider

COMPLETIONS_URL = "https://fal.run/openrouter/router/openai/v1/chat/completions"


class _FakeKeyManager:
    def get_key(self, provider, purpose):
        return "fal-key-test"


@pytest.fixture(autouse=True)
def fake_key_manager(monkeypatch):
    monkeypatch.setattr(openrouter_service, "get_key_manager", lambda: _FakeKeyManager())
    openrouter_service._clients.clear()
    yield
    openrouter_service._clients.clear()


def _text_model() -> AiModel:
    return AiModel(
        provider=ModelProvider.openrouter, category=ModelCategory.text,
        code="deepseek_v3", display_name="DeepSeek V3",
        provider_model_id="deepseek/deepseek-chat", tier=ModelTier.economy,
        cost_unit=CostUnit.tokens, min_credits=3, recommended_credits=3,
    )


@respx.mock
async def test_generate_success_returns_answer_and_usage():
    route = respx.post(COMPLETIONS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "gen-1",
                "object": "chat.completion",
                "created": 1720000000,
                "model": "deepseek/deepseek-chat",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Привет!"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 34, "total_tokens": 46},
            },
        )
    )

    result = await OpenRouterProvider().generate(_text_model(), "hi", 1000)

    assert result.answer == "Привет!"
    assert result.input_tokens == 12
    assert result.output_tokens == 34

    request = route.calls.last.request
    # fal-схема авторизации: "Key <...>", а не "Bearer".
    assert request.headers["authorization"] == "Key fal-key-test"
    body = json.loads(request.content)
    assert body["model"] == "deepseek/deepseek-chat"  # provider_model_id, НЕ model.code
    assert body["max_tokens"] == 1000
    # Системный промпт (язык ответа) идёт первым, затем вопрос пользователя.
    assert body["messages"][0]["role"] == "system"
    assert "русск" in body["messages"][0]["content"].lower()
    assert body["messages"][1] == {"role": "user", "content": "hi"}


@respx.mock
async def test_generate_wraps_http_error_as_aierror():
    # 400 не ретраится openai-SDK -- тест мгновенный.
    respx.post(COMPLETIONS_URL).mock(return_value=httpx.Response(400, json={"error": "bad"}))
    with pytest.raises(AIError):
        await OpenRouterProvider().generate(_text_model(), "hi", 1000)


@respx.mock
async def test_generate_wraps_timeout_as_aierror():
    # Таймауты SDK ретраит (max_retries=2 по умолчанию) -- тест занимает ~1-2 c.
    respx.post(COMPLETIONS_URL).mock(side_effect=httpx.TimeoutException("timed out"))
    with pytest.raises(AIError):
        await OpenRouterProvider().generate(_text_model(), "hi", 1000)
