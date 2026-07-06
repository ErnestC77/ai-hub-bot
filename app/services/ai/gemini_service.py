from google import genai
from google.genai import types

from app.config import settings
from app.db.models import ModelConfig
from app.services.ai.base import AIError, AIProvider, AIResult

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


class GeminiProvider(AIProvider):
    async def generate(self, model: ModelConfig, prompt: str, max_output_tokens: int) -> AIResult:
        try:
            client = _get_client()
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
