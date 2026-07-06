from openai import AsyncOpenAI

from app.config import settings
from app.db.models import ModelConfig
from app.services.ai.base import AIError, AIProvider, AIResult

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


class OpenAIProvider(AIProvider):
    async def generate(self, model: ModelConfig, prompt: str, max_output_tokens: int) -> AIResult:
        try:
            client = _get_client()
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
