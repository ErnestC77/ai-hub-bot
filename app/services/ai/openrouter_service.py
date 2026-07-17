import logging

from openai import AsyncOpenAI

from app.db.models import AiModel
from app.services.ai.base import AIError, AIProvider, AIResult
from app.services.keys.api_key_manager import get_key_manager
from app.services.keys.enums import KeyPurpose, Provider

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Системный промпт: без него модель без языкового контекста угадывает язык по
# вводу, и на неоднозначном (голые цифры «133», символы) DeepSeek -- китайская
# модель -- сваливалась в китайский. Приложение русскоязычное, поэтому по
# умолчанию отвечаем на русском, но следуем языку осмысленного вопроса.
SYSTEM_PROMPT = (
    "Ты — полезный ИИ-ассистент в русскоязычном приложении. Отвечай на том же "
    "языке, на котором задан вопрос. Если язык определить нельзя (только цифры, "
    "символы или очень короткий ввод) — отвечай на русском языке."
)

# Явный таймаут < TTL per-user лока (AI_LOCK_TTL_SECONDS=120 в
# text_generation_service). Дефолт AsyncOpenAI -- 600с: запрос мог пережить лок,
# тот истекал по TTL, второй запрос брал новый лок, а finally первого удалял
# ЧУЖОЙ лок -> single-flight ломался (аудит I3). С таймаутом запрос не переживёт лок.
OPENROUTER_TIMEOUT_SECONDS = 110.0

_clients: dict[str, AsyncOpenAI] = {}


def _get_client() -> AsyncOpenAI:
    api_key = get_key_manager().get_key(Provider.OPENROUTER, KeyPurpose.TEXT)
    client = _clients.get(api_key)
    if client is None:
        client = AsyncOpenAI(
            api_key=api_key, base_url=OPENROUTER_BASE_URL, timeout=OPENROUTER_TIMEOUT_SECONDS
        )
        _clients[api_key] = client
    return client


class OpenRouterProvider(AIProvider):
    """OpenRouter даёт OpenAI-совместимый chat-completions API (тот же паттерн,
    что был у DeepSeekProvider). Единственный текстовый провайдер с фазы 2."""

    async def generate(
        self, model: AiModel, prompt: str, max_output_tokens: int, extra: dict | None = None
    ) -> AIResult:
        try:
            client = _get_client()
            response = await client.chat.completions.create(
                model=model.provider_model_id,
                max_tokens=max_output_tokens,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            return AIResult(
                answer=response.choices[0].message.content or "",
                input_tokens=response.usage.prompt_tokens if response.usage else 0,
                output_tokens=response.usage.completion_tokens if response.usage else 0,
            )
        except Exception as exc:
            # Реальная причина -- только в лог; пользователю уходит нейтральный текст.
            logger.exception("OpenRouter request failed for model %s", model.code)
            raise AIError("OpenRouter API error") from exc
