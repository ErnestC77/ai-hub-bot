from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_admin, get_db
from app.db.enums import CreditTxType, PaymentProvider, PaymentStatus
from app.db.models import Banner, ModelConfig, Payment, Tariff, User
from app.services.admin_service import cancel_subscription, grant_manual_subscription
from app.services.credit_service import get_balance as get_credit_balance
from app.services.credit_service import grant_credits
from app.services.payments.refund_service import refund
from app.services.stats_service import get_daily_stats, get_monthly_stats
from app.services.subscription_service import get_active_subscription, get_tariff_by_code
from app.services.user_service import get_user_by_telegram_id, search_users, set_blocked

router = APIRouter(prefix="/admin", dependencies=[Depends(current_admin)])


# --- stats -------------------------------------------------------------

class StatsOut(BaseModel):
    today_new_users: int
    today_payments_count: int
    today_payments_amount_rub: float
    today_ai_requests: int
    today_api_cost_usd: float
    today_errors: int
    month_revenue_rub: float
    month_active_subscriptions: int


@router.get("/stats", response_model=StatsOut)
async def stats(session: AsyncSession = Depends(get_db)) -> StatsOut:
    daily = await get_daily_stats(session)
    monthly = await get_monthly_stats(session)
    return StatsOut(
        today_new_users=daily.new_users,
        today_payments_count=daily.payments_count,
        today_payments_amount_rub=daily.payments_amount_rub,
        today_ai_requests=daily.ai_requests,
        today_api_cost_usd=daily.api_cost_usd,
        today_errors=daily.errors,
        month_revenue_rub=monthly.revenue_rub,
        month_active_subscriptions=monthly.active_subscriptions,
    )


# --- users ---------------------------------------------------------------

class UserOut(BaseModel):
    telegram_id: int
    username: str | None
    first_name: str | None
    is_admin: bool
    is_blocked: bool
    tariff_code: str | None
    subscription_expires_at: str | None
    credits_balance: int


async def _to_user_out(session: AsyncSession, user: User) -> UserOut:
    subscription = await get_active_subscription(session, user.id)
    tariff = None
    if subscription:
        tariff = await session.get(Tariff, subscription.tariff_id)

    return UserOut(
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        is_admin=user.is_admin,
        is_blocked=user.is_blocked,
        tariff_code=tariff.code if tariff else None,
        subscription_expires_at=subscription.expires_at.isoformat() if subscription else None,
        credits_balance=await get_credit_balance(session, user),
    )


@router.get("/users", response_model=list[UserOut])
async def list_users(query: str | None = None, session: AsyncSession = Depends(get_db)) -> list[UserOut]:
    users = await search_users(session, query)
    return [await _to_user_out(session, u) for u in users]


async def _get_user_or_404(session: AsyncSession, telegram_id: int) -> User:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user


@router.get("/users/{telegram_id}", response_model=UserOut)
async def get_user(telegram_id: int, session: AsyncSession = Depends(get_db)) -> UserOut:
    user = await _get_user_or_404(session, telegram_id)
    return await _to_user_out(session, user)


@router.post("/users/{telegram_id}/block", response_model=UserOut)
async def block_user(telegram_id: int, session: AsyncSession = Depends(get_db)) -> UserOut:
    user = await _get_user_or_404(session, telegram_id)
    await set_blocked(session, user, True)
    return await _to_user_out(session, user)


@router.post("/users/{telegram_id}/unblock", response_model=UserOut)
async def unblock_user(telegram_id: int, session: AsyncSession = Depends(get_db)) -> UserOut:
    user = await _get_user_or_404(session, telegram_id)
    await set_blocked(session, user, False)
    return await _to_user_out(session, user)


class GrantRequest(BaseModel):
    tariff_code: str


@router.post("/users/{telegram_id}/grant", response_model=UserOut)
async def grant_subscription(
    telegram_id: int, body: GrantRequest, session: AsyncSession = Depends(get_db)
) -> UserOut:
    user = await _get_user_or_404(session, telegram_id)
    tariff = await get_tariff_by_code(session, body.tariff_code)
    if tariff is None:
        raise HTTPException(status_code=404, detail="Тариф не найден")

    await grant_manual_subscription(session, user, tariff)
    return await _to_user_out(session, user)


class GrantCreditsRequest(BaseModel):
    amount: int


@router.post("/users/{telegram_id}/grant-credits", response_model=UserOut)
async def grant_credits_to_user(
    telegram_id: int, body: GrantCreditsRequest, session: AsyncSession = Depends(get_db)
) -> UserOut:
    user = await _get_user_or_404(session, telegram_id)
    await grant_credits(
        session, user.id, body.amount, reason="manual admin grant", tx_type=CreditTxType.manual_adjustment
    )
    return await _to_user_out(session, user)


@router.post("/users/{telegram_id}/cancel-subscription", response_model=UserOut)
async def cancel_user_subscription(telegram_id: int, session: AsyncSession = Depends(get_db)) -> UserOut:
    user = await _get_user_or_404(session, telegram_id)
    subscription = await get_active_subscription(session, user.id)
    if subscription:
        await cancel_subscription(session, subscription)
    return await _to_user_out(session, user)


# --- payments ------------------------------------------------------------

class PaymentOut(BaseModel):
    id: int
    telegram_id: int
    provider: str
    amount: float
    currency: str
    status: str
    created_at: str


@router.get("/payments", response_model=list[PaymentOut])
async def list_payments(
    status: str | None = None, provider: str | None = None, session: AsyncSession = Depends(get_db)
) -> list[PaymentOut]:
    stmt = select(Payment).order_by(Payment.created_at.desc()).limit(50)
    if status:
        try:
            stmt = stmt.where(Payment.status == PaymentStatus(status))
        except ValueError:
            raise HTTPException(status_code=422, detail="Некорректный status")
    if provider:
        try:
            stmt = stmt.where(Payment.provider == PaymentProvider(provider))
        except ValueError:
            raise HTTPException(status_code=422, detail="Некорректный provider")

    payments = (await session.execute(stmt)).scalars().all()
    out = []
    for p in payments:
        user = await session.get(User, p.user_id)
        out.append(
            PaymentOut(
                id=p.id,
                telegram_id=user.telegram_id if user else 0,
                provider=p.provider.value,
                amount=float(p.amount),
                currency=p.currency,
                status=p.status.value,
                created_at=p.created_at.isoformat(),
            )
        )
    return out


@router.post("/payments/{payment_id}/refund", response_model=PaymentOut)
async def refund_payment(payment_id: int, session: AsyncSession = Depends(get_db)) -> PaymentOut:
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Платёж не найден")

    ok = await refund(session, payment)
    if not ok:
        raise HTTPException(status_code=400, detail="Возврат не удался")

    user = await session.get(User, payment.user_id)
    return PaymentOut(
        id=payment.id,
        telegram_id=user.telegram_id if user else 0,
        provider=payment.provider.value,
        amount=float(payment.amount),
        currency=payment.currency,
        status=payment.status.value,
        created_at=payment.created_at.isoformat(),
    )


# --- models ---------------------------------------------------------------

class ModelConfigOut(BaseModel):
    model_code: str
    provider: str
    display_name: str
    category: str
    credit_cost: int
    is_active: bool
    is_premium: bool


def _to_model_config_out(m: ModelConfig) -> ModelConfigOut:
    return ModelConfigOut(
        model_code=m.model_code, provider=m.provider.value, display_name=m.display_name,
        category=m.category.value, credit_cost=m.credit_cost, is_active=m.is_active, is_premium=m.is_premium,
    )


@router.get("/models", response_model=list[ModelConfigOut])
async def list_models(session: AsyncSession = Depends(get_db)) -> list[ModelConfigOut]:
    models = (await session.execute(select(ModelConfig))).scalars().all()
    return [_to_model_config_out(m) for m in models]


class ModelUpdateRequest(BaseModel):
    is_active: bool | None = None
    credit_cost: int | None = None


@router.patch("/models/{model_code}", response_model=ModelConfigOut)
async def update_model(
    model_code: str, body: ModelUpdateRequest, session: AsyncSession = Depends(get_db)
) -> ModelConfigOut:
    model = (
        await session.execute(select(ModelConfig).where(ModelConfig.model_code == model_code))
    ).scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="Модель не найдена")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(model, field, value)
    await session.commit()

    return _to_model_config_out(model)


# --- tariffs ---------------------------------------------------------------

class TariffAdminOut(BaseModel):
    code: str
    name: str
    price_rub: float
    price_stars: int
    fast_limit: int
    medium_limit: int
    premium_limit: int
    image_limit: int
    daily_limit: int
    is_active: bool


class TariffUpdateRequest(BaseModel):
    fast_limit: int | None = None
    medium_limit: int | None = None
    premium_limit: int | None = None
    image_limit: int | None = None
    daily_limit: int | None = None
    price_rub: float | None = None
    price_stars: int | None = None
    is_active: bool | None = None


def _to_tariff_admin_out(t: Tariff) -> TariffAdminOut:
    return TariffAdminOut(
        code=t.code, name=t.name, price_rub=float(t.price_rub), price_stars=t.price_stars,
        fast_limit=t.fast_limit, medium_limit=t.medium_limit, premium_limit=t.premium_limit,
        image_limit=t.image_limit, daily_limit=t.daily_limit, is_active=t.is_active,
    )


@router.get("/tariffs", response_model=list[TariffAdminOut])
async def list_all_tariffs(session: AsyncSession = Depends(get_db)) -> list[TariffAdminOut]:
    tariffs = (await session.execute(select(Tariff))).scalars().all()
    return [_to_tariff_admin_out(t) for t in tariffs]


@router.patch("/tariffs/{code}", response_model=TariffAdminOut)
async def update_tariff(
    code: str, body: TariffUpdateRequest, session: AsyncSession = Depends(get_db)
) -> TariffAdminOut:
    tariff = (await session.execute(select(Tariff).where(Tariff.code == code))).scalar_one_or_none()
    if tariff is None:
        raise HTTPException(status_code=404, detail="Тариф не найден")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(tariff, field, value)
    await session.commit()

    return _to_tariff_admin_out(tariff)


# --- banners ---------------------------------------------------------------

class BannerAdminOut(BaseModel):
    id: int
    title: str
    subtitle: str | None
    badge_text: str | None
    cta_text: str
    image_url: str
    action_type: str
    action_value: str
    sort_order: int
    is_active: bool


def _to_banner_admin_out(b: Banner) -> BannerAdminOut:
    return BannerAdminOut(
        id=b.id, title=b.title, subtitle=b.subtitle, badge_text=b.badge_text, cta_text=b.cta_text,
        image_url=b.image_url, action_type=b.action_type, action_value=b.action_value,
        sort_order=b.sort_order, is_active=b.is_active,
    )


@router.get("/banners", response_model=list[BannerAdminOut])
async def list_banners_admin(session: AsyncSession = Depends(get_db)) -> list[BannerAdminOut]:
    banners = (await session.execute(select(Banner).order_by(Banner.sort_order, Banner.id))).scalars().all()
    return [_to_banner_admin_out(b) for b in banners]


class BannerCreateRequest(BaseModel):
    title: str
    subtitle: str | None = None
    badge_text: str | None = None
    cta_text: str = "Открыть"
    image_url: str
    action_type: Literal["prompt", "link"] = "prompt"
    action_value: str
    sort_order: int = 0
    is_active: bool = True


@router.post("/banners", response_model=BannerAdminOut)
async def create_banner(body: BannerCreateRequest, session: AsyncSession = Depends(get_db)) -> BannerAdminOut:
    banner = Banner(**body.model_dump())
    session.add(banner)
    await session.commit()
    return _to_banner_admin_out(banner)


class BannerUpdateRequest(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    badge_text: str | None = None
    cta_text: str | None = None
    image_url: str | None = None
    action_type: Literal["prompt", "link"] | None = None
    action_value: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


async def _get_banner_or_404(session: AsyncSession, banner_id: int) -> Banner:
    banner = await session.get(Banner, banner_id)
    if banner is None:
        raise HTTPException(status_code=404, detail="Баннер не найден")
    return banner


@router.patch("/banners/{banner_id}", response_model=BannerAdminOut)
async def update_banner(
    banner_id: int, body: BannerUpdateRequest, session: AsyncSession = Depends(get_db)
) -> BannerAdminOut:
    banner = await _get_banner_or_404(session, banner_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(banner, field, value)
    await session.commit()
    return _to_banner_admin_out(banner)


@router.delete("/banners/{banner_id}")
async def delete_banner(banner_id: int, session: AsyncSession = Depends(get_db)) -> dict:
    banner = await _get_banner_or_404(session, banner_id)
    await session.delete(banner)
    await session.commit()
    return {"ok": True}
