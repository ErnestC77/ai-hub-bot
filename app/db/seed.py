import asyncio

from sqlalchemy import select

from app.db.enums import ModelCategory, ModelProvider
from app.db.models import ModelConfig, Tariff
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
         is_active=True, is_premium=False, max_context_tokens=32000),
    dict(model_code="deepseek-chat", provider=ModelProvider.deepseek, display_name="DeepSeek Chat",
         category=ModelCategory.fast, key_purpose="text", cost_input_per_1m=0.14, cost_output_per_1m=0.28,
         is_active=True, is_premium=False, max_context_tokens=32000),
    dict(model_code="gpt-4o-mini", provider=ModelProvider.openai, display_name="ChatGPT mini",
         category=ModelCategory.medium, key_purpose="text", cost_input_per_1m=0.15, cost_output_per_1m=0.60,
         is_active=True, is_premium=False, max_context_tokens=64000),
    dict(model_code="claude-3-5-haiku-20241022", provider=ModelProvider.anthropic, display_name="Claude Haiku",
         category=ModelCategory.medium, key_purpose="text", cost_input_per_1m=0.80, cost_output_per_1m=4.00,
         is_active=True, is_premium=False, max_context_tokens=64000),
    dict(model_code="gpt-4o", provider=ModelProvider.openai, display_name="ChatGPT full",
         category=ModelCategory.premium, key_purpose="text", cost_input_per_1m=2.50, cost_output_per_1m=10.00,
         is_active=True, is_premium=True, max_context_tokens=128000),
    dict(model_code="claude-3-5-sonnet-20241022", provider=ModelProvider.anthropic, display_name="Claude Sonnet",
         category=ModelCategory.premium, key_purpose="premium", cost_input_per_1m=3.00, cost_output_per_1m=15.00,
         is_active=True, is_premium=True, max_context_tokens=128000),
    dict(model_code="dall-e-3", provider=ModelProvider.openai, display_name="Генерация картинок",
         category=ModelCategory.image, key_purpose="image", cost_input_per_1m=0, cost_output_per_1m=0,
         is_active=True, is_premium=True, max_context_tokens=4000),
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

        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
