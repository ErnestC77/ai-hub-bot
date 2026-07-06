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


class ImageProvider(AIProvider):
    """Генерация картинок. max_output_tokens не применим — игнорируется."""

    async def generate(self, model: ModelConfig, prompt: str, max_output_tokens: int) -> AIResult:
        try:
            client = _get_client(KeyPurpose(model.key_purpose))
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
