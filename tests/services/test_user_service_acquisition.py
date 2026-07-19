"""Трекинг источника привлечения (users.acquisition_source из deep-link)."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.services.user_service import get_or_create_user, normalize_source


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


def test_normalize_source_ads_tag_passes_through():
    assert normalize_source("ads_neuro1") == "ads_neuro1"


def test_normalize_source_ref_collapses_to_referral():
    # Рефералов трекает таблица referrals; в отчёте по источникам нужен канал.
    assert normalize_source("ref_910256253") == "referral"


def test_normalize_source_strips_garbage_and_truncates():
    assert normalize_source("ads kanal!<script>") == "adskanalscript"
    assert normalize_source("x" * 100) == "x" * 64  # ширина колонки


def test_normalize_source_empty_is_none():
    assert normalize_source(None) is None
    assert normalize_source("") is None
    assert normalize_source("!!!") is None  # только мусор -> органика


async def test_source_saved_on_create(session):
    user = await get_or_create_user(session, telegram_id=1, source="ads_neuro1")
    assert user.acquisition_source == "ads_neuro1"


async def test_source_not_overwritten_for_existing_user(session):
    """Атрибуция по первому касанию: повторный /start с другой меткой
    (или без неё) не должен переписывать источник."""
    await get_or_create_user(session, telegram_id=1, source="ads_neuro1")
    user = await get_or_create_user(session, telegram_id=1, source="ads_other")
    assert user.acquisition_source == "ads_neuro1"

    user = await get_or_create_user(session, telegram_id=1)
    assert user.acquisition_source == "ads_neuro1"


async def test_no_source_is_organic_null(session):
    user = await get_or_create_user(session, telegram_id=2)
    assert user.acquisition_source is None
