from google import genai
from google.genai import types

from app.db.models import ModelConfig
from app.services.ai.base import AIError, AIProvider, AIResult
from app.services.keys.api_key_manager import get_key_manager
from app.services.keys.enums import KeyPurpose, Provider

_clients: dict[str, genai.Client] = {}


def _get_client(purpose: KeyPurpose) -> genai.Client:
    api_key = get_key_manager().get_key(Provider.GEMINI, purpose)
    client = _clients.get(api_key)
    if client is None:
        client = genai.Client(api_key=api_key)
        _clients[api_key] = client
    return client


class GeminiProvider(AIProvider):
    async def generate(self, model: ModelConfig, prompt: str, max_output_tokens: int) -> AIResult:
        try:
            client = _get_client(KeyPurpose(model.key_purpose))
            response = await client.aio.models.generate_content(
                model=model.model_code,
                contents=prompt,
                config=types.GenerateContentConfig(max_output_tokens=max_output_tokens),
            )
            usage = response.usage_metadata
            return AIResult(
                answer=response.text or "",
                input_tokens=usage.prompt_token_count if usage else 0,
                output_tokens=usage.candidates_token_count if usage else 0,
            )
        except Exception as exc:
            raise AIError("Gemini API error") from exc
