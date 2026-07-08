import asyncio

from sqlalchemy import select

from app.db.enums import ModelCategory, ModelProvider
from app.db.models import Banner, ModelConfig, Tariff
from app.db.session import get_session

TARIFFS = [
    dict(
        code="free", name="Free", description="5 бесплатных запросов, только fast-модели",
        price_rub=0, price_stars=0, period_days=36500,
        fast_limit=5, medium_limit=0, premium_limit=0, image_limit=0, daily_limit=5,
        max_input_tokens=2000, max_output_tokens=1000,
    ),
    dict(
        code="start", name="Start", description="220 fast-запросов",
        price_rub=299, price_stars=150, period_days=30,
        fast_limit=220, medium_limit=0, premium_limit=0, image_limit=0, daily_limit=30,
        max_input_tokens=4000, max_output_tokens=2000,
    ),
    dict(
        code="pro", name="Pro", description="700 fast, 200 medium, 30 premium",
        price_rub=990, price_stars=500, period_days=30,
        fast_limit=700, medium_limit=200, premium_limit=30, image_limit=0, daily_limit=60,
        max_input_tokens=8000, max_output_tokens=4000,
    ),
    dict(
        code="max", name="Max", description="1700 fast, 500 medium, 80 premium, 20 картинок",
        price_rub=2490, price_stars=1250, period_days=30,
        fast_limit=1700, medium_limit=500, premium_limit=80, image_limit=20, daily_limit=150,
        max_input_tokens=16000, max_output_tokens=8000,
    ),
]

MODEL_CONFIGS = [
    dict(model_code="gemini-2.0-flash-lite", provider=ModelProvider.google, display_name="Gemini Flash-Lite",
         category=ModelCategory.fast, key_purpose="text", cost_input_per_1m=0.075, cost_output_per_1m=0.30,
         credit_cost=1, is_active=True, is_premium=False, max_context_tokens=32000),
    dict(model_code="deepseek-chat", provider=ModelProvider.deepseek, display_name="DeepSeek Chat",
         category=ModelCategory.fast, key_purpose="text", cost_input_per_1m=0.14, cost_output_per_1m=0.28,
         credit_cost=1, is_active=True, is_premium=False, max_context_tokens=32000),
    dict(model_code="gpt-4o-mini", provider=ModelProvider.openai, display_name="ChatGPT mini",
         category=ModelCategory.medium, key_purpose="text", cost_input_per_1m=0.15, cost_output_per_1m=0.60,
         credit_cost=3, is_active=True, is_premium=False, max_context_tokens=64000),
    dict(model_code="claude-3-5-haiku-20241022", provider=ModelProvider.anthropic, display_name="Claude Haiku",
         category=ModelCategory.medium, key_purpose="text", cost_input_per_1m=0.80, cost_output_per_1m=4.00,
         credit_cost=3, is_active=True, is_premium=False, max_context_tokens=64000),
    dict(model_code="gpt-4o", provider=ModelProvider.openai, display_name="ChatGPT full",
         category=ModelCategory.premium, key_purpose="text", cost_input_per_1m=2.50, cost_output_per_1m=10.00,
         credit_cost=10, is_active=True, is_premium=True, max_context_tokens=128000),
    dict(model_code="claude-3-5-sonnet-20241022", provider=ModelProvider.anthropic, display_name="Claude Sonnet",
         category=ModelCategory.premium, key_purpose="premium", cost_input_per_1m=3.00, cost_output_per_1m=15.00,
         credit_cost=10, is_active=True, is_premium=True, max_context_tokens=128000),
    dict(model_code="dall-e-3", provider=ModelProvider.openai, display_name="Генерация картинок",
         category=ModelCategory.image, key_purpose="image", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=15, is_active=True, is_premium=True, max_context_tokens=4000),
    # --- PiAPI image models (30% margin, 77₽/$, floor 0.65₽/credit) ---
    dict(model_code="piapi-flux-dev", provider=ModelProvider.piapi, display_name="AI Photo Fast",
         category=ModelCategory.image, key_purpose="image", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=3, is_active=True, is_premium=False, max_context_tokens=4000,
         piapi_model="Qubico/flux1-dev", piapi_task_type="txt2img",
         piapi_extra_input={"width": 1024, "height": 1024}),
    # CONFIRMED verbatim: https://piapi.ai/docs/qwen-image-api/text-to-image (cross-checked
    # with two independent fetches, identical both times).
    dict(model_code="piapi-qwen-image", provider=ModelProvider.piapi, display_name="AI Photo Edit",
         category=ModelCategory.image, key_purpose="image", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=3, is_active=True, is_premium=False, max_context_tokens=4000,
         piapi_model="Qubico/qwen-image", piapi_task_type="txt2img",
         piapi_extra_input={}),
    # UNVERIFIED — confirm against a real PiAPI account/API call before enabling in production.
    # PiAPI's docs are ambiguous/inconsistent about how GPT Image 1.5 is invoked: one docs page
    # (https://piapi.ai/docs/gpt-image/gpt-image-api) describes a *separate* OpenAI-compatible
    # endpoint (`POST /api/v1/images/generations/async` with `X-API-KEY`, polled via the normal
    # `/api/v1/task/{id}`) rather than the unified `POST /api/v1/task` endpoint that
    # PiAPIClient.create_task() calls; a second, less authoritative source describes a unified
    # `task_type: "gpt-image-generation"` on the same `/task` endpoint. No page was found with a
    # verbatim create-task example showing which is actually correct, and
    # https://piapi.ai/docs/gpt-image-api/create-task 404s. If the async-endpoint reading is
    # right, PiAPIClient needs a new method (generation_service.py's PiAPI path calls
    # create_task() unconditionally today, so this row would misroute/fail if enabled as-is).
    # Values below are the best-grounded guess (unified schema, flat model id), not confirmed.
    dict(model_code="piapi-gpt-image-1-5", provider=ModelProvider.piapi, display_name="AI Photo Pro",
         category=ModelCategory.image, key_purpose="image", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=8, is_active=False, is_premium=True, max_context_tokens=4000,
         piapi_model="gpt-image-1.5", piapi_task_type="gpt-image-generation",
         piapi_extra_input={"size": "1024x1024", "quality": "medium"}),
    # CONFIRMED verbatim: https://piapi.ai/docs/seedream-api/seedream-5-lite (cross-checked with
    # two independent fetches, identical both times). Not explicitly flagged in the brief's Step
    # 1 list but shipped with a placeholder in Step 2 — verified anyway since it would otherwise
    # be a silent guess.
    dict(model_code="piapi-seedream5-lite", provider=ModelProvider.piapi, display_name="AI Photo Lite",
         category=ModelCategory.image, key_purpose="image", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=6, is_active=True, is_premium=False, max_context_tokens=4000,
         piapi_model="seedream", piapi_task_type="seedream-5-lite",
         piapi_extra_input={}),
    # CONFIRMED verbatim: https://piapi.ai/docs/gemini-api/nano-banana-pro (cross-checked with
    # two independent fetches, identical both times; matches the brief's prediction exactly).
    dict(model_code="piapi-nano-banana-pro", provider=ModelProvider.piapi, display_name="AI Photo Ultra",
         category=ModelCategory.image, key_purpose="image", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=18, is_active=True, is_premium=True, max_context_tokens=4000,
         piapi_model="gemini", piapi_task_type="nano-banana-pro",
         piapi_extra_input={"resolution": "2K", "aspect_ratio": "1:1", "output_format": "jpg"}),
    # --- PiAPI video models ---
    dict(model_code="piapi-veo3-fast", provider=ModelProvider.piapi, display_name="AI Video Fast",
         category=ModelCategory.video, key_purpose="video", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=51, is_active=True, is_premium=False, max_context_tokens=4000, duration_seconds=5,
         piapi_model="veo3.1", piapi_task_type="veo3.1-video-fast",
         piapi_extra_input={"aspect_ratio": "16:9", "duration": "5s", "resolution": "720p", "generate_audio": False}),
    # CONFIRMED verbatim: https://piapi.ai/docs/wan-api/wan26-text-to-video (cross-checked with
    # two independent fetches, identical both times; confirms the brief's "likely wan26-txt2video
    # by symmetry" guess exactly). Sibling wan26-img2video was already confirmed during design.
    dict(model_code="piapi-wan26", provider=ModelProvider.piapi, display_name="AI Video Standard",
         category=ModelCategory.video, key_purpose="video", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=68, is_active=True, is_premium=False, max_context_tokens=4000, duration_seconds=5,
         piapi_model="Wan", piapi_task_type="wan26-txt2video",
         piapi_extra_input={"resolution": "720p", "duration": 5}),
    # CONFIRMED verbatim: https://piapi.ai/docs/sora2-api/text-to-video (cross-checked with two
    # independent fetches, identical both times).
    dict(model_code="piapi-sora2", provider=ModelProvider.piapi, display_name="AI Video Sora",
         category=ModelCategory.video, key_purpose="video", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=68, is_active=True, is_premium=True, max_context_tokens=4000, duration_seconds=5,
         piapi_model="sora2", piapi_task_type="sora2-video",
         piapi_extra_input={"duration": 5}),
    dict(model_code="piapi-hailuo", provider=ModelProvider.piapi, display_name="AI Video Hailuo",
         category=ModelCategory.video, key_purpose="video", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=39, is_active=True, is_premium=False, max_context_tokens=4000, duration_seconds=6,
         piapi_model="hailuo", piapi_task_type="video_generation",
         piapi_extra_input={"model": "v2.3", "duration": 6, "resolution": 768, "expand_prompt": True}),
    # CONFIRMED verbatim: https://piapi.ai/docs/kling-api/kling-3-omni-api (cross-checked with two
    # independent fetches, identical both times across 4 separate examples on that page). This
    # confirms the brief's suspicion: Kling 3.0 Omni is NOT the generic kling-api/create-task
    # page's "version" enum (which tops out at "2.6" for task_type="video_generation") — it is a
    # distinct task_type="omni_video_generation" with "version": "3.0" set inside `input`.
    dict(model_code="piapi-kling3-omni", provider=ModelProvider.piapi, display_name="AI Video Kling",
         category=ModelCategory.video, key_purpose="video", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=85, is_active=True, is_premium=True, max_context_tokens=4000, duration_seconds=5,
         piapi_model="kling", piapi_task_type="omni_video_generation",
         piapi_extra_input={"version": "3.0", "resolution": "720p", "duration": 5}),
    dict(model_code="piapi-seedance2-fast", provider=ModelProvider.piapi, display_name="AI Video Seedance",
         category=ModelCategory.video, key_purpose="video", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=119, is_active=True, is_premium=False, max_context_tokens=4000, duration_seconds=5,
         piapi_model="seedance", piapi_task_type="seedance-2-fast",
         piapi_extra_input={"duration": 5, "aspect_ratio": "16:9"}),
    # CONFIRMED verbatim: https://piapi.ai/docs/dream-machine/create-task (cross-checked with two
    # independent fetches, identical both times; matches the brief's prediction exactly).
    dict(model_code="piapi-luma", provider=ModelProvider.piapi, display_name="AI Video Luma",
         category=ModelCategory.video, key_purpose="video", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=34, is_active=True, is_premium=False, max_context_tokens=4000, duration_seconds=5,
         piapi_model="luma", piapi_task_type="video_generation",
         piapi_extra_input={}),
]


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


async def seed() -> None:
    async with get_session() as session:
        existing_codes = {row[0] for row in (await session.execute(select(Tariff.code))).all()}
        for data in TARIFFS:
            if data["code"] not in existing_codes:
                session.add(Tariff(**data))

        existing_models = {row[0] for row in (await session.execute(select(ModelConfig.model_code))).all()}
        for data in MODEL_CONFIGS:
            if data["model_code"] not in existing_models:
                session.add(ModelConfig(**data))

        existing_banner_titles = {row[0] for row in (await session.execute(select(Banner.title))).all()}
        for data in BANNERS:
            if data["title"] not in existing_banner_titles:
                session.add(Banner(**data))

        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
