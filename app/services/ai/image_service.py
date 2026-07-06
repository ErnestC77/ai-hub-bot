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


class ImageProvider(AIProvider):
    """Генерация картинок. max_output_tokens не применим — игнорируется."""

    async def generate(self, model: ModelConfig, prompt: str, max_output_tokens: int) -> AIResult:
        try:
            client = _get_client()
            response = await client.images.generate(
                model=model.model_code,
                prompt=prompt,
                n=1,
                size="1024x1024",
                response_format="url",
            )
            url = response.data[0].url if response.data else None
            if not url:
                raise AIError("empty image response")
            return AIResult(answer=url, input_tokens=0, output_tokens=0)
        except AIError:
            raise
        except Exception as exc:
            raise AIError("Image API error") from exc
