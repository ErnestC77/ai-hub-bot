import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import CostUnit, ModelCategory, ModelOptionKind, ModelProvider, ModelTier
from app.db.models import AiModel, Banner, CreditPackage, ModelOption, Setting
from app.db.session import get_session

SETTINGS_ROWS = [
    dict(key="usd_to_rub_rate", value="80", type="float",
         description="Внутренний курс USD→RUB (с запасом; редактируется админкой, фаза 5)"),
    dict(key="rub_per_credit", value="0.10", type="float",
         description="Номинальная стоимость 1 кредита в рублях"),
    dict(key="provider_fee_multiplier", value="1.15", type="float",
         description="Надбавка за комиссии OpenRouter/fal.ai поверх API-цены"),
    dict(key="margin_multiplier", value="1.428571", type="float",
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
    # --- referral bonus (фаза 6) ---
    dict(key="referral_bonus_referrer_credits", value="20", type="int",
         description="Бонус пригласившему за друга, сделавшего первый запрос"),
    dict(key="referral_bonus_referred_credits", value="20", type="int",
         description="Бонус приглашённому после его первого запроса"),
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
    # --- IMAGE (fal.ai), 4 модели ---
    dict(**_MEDIA, category=ModelCategory.image, code="qwen_image", display_name="Qwen Image",
         tier=ModelTier.economy, cost_unit=CostUnit.megapixel,
         provider_model_id="fal-ai/qwen-image",
         min_credits=29, recommended_credits=29, sort_order=130),
    # v3 депрецирован fal; 2K/4K (image_size=auto_2K/auto_4K) есть только у v4.
    dict(**_MEDIA, category=ModelCategory.image, code="seedream", display_name="Seedream",
         tier=ModelTier.standard, cost_unit=CostUnit.image,
         provider_model_id="fal-ai/bytedance/seedream/v4/text-to-image",
         min_credits=43, recommended_credits=43, sort_order=140),
    # Голый fal-ai/flux-pro/kontext -- это image-to-image, у него image_url обязателен
    # (required: ["prompt","image_url"]). Для text-to-image нужен отдельный маршрут.
    dict(**_MEDIA, category=ModelCategory.image, code="flux_kontext_pro", display_name="Flux Kontext Pro",
         tier=ModelTier.premium, cost_unit=CostUnit.image,
         provider_model_id="fal-ai/flux-pro/kontext/text-to-image",
         provider_model_id_edit="fal-ai/flux-pro/kontext",
         min_credits=58, recommended_credits=58, sort_order=150),
    dict(**_MEDIA, category=ModelCategory.image, code="nano_banana", display_name="Nano Banana",
         tier=ModelTier.premium, cost_unit=CostUnit.image,
         provider_model_id="fal-ai/nano-banana",
         provider_model_id_edit="fal-ai/nano-banana/edit",
         min_credits=58, recommended_credits=58, sort_order=160),
    # Gemini 3 Pro Image. Единственная модель каталога с настоящим селектором
    # 1K/2K/4K (resolution в схеме) -- тем самым, что рисовал дизайн-макет.
    # Измерено 2026-07-15: 1K=$0.15, 2K=$0.15 (бесплатно!), 4K=$0.30.
    # $0.15 * 1314 = 198 (было 345 при факторе 2300 / марже 2.5).
    dict(**_MEDIA, category=ModelCategory.image, code="nano_banana_pro",
         display_name="Nano Banana Pro", tier=ModelTier.pro, cost_unit=CostUnit.image,
         provider_model_id="fal-ai/nano-banana-pro",
         provider_model_id_edit="fal-ai/nano-banana-pro/edit",
         min_credits=198, recommended_credits=198, sort_order=165),
    # --- VIDEO (fal.ai), 4 модели (recommended_credits -- цена за дефолтную комбинацию модели) ---
    dict(**_MEDIA, category=ModelCategory.video, code="ovi_video", display_name="Ovi Video",
         tier=ModelTier.economy, cost_unit=CostUnit.video,
         provider_model_id="fal-ai/ovi",
         min_credits=286, recommended_credits=286, sort_order=170),
    # Приложение -- fal-ai/wan, а v2.2-a14b/text-to-video -- маршрут внутри него.
    # Заявленный ранее fal-ai/wan/v2.2 очередь принимает, но воркер отдаёт
    # {"detail":"Path /v2.2 not found"} -- уже после резервирования кредитов.
    dict(**_MEDIA, category=ModelCategory.video, code="wan_video", display_name="Wan Video",
         tier=ModelTier.standard, cost_unit=CostUnit.second,
         provider_model_id="fal-ai/wan/v2.2-a14b/text-to-video",
         # $0.08/с * 5.0625с (81 кадр / 16 fps) = $0.405 * 1314 -> 533; пол = 480p ($0.2025 -> 267)
         min_credits=267, recommended_credits=533, sort_order=180),
    # Аналогично: приложение fal-ai/kling-video, маршрут v2/master/text-to-video.
    dict(**_MEDIA, category=ModelCategory.video, code="kling_video", display_name="Kling Video",
         tier=ModelTier.premium, cost_unit=CostUnit.second,
         provider_model_id="fal-ai/kling-video/v2/master/text-to-video",
         # $1.40 за 5с (измерено списанием) * 1314 -> 1840 (было 3220 при факторе 2300).
         min_credits=1840, recommended_credits=1840, sort_order=190),
    # veo3 депрецирован; resolution=4k есть только у veo3.1.
    dict(**_MEDIA, category=ModelCategory.video, code="veo_video", display_name="Veo Video",
         tier=ModelTier.ultra, cost_unit=CostUnit.second,
         provider_model_id="fal-ai/veo3.1",
         # дефолт 8с со звуком: $0.40/с * 8 = $3.20 * 1314 -> 4206.
         # пол: 4с без звука $0.20/с * 4 = $0.80 -> 1052.
         min_credits=1052, recommended_credits=4206, sort_order=200),
]

# Опции моделей. Каждый множитель ВЫВЕДЕН из замера живого fal 2026-07-15
# (списание с баланса), а не назначен -- см. спек, раздел «Цены».
# provider_params сверены со схемами fal: типы значений обязаны совпадать
# (Kling ждёт duration строкой, Wan -- num_frames числом).
MODEL_OPTIONS = [
    # --- Wan: две независимые оси качества (resolution + video_quality) ---
    # 480p $0.04/с, 580p $0.06/с, 720p $0.08/с -> 0.5 / 0.75 / 1.0
    dict(model_code="wan_video", kind=ModelOptionKind.quality, code="480p", label="480p",
         provider_params={"resolution": "480p", "video_quality": "high"},
         credits_multiplier=0.5, is_default=False, sort_order=10),
    dict(model_code="wan_video", kind=ModelOptionKind.quality, code="580p", label="580p",
         provider_params={"resolution": "580p", "video_quality": "high"},
         credits_multiplier=0.75, is_default=False, sort_order=20),
    dict(model_code="wan_video", kind=ModelOptionKind.quality, code="720p", label="720p",
         # video_quality оставлен на дефолте fal "high" -- эффект этого параметра
         # на цену НЕ замерялся (замер варьировал только resolution), поэтому
         # менять его на "maximum" нельзя без отдельного замера.
         provider_params={"resolution": "720p", "video_quality": "high"},
         credits_multiplier=1.0, is_default=True, sort_order=30),
    # У Wan поля duration нет: длина = num_frames / frames_per_second.
    # 81/16 = 5.0625с (дефолт модели), 161/16 = 10.0625с -> 10.0625/5.0625 = 1.988.
    dict(model_code="wan_video", kind=ModelOptionKind.duration, code="5s", label="5 сек",
         provider_params={"num_frames": 81, "frames_per_second": 16},
         credits_multiplier=1.0, is_default=True, sort_order=10),
    dict(model_code="wan_video", kind=ModelOptionKind.duration, code="10s", label="10 сек",
         provider_params={"num_frames": 161, "frames_per_second": 16},
         credits_multiplier=1.988, is_default=False, sort_order=20),
    # --- Kling: duration СТРОКОЙ, размером управлять нельзя (только aspect_ratio) ---
    # $1.40 за 5с, $2.80 за 10с -> 2.0 (нелинейно по секундам: $1.40 + $0.28/с,
    # формулой не выражается -- ровно поэтому множитель, а не расчёт).
    dict(model_code="kling_video", kind=ModelOptionKind.duration, code="5s", label="5 сек",
         provider_params={"duration": "5"},
         credits_multiplier=1.0, is_default=True, sort_order=10),
    dict(model_code="kling_video", kind=ModelOptionKind.duration, code="10s", label="10 сек",
         provider_params={"duration": "10"},
         credits_multiplier=2.0, is_default=False, sort_order=20),
    # --- Veo: duration строкой с суффиксом; звук удваивает цену ---
    # $0.40/с со звуком, $0.20/с без (оба измерены) -> off = 0.5.
    dict(model_code="veo_video", kind=ModelOptionKind.duration, code="4s", label="4 сек",
         provider_params={"duration": "4s"},
         credits_multiplier=0.5, is_default=False, sort_order=10),
    dict(model_code="veo_video", kind=ModelOptionKind.duration, code="6s", label="6 сек",
         provider_params={"duration": "6s"},
         credits_multiplier=0.75, is_default=False, sort_order=20),
    dict(model_code="veo_video", kind=ModelOptionKind.duration, code="8s", label="8 сек",
         provider_params={"duration": "8s"},
         credits_multiplier=1.0, is_default=True, sort_order=30),
    dict(model_code="veo_video", kind=ModelOptionKind.audio, code="on", label="Со звуком",
         provider_params={"generate_audio": True},
         credits_multiplier=1.0, is_default=True, sort_order=10),
    dict(model_code="veo_video", kind=ModelOptionKind.audio, code="off", label="Без звука",
         provider_params={"generate_audio": False},
         credits_multiplier=0.5, is_default=False, sort_order=20),
    # Разрешение Veo измерено (3 генерации 4с без звука): 720p $0.80, 1080p $0.80, 4k $1.60.
    # 1080p БЕСПЛАТЕН -- стоит ровно как 720p. Дорожает только 4K, ровно вдвое.
    dict(model_code="veo_video", kind=ModelOptionKind.quality, code="720p", label="720p",
         provider_params={"resolution": "720p"},
         credits_multiplier=1.0, is_default=True, sort_order=10),
    dict(model_code="veo_video", kind=ModelOptionKind.quality, code="1080p", label="1080p",
         provider_params={"resolution": "1080p"},
         credits_multiplier=1.0, is_default=False, sort_order=20),
    dict(model_code="veo_video", kind=ModelOptionKind.quality, code="4k", label="4K",
         provider_params={"resolution": "4k"},
         credits_multiplier=2.0, is_default=False, sort_order=30),
    # --- qwen_image: image_size пресетом или объектом ---
    # $0.02/МП. square_hd = 1024^2 = 1.05 МП (дефолт), 2048^2 = 4.19 МП -> 4.0.
    dict(model_code="qwen_image", kind=ModelOptionKind.quality, code="1k", label="1K",
         provider_params={"image_size": "square_hd"},
         credits_multiplier=1.0, is_default=True, sort_order=10),
    dict(model_code="qwen_image", kind=ModelOptionKind.quality, code="2k", label="2K",
         provider_params={"image_size": {"width": 2048, "height": 2048}},
         credits_multiplier=4.0, is_default=False, sort_order=20),
    # --- seedream v4: разрешение бесплатно ---
    # Измерено: square_hd, auto_2K и auto_4K списали ровно $0.09 на троих, т.е.
    # $0.03 за картинку независимо от разрешения (cost_unit=image -- плоский тариф).
    # Множители 1.0: 2K и 4K достаются пользователю даром.
    dict(model_code="seedream", kind=ModelOptionKind.quality, code="1k", label="1K",
         provider_params={"image_size": "square_hd"},
         credits_multiplier=1.0, is_default=True, sort_order=10),
    dict(model_code="seedream", kind=ModelOptionKind.quality, code="2k", label="2K",
         provider_params={"image_size": "auto_2K"},
         credits_multiplier=1.0, is_default=False, sort_order=20),
    dict(model_code="seedream", kind=ModelOptionKind.quality, code="4k", label="4K",
         provider_params={"image_size": "auto_4K"},
         credits_multiplier=1.0, is_default=False, sort_order=30),
    # --- nano_banana_pro: тот самый селектор 1K/2K/4K из дизайн-макета ---
    # Измерено: 1K $0.15, 2K $0.15, 4K $0.30. 2K БЕСПЛАТЕН -- ровно как 1K;
    # дорожает только 4K, вдвое. Тот же узор, что у Veo (720p = 1080p < 4k x2).
    # Здравый смысл сказал бы 1/2/4 -- и мы брали бы вдвое лишнего за 2K.
    dict(model_code="nano_banana_pro", kind=ModelOptionKind.quality, code="1k", label="1K",
         provider_params={"resolution": "1K"},
         credits_multiplier=1.0, is_default=True, sort_order=10),
    dict(model_code="nano_banana_pro", kind=ModelOptionKind.quality, code="2k", label="2K",
         provider_params={"resolution": "2K"},
         credits_multiplier=1.0, is_default=False, sort_order=20),
    dict(model_code="nano_banana_pro", kind=ModelOptionKind.quality, code="4k", label="4K",
         provider_params={"resolution": "4K"},
         credits_multiplier=2.0, is_default=False, sort_order=30),
    # НЕ заведены намеренно:
    #  - ovi: цена плоская ($0.20/видео), но влияние resolution не мерили; длительность
    #    не управляется вовсе (в схеме нет ни duration, ни num_frames);
    #  - flux_kontext_pro, nano_banana (обычная), kling quality: у провайдера НЕТ ручки
    #    размера, только aspect_ratio.
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

    # Опции вставляем после моделей: model_id известен только после их flush.
    await session.flush()
    model_ids = {
        row[0]: row[1]
        for row in (await session.execute(select(AiModel.code, AiModel.id))).all()
    }
    existing_options = {
        (row[0], row[1], row[2])
        for row in (
            await session.execute(
                select(ModelOption.model_id, ModelOption.kind, ModelOption.code)
            )
        ).all()
    }
    for data in MODEL_OPTIONS:
        model_id = model_ids.get(data["model_code"])
        if model_id is None:
            continue  # модель скрыта/удалена -- опции ей не нужны
        key = (model_id, data["kind"], data["code"])
        if key in existing_options:
            continue
        payload = {k: v for k, v in data.items() if k != "model_code"}
        session.add(ModelOption(model_id=model_id, **payload))

    await session.commit()


async def seed() -> None:
    async with get_session() as session:
        await apply_seed(session)


if __name__ == "__main__":
    asyncio.run(seed())
