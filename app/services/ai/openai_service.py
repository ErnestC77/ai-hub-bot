from openai import AsyncOpenAI

from app.db.models import ModelConfig
from app.services.ai.base import AIError, AIProvider, AIResult
from app.services.keys.api_key_manager import get_key_manager
from app.services.keys.enums import KeyPurpose, Provider

_clients: dict[str, AsyncOpenAI] = {}


def _get_client(purpose: KeyPurpose) -> AsyncOpenAI:
    api_key = get_key_manager().get_key(Provider.OPENAI, purpose)
    client = _clients.get(api_key)
    if client is None:
        client = AsyncOpenAI(api_key=api_key)
        _clients[api_key] = client
    return client


class OpenAIProvider(AIProvider):
    async def generate(self, model: ModelConfig, prompt: str, max_output_tokens: int) -> AIResult:
        try:
            client = _get_client(KeyPurpose(model.key_purpose))
            response = await client.chat.completions.create(
                model=model.model_code,
                max_tokens=max_output_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return AIResult(
                answer=response.choices[0].message.content or "",
                input_tokens=response.usage.prompt_tokens if response.usage else 0,
                output_tokens=response.usage.completion_tokens if response.usage else 0,
            )
        except Exception as exc:
            raise AIError("OpenAI API error") from exc
