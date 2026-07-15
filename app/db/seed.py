import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import CostUnit, ModelCategory, ModelProvider, ModelTier
from app.db.models import AiModel, Banner, CreditPackage, Setting
from app.db.session import get_session

SETTINGS_ROWS = [
    dict(key="usd_to_rub_rate", value="80", type="float",
         description="Внутренний курс USD→RUB (с запасом; редактируется админкой, фаза 5)"),
    dict(key="rub_per_credit", value="0.10", type="float",
         description="Номинальная стоимость 1 кредита в рублях"),
    dict(key="provider_fee_multiplier", value="1.15", type="float",
         description="Надбавка за комиссии OpenRouter/fal.ai поверх API-цены"),
    dict(key="margin_multiplier", value="2.5", type="float",
         description="Множитель целевой маржи"),
    dict(key="minimum_text_credits", value="3", type="int",
         description="Минимальное списание за любой текстовый запрос"),
    # --- antifraud (фаза 5) ---
    dict(key="daily_spend_limit_credits", value="10000", type="int",
         description="Дневной лимит трат на пользователя"),
    dict(key="rate_limit_per_user_per_minute", value="10", type="int",
         description="Rate limit запросов на пользователя"),
    dict(key="rate_limit_per_model_per_minute", value="60", type="int",
         description="Rate limit запросов на модель (глобально)"),
    dict(key="duplicate_cooldown_seconds", value="5", type="int",
         description="Окно блокировки повторного идентичного запроса"),
    dict(key="free_tier_credit_cap", value="100", type="int",
         description="Максимум бесплатных кредитов для непокупавших пользователей"),
]

CREDIT_PACKAGES = [
    dict(code="start", title="START", credits=1000, price_rub=149, price_stars=75,
         description="Для знакомства с ботом"),
    dict(code="basic", title="BASIC", credits=5000, price_rub=599, price_stars=300,
         description="Для обычного использования"),
    dict(code="plus", title="PLUS", credits=12000, price_rub=1290, price_stars=645,
         description="Для активной работы с текстом и изображениями"),
    dict(code="pro", title="PRO", credits=30000, price_rub=2990, price_stars=1495,
         description="Для частой генерации изображений и видео"),
    dict(code="business", title="BUSINESS", credits=70000, price_rub=5990, price_stars=2995,
         description="Для агентств и heavy users"),
]

# provider_model_id медиа-моделей проверены по схемам fal 2026-07-15 (см. спек
# docs/superpowers/specs/2026-07-15-generation-quality-design.md).
# Текстовые (OpenRouter) -- ВСЁ ЕЩЁ ПЛЕЙСХОЛДЕРЫ, не проверялись; цены = 0,
# поэтому списание текста идёт по min_credits (защитный минимум).
_TEXT = dict(provider=ModelProvider.openrouter, category=ModelCategory.text, cost_unit=CostUnit.tokens,
             input_price_usd_per_1m_tokens=0, output_price_usd_per_1m_tokens=0, fixed_cost_usd=0,
             max_context_tokens=128000, is_active=True, is_visible=True)
_MEDIA = dict(provider=ModelProvider.fal, input_price_usd_per_1m_tokens=0, output_price_usd_per_1m_tokens=0,
              fixed_cost_usd=0, max_context_tokens=4000, is_active=True, is_visible=True)

AI_MODELS = [
    # --- TEXT (OpenRouter), 12 моделей из ТЗ ---
    dict(**_TEXT, code="deepseek_v3", display_name="DeepSeek V3", tier=ModelTier.economy,
         provider_model_id="deepseek/deepseek-chat",  # PLACEHOLDER
         min_credits=3, recommended_credits=3, sort_order=10),
    dict(**_TEXT, code="llama_3_1_8b", display_name="Llama 3.1 8B", tier=ModelTier.economy,
         provider_model_id="meta-llama/llama-3.1-8b-instruct",  # PLACEHOLDER
         min_credits=3, recommended_credits=3, sort_order=20),
    dict(**_TEXT, code="qwen_plus", display_name="Qwen Plus", tier=ModelTier.economy,
         provider_model_id="qwen/qwen-plus",  # PLACEHOLDER
         min_credits=3, recommended_credits=6, sort_order=30),
    dict(**_TEXT, code="mistral_large", display_name="Mistral Large", tier=ModelTier.economy,
         provider_model_id="mistralai/mistral-large",  # PLACEHOLDER
         min_credits=3, recommended_credits=6, sort_order=40),
    dict(**_TEXT, code="gpt_mini", display_name="GPT Mini", tier=ModelTier.standard,
         provider_model_id="openai/gpt-4o-mini",  # PLACEHOLDER
         min_credits=5, recommended_credits=6, sort_order=50),
    dict(**_TEXT, code="qwen_max", display_name="Qwen Max", tier=ModelTier.standard,
         provider_model_id="qwen/qwen-max",  # PLACEHOLDER
         min_credits=10, recommended_credits=15, sort_order=60),
    dict(**_TEXT, code="grok", display_name="Grok", tier=ModelTier.standard,
         provider_model_id="x-ai/grok-2",  # PLACEHOLDER
         min_credits=10, recommended_credits=15, sort_order=70),
    dict(**_TEXT, code="gpt_premium", display_name="GPT Premium", tier=ModelTier.premium,
         provider_model_id="openai/gpt-4o",  # PLACEHOLDER
         min_credits=20, recommended_credits=30, sort_order=80,
         fallback_model_code="gemini_flash"),
    dict(**_TEXT, code="gemini_flash", display_name="Gemini Flash", tier=ModelTier.premium,
         provider_model_id="google/gemini-flash-1.5",  # PLACEHOLDER
         min_credits=20, recommended_credits=30, sort_order=90),
    dict(**_TEXT, code="gemini_pro", display_name="Gemini Pro", tier=ModelTier.premium,
         provider_model_id="google/gemini-pro-1.5",  # PLACEHOLDER
         min_credits=30, recommended_credits=40, sort_order=100),
    dict(**_TEXT, code="claude_sonnet", display_name="Claude Sonnet", tier=ModelTier.pro,
         provider_model_id="anthropic/claude-3.5-sonnet",  # PLACEHOLDER
         min_credits=40, recommended_credits=50, sort_order=110),
    dict(**_TEXT, code="claude_opus", display_name="Claude Opus", tier=ModelTier.ultra,
         provider_model_id="anthropic/claude-3-opus",  # PLACEHOLDER
         min_credits=70, recommended_credits=90, sort_order=120,
         fallback_model_code="claude_sonnet"),
    # --- IMAGE (fal.ai), 4 модели из ТЗ ---
    dict(**_MEDIA, category=ModelCategory.image, code="qwen_image", display_name="Qwen Image",
         tier=ModelTier.economy, cost_unit=CostUnit.megapixel,
         provider_model_id="fal-ai/qwen-image",
         min_credits=50, recommended_credits=50, sort_order=130),
    # v3 депрецирован fal; 2K/4K (image_size=auto_2K/auto_4K) есть только у v4.
    dict(**_MEDIA, category=ModelCategory.image, code="seedream", display_name="Seedream",
         tier=ModelTier.standard, cost_unit=CostUnit.image,
         provider_model_id="fal-ai/bytedance/seedream/v4/text-to-image",
         min_credits=75, recommended_credits=75, sort_order=140),
    # Голый fal-ai/flux-pro/kontext -- это image-to-image, у него image_url обязателен
    # (required: ["prompt","image_url"]). Для text-to-image нужен отдельный маршрут.
    dict(**_MEDIA, category=ModelCategory.image, code="flux_kontext_pro", display_name="Flux Kontext Pro",
         tier=ModelTier.premium, cost_unit=CostUnit.image,
         provider_model_id="fal-ai/flux-pro/kontext/text-to-image",
         provider_model_id_edit="fal-ai/flux-pro/kontext",
         min_credits=100, recommended_credits=100, sort_order=150),
    dict(**_MEDIA, category=ModelCategory.image, code="nano_banana", display_name="Nano Banana",
         tier=ModelTier.premium, cost_unit=CostUnit.image,
         provider_model_id="fal-ai/nano-banana",
         provider_model_id_edit="fal-ai/nano-banana/edit",
         min_credits=100, recommended_credits=100, sort_order=160),
    # --- VIDEO (fal.ai), 4 модели из ТЗ (recommended_credits -- цена за 5 секунд) ---
    dict(**_MEDIA, category=ModelCategory.video, code="ovi_video", display_name="Ovi Video",
         tier=ModelTier.economy, cost_unit=CostUnit.video,
         provider_model_id="fal-ai/ovi",
         min_credits=500, recommended_credits=500, sort_order=170),
    # Приложение -- fal-ai/wan, а v2.2-a14b/text-to-video -- маршрут внутри него.
    # Заявленный ранее fal-ai/wan/v2.2 очередь принимает, но воркер отдаёт
    # {"detail":"Path /v2.2 not found"} -- уже после резервирования кредитов.
    dict(**_MEDIA, category=ModelCategory.video, code="wan_video", display_name="Wan Video",
         tier=ModelTier.standard, cost_unit=CostUnit.second,
         provider_model_id="fal-ai/wan/v2.2-a14b/text-to-video",
         # $0.08/с * 5.0625с (81 кадр / 16 fps) = $0.405 -> 932; пол = 480p ($0.2025 -> 466)
         min_credits=466, recommended_credits=932, sort_order=180),
    # Аналогично: приложение fal-ai/kling-video, маршрут v2/master/text-to-video.
    dict(**_MEDIA, category=ModelCategory.video, code="kling_video", display_name="Kling Video",
         tier=ModelTier.premium, cost_unit=CostUnit.second,
         provider_model_id="fal-ai/kling-video/v2/master/text-to-video",
         # $1.40 за 5с (измерено списанием) -> 3220. Было 850 = продажа в минус.
         min_credits=3220, recommended_credits=3220, sort_order=190),
    # veo3 депрецирован; resolution=4k есть только у veo3.1.
    dict(**_MEDIA, category=ModelCategory.video, code="veo_video", display_name="Veo Video",
         tier=ModelTier.ultra, cost_unit=CostUnit.second,
         provider_model_id="fal-ai/veo3.1",
         # дефолт 8с со звуком: $0.40/с * 8 = $3.20 -> 7360.
         # пол: 4с без звука $0.20/с * 4 = $0.80 -> 1840.
         min_credits=1840, recommended_credits=7360, sort_order=200),
]

# Banner-сиды переносятся как есть (не относятся к кредитной системе).
BANNERS = [
    dict(
        title="ChatGPT, Claude и Gemini в одном чате",
        subtitle="Переключайтесь между моделями одним тапом",
        badge_text="Новое",
        cta_text="Попробовать",
        image_url="https://picsum.photos/seed/ai-hub-banner-1/800/450",
        action_type="prompt",
        action_value="Расскажи, что ты умеешь и чем можешь помочь",
        sort_order=0,
    ),
    dict(
        title="Генерация изображений",
        subtitle="Опишите идею словами — получите картинку",
        badge_text="Popular",
        cta_text="Создать картинку",
        image_url="https://picsum.photos/seed/ai-hub-banner-2/800/450",
        action_type="prompt",
        action_value="Сгенерируй изображение: ",
        sort_order=1,
    ),
    dict(
        title="Кредиты поверх тарифа",
        subtitle="Докупайте запросы, когда лимит закончился",
        badge_text=None,
        cta_text="Подробнее",
        image_url="https://picsum.photos/seed/ai-hub-banner-3/800/450",
        action_type="prompt",
        action_value="Как работают кредиты в этом боте?",
        sort_order=2,
    ),
]


async def apply_seed(session: AsyncSession) -> None:
    """Идемпотентный сид: вставляет только отсутствующие строки (по естественному ключу)."""
    existing_settings = {row[0] for row in (await session.execute(select(Setting.key))).all()}
    for data in SETTINGS_ROWS:
        if data["key"] not in existing_settings:
            session.add(Setting(**data))

    existing_packages = {row[0] for row in (await session.execute(select(CreditPackage.code))).all()}
    for data in CREDIT_PACKAGES:
        if data["code"] not in existing_packages:
            session.add(CreditPackage(**data))

    existing_models = {row[0] for row in (await session.execute(select(AiModel.code))).all()}
    for data in AI_MODELS:
        if data["code"] not in existing_models:
            session.add(AiModel(**data))

    existing_banner_titles = {row[0] for row in (await session.execute(select(Banner.title))).all()}
    for data in BANNERS:
        if data["title"] not in existing_banner_titles:
            session.add(Banner(**data))

    await session.commit()


async def seed() -> None:
    async with get_session() as session:
        await apply_seed(session)


if __name__ == "__main__":
    asyncio.run(seed())
