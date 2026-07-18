import logging

from openai import AsyncOpenAI

from app.db.models import AiModel
from app.services.ai.base import AIError, AIProvider, AIResult
from app.services.keys.api_key_manager import get_key_manager
from app.services.keys.enums import KeyPurpose, Provider
from app.services.keys.exceptions import ApiKeyNotConfiguredError

logger = logging.getLogger(__name__)

# Текст идёт через fal LLM router (OpenAI-совместимый, синхронный), а НЕ через
# прямой openrouter.ai: fal проксирует те же модели OpenRouter со своих не-РФ
# серверов, поэтому доступен из РФ (прямой OpenRouter Cloudflare режет по гео).
# provider_model_id остаются в openrouter-формате (deepseek/deepseek-chat,
# anthropic/claude-opus-4.8, ...) -- router понимает их as-is.
FAL_ROUTER_BASE_URL = "https://fal.run/openrouter/router/openai/v1"

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


def _fal_text_key() -> str:
    """Ключ fal для текста: FAL_TEXT_KEY, а при его отсутствии -- FAL_IMAGE_KEY
    (тот же fal-аккаунт). Отдельный ключ нужен лишь для раздельного учёта трат."""
    km = get_key_manager()
    try:
        return km.get_key(Provider.FAL, KeyPurpose.TEXT)
    except ApiKeyNotConfiguredError:
        return km.get_key(Provider.FAL, KeyPurpose.IMAGE)


def _get_client() -> AsyncOpenAI:
    key = _fal_text_key()
    client = _clients.get(key)
    if client is None:
        client = AsyncOpenAI(
            # api_key обязателен конструктору, но fal ждёт схему "Key <...>", а не
            # "Bearer", поэтому реальную авторизацию задаём через default_headers.
            api_key=key,
            base_url=FAL_ROUTER_BASE_URL,
            timeout=OPENROUTER_TIMEOUT_SECONDS,
            default_headers={"Authorization": f"Key {key}"},
        )
        _clients[key] = client
    return client


class OpenRouterProvider(AIProvider):
    """Текстовый провайдер: OpenAI-совместимый chat-completions через fal LLM
    router (fal.run/openrouter/router). Единственный текстовый провайдер."""

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
            logger.exception("fal LLM router request failed for model %s", model.code)
            raise AIError("fal LLM router error") from exc
