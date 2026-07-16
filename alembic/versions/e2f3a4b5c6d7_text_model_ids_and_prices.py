"""text models: real OpenRouter ids + token prices

6 из 12 текстовых provider_model_id были мертвы на OpenRouter (генерация падала),
у всех 12 цены токенов = 0 (текст списывал только min_credits -> убыток на дорогих).
ID и цены сверены с живым каталогом openrouter.ai/api/v1/models 2026-07-16.
recommended_credits/min_credits (полы) не трогаем.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-07-16
"""

from alembic import op

revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None

# code -> (new_id, new_in, new_out, old_id)  -- old prices = 0
_TEXT = {
    "deepseek_v3": ("deepseek/deepseek-chat", 0.2, 0.8, "deepseek/deepseek-chat"),
    "llama_3_1_8b": ("meta-llama/llama-3.1-8b-instruct", 0.05, 0.08, "meta-llama/llama-3.1-8b-instruct"),
    "qwen_plus": ("qwen/qwen3.7-plus", 0.32, 1.28, "qwen/qwen-plus"),
    "mistral_large": ("mistralai/mistral-large", 2.0, 6.0, "mistralai/mistral-large"),
    "gpt_mini": ("openai/gpt-4o-mini", 0.15, 0.6, "openai/gpt-4o-mini"),
    "qwen_max": ("qwen/qwen3.7-max", 1.475, 4.425, "qwen/qwen-max"),
    "grok": ("x-ai/grok-4.5", 2.0, 6.0, "x-ai/grok-2"),
    "gpt_premium": ("openai/gpt-4o", 2.5, 10.0, "openai/gpt-4o"),
    "gemini_flash": ("google/gemini-2.5-flash", 0.3, 2.5, "google/gemini-flash-1.5"),
    "gemini_pro": ("google/gemini-2.5-pro", 1.25, 10.0, "google/gemini-pro-1.5"),
    "claude_sonnet": ("anthropic/claude-sonnet-5", 2.0, 10.0, "anthropic/claude-3.5-sonnet"),
    "claude_opus": ("anthropic/claude-opus-4.8", 5.0, 25.0, "anthropic/claude-3-opus"),
}


def _apply(id_idx: int, in_price, out_price) -> None:
    for code, vals in _TEXT.items():
        op.execute(
            "UPDATE ai_models SET "
            f"provider_model_id = '{vals[id_idx]}', "
            f"input_price_usd_per_1m_tokens = {vals[1] if in_price is None else in_price}, "
            f"output_price_usd_per_1m_tokens = {vals[2] if out_price is None else out_price} "
            f"WHERE code = '{code}'"
        )


def upgrade() -> None:
    # новые id (индекс 0), реальные цены (None -> берём из кортежа)
    _apply(0, None, None)


def downgrade() -> None:
    # старые id (индекс 3), цены обратно в 0
    _apply(3, 0, 0)
