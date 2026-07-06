from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AIRequest, ModelConfig
from app.services.ai.base import AIResult

ONE_MILLION = Decimal(1_000_000)


async def fill_request_cost(
    session: AsyncSession, request: AIRequest, model: ModelConfig, result: AIResult
) -> None:
    request.input_tokens = result.input_tokens
    request.output_tokens = result.output_tokens
    request.total_tokens = result.input_tokens + result.output_tokens
    request.estimated_cost_usd = (
        Decimal(result.input_tokens) / ONE_MILLION * Decimal(model.cost_input_per_1m)
        + Decimal(result.output_tokens) / ONE_MILLION * Decimal(model.cost_output_per_1m)
    )
    await session.commit()
