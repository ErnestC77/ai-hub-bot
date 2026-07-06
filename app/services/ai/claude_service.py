from anthropic import AsyncAnthropic

from app.db.models import ModelConfig
from app.services.ai.base import AIError, AIProvider, AIResult
from app.services.keys.api_key_manager import get_key_manager
from app.services.keys.enums import KeyPurpose, Provider

_clients: dict[str, AsyncAnthropic] = {}


def _get_client(purpose: KeyPurpose) -> AsyncAnthropic:
    api_key = get_key_manager().get_key(Provider.ANTHROPIC, purpose)
    client = _clients.get(api_key)
    if client is None:
        client = AsyncAnthropic(api_key=api_key)
        _clients[api_key] = client
    return client


class ClaudeProvider(AIProvider):
    async def generate(self, model: ModelConfig, prompt: str, max_output_tokens: int) -> AIResult:
        try:
            client = _get_client(KeyPurpose(model.key_purpose))
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
