from datetime import datetime

from pydantic import BaseModel


class CategoryLimitOut(BaseModel):
    used: int
    limit: int


class LimitsOut(BaseModel):
    daily_used: int
    daily_limit: int
    categories: dict[str, CategoryLimitOut]


class MeOut(BaseModel):
    telegram_id: int
    username: str | None
    first_name: str | None
    is_admin: bool
    active_model: str | None
    tariff_code: str
    tariff_name: str
    subscription_expires_at: datetime | None
    limits: LimitsOut


class SubscriptionStatusOut(BaseModel):
    tariff_code: str
    status: str
    expires_at: datetime | None
