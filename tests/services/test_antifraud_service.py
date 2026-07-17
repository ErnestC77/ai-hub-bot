import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.enums import CostUnit, ModelCategory, ModelProvider, ModelTier
from app.db.models import AiModel, Setting, User
from app.services import antifraud_service as afs
from app.services.antifraud_service import (
    AntifraudSettings,
    DailySpendLimitExceededError,
    DuplicateRequestError,
    FreeTierLimitExceededError,
    RateLimitExceededError,
    TierNotAllowedError,
    check_daily_spend_limit,
    check_duplicate_request,
    check_free_tier_cap,
    check_rate_limits,
    check_tier_allowed,
    load_antifraud_settings,
    record_daily_spend,
)


class FakeRedis:
    """In-memory Redis: set(nx)/get/delete/incr/incrby/decrby/expire.

    locked=True отклоняет ТОЛЬКО попытку взять ai_lock:* (эмуляция занятого
    per-user лока) -- antifraud-ключи (dup:*, rate_limit:*, daily_spend:*)
    живут как обычно. Тот же класс копируется в generation-тесты (Tasks 4-5).
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


DEFAULTS = AntifraudSettings()


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(afs, "redis_client", fake)
    return fake


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


def _user(*, purchased=0, spent=0) -> User:
    return User(
        telegram_id=1, username="u", credits_balance=1000,
        total_credits_purchased=purchased, total_credits_spent=spent,
    )


def _model(*, category=ModelCategory.text, tier=ModelTier.economy, free_tier=False) -> AiModel:
    cost_unit = CostUnit.tokens if category == ModelCategory.text else CostUnit.image
    provider = ModelProvider.openrouter if category == ModelCategory.text else ModelProvider.fal
    return AiModel(
        provider=provider, category=category, code="m", display_name="m",
        provider_model_id="x/m", tier=tier, cost_unit=cost_unit,
        min_credits=0, recommended_credits=1,
        # Задаём явно: у transient-объекта незаданный столбец равен None, а не
        # False (default применяется только на flush) -- без этого «модель не
        # бесплатного тарифа» и «модель, о которой мы не спросили» неразличимы.
        free_tier_allowed=free_tier,
    )


# --- AntifraudSettings / load_antifraud_settings ---

def test_defaults_match_phase5_seed():
    assert DEFAULTS == AntifraudSettings(
        daily_spend_limit_credits=10_000,
        rate_limit_per_user_per_minute=10,
        rate_limit_per_model_per_minute=60,
        duplicate_cooldown_seconds=5,
        free_tier_credit_cap=100,
    )


async def test_load_antifraud_settings_empty_db_uses_defaults(session):
    assert await load_antifraud_settings(session) == DEFAULTS


async def test_load_antifraud_settings_reads_overrides(session):
    session.add(Setting(key="daily_spend_limit_credits", value="5000", type="int"))
    session.add(Setting(key="free_tier_credit_cap", value="250", type="int"))
    await session.commit()

    loaded = await load_antifraud_settings(session)
    assert loaded.daily_spend_limit_credits == 5000
    assert loaded.free_tier_credit_cap == 250
    assert loaded.rate_limit_per_user_per_minute == 10  # остальные -- дефолты


# --- check_duplicate_request ---

async def test_duplicate_first_request_passes_and_sets_cooldown_key(fake_redis):
    await check_duplicate_request(1, "deepseek_v3", "привет", settings=DEFAULTS)

    [key] = list(fake_redis.store)
    assert key.startswith("dup:1:")
    assert len(key.split(":")[2]) == 16  # sha256(model_code+prompt)[:16]
    assert fake_redis.expire_calls == [(key, 5)]  # TTL = duplicate_cooldown_seconds


async def test_duplicate_repeat_within_cooldown_raises(fake_redis):
    await check_duplicate_request(1, "deepseek_v3", "привет", settings=DEFAULTS)
    with pytest.raises(DuplicateRequestError):
        await check_duplicate_request(1, "deepseek_v3", "привет", settings=DEFAULTS)


async def test_duplicate_different_prompt_or_user_passes(fake_redis):
    await check_duplicate_request(1, "deepseek_v3", "привет", settings=DEFAULTS)
    await check_duplicate_request(1, "deepseek_v3", "другой prompt", settings=DEFAULTS)
    await check_duplicate_request(2, "deepseek_v3", "привет", settings=DEFAULTS)  # другой user


async def test_duplicate_passes_again_after_ttl_expiry(fake_redis):
    await check_duplicate_request(1, "deepseek_v3", "привет", settings=DEFAULTS)
    fake_redis.store.clear()  # эмуляция истечения TTL (FakeRedis не тикает время)
    await check_duplicate_request(1, "deepseek_v3", "привет", settings=DEFAULTS)


async def test_duplicate_different_option_codes_pass(fake_redis):
    """Один промпт в 480p и 720p -- это ДВА разных запроса, а не дубль.
    Опции теперь то, что юзер итерирует, и дедуп обязан их различать,
    иначе смена качества внутри cooldown ловит ложный DuplicateRequestError."""
    await check_duplicate_request(
        1, "wan_video", "кот", option_codes={"quality": "480p"}, settings=DEFAULTS
    )
    # тот же промпт, другое качество -- проходит
    await check_duplicate_request(
        1, "wan_video", "кот", option_codes={"quality": "720p"}, settings=DEFAULTS
    )


async def test_duplicate_same_option_codes_raise_regardless_of_key_order(fake_redis):
    """Один и тот же выбор опций = дубль, даже если ключи пришли в другом
    порядке (хеш канонизирует по sort_keys)."""
    await check_duplicate_request(
        1, "veo_video", "кот",
        option_codes={"quality": "4k", "audio": "off"}, settings=DEFAULTS,
    )
    with pytest.raises(DuplicateRequestError):
        await check_duplicate_request(
            1, "veo_video", "кот",
            option_codes={"audio": "off", "quality": "4k"}, settings=DEFAULTS,
        )


# --- check_rate_limits ---

async def test_rate_limit_user_allows_up_to_limit_then_raises(fake_redis, monkeypatch):
    monkeypatch.setattr(afs, "_minute_bucket", lambda: 100)
    for _ in range(10):  # ровно лимит -- проходит
        await check_rate_limits(1, "deepseek_v3", settings=DEFAULTS)
    with pytest.raises(RateLimitExceededError):
        await check_rate_limits(1, "deepseek_v3", settings=DEFAULTS)
    # EXPIRE ставился только при первом инкременте каждого ключа
    assert fake_redis.expire_calls == [
        ("rate_limit:user:1:100", 60),
        ("rate_limit:model:deepseek_v3:100", 60),
    ]


async def test_rate_limit_model_is_global_across_users(fake_redis, monkeypatch):
    monkeypatch.setattr(afs, "_minute_bucket", lambda: 100)
    settings = AntifraudSettings(rate_limit_per_model_per_minute=2)
    await check_rate_limits(1, "veo_video", settings=settings)
    await check_rate_limits(2, "veo_video", settings=settings)
    with pytest.raises(RateLimitExceededError):
        await check_rate_limits(3, "veo_video", settings=settings)


async def test_rate_limit_resets_in_next_minute_bucket(fake_redis, monkeypatch):
    monkeypatch.setattr(afs, "_minute_bucket", lambda: 100)
    settings = AntifraudSettings(rate_limit_per_user_per_minute=1)
    await check_rate_limits(1, "deepseek_v3", settings=settings)
    with pytest.raises(RateLimitExceededError):
        await check_rate_limits(1, "deepseek_v3", settings=settings)

    monkeypatch.setattr(afs, "_minute_bucket", lambda: 101)  # новое окно
    await check_rate_limits(1, "deepseek_v3", settings=settings)


# --- check_tier_allowed ---

async def test_tier_blocks_video_and_ultra_for_non_payers():
    with pytest.raises(TierNotAllowedError):
        await check_tier_allowed(_user(purchased=0), _model(category=ModelCategory.video))
    with pytest.raises(TierNotAllowedError):
        await check_tier_allowed(_user(purchased=0), _model(tier=ModelTier.ultra))


async def test_tier_allows_everything_else(fake_redis):
    await check_tier_allowed(_user(purchased=0), _model())  # text economy
    await check_tier_allowed(_user(purchased=1), _model(category=ModelCategory.video))


async def test_tier_blocks_paid_image_models_for_non_payers():
    # Welcome-кредиты рассчитаны на 5 генераций дешёвой модели; без этого гейта
    # их можно спустить на 3-4 дорогих, удвоив себестоимость новичка.
    with pytest.raises(TierNotAllowedError):
        await check_tier_allowed(_user(purchased=0), _model(category=ModelCategory.image))


async def test_tier_allows_free_tier_image_for_non_payers():
    await check_tier_allowed(
        _user(purchased=0), _model(category=ModelCategory.image, free_tier=True)
    )


async def test_tier_allows_any_image_after_purchase():
    await check_tier_allowed(_user(purchased=1), _model(category=ModelCategory.image))
    await check_tier_allowed(_user(purchased=1), _model(tier=ModelTier.ultra))


# --- check_free_tier_cap ---

async def test_free_tier_cap_allows_exactly_at_cap():
    await check_free_tier_cap(_user(purchased=0, spent=95), 5, settings=DEFAULTS)  # 100 == cap


async def test_free_tier_cap_blocks_over_cap():
    with pytest.raises(FreeTierLimitExceededError):
        await check_free_tier_cap(_user(purchased=0, spent=95), 6, settings=DEFAULTS)


async def test_free_tier_cap_ignored_after_first_purchase():
    await check_free_tier_cap(_user(purchased=1, spent=100_000), 100_000, settings=DEFAULTS)


# --- check_daily_spend_limit / record_daily_spend ---

async def test_daily_limit_allows_exactly_at_limit(fake_redis):
    await check_daily_spend_limit(1, 10_000, settings=DEFAULTS)  # 0 + 10000 == limit


async def test_daily_limit_blocks_over_limit_using_current_counter(fake_redis):
    fake_redis.store[afs._daily_spend_key(1)] = "9995"
    with pytest.raises(DailySpendLimitExceededError):
        await check_daily_spend_limit(1, 6, settings=DEFAULTS)
    await check_daily_spend_limit(1, 5, settings=DEFAULTS)  # 9995 + 5 == limit


async def test_check_daily_limit_is_read_only(fake_redis):
    await check_daily_spend_limit(1, 100, settings=DEFAULTS)
    assert fake_redis.store == {}  # GET без записи: запись -- только record_daily_spend


async def test_record_daily_spend_increments_and_sets_ttl_once(fake_redis):
    key = afs._daily_spend_key(1)
    await record_daily_spend(1, 100)
    assert fake_redis.store[key] == "100"
    assert fake_redis.expire_calls == [(key, afs.DAILY_SPEND_TTL_SECONDS)]

    await record_daily_spend(1, 50)  # ключ уже существует -- второго EXPIRE нет
    assert fake_redis.store[key] == "150"
    assert len(fake_redis.expire_calls) == 1


async def test_record_daily_spend_negative_delta_decrements(fake_redis):
    key = afs._daily_spend_key(1)
    await record_daily_spend(1, 100)
    await record_daily_spend(1, -40)
    assert fake_redis.store[key] == "60"


async def test_record_daily_spend_zero_delta_is_noop(fake_redis):
    await record_daily_spend(1, 0)
    assert fake_redis.store == {}
    assert fake_redis.expire_calls == []
