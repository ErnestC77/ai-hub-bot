import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db.base import Base
from app.db.enums import ModelCategory, ModelProvider, RequestStatus
from app.db.models import AIRequest, ModelConfig, User


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def test_model_config_piapi_columns_round_trip(session):
    model = ModelConfig(
        model_code="piapi-flux-dev",
        provider=ModelProvider.piapi,
        display_name="AI Photo Fast",
        category=ModelCategory.image,
        credit_cost=3,
        key_purpose="image",
        piapi_model="Qubico/flux1-dev",
        piapi_task_type="txt2img",
        piapi_extra_input={"width": 1024, "height": 1024},
        duration_seconds=None,
    )
    session.add(model)
    await session.commit()

    fetched = await session.get(ModelConfig, model.id)
    assert fetched.piapi_model == "Qubico/flux1-dev"
    assert fetched.piapi_task_type == "txt2img"
    assert fetched.piapi_extra_input == {"width": 1024, "height": 1024}
    assert fetched.category == ModelCategory.video or fetched.category == ModelCategory.image  # sanity: enum usable


async def test_ai_request_provider_task_id_round_trip(session):
    user = User(telegram_id=1, username="u")
    session.add(user)
    await session.flush()

    request = AIRequest(
        user_id=user.id,
        model_code="piapi-veo3-fast",
        model_category=ModelCategory.video,
        prompt="a sunset",
        status=RequestStatus.processing,
        provider_task_id="58cb41b7-556d-46c0-b82e-1e116aa1a31a",
    )
    session.add(request)
    await session.commit()

    fetched = await session.get(AIRequest, request.id)
    assert fetched.provider_task_id == "58cb41b7-556d-46c0-b82e-1e116aa1a31a"
