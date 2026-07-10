"""Тонкий helper над таблицей settings (бизнес-настройки: курс, маржа, цена кредита).
НЕ путать с app.config.Settings (env/.env: API-ключи, DATABASE_URL и т.п.)."""

from typing import Callable, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Setting
from app.services.pricing import PricingSettings

T = TypeVar("T")


async def get_setting(
    session: AsyncSession,
    key: str,
    *,
    cast: Callable[[str], T] = str,
    default: T | None = None,
) -> T | None:
    """Читает settings.value по ключу и приводит cast'ом. Если строки нет
    (БД ещё не засижена) -- возвращает default."""
    row = await session.get(Setting, key)
    if row is None:
        return default
    return cast(row.value)


async def load_pricing_settings(session: AsyncSession) -> PricingSettings:
    defaults = PricingSettings()
    return PricingSettings(
        usd_to_rub_rate=await get_setting(session, "usd_to_rub_rate", cast=float, default=defaults.usd_to_rub_rate),
        rub_per_credit=await get_setting(session, "rub_per_credit", cast=float, default=defaults.rub_per_credit),
        provider_fee_multiplier=await get_setting(
            session, "provider_fee_multiplier", cast=float, default=defaults.provider_fee_multiplier
        ),
        margin_multiplier=await get_setting(
            session, "margin_multiplier", cast=float, default=defaults.margin_multiplier
        ),
        minimum_text_credits=await get_setting(
            session, "minimum_text_credits", cast=int, default=defaults.minimum_text_credits
        ),
    )


async def set_setting(
    session: AsyncSession,
    key: str,
    value: str,
    *,
    type_: str,
    description: str | None = None,
) -> Setting:
    """Upsert строки settings. Единственное место записи в таблицу settings.
    При обновлении существующего ключа меняется только value -- type/description
    заданы сидом и при правке значения не трогаются (спека фазы 5).
    flush, не commit -- транзакцией владеет вызывающий код."""
    row = await session.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=value, type=type_, description=description)
        session.add(row)
    else:
        row.value = value
    await session.flush()
    return row
