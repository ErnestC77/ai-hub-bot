from collections.abc import Callable

from app.db.enums import ModelProvider
from app.services.ai.base import AIProvider
from app.services.ai.claude_service import ClaudeProvider
from app.services.ai.deepseek_service import DeepSeekProvider
from app.services.ai.gemini_service import GeminiProvider
from app.services.ai.image_service import ImageProvider
from app.services.ai.openai_service import OpenAIProvider

# Текстовые модели — ключ по provider (fast/medium/premium категории).
TEXT_PROVIDERS: dict[ModelProvider, Callable[[], AIProvider]] = {
    ModelProvider.anthropic: ClaudeProvider,
    ModelProvider.openai: OpenAIProvider,
    ModelProvider.google: GeminiProvider,
    ModelProvider.deepseek: DeepSeekProvider,
}

# Генерация картинок — отдельный реестр: у одного provider (например openai)
# может быть и чат-модель, и image-модель одновременно.
IMAGE_PROVIDERS: dict[ModelProvider, Callable[[], AIProvider]] = {
    ModelProvider.openai: ImageProvider,
}
