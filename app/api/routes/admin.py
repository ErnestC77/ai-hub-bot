from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_admin, get_db
from app.db.enums import PaymentProvider, PaymentStatus
from app.db.models import (
    AiModel,
    Banner,
    CreditPackage,
    CreditTransaction,
    ModelOption,
    Payment,
    Setting,
    User,
)
from app.services.credit_service import InsufficientBalanceError, adjust_credits_admin
from app.services.payments.refund_service import refund
from app.services.settings_service import set_setting
from app.services.stats_service import get_daily_stats, get_monthly_stats
from app.services.user_service import get_user_by_telegram_id, search_users, set_blocked

router = APIRouter(prefix="/admin", dependencies=[Depends(current_admin)])


# --- stats -------------------------------------------------------------

class ModelUsageOut(BaseModel):
    model_code: str
    requests: int
    credits_spent: int
    cost_usd: float


class UserSpendOut(BaseModel):
    telegram_id: int
    credits_spent: int


class StatsOut(BaseModel):
    today_new_users: int
    today_payments_count: int
    today_payments_amount_rub: float
    today_ai_requests: int
    today_api_cost_usd: float
    today_errors: int
    today_revenue_credits: int
    today_revenue_rub_estimated: float
    today_margin_rub: float
    today_avg_cost_credits: float
    model_usage: list[ModelUsageOut]
    top_users_by_spend: list[UserSpendOut]
    month_revenue_rub: float
    month_credits_purchases_count: int


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
        today_revenue_credits=daily.revenue_credits,
        today_revenue_rub_estimated=daily.revenue_rub_estimated,
        today_margin_rub=daily.margin_rub,
        today_avg_cost_credits=daily.avg_cost_credits,
        model_usage=[
            ModelUsageOut(
                model_code=m.model_code,
                requests=m.requests,
                credits_spent=m.credits_spent,
                cost_usd=m.cost_usd,
            )
            for m in daily.model_usage
        ],
        top_users_by_spend=[
            UserSpendOut(telegram_id=u.telegram_id, credits_spent=u.credits_spent)
            for u in daily.top_users_by_spend
        ],
        month_revenue_rub=monthly.revenue_rub,
        month_credits_purchases_count=monthly.credits_purchases_count,
    )


# --- users ---------------------------------------------------------------

class UserOut(BaseModel):
    telegram_id: int
    username: str | None
    first_name: str | None
    is_admin: bool
    is_blocked: bool
    credits_balance: int
    total_credits_purchased: int
    total_credits_spent: int


def _to_user_out(user: User) -> UserOut:
    return UserOut(
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        is_admin=user.is_admin,
        is_blocked=user.is_blocked,
        credits_balance=user.credits_balance,
        total_credits_purchased=user.total_credits_purchased,
        total_credits_spent=user.total_credits_spent,
    )


@router.get("/users", response_model=list[UserOut])
async def list_users(query: str | None = None, session: AsyncSession = Depends(get_db)) -> list[UserOut]:
    users = await search_users(session, query)
    return [_to_user_out(u) for u in users]


async def _get_user_or_404(session: AsyncSession, telegram_id: int) -> User:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user


@router.get("/users/{telegram_id}", response_model=UserOut)
async def get_user(telegram_id: int, session: AsyncSession = Depends(get_db)) -> UserOut:
    user = await _get_user_or_404(session, telegram_id)
    return _to_user_out(user)


@router.post("/users/{telegram_id}/block", response_model=UserOut)
async def block_user(telegram_id: int, session: AsyncSession = Depends(get_db)) -> UserOut:
    user = await _get_user_or_404(session, telegram_id)
    await set_blocked(session, user, True)
    return _to_user_out(user)


@router.post("/users/{telegram_id}/unblock", response_model=UserOut)
async def unblock_user(telegram_id: int, session: AsyncSession = Depends(get_db)) -> UserOut:
    user = await _get_user_or_404(session, telegram_id)
    await set_blocked(session, user, False)
    return _to_user_out(user)


class TransactionOut(BaseModel):
    id: int
    type: str
    amount: int
    balance_before: int
    balance_after: int
    provider: str | None
    model_code: str | None
    request_id: int | None
    description: str | None
    created_at: str


@router.get("/users/{telegram_id}/transactions", response_model=list[TransactionOut])
async def list_user_transactions(
    telegram_id: int,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
) -> list[TransactionOut]:
    user = await _get_user_or_404(session, telegram_id)
    txs = (
        await session.execute(
            select(CreditTransaction)
            .where(CreditTransaction.user_id == user.id)
            .order_by(CreditTransaction.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return [
        TransactionOut(
            id=tx.id,
            type=tx.type.value,
            amount=tx.amount,
            balance_before=tx.balance_before,
            balance_after=tx.balance_after,
            provider=tx.provider,
            model_code=tx.model_code,
            request_id=tx.request_id,
            description=tx.description,
            created_at=tx.created_at.isoformat(),
        )
        for tx in txs
    ]


class AdjustCreditsRequest(BaseModel):
    amount: int
    reason: str = "ручная корректировка админом"


@router.post("/users/{telegram_id}/credits", response_model=UserOut)
async def adjust_user_credits(
    telegram_id: int, body: AdjustCreditsRequest, session: AsyncSession = Depends(get_db)
) -> UserOut:
    if body.amount == 0:
        raise HTTPException(status_code=422, detail="amount не может быть нулевым")
    user = await _get_user_or_404(session, telegram_id)
    try:
        await adjust_credits_admin(session, user.id, body.amount, reason=body.reason)
    except InsufficientBalanceError as exc:
        raise HTTPException(status_code=400, detail="Недостаточно кредитов для списания") from exc
    await session.commit()
    return _to_user_out(user)


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

class AiModelAdminOut(BaseModel):
    code: str
    provider: str
    category: str
    tier: str
    display_name: str
    provider_model_id: str
    input_price_usd_per_1m_tokens: float
    output_price_usd_per_1m_tokens: float
    min_credits: int
    recommended_credits: int
    is_active: bool
    is_visible: bool
    sort_order: int


def _to_model_out(m: AiModel) -> AiModelAdminOut:
    return AiModelAdminOut(
        code=m.code,
        provider=m.provider.value,
        category=m.category.value,
        tier=m.tier.value,
        display_name=m.display_name,
        provider_model_id=m.provider_model_id,
        input_price_usd_per_1m_tokens=float(m.input_price_usd_per_1m_tokens),
        output_price_usd_per_1m_tokens=float(m.output_price_usd_per_1m_tokens),
        min_credits=m.min_credits,
        recommended_credits=m.recommended_credits,
        is_active=m.is_active,
        is_visible=m.is_visible,
        sort_order=m.sort_order,
    )


@router.get("/models", response_model=list[AiModelAdminOut])
async def list_models(session: AsyncSession = Depends(get_db)) -> list[AiModelAdminOut]:
    models = (
        await session.execute(select(AiModel).order_by(AiModel.sort_order, AiModel.id))
    ).scalars().all()
    return [_to_model_out(m) for m in models]


class AiModelUpdateRequest(BaseModel):
    is_active: bool | None = None
    is_visible: bool | None = None
    recommended_credits: int | None = None
    min_credits: int | None = None
    provider_model_id: str | None = None
    input_price_usd_per_1m_tokens: float | None = None
    output_price_usd_per_1m_tokens: float | None = None
    sort_order: int | None = None


@router.patch("/models/{code}", response_model=AiModelAdminOut)
async def update_model(
    code: str, body: AiModelUpdateRequest, session: AsyncSession = Depends(get_db)
) -> AiModelAdminOut:
    model = (
        await session.execute(select(AiModel).where(AiModel.code == code))
    ).scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="Модель не найдена")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(model, field, value)
    await session.commit()

    return _to_model_out(model)


# --- model options -----------------------------------------------------------

class AdminModelOptionOut(BaseModel):
    id: int
    model_code: str
    kind: str
    code: str
    label: str
    provider_params: dict
    credits_multiplier: float
    is_default: bool
    sort_order: int
    is_active: bool


def _to_option_out(opt: ModelOption, model_code: str) -> AdminModelOptionOut:
    return AdminModelOptionOut(
        id=opt.id, model_code=model_code, kind=opt.kind.value, code=opt.code,
        label=opt.label, provider_params=opt.provider_params or {},
        credits_multiplier=float(opt.credits_multiplier), is_default=opt.is_default,
        sort_order=opt.sort_order, is_active=opt.is_active,
    )


@router.get("/models/{code}/options", response_model=list[AdminModelOptionOut])
async def list_model_options(
    code: str, session: AsyncSession = Depends(get_db)
) -> list[AdminModelOptionOut]:
    model = (
        await session.execute(select(AiModel).where(AiModel.code == code))
    ).scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="Модель не найдена")
    # Админу -- ВСЕ опции, включая неактивные (публичный /api/models их скрывает).
    options = (
        await session.execute(
            select(ModelOption)
            .where(ModelOption.model_id == model.id)
            .order_by(ModelOption.kind, ModelOption.sort_order)
        )
    ).scalars().all()
    return [_to_option_out(o, model.code) for o in options]


class ModelOptionUpdateRequest(BaseModel):
    # provider_params/kind/code/model_id НЕ здесь -- это контракт провайдера,
    # правится миграцией. Правка сырого JSON из UI = произвольный запрос к fal.
    label: str | None = None
    credits_multiplier: float | None = None
    sort_order: int | None = None
    is_active: bool | None = None
    is_default: bool | None = None


@router.patch("/options/{option_id}", response_model=AdminModelOptionOut)
async def update_model_option(
    option_id: int, body: ModelOptionUpdateRequest, session: AsyncSession = Depends(get_db)
) -> AdminModelOptionOut:
    opt = (
        await session.execute(select(ModelOption).where(ModelOption.id == option_id))
    ).scalar_one_or_none()
    if opt is None:
        raise HTTPException(status_code=404, detail="Опция не найдена")

    patch = body.model_dump(exclude_unset=True)

    # Инвариант ценообразования (аудит pricing I1): recommended_credits модели =
    # цена ДЕФОЛТНОЙ комбинации, а _resolve_options домножает и на множитель
    # дефолтной опции -> дефолт ОБЯЗАН иметь множитель 1.0 и быть активным, иначе
    # витрина и списание разъедутся. Проверяем ПОСТ-патч состояние.
    new_is_default = patch.get("is_default", opt.is_default)
    new_multiplier = patch.get("credits_multiplier", float(opt.credits_multiplier))
    new_is_active = patch.get("is_active", opt.is_active)
    if new_is_default and abs(new_multiplier - 1.0) > 1e-9:
        raise HTTPException(
            status_code=400,
            detail="Дефолтная опция обязана иметь множитель 1.0 "
                   "(recommended_credits = цена дефолтной комбинации)",
        )
    if new_is_default and not new_is_active:
        raise HTTPException(
            status_code=400,
            detail="Нельзя деактивировать дефолтную опцию -- сначала назначьте "
                   "дефолтом другую активную опцию этого вида",
        )

    if "is_default" in patch:
        if patch["is_default"] is False and opt.is_default:
            # Нельзя оставить (model, kind) без дефолта: recommended_credits =
            # цена дефолтной комбинации, она обязана существовать.
            raise HTTPException(
                status_code=400,
                detail="Нельзя снять дефолт с единственной дефолтной опции -- "
                       "сначала назначьте дефолтом другую опцию этого вида",
            )
        if patch["is_default"] is True and not opt.is_default:
            # Снимаем флаг с прежнего дефолта того же (model_id, kind) в ЭТОЙ же
            # транзакции -- иначе частичный уникальный индекс уронит вставку.
            await session.execute(
                update(ModelOption)
                .where(
                    ModelOption.model_id == opt.model_id,
                    ModelOption.kind == opt.kind,
                    ModelOption.is_default.is_(True),
                )
                .values(is_default=False)
            )

    for field, value in patch.items():
        setattr(opt, field, value)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        # 409 -- ТОЛЬКО на гонку по дефолту (два админа назначают дефолт одному
        # (model_id, kind), проигравший упирается в uq_model_option_default).
        # Прочие IntegrityError (напр. NOT NULL от руками присланного null) --
        # честный 500, а не ложное "повторите".
        if "uq_model_option_default" in str(exc.orig):
            raise HTTPException(
                status_code=409, detail="Опции изменены параллельно, повторите"
            ) from None
        raise

    model = (
        await session.execute(select(AiModel).where(AiModel.id == opt.model_id))
    ).scalar_one()
    return _to_option_out(opt, model.code)


# --- packages ---------------------------------------------------------------

class PackageAdminOut(BaseModel):
    code: str
    title: str
    credits: int
    price_rub: float
    price_stars: int
    description: str | None
    is_active: bool


def _to_package_out(p: CreditPackage) -> PackageAdminOut:
    return PackageAdminOut(
        code=p.code,
        title=p.title,
        credits=p.credits,
        price_rub=float(p.price_rub),
        price_stars=p.price_stars,
        description=p.description,
        is_active=p.is_active,
    )


@router.get("/packages", response_model=list[PackageAdminOut])
async def list_packages(session: AsyncSession = Depends(get_db)) -> list[PackageAdminOut]:
    packages = (
        await session.execute(select(CreditPackage).order_by(CreditPackage.price_rub))
    ).scalars().all()
    return [_to_package_out(p) for p in packages]


class PackageUpdateRequest(BaseModel):
    credits: int | None = None
    price_rub: float | None = None
    price_stars: int | None = None
    is_active: bool | None = None


@router.patch("/packages/{code}", response_model=PackageAdminOut)
async def update_package(
    code: str, body: PackageUpdateRequest, session: AsyncSession = Depends(get_db)
) -> PackageAdminOut:
    package = (
        await session.execute(select(CreditPackage).where(CreditPackage.code == code))
    ).scalar_one_or_none()
    if package is None:
        raise HTTPException(status_code=404, detail="Пакет не найден")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(package, field, value)
    await session.commit()

    return _to_package_out(package)


# --- settings ---------------------------------------------------------------

class SettingOut(BaseModel):
    key: str
    value: str
    type: str
    description: str | None


def _to_setting_out(s: Setting) -> SettingOut:
    return SettingOut(key=s.key, value=s.value, type=s.type, description=s.description)


@router.get("/settings", response_model=list[SettingOut])
async def list_settings(session: AsyncSession = Depends(get_db)) -> list[SettingOut]:
    rows = (await session.execute(select(Setting).order_by(Setting.key))).scalars().all()
    return [_to_setting_out(s) for s in rows]


class SettingUpdateRequest(BaseModel):
    value: str


def _validate_setting_value(type_: str, value: str) -> None:
    """Проверяет, что value парсится согласно заявленному типу настройки. Без этой
    проверки некорректная строка тихо запишется в БД, а упадёт только следующий
    запрос генерации (get_setting делает cast(row.value) на каждый вызов) -- поэтому
    ошибка должна быть здесь, на PATCH, а не там."""
    if type_ == "int":
        try:
            int(value)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"value должно быть целым числом (int), получено: {value!r}",
            )
    elif type_ == "float":
        try:
            float(value)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"value должно быть числом (float), получено: {value!r}",
            )
    elif type_ == "bool":
        if value.lower() not in ("true", "false"):
            raise HTTPException(
                status_code=422,
                detail=f"value должно быть 'true' или 'false' (bool), получено: {value!r}",
            )
    # type_ == "str" -- любая строка валидна, проверка не требуется.


@router.patch("/settings/{key}", response_model=SettingOut)
async def update_setting(
    key: str, body: SettingUpdateRequest, session: AsyncSession = Depends(get_db)
) -> SettingOut:
    row = await session.get(Setting, key)
    if row is None:
        raise HTTPException(status_code=404, detail="Настройка не найдена")

    _validate_setting_value(row.type, body.value)

    # type/description не меняются при обновлении значения существующего ключа.
    row = await set_setting(session, key, body.value, type_=row.type, description=row.description)
    await session.commit()
    return _to_setting_out(row)


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
