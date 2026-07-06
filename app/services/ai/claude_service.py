from anthropic import AsyncAnthropic

from app.config import settings
from app.db.models import ModelConfig
from app.services.ai.base import AIError, AIProvider, AIResult

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


class ClaudeProvider(AIProvider):
    async def generate(self, model: ModelConfig, prompt: str, max_output_tokens: int) -> AIResult:
        try:
            client = _get_client()
            response = await client.messages.create(
                model=model.model_code,
                max_tokens=max_output_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            answer = "".join(block.text for block in response.content if block.type == "text")
            return AIResult(
                answer=answer,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
        except Exception as exc:
            # Границa с внешним SDK: конфигурация ключа, сетевые сбои, неожиданный формат
            # ответа — всё это не должно долетать до пользователя как есть (раздел 24 ТЗ).
            raise AIError("Claude API error") from exc
