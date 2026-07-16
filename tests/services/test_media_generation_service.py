import asyncio
import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("BOT_TOKEN", "123456:TEST-token")
os.environ.setdefault("DATABASE_URL", "postgresql://test")

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.enums import (
    CostUnit,
    CreditTxType,
    ModelCategory,
    ModelOptionKind,
    ModelProvider,
    ModelTier,
    RequestStatus,
)
from app.db.models import AIRequest, AiModel, CreditTransaction, ModelOption, Referral, Setting, User
from app.services import antifraud_service as afs
from app.services import media_generation_service as mgs
from app.services.ai.base import AIError
from app.services.antifraud_service import (
    DailySpendLimitExceededError,
    DuplicateRequestError,
    FreeTierLimitExceededError,
    RateLimitExceededError,
    TierNotAllowedError,
)
from app.services.credit_service import InsufficientBalanceError, settle_request
from app.services.media_generation_service import (
    ConfirmationRequiredError,
    ModelNotFoundError,
    RequestInProgressError,
    UnknownOptionError,
    get_generation,
    handle_fal_webhook,
    refund_stale_reserved_requests,
    start_media_generation,
)


class FakeRedis:
    """In-memory Redis: set(nx)/get/delete/incr/incrby/decrby/expire.

    locked=True отклоняет ТОЛЬКО попытку взять ai_lock:* (эмуляция занятого
    per-user лока) -- antifraud-ключи (dup:*, rate_limit:*, daily_spend:*)
    живут как обычно. Тот же класс скопирован из test_text_generation_service.py.
    """

    def __init__(self, locked: bool = False):
        self.locked = locked
        self.deleted: list[str] = []
        self.store: dict[str, str] = {}
        self.expire_calls: list[tuple[str, int]] = []

    async def set(self, key, value, nx=False, ex=None):
        if key.startswith("ai_lock:") and self.locked:
            return None
        if nx and key in self.store:
            return None
        self.store[key] = str(value)
        if ex is not None:
            self.expire_calls.append((key, ex))
        return True

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, key):
        self.deleted.append(key)
        self.store.pop(key, None)

    async def incr(self, key):
        return await self.incrby(key, 1)

    async def incrby(self, key, amount):
        value = int(self.store.get(key, "0")) + int(amount)
        self.store[key] = str(value)
        return value

    async def decrby(self, key, amount):
        return await self.incrby(key, -int(amount))

    async def expire(self, key, seconds):
        self.expire_calls.append((key, seconds))
        return True


class FakeKeyManager:
    def get_key(self, provider, purpose):
        return f"key-{provider.value}-{purpose.value}"


class FakeFalClient:
    """Подменяет mgs.FalClient. Сервис делает FalClient(api_key=...), поэтому
    сам fake используется как фабрика: __call__ записывает ключ и возвращает self."""

    def __init__(self, request_id: str = "fal-req-1", error: Exception | None = None):
        self.request_id = request_id
        self.error = error
        self.api_keys: list[str] = []
        self.image_calls: list[dict] = []
        self.video_calls: list[dict] = []

    def __call__(self, api_key: str):
        self.api_keys.append(api_key)
        return self

    async def submit_image(self, model, prompt, *, image_url=None, provider_params=None, webhook_url):
        if self.error is not None:
            raise self.error
        # Зеркалит выбор маршрута в реальном FalClient.submit_image
        # (app/services/ai/fal_client.py, Fix 1): при наличии image_url --
        # provider_model_id_edit, если он задан, иначе всегда provider_model_id.
        endpoint = (
            (model.provider_model_id_edit or model.provider_model_id)
            if image_url is not None
            else model.provider_model_id
        )
        self.image_calls.append({
            "model": model.code, "prompt": prompt,
            "image_url": image_url, "webhook_url": webhook_url,
            "endpoint": endpoint, "provider_params": provider_params,
        })
        return self.request_id

    async def submit_video(self, model, prompt, *, provider_params=None, webhook_url):
        if self.error is not None:
            raise self.error
        self.video_calls.append({
            "model": model.code, "prompt": prompt,
            "provider_params": provider_params, "webhook_url": webhook_url,
        })
        return self.request_id


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(mgs, "redis_client", fake)
    monkeypatch.setattr(afs, "redis_client", fake)
    return fake


@pytest.fixture(autouse=True)
def fal(monkeypatch):
    fake = FakeFalClient()
    monkeypatch.setattr(mgs, "FalClient", fake)
    monkeypatch.setattr(mgs, "get_key_manager", lambda: FakeKeyManager())
    monkeypatch.setattr(mgs.settings, "backend_public_url", "https://backend.example.com")
    monkeypatch.setattr(mgs.settings, "fal_webhook_secret", "whsec")
    return fake


EXPECTED_WEBHOOK_URL = "https://backend.example.com/api/fal/webhook?secret=whsec"


def _image_model(code="img", *, cost_unit=CostUnit.image, recommended=100,
                 min_credits=0, fixed_cost_usd=0.0, provider_model_id_edit=None) -> AiModel:
    return AiModel(
        provider=ModelProvider.fal, category=ModelCategory.image, code=code,
        display_name=code, provider_model_id=f"fal-ai/{code}", tier=ModelTier.standard,
        cost_unit=cost_unit, min_credits=min_credits, recommended_credits=recommended,
        fixed_cost_usd=fixed_cost_usd, provider_model_id_edit=provider_model_id_edit,
    )


def _video_model(code="vid", *, cost_unit=CostUnit.second, recommended=600,
                 min_credits=0, fixed_cost_usd=0.0) -> AiModel:
    return AiModel(
        provider=ModelProvider.fal, category=ModelCategory.video, code=code,
        display_name=code, provider_model_id=f"fal-ai/{code}", tier=ModelTier.premium,
        cost_unit=cost_unit, min_credits=min_credits, recommended_credits=recommended,
        fixed_cost_usd=fixed_cost_usd,
    )


async def _add_option(
    session, model, *, kind: ModelOptionKind, code: str, params: dict, mult: float,
    is_default: bool = False, is_active: bool = True,
) -> ModelOption:
    """Добавляет строку опции модели напрямую в БД (model уже должен быть
    сохранён -- нужен его id). Зеркалит форму, которую сеет реальный сид."""
    option = ModelOption(
        model_id=model.id, kind=kind, code=code, label=code,
        provider_params=params, credits_multiplier=mult,
        is_default=is_default, is_active=is_active,
    )
    session.add(option)
    await session.commit()
    return option


async def _seed(session, *models, balance=1000, purchased=1, spent=0) -> User:
    user = User(
        telegram_id=1, username="u", credits_balance=balance,
        total_credits_purchased=purchased, total_credits_spent=spent,
    )
    session.add(user)
    for m in models:
        session.add(m)
    await session.commit()
    return user


async def _request_rows(session) -> list[AIRequest]:
    return list((await session.execute(select(AIRequest))).scalars().all())


async def _tx_types(session) -> list[CreditTxType]:
    return [
        row[0]
        for row in (
            await session.execute(
                select(CreditTransaction.type).order_by(CreditTransaction.id)
            )
        ).all()
    ]


# --- успешный старт генерации ---

async def test_image_success_reserves_and_submits(session, fake_redis, fal):
    user = await _seed(session, _image_model())

    request = await start_media_generation(session, user, "img", "a bear")

    assert request.status == RequestStatus.reserved
    assert request.provider == "fal"
    assert request.category == ModelCategory.image
    assert request.model_code == "img"
    assert request.prompt_preview == "a bear"
    assert request.estimated_credits == 100   # 1 image * recommended 100
    assert request.reserved_credits == 100
    assert request.provider_response_id == "fal-req-1"
    assert request.result_url is None  # результат появится только из вебхука

    assert fal.image_calls == [{
        "model": "img", "prompt": "a bear",
        "image_url": None, "webhook_url": EXPECTED_WEBHOOK_URL,
        "endpoint": "fal-ai/img", "provider_params": {},
    }]
    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 900
    assert await _tx_types(session) == [CreditTxType.reserve]
    assert fake_redis.deleted == []  # лок держится до вебхука, НЕ снимается здесь


async def test_image_edit_multiplier_applied_only_for_edit_capable_model(session, fal):
    # У модели ЕСТЬ edit-маршрут -- наценка x1.5 законна.
    user = await _seed(session, _image_model(provider_model_id_edit="fal-ai/img/edit"))

    request = await start_media_generation(
        session, user, "img", "make it night",
        image_url="https://cdn.example.com/in.png",
    )

    # calculate_image_credits(..., is_edit=True): max(ceil(100 * 1.5), 100) = 150
    assert request.estimated_credits == 150
    assert fal.image_calls[0]["image_url"] == "https://cdn.example.com/in.png"


async def test_no_edit_surcharge_for_model_without_edit_route(session, fal):
    """Наценку x1.5 берём ТОЛЬКО с моделей, у которых есть provider_model_id_edit.
    Раньше is_edit = (image_url is not None) без проверки capability: юзер платил
    +50% за фото на qwen_image/seedream, где edit-маршрута нет и фото провайдером
    не используется. Фронт теперь и не даёт прикрепить фото к таким моделям, но
    прямой API-клиент не должен переплачивать за неработающее редактирование."""
    user = await _seed(session, _image_model())  # provider_model_id_edit не задан

    request = await start_media_generation(
        session, user, "img", "make it night",
        image_url="https://cdn.example.com/in.png",
    )

    # is_edit=False -> без x1.5: цена как у обычной генерации (recommended 100).
    assert request.estimated_credits == 100


# --- Fix 1: маршрут i2i/t2i выбирается по provider_model_id_edit ---
# Регрессия: до фикса submit_image всегда слал provider_model_id, даже когда
# у модели был отдельный i2i-маршрут (flux_kontext_pro/nano_banana) -- пользователь
# платил edit-наценку (x1.5), но фактически получал t2i-результат по прежнему PN.

async def test_image_url_with_edit_endpoint_set_uses_edit_route(session, fal):
    model = _image_model(code="kontext", provider_model_id_edit="fal-ai/kontext/edit")
    user = await _seed(session, model)

    await start_media_generation(
        session, user, "kontext", "make it night",
        image_url="https://cdn.example.com/in.png",
    )

    assert fal.image_calls[0]["endpoint"] == "fal-ai/kontext/edit"


async def test_image_url_without_edit_endpoint_falls_back_to_provider_model_id(session, fal):
    user = await _seed(session, _image_model(code="img"))  # provider_model_id_edit не задан

    await start_media_generation(
        session, user, "img", "make it night",
        image_url="https://cdn.example.com/in.png",
    )

    assert fal.image_calls[0]["endpoint"] == "fal-ai/img"


async def test_no_image_url_always_uses_provider_model_id_even_with_edit_route(session, fal):
    model = _image_model(code="kontext", provider_model_id_edit="fal-ai/kontext/edit")
    user = await _seed(session, model)

    await start_media_generation(session, user, "kontext", "a bear")

    assert fal.image_calls[0]["endpoint"] == "fal-ai/kontext"
    assert fal.image_calls[0]["image_url"] is None


async def test_video_uses_default_duration_of_five_seconds(session, fal):
    # Без опций -- множитель 1.0, provider_params пуст (у модели нет опций
    # вовсе, поэтому и дефолта навязывать нечему).
    user = await _seed(session, _video_model())

    request = await start_media_generation(session, user, "vid", "a bear runs")

    assert request.estimated_credits == 600  # recommended_credits * 1.0
    assert fal.video_calls == [{
        "model": "vid", "prompt": "a bear runs",
        "provider_params": {}, "webhook_url": EXPECTED_WEBHOOK_URL,
    }]


async def test_video_duration_scales_credits_and_is_passed_to_fal(session, fal):
    model = _video_model(recommended=600)
    user = await _seed(session, model, balance=2000)
    await _add_option(session, model, kind=ModelOptionKind.duration, code="10s",
                      params={"duration": "10"}, mult=2.0)

    request = await start_media_generation(
        session, user, "vid", "a bear runs", option_codes={"duration": "10s"}, confirm=True
    )

    assert request.estimated_credits == 1200  # ceil(600 * 2.0); >1000 -> нужен confirm
    assert fal.video_calls[0]["provider_params"] == {"duration": "10"}


# --- provider_cost_usd (фаза 6) ---

async def test_image_start_fills_provider_cost_usd(session, fal):
    user = await _seed(session, _image_model(fixed_cost_usd=0.04))

    request = await start_media_generation(session, user, "img", "a bear")

    # cost_unit=image: 1 * fixed_cost_usd = 0.04, считается на reserve
    assert float(request.provider_cost_usd) == pytest.approx(0.04)


async def test_image_edit_does_not_multiply_provider_cost_usd(session, fal):
    # edit-множитель применяется только к edit-capable модели, поэтому маршрут задан.
    user = await _seed(session, _image_model(
        fixed_cost_usd=0.04, provider_model_id_edit="fal-ai/img/edit"))

    request = await start_media_generation(
        session, user, "img", "make it night",
        image_url="https://cdn.example.com/in.png",
    )

    # Кредиты с edit-множителем (150), себестоимость -- без него (fal берёт столько же)
    assert request.estimated_credits == 150
    assert float(request.provider_cost_usd) == pytest.approx(0.04)


async def test_video_start_fills_provider_cost_usd(session, fal):
    user = await _seed(session, _video_model(fixed_cost_usd=0.5), balance=2000)

    request = await start_media_generation(session, user, "vid", "a bear runs")

    # cost_unit=second: провайдерская себестоимость всегда считается по
    # VIDEO_DEFAULT_DURATION_SECONDS (5с) -- это отдельная забота от
    # пользовательской цены, которую задаёт опция duration (см. бриф Task 6).
    # 5/5 * 0.5 = 0.5
    assert float(request.provider_cost_usd) == pytest.approx(0.5)


# --- подтверждение дорогого запроса ---

async def test_expensive_image_without_confirm_raises(session, fake_redis, fal):
    user = await _seed(session, _image_model(recommended=400))

    with pytest.raises(ConfirmationRequiredError) as exc_info:
        await start_media_generation(session, user, "img", "a bear")

    assert exc_info.value.estimated_credits == 400  # > 300
    assert fal.image_calls == []
    assert await _request_rows(session) == []
    assert await _tx_types(session) == []
    # порог проверяется ДО лока -- лок не брался и не снимался
    assert fake_redis.deleted == []


async def test_image_at_threshold_does_not_require_confirm(session, fal):
    user = await _seed(session, _image_model(recommended=300))
    request = await start_media_generation(session, user, "img", "a bear")
    assert request.estimated_credits == 300  # порог строго "больше": ровно 300 проходит


async def test_expensive_video_without_confirm_raises(session, fal):
    user = await _seed(
        session, _video_model(cost_unit=CostUnit.video, recommended=1500), balance=2000
    )

    with pytest.raises(ConfirmationRequiredError) as exc_info:
        await start_media_generation(session, user, "vid", "a bear runs")

    assert exc_info.value.estimated_credits == 1500  # > 1000
    assert await _request_rows(session) == []


# --- недостаточный баланс ---

async def test_insufficient_balance_rolls_back_and_releases_lock(session, fake_redis, fal):
    user = await _seed(session, _image_model(), balance=50)
    user_id = user.id  # захват ДО rollback (см. комментарий в test_text_generation_service.py)

    with pytest.raises(InsufficientBalanceError):
        await start_media_generation(session, user, "img", "a bear")

    assert await _request_rows(session) == []   # pending-запись откатилась
    assert await _tx_types(session) == []
    fetched = await session.get(User, user_id)
    assert fetched.credits_balance == 50
    assert fake_redis.deleted == [f"ai_lock:{user_id}"]  # синхронная ошибка -> лок снят


# --- per-user лок ---

async def test_busy_lock_raises_request_in_progress(session, monkeypatch, fal):
    user = await _seed(session, _image_model())
    monkeypatch.setattr(mgs, "redis_client", FakeRedis(locked=True))

    with pytest.raises(RequestInProgressError):
        await start_media_generation(session, user, "img", "a bear")

    assert await _request_rows(session) == []
    assert await _tx_types(session) == []


# --- ошибка submit -> refund ---

async def test_submit_failure_refunds_and_releases_lock(session, fake_redis, monkeypatch):
    # fixed_cost_usd>0 -- provider_cost_usd проставляется на reserve (ДО submit),
    # проверяем, что refund его зануляет (Finding 1), т.к. submit не прошёл.
    user = await _seed(session, _image_model(fixed_cost_usd=0.04))
    broken = FakeFalClient(error=RuntimeError("fal down"))
    monkeypatch.setattr(mgs, "FalClient", broken)

    with pytest.raises(AIError):
        await start_media_generation(session, user, "img", "a bear")

    [request] = await _request_rows(session)
    # Синхронная ошибка submit -- подтверждённая ошибка провайдера (Finding 2).
    assert request.status == RequestStatus.failed
    assert request.charged_credits == 0
    assert request.provider_cost_usd == 0
    assert "fal down" in request.error_message
    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 1000  # резерв возвращён полностью
    assert await _tx_types(session) == [CreditTxType.reserve, CreditTxType.refund]
    assert fake_redis.deleted == [f"ai_lock:{user.id}"]


# --- резолв модели ---

async def test_unknown_model_code_raises_model_not_found(session, fal):
    user = await _seed(session, _image_model())
    with pytest.raises(ModelNotFoundError):
        await start_media_generation(session, user, "no_such_model", "a bear")


async def test_text_model_is_not_a_media_model(session, fal):
    text_model = AiModel(
        provider=ModelProvider.openrouter, category=ModelCategory.text, code="txt",
        display_name="txt", provider_model_id="vendor/txt", tier=ModelTier.economy,
        cost_unit=CostUnit.tokens, min_credits=3, recommended_credits=3,
    )
    user = await _seed(session, text_model)
    with pytest.raises(ModelNotFoundError):
        await start_media_generation(session, user, "txt", "a bear")


# --- get_generation (owner-scoped) ---

async def test_get_generation_returns_own_request(session, fal):
    user = await _seed(session, _image_model())
    request = await start_media_generation(session, user, "img", "a bear")

    found = await get_generation(session, user, request.id)

    assert found is not None
    assert found.id == request.id


async def test_get_generation_hides_foreign_and_missing_requests(session, fal):
    user = await _seed(session, _image_model())
    request = await start_media_generation(session, user, "img", "a bear")
    other = User(telegram_id=2, username="other", credits_balance=0)
    session.add(other)
    await session.commit()

    assert await get_generation(session, other, request.id) is None
    assert await get_generation(session, user, request.id + 100) is None


# --- handle_fal_webhook ---

def _ok_payload(request_id="fal-req-1", url="https://cdn.fal.media/out.png") -> dict:
    return {"request_id": request_id, "status": "OK", "payload": {"images": [{"url": url}]}}


async def test_webhook_ok_settles_and_stores_result_url(session, fake_redis, fal):
    user = await _seed(session, _image_model())
    request = await start_media_generation(session, user, "img", "a bear")
    assert fake_redis.deleted == []  # лок держится весь round-trip

    await handle_fal_webhook(session, _ok_payload())

    await session.refresh(request)
    assert request.status == RequestStatus.completed
    # результат -- в durable-колонке ai_requests.result_url, не в Redis
    assert request.result_url == "https://cdn.fal.media/out.png"
    assert request.charged_credits == 100
    assert request.completed_at is not None
    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 900
    # actual == reserved -> settle без корректирующей транзакции (штатный путь)
    assert await _tx_types(session) == [CreditTxType.reserve]
    assert fake_redis.deleted == [f"ai_lock:{user.id}"]


# --- Task 3: реферальный бонус по успешному вебхуку ---

async def test_webhook_ok_grants_referral_bonus_to_referrer(session, fake_redis, fal):
    """Приглашённый (Referral на него) успешно завершает генерацию через
    вебхук OK -> пригласившему начисляется бонус в ТОЙ ЖЕ транзакции (до commit)."""
    referrer = User(telegram_id=999, username="referrer", credits_balance=0)
    session.add(referrer)
    await session.flush()

    referred = await _seed(session, _image_model())  # приглашённый делает запрос
    session.add(Referral(referrer_user_id=referrer.id, referred_user_id=referred.id))
    session.add_all([
        Setting(key="referral_bonus_referrer_credits", value="20", type="int"),
        Setting(key="referral_bonus_referred_credits", value="0", type="int"),
    ])
    await session.commit()

    await start_media_generation(session, referred, "img", "a bear")
    await handle_fal_webhook(session, _ok_payload())

    fetched_referrer = await session.get(User, referrer.id)
    assert fetched_referrer.credits_balance == 20  # бонус начислен после успешного OK

    referral = (await session.execute(select(Referral))).scalar_one()
    assert referral.bonus_granted is True
    assert referral.bonus_credits == 20


async def test_webhook_error_does_not_grant_referral_bonus(session, fake_redis, fal):
    """ERROR-ветка -- запрос не успешен, бонус не начисляется (только OK-ветка)."""
    referrer = User(telegram_id=999, username="referrer", credits_balance=0)
    session.add(referrer)
    await session.flush()

    referred = await _seed(session, _image_model(fixed_cost_usd=0.04))
    session.add(Referral(referrer_user_id=referrer.id, referred_user_id=referred.id))
    session.add_all([
        Setting(key="referral_bonus_referrer_credits", value="20", type="int"),
        Setting(key="referral_bonus_referred_credits", value="0", type="int"),
    ])
    await session.commit()

    await start_media_generation(session, referred, "img", "a bear")
    await handle_fal_webhook(
        session, {"request_id": "fal-req-1", "status": "ERROR", "error": "nsfw content"}
    )

    fetched_referrer = await session.get(User, referrer.id)
    assert fetched_referrer.credits_balance == 0  # бонус НЕ начислен -- запрос failed

    referral = (await session.execute(select(Referral))).scalar_one()
    assert referral.bonus_granted is False


async def test_webhook_ok_extracts_video_url(session, fal):
    user = await _seed(session, _video_model(), balance=2000)
    request = await start_media_generation(session, user, "vid", "a bear runs")

    await handle_fal_webhook(session, {
        "request_id": "fal-req-1", "status": "OK",
        "payload": {"video": {"url": "https://cdn.fal.media/out.mp4"}},
    })

    await session.refresh(request)
    assert request.status == RequestStatus.completed
    assert request.result_url == "https://cdn.fal.media/out.mp4"


async def test_webhook_error_refunds_and_releases_lock(session, fake_redis, fal):
    user = await _seed(session, _image_model(fixed_cost_usd=0.04))
    request = await start_media_generation(session, user, "img", "a bear")

    await handle_fal_webhook(
        session, {"request_id": "fal-req-1", "status": "ERROR", "error": "nsfw content"}
    )

    await session.refresh(request)
    # fal явно сообщил об ошибке -- подтверждённый provider error (Finding 2).
    assert request.status == RequestStatus.failed
    assert request.charged_credits == 0
    assert request.provider_cost_usd == 0  # Finding 1: ничего не доставлено
    assert request.error_message == "nsfw content"
    assert request.result_url is None
    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 1000  # резерв возвращён полностью
    assert await _tx_types(session) == [CreditTxType.reserve, CreditTxType.refund]
    assert fake_redis.deleted == [f"ai_lock:{user.id}"]


async def test_webhook_duplicate_delivery_is_idempotent(session, fake_redis, fal):
    user = await _seed(session, _image_model())
    request = await start_media_generation(session, user, "img", "a bear")

    await handle_fal_webhook(session, _ok_payload())
    await handle_fal_webhook(session, _ok_payload())  # повторная доставка

    await session.refresh(request)
    assert request.status == RequestStatus.completed
    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 900               # не списано второй раз
    assert await _tx_types(session) == [CreditTxType.reserve]
    assert fake_redis.deleted == [f"ai_lock:{user.id}"]  # лок снят ровно один раз


async def test_webhook_unknown_request_id_is_noop(session, fake_redis, fal):
    user = await _seed(session, _image_model())
    await start_media_generation(session, user, "img", "a bear")

    await handle_fal_webhook(session, _ok_payload(request_id="someone-elses-id"))

    [request] = await _request_rows(session)
    assert request.status == RequestStatus.reserved  # ничего не изменилось
    assert fake_redis.deleted == []                  # лок не тронут


async def test_webhook_missing_request_id_is_noop(session, fal):
    user = await _seed(session, _image_model())
    await start_media_generation(session, user, "img", "a bear")

    await handle_fal_webhook(session, {"status": "OK", "payload": {}})

    [request] = await _request_rows(session)
    assert request.status == RequestStatus.reserved


async def test_webhook_ok_without_extractable_url_refunds(session, fake_redis, fal):
    user = await _seed(session, _image_model(fixed_cost_usd=0.04))
    request = await start_media_generation(session, user, "img", "a bear")

    await handle_fal_webhook(
        session,
        {"request_id": "fal-req-1", "status": "OK", "payload": {"unexpected": True}},
    )

    await session.refresh(request)
    # URL извлечь не удалось -> кредиты за недоставленный результат не списываем.
    # Малформленный success-ответ -- подтверждённая provider-side ошибка (Finding 2).
    assert request.status == RequestStatus.failed
    assert request.charged_credits == 0
    assert request.provider_cost_usd == 0  # Finding 1: ничего не доставлено
    assert request.result_url is None
    assert request.error_message == "fal webhook: could not extract result url"
    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 1000
    assert fake_redis.deleted == [f"ai_lock:{user.id}"]


# --- reconciliation: возврат кредитов за "зависшие" reserved-запросы ---


async def _seed_reserved_request(
    session, user, model, *, reserved_credits=100, age_minutes=30, status=RequestStatus.reserved
) -> AIRequest:
    """Имитирует состояние ПОСЛЕ start_media_generation: AIRequest в статусе
    reserved (или другом, для теста игнорирования) и баланс уже списан на
    reserved_credits -- как в test_concurrent_webhook_delivery_settles_exactly_once,
    где резерв воссоздаётся напрямую, без вызова start_media_generation."""
    created_at = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
    request = AIRequest(
        user_id=user.id,
        provider="fal",
        model_code=model.code,
        category=model.category,
        status=status,
        prompt_preview="stale",
        estimated_credits=reserved_credits,
        reserved_credits=reserved_credits,
        charged_credits=reserved_credits if status == RequestStatus.completed else 0,
        provider_response_id=f"fal-stale-{user.id}",
        created_at=created_at,
    )
    session.add(request)

    balance_before = user.credits_balance
    user.credits_balance = balance_before - reserved_credits
    tx = CreditTransaction(
        user_id=user.id,
        type=CreditTxType.reserve,
        amount=-reserved_credits,
        balance_before=balance_before,
        balance_after=user.credits_balance,
        provider="fal",
        model_code=model.code,
        request_id=None,
    )
    session.add(tx)
    await session.flush()
    tx.request_id = request.id
    await session.commit()
    await session.refresh(request)
    return request


async def test_refund_stale_reserved_requests_refunds_old_reserves(session, fake_redis):
    # fixed_cost_usd>0 -- provider_cost_usd был проставлен на reserve; здесь
    # проверяем, что даже для 5-го (нетронутого) call site refund_request
    # по-прежнему зануляет provider_cost_usd (Finding 1 применяется независимо
    # от того, какой final_status используется -- это неоднозначный случай,
    # поэтому final_status остаётся дефолтным refunded, см. Finding 2).
    model = _image_model(fixed_cost_usd=0.04)
    user = await _seed(session, model)
    request = await _seed_reserved_request(session, user, model, age_minutes=30)
    request.provider_cost_usd = 0.04
    await session.commit()

    count = await refund_stale_reserved_requests(session, older_than_minutes=20)

    assert count == 1
    await session.refresh(request)
    # Неоднозначный случай (вебхук так и не пришёл) -- final_status остаётся
    # дефолтным refunded, НЕ failed (5-й call site умышленно не тронут).
    assert request.status == RequestStatus.refunded
    assert request.charged_credits == 0
    assert request.provider_cost_usd == 0
    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 1000  # резерв (100) возвращён полностью
    assert fake_redis.deleted == [f"ai_lock:{user.id}"]


async def test_refund_stale_reserved_requests_ignores_recent_reserves(session, fake_redis):
    model = _image_model()
    user = await _seed(session, model)
    request = await _seed_reserved_request(session, user, model, age_minutes=1)

    count = await refund_stale_reserved_requests(session, older_than_minutes=20)

    assert count == 0
    await session.refresh(request)
    assert request.status == RequestStatus.reserved
    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 900  # резерв всё ещё удержан
    assert fake_redis.deleted == []


async def test_refund_stale_reserved_requests_ignores_non_reserved_status(session, fake_redis):
    model = _image_model()
    user = await _seed(session, model)
    request = await _seed_reserved_request(
        session, user, model, age_minutes=30, status=RequestStatus.completed
    )

    count = await refund_stale_reserved_requests(session, older_than_minutes=20)

    assert count == 0
    await session.refresh(request)
    assert request.status == RequestStatus.completed  # без изменений, без двойного возврата
    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 900
    assert fake_redis.deleted == []


async def test_refund_stale_reserved_requests_handles_multiple_users(session, fake_redis):
    model = _image_model()
    user1 = await _seed(session, model)
    user2 = User(telegram_id=2, username="u2", credits_balance=500)
    session.add(user2)
    await session.commit()

    request1 = await _seed_reserved_request(
        session, user1, model, reserved_credits=100, age_minutes=30
    )
    request2 = await _seed_reserved_request(
        session, user2, model, reserved_credits=50, age_minutes=45
    )

    count = await refund_stale_reserved_requests(session, older_than_minutes=20)

    assert count == 2
    await session.refresh(request1)
    await session.refresh(request2)
    assert request1.status == RequestStatus.refunded
    assert request2.status == RequestStatus.refunded

    fetched1 = await session.get(User, user1.id)
    fetched2 = await session.get(User, user2.id)
    assert fetched1.credits_balance == 1000  # 1000 - 100 + 100
    assert fetched2.credits_balance == 500   # 500 - 50 + 50, без перекрёстного влияния

    assert set(fake_redis.deleted) == {f"ai_lock:{user1.id}", f"ai_lock:{user2.id}"}


async def test_refund_stale_reserved_requests_skips_request_settled_concurrently(
    session, fake_redis
):
    """Гонка: настоящий (не потерянный) вебхук settle-ит запрос ПОСЛЕ того, как
    sweep уже прочитал его как reserved через SELECT, но ДО того, как sweep
    дошёл до refund. Атомарный claim в refund_stale_reserved_requests должен
    получить rowcount=0 и пропустить строку, не откатывая settle обратно."""
    model = _image_model()
    user = await _seed(session, model)
    request = await _seed_reserved_request(session, user, model, age_minutes=30)

    # "Вебхук выиграл гонку": settle-им запрос напрямую, как это сделал бы
    # handle_fal_webhook в своей OK-ветке, ДО вызова sweep.
    await settle_request(session, request, request.estimated_credits)
    await session.commit()
    await session.refresh(request)
    assert request.status == RequestStatus.completed
    assert request.charged_credits == 100

    count = await refund_stale_reserved_requests(session, older_than_minutes=20)

    assert count == 0  # ничего не возвращено -- claim не сработал, запрос уже settled
    await session.refresh(request)
    assert request.status == RequestStatus.completed  # не откатился на refunded
    assert request.charged_credits == 100  # реальная settled-сумма не тронута
    fetched = await session.get(User, user.id)
    # Баланс отражает реальный settle (900, резерв уже списан settle'ом), без
    # спурного возврата поверх него.
    assert fetched.credits_balance == 900
    assert fake_redis.deleted == []  # sweep не трогал лок несобственной строки


# --- Конкурентная доставка вебхука: интеграционный тест с реальным Postgres ---
# Как test_concurrent_reserve_cannot_overdraw_balance в test_credit_service.py:
# SQLite не берёт настоящих row-level локов на UPDATE, поэтому доказать, что
# claim-UPDATE (WHERE status='reserved') в handle_fal_webhook действительно
# защищает от двойного settle при ИСТИННО параллельных транзакциях (не просто
# последовательной повторной доставке, как в
# test_webhook_duplicate_delivery_is_idempotent выше), можно только на
# настоящем Postgres. Задайте TEST_DATABASE_URL на ОДНОРАЗОВУЮ базу, например:
#   postgresql+asyncpg://postgres:postgres@localhost:5432/ai_hub_test
# Тест делает drop_all/create_all -- не указывайте рабочую базу.

POSTGRES_TEST_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.mark.skipif(
    not POSTGRES_TEST_URL,
    reason="TEST_DATABASE_URL not set; row-lock test requires a real Postgres",
)
async def test_concurrent_webhook_delivery_settles_exactly_once():
    engine = create_async_engine(POSTGRES_TEST_URL)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)

        async with maker() as s:
            user = User(telegram_id=998, username="racer2", credits_balance=100)
            s.add(user)
            model = _image_model(code="race-img")
            s.add(model)
            await s.flush()
            # reserved=50 отражает состояние после reserve_credits (баланс уже
            # списан на этапе start_media_generation); estimated=30 нарочно
            # отличается от reserved, чтобы settle_request создал
            # корректирующую transaction (release) с ненулевой суммой -- это
            # даёт однозначно считаемый сигнал: если бы вебхук settle'ил
            # дважды, release создался бы дважды и баланс "уполз" бы выше 70.
            request = AIRequest(
                user_id=user.id,
                provider="fal",
                model_code=model.code,
                category=ModelCategory.image,
                status=RequestStatus.reserved,
                prompt_preview="race",
                estimated_credits=30,
                reserved_credits=50,
                provider_response_id="fal-req-race",
            )
            s.add(request)
            user.credits_balance = 50  # состояние после reserve (100 - 50)
            await s.commit()
            user_id = user.id
            request_id = request.id

        payload = {
            "request_id": "fal-req-race",
            "status": "OK",
            "payload": {"images": [{"url": "https://cdn.fal.media/race.png"}]},
        }

        async def deliver():
            # Отдельная сессия = отдельное соединение = отдельная транзакция,
            # как try_reserve() в test_concurrent_reserve_cannot_overdraw_balance.
            async with maker() as s:
                await handle_fal_webhook(s, payload)

        await asyncio.gather(deliver(), deliver())

        async with maker() as s:
            fetched_request = await s.get(AIRequest, request_id)
            assert fetched_request.status == RequestStatus.completed
            assert fetched_request.charged_credits == 30

            fetched_user = await s.get(User, user_id)
            # 50 (после reserve) + 20 (release 50-30) = 70 ровно один раз --
            # НЕ 90, что было бы при двойном settle одной и той же доставки.
            assert fetched_user.credits_balance == 70

            release_count = (
                await s.execute(
                    select(func.count())
                    .select_from(CreditTransaction)
                    .where(
                        CreditTransaction.request_id == request_id,
                        CreditTransaction.type == CreditTxType.release,
                    )
                )
            ).scalar_one()
            assert release_count == 1, "settle must apply exactly once under concurrent delivery"
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


# --- antifraud (фаза 5) ---

async def test_duplicate_media_prompt_within_cooldown_is_rejected(session, fal):
    user = await _seed(session, _image_model())

    await start_media_generation(session, user, "img", "a bear")
    with pytest.raises(DuplicateRequestError):
        await start_media_generation(session, user, "img", "a bear")

    assert len(fal.image_calls) == 1
    assert len(await _request_rows(session)) == 1


async def test_media_user_rate_limit_rejects_over_limit(session, fake_redis, fal):
    user = await _seed(session, _image_model())
    bucket = afs._minute_bucket()
    fake_redis.store[f"rate_limit:user:{user.id}:{bucket}"] = "10"

    with pytest.raises(RateLimitExceededError):
        await start_media_generation(session, user, "img", "a bear")

    assert fal.image_calls == []
    assert await _request_rows(session) == []


async def test_video_blocked_until_first_purchase(session, fake_redis, fal):
    user = await _seed(session, _video_model(), purchased=0)

    with pytest.raises(TierNotAllowedError):
        await start_media_generation(session, user, "vid", "a bear runs")

    assert fal.video_calls == []
    assert await _request_rows(session) == []
    assert fake_redis.deleted == []  # отказ ДО взятия лока


async def test_free_tier_cap_blocks_media_over_cap(session, fal):
    # cap=100, spent=50, оценка image = 100 -> 50 + 100 > 100.
    user = await _seed(session, _image_model(), purchased=0, spent=50)

    with pytest.raises(FreeTierLimitExceededError):
        await start_media_generation(session, user, "img", "a bear")

    assert await _request_rows(session) == []


async def test_daily_spend_limit_blocks_media(session, fake_redis, fal):
    user = await _seed(session, _image_model())
    fake_redis.store[afs._daily_spend_key(user.id)] = "9950"  # 9950 + 100 > 10000

    with pytest.raises(DailySpendLimitExceededError):
        await start_media_generation(session, user, "img", "a bear")

    assert await _request_rows(session) == []
    assert fake_redis.store[afs._daily_spend_key(user.id)] == "9950"


async def test_start_records_daily_spend(session, fake_redis, fal):
    user = await _seed(session, _image_model())

    await start_media_generation(session, user, "img", "a bear")

    assert fake_redis.store[afs._daily_spend_key(user.id)] == "100"


async def test_submit_failure_decrements_daily_spend(session, fake_redis, monkeypatch):
    user = await _seed(session, _image_model())
    monkeypatch.setattr(mgs, "FalClient", FakeFalClient(error=RuntimeError("fal down")))

    with pytest.raises(AIError):
        await start_media_generation(session, user, "img", "a bear")

    assert fake_redis.store[afs._daily_spend_key(user.id)] == "0"


async def test_webhook_error_decrements_daily_spend(session, fake_redis, fal):
    user = await _seed(session, _image_model())
    await start_media_generation(session, user, "img", "a bear")
    assert fake_redis.store[afs._daily_spend_key(user.id)] == "100"

    await handle_fal_webhook(
        session, {"request_id": "fal-req-1", "status": "ERROR", "error": "nsfw content"}
    )

    assert fake_redis.store[afs._daily_spend_key(user.id)] == "0"


async def test_webhook_ok_keeps_daily_spend(session, fake_redis, fal):
    # actual == estimated -> settle без корректировки, счётчик остаётся равным списанию.
    user = await _seed(session, _image_model())
    await start_media_generation(session, user, "img", "a bear")

    await handle_fal_webhook(session, _ok_payload())

    assert fake_redis.store[afs._daily_spend_key(user.id)] == "100"


async def test_reconcile_refund_decrements_daily_spend(session, fake_redis):
    model = _image_model()
    user = await _seed(session, model)
    await _seed_reserved_request(session, user, model, reserved_credits=100, age_minutes=30)
    fake_redis.store[afs._daily_spend_key(user.id)] = "100"  # состояние после record при reserve

    count = await refund_stale_reserved_requests(session, older_than_minutes=20)

    assert count == 1
    assert fake_redis.store[afs._daily_spend_key(user.id)] == "0"


async def test_worker_rejection_body_refunds_credits(session, fal, fake_redis):
    """Наблюдалось вживую 2026-07-15: сломанный эндпоинт fal-ai/wan/v2.2 --
    очередь приняла запрос (кредиты зарезервированы), а воркер вернул
    {"detail": "Path /v2.2 not found"} вместо результата.

    extract_result_url не найдёт ни images, ни video -> вернёт None ->
    кредиты обязаны вернуться, иначе пользователь платит за 404.
    """
    user = await _seed(session, _image_model())
    await start_media_generation(session, user, "img", "a bear")
    assert (await session.get(User, user.id)).credits_balance == 900  # 100 зарезервировано

    await handle_fal_webhook(session, {
        "request_id": "fal-req-1",
        "status": "OK",
        "payload": {"detail": "Path /v2.2 not found"},
    })

    assert (await session.get(User, user.id)).credits_balance == 1000  # вернулись
    rows = await _request_rows(session)
    assert rows[0].status == RequestStatus.failed
    assert await _tx_types(session) == [CreditTxType.reserve, CreditTxType.refund]


async def test_worker_validation_error_body_refunds_credits(session, fal, fake_redis):
    """Вторая наблюдённая форма отказа: pydantic-ошибка воркера списком.
    fal при этом отдаёт status=ERROR."""
    user = await _seed(session, _image_model())
    await start_media_generation(session, user, "img", "a bear")

    await handle_fal_webhook(session, {
        "request_id": "fal-req-1",
        "status": "ERROR",
        "payload": {"detail": [
            {"type": "missing", "loc": ["body", "prompt"], "msg": "Field required"}
        ]},
    })

    assert (await session.get(User, user.id)).credits_balance == 1000
    assert await _tx_types(session) == [CreditTxType.reserve, CreditTxType.refund]


# --- Task 6: резолв опций (option_codes -> множитель + provider_params) ---

async def test_options_multiply_price_and_reach_provider(session, fal):
    model = _video_model(recommended=3220, min_credits=3220)
    user = await _seed(session, model, balance=10000)
    await _add_option(session, model, kind=ModelOptionKind.duration, code="10s",
                      params={"duration": "10"}, mult=2.0)

    # confirm=True: 6440 > VIDEO_CONFIRM_THRESHOLD_CREDITS (1000) -- у kling уже
    # база (3220) выше порога, это отдельная забота (антифрод-подтверждение),
    # не то, что проверяет этот тест (композицию множителя опции).
    request = await start_media_generation(
        session, user, model.code, "a cube",
        option_codes={"duration": "10s"}, confirm=True,
    )

    assert request.estimated_credits == 6440  # 3220 * 2.0
    assert fal.video_calls[-1]["provider_params"] == {"duration": "10"}


async def test_default_option_used_when_code_absent(session, fal):
    model = _video_model(recommended=3220, min_credits=3220)
    user = await _seed(session, model, balance=10000)
    await _add_option(session, model, kind=ModelOptionKind.duration, code="5s",
                      params={"duration": "5"}, mult=1.0, is_default=True)

    # confirm=True: та же причина, что в test_options_multiply_price_and_reach_provider --
    # 3220 (база kling) уже выше VIDEO_CONFIRM_THRESHOLD_CREDITS сама по себе.
    request = await start_media_generation(
        session, user, model.code, "a cube", confirm=True
    )

    assert request.estimated_credits == 3220
    assert fal.video_calls[-1]["provider_params"] == {"duration": "5"}


async def test_unknown_option_code_raises(session, fal):
    """400, не тихий дефолт: молчаливый откат вернёт нас ровно к тому,
    от чего уходим -- контролу, который делает не то, что показывает."""
    model = _video_model()
    user = await _seed(session, model, balance=10000)
    await _add_option(session, model, kind=ModelOptionKind.duration, code="5s",
                      params={"duration": "5"}, mult=1.0, is_default=True)

    with pytest.raises(UnknownOptionError):
        await start_media_generation(
            session, user, model.code, "a cube", option_codes={"duration": "99s"}
        )


async def test_inactive_option_rejected(session, fal):
    model = _video_model()
    user = await _seed(session, model, balance=10000)
    await _add_option(session, model, kind=ModelOptionKind.duration, code="10s",
                      params={"duration": "10"}, mult=2.0, is_active=False)
    with pytest.raises(UnknownOptionError):
        await start_media_generation(
            session, user, model.code, "a cube", option_codes={"duration": "10s"}
        )


async def test_unknown_option_kind_with_no_options_raises(session, fal):
    """Модель без единой опции вида quality (аналог kling_video, у которой
    нет размерного knob'а -- только aspect_ratio) должна ОТКАЗАТЬ на
    option_codes={"quality": ...}, а не молча проигнорировать код.

    Это защита именно пре-валидационного прохода в _resolve_options: он
    сверяет requested-коды со ВСЕМИ {k.value for k in by_kind} ДО основного
    цикла, который сам идёт по by_kind и потому "чужой" kind никогда не
    увидит. Без этого прохода запрос с {"quality": "4k"} к модели без
    quality-опций был бы тихо отброшен: спишется базовая цена, а на fal
    улетит generation без единого resolution-параметра -- ровно тот класс
    молчаливой порчи контрола, который весь этот план должен исключить.
    Тест специально не даёт модели вообще НИ ОДНОЙ опции вида quality
    (в отличие от test_unknown_option_code_raises, где kind duration у
    модели есть, просто код не тот), чтобы упасть именно на пре-проходе,
    а не на поиске совпадения кода внутри цикла.
    """
    model = _video_model()
    user = await _seed(session, model, balance=10000)
    await _add_option(session, model, kind=ModelOptionKind.duration, code="5s",
                      params={"duration": "5"}, mult=1.0, is_default=True)

    with pytest.raises(UnknownOptionError):
        await start_media_generation(
            session, user, model.code, "a cube", option_codes={"quality": "4k"}
        )


async def test_multiple_kinds_compose(session, fal):
    """Veo: длительность и звук -- независимые оси, множители перемножаются,
    provider_params сливаются."""
    model = _video_model(recommended=7360, min_credits=1840)
    user = await _seed(session, model, balance=100000)
    await _add_option(session, model, kind=ModelOptionKind.duration, code="4s",
                      params={"duration": "4s"}, mult=0.5)
    await _add_option(session, model, kind=ModelOptionKind.audio, code="off",
                      params={"generate_audio": False}, mult=0.5)

    # confirm=True: 1840 > VIDEO_CONFIRM_THRESHOLD_CREDITS (1000) -- независимо
    # от опций у Veo уже такая база; проверяем композицию множителей, не gate.
    request = await start_media_generation(
        session, user, model.code, "a cube",
        option_codes={"duration": "4s", "audio": "off"}, confirm=True,
    )

    assert request.estimated_credits == 1840  # 7360 * 0.5 * 0.5
    assert fal.video_calls[-1]["provider_params"] == {"duration": "4s", "generate_audio": False}
