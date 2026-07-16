# Реферальный бонус: начисление — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Начислять реферальный бонус обеим сторонам после первого успешного запроса приглашённого — сейчас `bonus_granted` никогда не выставляется, и `bonus_count` вечный 0.

**Architecture:** Новая `maybe_grant_referral_bonus` в `referral_service` (зависимость `referral → credit`, как у `payments/activation`). Оркестрируют её сервисы генерации после `settle_request` — обратное направление дало бы цикл импортов. Идемпотентность — атомарным `UPDATE ... WHERE bonus_granted=false` (claim по rowcount), тем же приёмом, что fal-вебхук.

**Tech Stack:** FastAPI + SQLAlchemy 2 async, Alembic, PostgreSQL (нативный enum `credittxtype`), pytest на in-memory SQLite.

**Спек:** `docs/superpowers/specs/2026-07-15-referral-bonus-design.md` (утверждён).

## Global Constraints

- **Голова миграций — `bb51258925d4`.** Спек называет `f7a8b9c0d1e2` — он писался раньше; актуальная голова другая, `down_revision = 'bb51258925d4'`.
- **Бонус — новый tx_type `referral_bonus`, НЕ `purchase`.** `grant_credits` инкрементит `total_credits_purchased` только при `purchase`, а `check_tier_allowed` пускает к video/ultra любого с `total_credits_purchased > 0`. Бонус типом `purchase` = бесплатный ключ к премиуму.
- **Обе стороны — строго после первого успешного запроса друга.** Приветственный грант НЕ вводим (спек §«Осознанно не делаем»).
- **`credittxtype` — нативный Postgres enum**: `ALTER TYPE ... ADD VALUE` только в `autocommit_block` (вне транзакции alembic). На SQLite (тесты) enum = VARCHAR, значение подхватывается из Python-enum само.
- **Начисление и claim — в одной транзакции с `settle`, до `commit`.** Вызов рефералки — ВНЕ `try/except`, обрамляющего `settle` (её падение не должно откатывать состоявшийся `settle`).
- **`earned_credits` = `SUM(bonus_credits)` по роли пригласившего**, не `SUM` транзакций (иначе попадёт собственный бонус пользователя-приглашённого).
- Комментарии/docstring на русском. Ветка `aurora-glass`. Дерево делят: **только поимённый `git add`**.

---

### Task 1: Схема, enum, настройки, миграция

**Files:**
- Modify: `app/db/models/referral.py` (колонка `bonus_credits`)
- Modify: `app/db/enums.py` (значение `referral_bonus` в `CreditTxType`)
- Modify: `app/db/seed.py` (две строки в `SETTINGS_ROWS`)
- Create: `alembic/versions/c7d8e9f0a1b2_referral_bonus.py`
- Test: `tests/db/test_seed_catalog.py` (или новый — см. Step 1)

**Interfaces:**
- Produces: `Referral.bonus_credits: int` (default 0), `CreditTxType.referral_bonus`, настройки `referral_bonus_referrer_credits`/`referral_bonus_referred_credits` (=20). Task 2 их использует. Миграция `c7d8e9f0a1b2` — новая голова.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/db/test_seed_catalog.py` (прочитать импорты — `SETTINGS_ROWS` из `app.db.seed`, `CreditTxType` из `app.db.enums`):

```python
def test_referral_bonus_settings_seeded():
    keys = {r["key"] for r in SETTINGS_ROWS}
    assert "referral_bonus_referrer_credits" in keys
    assert "referral_bonus_referred_credits" in keys
    by_key = {r["key"]: r for r in SETTINGS_ROWS}
    assert by_key["referral_bonus_referrer_credits"]["value"] == "20"
    assert by_key["referral_bonus_referrer_credits"]["type"] == "int"


def test_credittxtype_has_referral_bonus():
    assert CreditTxType.referral_bonus.value == "referral_bonus"
```

- [ ] **Step 2: Прогнать — падают**

Run: `python -m pytest tests/db/test_seed_catalog.py -v -k "referral or credittxtype"`
Expected: FAIL (`AttributeError: referral_bonus`, ключей нет).

- [ ] **Step 3: Enum + колонка + сид**

`app/db/enums.py`, в `class CreditTxType`, после `admin_adjustment`:
```python
    referral_bonus = "referral_bonus"
```

`app/db/models/referral.py`, добавить импорт `Integer` в `from sqlalchemy import ...` и колонку после `bonus_granted`:
```python
    # Сколько кредитов выплачено ПРИГЛАСИВШЕМУ за этого друга. Историческая точность:
    # переживает смену настройки. server_default -- для легаси-строк (SUM без NULL).
    bonus_credits: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
```

`app/db/seed.py`, в `SETTINGS_ROWS` (после последней antifraud-строки):
```python
    dict(key="referral_bonus_referrer_credits", value="20", type="int",
         description="Бонус пригласившему за друга, сделавшего первый запрос"),
    dict(key="referral_bonus_referred_credits", value="20", type="int",
         description="Бонус приглашённому после его первого запроса"),
```

- [ ] **Step 4: Прогнать — проходят**

Run: `python -m pytest tests/db/test_seed_catalog.py -v -k "referral or credittxtype"`
Expected: PASS.

- [ ] **Step 5: Миграция**

Создать `alembic/versions/c7d8e9f0a1b2_referral_bonus.py`:

```python
"""referral bonus: колонка bonus_credits, enum-значение, настройки.

Revision ID: c7d8e9f0a1b2
Revises: bb51258925d4
Create Date: 2026-07-16 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, None] = 'bb51258925d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SETTINGS = [
    {"key": "referral_bonus_referrer_credits", "value": "20", "type": "int",
     "description": "Бонус пригласившему за друга, сделавшего первый запрос"},
    {"key": "referral_bonus_referred_credits", "value": "20", "type": "int",
     "description": "Бонус приглашённому после его первого запроса"},
]


def upgrade() -> None:
    op.add_column("referrals", sa.Column("bonus_credits", sa.Integer(), nullable=False,
                                         server_default="0"))
    # credittxtype -- нативный Postgres enum; ADD VALUE только вне транзакции.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE credittxtype ADD VALUE IF NOT EXISTS 'referral_bonus'")
    # Сид тоже вставит эти ключи (INSERT только отсутствующих), поэтому конфликта нет;
    # миграция нужна для БД, где сид уже отработал до апдейта.
    settings = sa.table(
        "settings",
        sa.column("key", sa.String), sa.column("value", sa.String),
        sa.column("type", sa.String), sa.column("description", sa.String),
    )
    for row in _SETTINGS:
        op.execute(
            settings.insert().from_select(
                ["key", "value", "type", "description"],
                sa.select(
                    sa.literal(row["key"]), sa.literal(row["value"]),
                    sa.literal(row["type"]), sa.literal(row["description"]),
                ).where(~sa.exists().where(settings.c.key == row["key"]))
            )
        )


def downgrade() -> None:
    op.execute("DELETE FROM settings WHERE key IN "
               "('referral_bonus_referrer_credits', 'referral_bonus_referred_credits')")
    op.drop_column("referrals", "bonus_credits")
    # Postgres не умеет удалять значение из enum -- referral_bonus остаётся (безвредно).
```

Свериться с прецедентом `f7a8b9c0d1e2_phase5_antifraud_settings.py` на предмет реального способа вставки settings-строк — **повторить его идиому**, если она отличается от `insert().from_select` выше (главное — INSERT только отсутствующих ключей).

- [ ] **Step 6: Проверить миграцию на живом Postgres**

`postgres` в docker (`ai-hub-bot-postgres-1`, порт не опубликован — через одноразовый контейнер в compose-сети, рецепт в `.superpowers/sdd/task-3-report.md` предыдущих планов). `python -m alembic heads` → одна голова `c7d8e9f0a1b2`. `upgrade head` → `downgrade -1` → `upgrade head` — чисто. Убедиться запросом, что `bonus_credits` и обе настройки на месте, а `credittxtype` содержит `referral_bonus`.

- [ ] **Step 7: Коммит**

```bash
git add app/db/enums.py app/db/models/referral.py app/db/seed.py alembic/versions/c7d8e9f0a1b2_referral_bonus.py tests/db/test_seed_catalog.py
git commit -m "feat(referral): схема бонуса -- bonus_credits, enum-значение, настройки

Колонка referrals.bonus_credits (выплата пригласившему, для earned_credits),
CreditTxType.referral_bonus (НЕ purchase -- иначе бонус открыл бы премиум через
total_credits_purchased), две настройки по 20. Enum-значение через autocommit_block
(нативный Postgres enum)."
```

---

### Task 2: `maybe_grant_referral_bonus` + тесты

**Files:**
- Modify: `app/services/referral_service.py`
- Test: `tests/services/test_referral_service.py` (создать по образцу `test_credit_service.py`)

**Interfaces:**
- Consumes: `Referral.bonus_credits`, `CreditTxType.referral_bonus` (Task 1); `grant_credits(session, user_id, amount, *, reason, tx_type, metadata)` из `credit_service`; `get_setting(session, key, cast=int, default=...)` из `settings_service`.
- Produces: `async def maybe_grant_referral_bonus(session: AsyncSession, referred_user_id: int) -> None`. Task 3 её вызывает.

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/services/test_referral_service.py` — per-test engine на `sqlite+aiosqlite`, `Base.metadata.create_all`, без conftest (образец — `tests/services/test_credit_service.py`, прочитать его фикстуры). Реализовать 6 тестов спека:

```python
import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.enums import CreditTxType
from app.db.models import Referral, User, CreditTransaction, Setting
from app.services.referral_service import maybe_grant_referral_bonus


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _setup(session, *, referrer_bonus="20", referred_bonus="20", with_referral=True):
    referrer = User(telegram_id=1, username="ref", credits_balance=0)
    referred = User(telegram_id=2, username="new", credits_balance=0)
    session.add_all([referrer, referred])
    session.add_all([
        Setting(key="referral_bonus_referrer_credits", value=referrer_bonus, type="int"),
        Setting(key="referral_bonus_referred_credits", value=referred_bonus, type="int"),
    ])
    await session.flush()
    if with_referral:
        session.add(Referral(referrer_user_id=referrer.id, referred_user_id=referred.id))
    await session.commit()
    return referrer, referred


async def test_grants_both_sides(session):
    referrer, referred = await _setup(session)
    await maybe_grant_referral_bonus(session, referred.id)
    await session.commit()

    assert (await session.get(User, referrer.id)).credits_balance == 20
    assert (await session.get(User, referred.id)).credits_balance == 20
    r = (await session.execute(select(Referral))).scalar_one()
    assert r.bonus_granted is True
    assert r.bonus_credits == 20
    txs = (await session.execute(
        select(CreditTransaction).where(CreditTransaction.type == CreditTxType.referral_bonus)
    )).scalars().all()
    assert len(txs) == 2


async def test_idempotent(session):
    referrer, referred = await _setup(session)
    await maybe_grant_referral_bonus(session, referred.id)
    await session.commit()
    await maybe_grant_referral_bonus(session, referred.id)  # повтор
    await session.commit()

    assert (await session.get(User, referrer.id)).credits_balance == 20  # не удвоилось
    count = (await session.execute(
        select(func.count()).select_from(CreditTransaction)
        .where(CreditTransaction.type == CreditTxType.referral_bonus)
    )).scalar_one()
    assert count == 2


async def test_no_referral_is_noop(session):
    _, referred = await _setup(session, with_referral=False)
    await maybe_grant_referral_bonus(session, referred.id)  # реферала нет
    await session.commit()
    assert (await session.get(User, referred.id)).credits_balance == 0


async def test_disabled_keeps_flag_false(session):
    referrer, referred = await _setup(session, referrer_bonus="0", referred_bonus="0")
    await maybe_grant_referral_bonus(session, referred.id)
    await session.commit()
    r = (await session.execute(select(Referral))).scalar_one()
    assert r.bonus_granted is False  # реферал доступен для будущего начисления
    assert (await session.get(User, referrer.id)).credits_balance == 0


async def test_bonus_does_not_unlock_premium(session):
    referrer, referred = await _setup(session)
    await maybe_grant_referral_bonus(session, referred.id)
    await session.commit()
    # total_credits_purchased остаётся 0 -- иначе рефссылка = ключ к video/ultra
    assert (await session.get(User, referrer.id)).total_credits_purchased == 0
    assert (await session.get(User, referred.id)).total_credits_purchased == 0


async def test_one_side_disabled_grants_only_other(session):
    referrer, referred = await _setup(session, referred_bonus="0")  # приглашённому 0
    await maybe_grant_referral_bonus(session, referred.id)
    await session.commit()
    assert (await session.get(User, referrer.id)).credits_balance == 20
    assert (await session.get(User, referred.id)).credits_balance == 0
```

- [ ] **Step 2: Прогнать — падают**

Run: `python -m pytest tests/services/test_referral_service.py -v`
Expected: FAIL (`ImportError: maybe_grant_referral_bonus`).

- [ ] **Step 3: Реализовать функцию**

В `app/services/referral_service.py` добавить импорты (`from sqlalchemy import update`; `from app.db.enums import CreditTxType`; `from app.services.credit_service import grant_credits`; `from app.services.settings_service import get_setting`) и функцию:

```python
async def maybe_grant_referral_bonus(session: AsyncSession, referred_user_id: int) -> None:
    """Начисляет реферальный бонус обеим сторонам после первого успешного запроса
    приглашённого. Идемпотентно: атомарный claim по bonus_granted. Тихий no-op,
    если реферала нет, бонус уже выдан, или обе стороны выключены (=0).

    Вызывается ВНЕ try/except settle_request и в его же транзакции, до commit.
    """
    referrer_amount = await get_setting(
        session, "referral_bonus_referrer_credits", cast=int, default=0
    )
    referred_amount = await get_setting(
        session, "referral_bonus_referred_credits", cast=int, default=0
    )
    # Обе выключены -- НЕ клеймим: реферал отработает, когда админ вернёт ненулевое.
    if referrer_amount <= 0 and referred_amount <= 0:
        return

    referral = (
        await session.execute(
            select(Referral).where(Referral.referred_user_id == referred_user_id)
        )
    ).scalar_one_or_none()
    if referral is None or referral.bonus_granted:
        return

    # Атомарный claim: UPDATE берёт блокировку строки, параллельная транзакция
    # дождётся коммита и увидит bonus_granted=true -> rowcount 0. Размер выплаты
    # пишем тем же UPDATE (bonus_credits = выплата пригласившему).
    claimed = await session.execute(
        update(Referral)
        .where(Referral.referred_user_id == referred_user_id, Referral.bonus_granted.is_(False))
        .values(bonus_granted=True, bonus_credits=referrer_amount)
    )
    if claimed.rowcount == 0:
        return  # гонку проиграли -- тихий no-op

    if referrer_amount > 0:
        await grant_credits(
            session, referral.referrer_user_id, referrer_amount,
            reason="referral bonus (referrer)", tx_type=CreditTxType.referral_bonus,
            metadata={"referral_id": referral.id, "role": "referrer"},
        )
    if referred_amount > 0:
        await grant_credits(
            session, referred_user_id, referred_amount,
            reason="referral bonus (referred)", tx_type=CreditTxType.referral_bonus,
            metadata={"referral_id": referral.id, "role": "referred"},
        )
```

Прочитать сигнатуру `get_setting` в `app/services/settings_service.py` — если параметр каста называется иначе (`cast`/`type_`/…), исправить вызовы. Убедиться, что `grant_credits` НЕ коммитит внутри (иначе разорвёт транзакцию settle) — прочитать её тело; если коммитит, отметить в отчёте (это меняет размещение вызовов).

- [ ] **Step 4: Прогнать — проходят**

Run: `python -m pytest tests/services/test_referral_service.py -v`
Expected: PASS (все 6).

- [ ] **Step 5: Коммит**

```bash
git add app/services/referral_service.py tests/services/test_referral_service.py
git commit -m "feat(referral): maybe_grant_referral_bonus -- начисление обеим сторонам

Идемпотентно (атомарный claim по bonus_granted, rowcount). Обе выключены ->
no-op без claim (реферал доступен для будущего). Сторона с настройкой 0
пропускается. Тип referral_bonus -- premium не открывается."
```

---

### Task 3: Встроить вызов в сервисы генерации

**Files:**
- Modify: `app/services/text_generation_service.py` (после `settle_request`, вне `try`)
- Modify: `app/services/media_generation_service.py` (ветка вебхука `status=="OK"`, после `settle_request`)
- Test: расширить `tests/services/test_media_generation_service.py` и/или `test_text_generation_service.py`

**Interfaces:**
- Consumes: `maybe_grant_referral_bonus` (Task 2).
- Produces: реальное начисление на живом пути генерации.

- [ ] **Step 1: Написать тест на интеграцию**

Прочитать `test_media_generation_service.py` (там уже есть тесты `handle_fal_webhook` со `status="OK"`, хелперы `_seed`, `_image_model`). Добавить тест: приглашённый (`Referral` на него) делает успешную генерацию → у пригласившего +бонус, `bonus_granted=true`. Использовать существующий стиль сборки вебхука. Аналогично — по возможности — в `test_text_generation_service.py`.

Пример для media (подогнать под фикстуры файла):

```python
async def test_successful_generation_grants_referral_bonus(session, fal, fake_redis):
    from app.db.models import Referral, Setting
    referrer = await _seed(session, _image_model(), balance=0)  # пригласивший
    # приглашённый -- отдельный юзер; _seed создаёт одного, поэтому досоздаём вручную
    # (прочитать _seed и повторить его приём для второго юзера + Referral + Settings)
    ...
    # после успешного вебхука OK:
    assert (await session.get(User, referrer.id)).credits_balance >= 20
```

Если сборка двух юзеров в фикстуре громоздкая — тест интеграции допустимо ограничить проверкой, что `handle_fal_webhook`/text-путь ВЫЗЫВАЕТ `maybe_grant_referral_bonus` с нужным `referred_user_id` (monkeypatch-спай), а полноту начисления уже покрывают юнит-тесты Task 2. Выбрать подход по месту, **не ослабляя** проверку факта вызова.

- [ ] **Step 2: Прогнать — падает**

Run: `python -m pytest tests/services/test_media_generation_service.py -v -k referral`
Expected: FAIL (вызова ещё нет).

- [ ] **Step 3: Встроить вызовы**

`app/services/text_generation_service.py` — **вне** блока `try/except` вокруг settle (после строки ~192, до `balance_after = user.credits_balance` на ~207):
```python
        # Реферальный бонус -- после состоявшегося settle, ВНЕ try: его падение
        # не должно откатывать уже списанный запрос. Та же транзакция, до commit.
        await maybe_grant_referral_bonus(session, request.user_id)
```
Импортировать `maybe_grant_referral_bonus` в шапке.

`app/services/media_generation_service.py` — в `handle_fal_webhook`, ветка `status == "OK"`, после `settle_request(...)` (строка ~339), до `await session.commit()`:
```python
                await maybe_grant_referral_bonus(session, request.user_id)
```
Импортировать в шапке. **Только в OK-ветке** — при ERROR/refund запрос не «успешный».

- [ ] **Step 4: Прогнать**

Run: `python -m pytest tests/services/test_media_generation_service.py tests/services/test_text_generation_service.py -v`
Expected: PASS. Затем `python -m pytest tests/ -q`.

- [ ] **Step 5: Коммит**

```bash
git add app/services/text_generation_service.py app/services/media_generation_service.py tests/services/test_media_generation_service.py tests/services/test_text_generation_service.py
git commit -m "feat(referral): начислять бонус после успешной генерации

text: вне try/except settle (падение рефералки не откатывает списание).
media: только в OK-ветке вебхука, после settle, до commit. Оба -- в той же
транзакции. Триггер = первый успешный запрос приглашённого."
```

---

### Task 4: API — earned_credits и bonus_amount

**Files:**
- Modify: `app/services/referral_service.py` (`ReferralStats` + `get_referral_stats`)
- Modify: `app/api/routes/referral.py` (`ReferralOut` + роутер)
- Test: `tests/api/` (роут `/api/referral/me`) + `tests/services/test_referral_service.py`

**Interfaces:**
- Consumes: `Referral.bonus_credits` (Task 1); `get_setting` для `bonus_amount`.
- Produces: `ReferralOut` с `earned_credits`, `bonus_amount`. Task 5 (фронт) их читает.

- [ ] **Step 1: Написать падающие тесты**

В `tests/services/test_referral_service.py` — тест §6 спека (earned только роль пригласившего):

```python
async def test_earned_credits_only_referrer_role(session):
    # A позвал B; C позвал A. earned_credits(A) = бонус за B, без собственного бонуса A.
    a = User(telegram_id=1, username="a", credits_balance=0)
    b = User(telegram_id=2, username="b", credits_balance=0)
    c = User(telegram_id=3, username="c", credits_balance=0)
    session.add_all([a, b, c])
    session.add_all([
        Setting(key="referral_bonus_referrer_credits", value="20", type="int"),
        Setting(key="referral_bonus_referred_credits", value="20", type="int"),
    ])
    await session.flush()
    session.add_all([
        Referral(referrer_user_id=a.id, referred_user_id=b.id),  # A пригласил B
        Referral(referrer_user_id=c.id, referred_user_id=a.id),  # C пригласил A
    ])
    await session.commit()

    await maybe_grant_referral_bonus(session, b.id)  # A получает бонус за B
    await maybe_grant_referral_bonus(session, a.id)  # A получает бонус как приглашённый
    await session.commit()

    from app.services.referral_service import get_referral_stats
    stats = await get_referral_stats(session, await session.get(User, a.id))
    assert stats.earned_credits == 20  # только за B, НЕ собственный бонус приглашённого
```

- [ ] **Step 2: Прогнать — падает**

Run: `python -m pytest tests/services/test_referral_service.py -v -k earned`
Expected: FAIL (`ReferralStats` без `earned_credits`).

- [ ] **Step 3: Расширить сервис и роутер**

`app/services/referral_service.py`:
```python
@dataclass
class ReferralStats:
    referred_count: int
    bonus_count: int
    earned_credits: int
```
и в `get_referral_stats` — добавить агрегат в тот же запрос:
```python
    row = (
        await session.execute(
            select(
                func.count(Referral.id),
                func.count(Referral.id).filter(Referral.bonus_granted.is_(True)),
                func.coalesce(func.sum(Referral.bonus_credits), 0),
            ).where(Referral.referrer_user_id == user.id)
        )
    ).one()
    return ReferralStats(referred_count=row[0], bonus_count=row[1], earned_credits=row[2])
```

`app/api/routes/referral.py`:
```python
class ReferralOut(BaseModel):
    link: str
    referred_count: int
    bonus_count: int
    earned_credits: int
    bonus_amount: int
```
В роутере — `bonus_amount` через `get_setting(session, "referral_bonus_referrer_credits", cast=int, default=0)`; передать оба новых поля в `ReferralOut(...)`.

- [ ] **Step 4: Прогнать**

Run: `python -m pytest tests/services/test_referral_service.py tests/api/ -v -k "referral or earned"`, затем `python -m pytest tests/ -q`.
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add app/services/referral_service.py app/api/routes/referral.py tests/services/test_referral_service.py tests/api/
git commit -m "feat(referral): earned_credits + bonus_amount в API

earned_credits = SUM(bonus_credits) по роли пригласившего (тот же агрегат, что
counts) -- не SUM транзакций, иначе попал бы собственный бонус приглашённого.
bonus_amount = текущая настройка, для промо-строки."
```

---

### Task 5: Фронтенд — плитка «Заработано» и промо

**Files:**
- Modify: `frontend-next/src/api/client.ts` (`ReferralOut`)
- Modify: `frontend-next/src/app/referral/page.tsx`

**Interfaces:**
- Consumes: API из Task 4 (`earned_credits`, `bonus_amount`).

- [ ] **Step 1: Тип**

В `frontend-next/src/api/client.ts`, интерфейс `ReferralOut`: добавить `earned_credits: number;` и `bonus_amount: number;`.

- [ ] **Step 2: Экран**

`frontend-next/src/app/referral/page.tsx`: плитка-счётчик «Бонусов начислено» → «Заработано» со значением `data.earned_credits` (и 💎, раз это теперь реальные кредиты); промо-карточка «+20 💎 за каждого друга» → `+{data.bonus_amount} 💎`. Прочитать файл, повторить его стиль. Соответствует `docs/design/HANDOFF.md` §5.

- [ ] **Step 3: Typecheck + build + e2e**

Run: `cd frontend-next && npx tsc --noEmit && npm run lint && npm run build`. Затем `referral.spec.ts` (env как в прочих e2e); если он проверял старый текст «Бонусов начислено» — обновить под «Заработано», **не ослабляя**.

- [ ] **Step 4: Коммит**

```bash
git add frontend-next/src/api/client.ts frontend-next/src/app/referral/page.tsx frontend-next/e2e/referral.spec.ts
git commit -m "feat(referral-ui): плитка Заработано (earned_credits) + промо bonus_amount

Счётчик выданных бонусов -> сумма заработанных кредитов; промо-строка берёт
реальную настройку вместо выдуманного +20. Соответствует HANDOFF §5."
```

---

## Приёмка плана

- [ ] `python -m pytest tests/ -q` — зелёный (базовая линия 338 passed → +тесты).
- [ ] `python -m alembic heads` — одна голова `c7d8e9f0a1b2`; round-trip на живом Postgres чист; `credittxtype` содержит `referral_bonus`.
- [ ] `cd frontend-next && npx tsc --noEmit && npm run lint && npm run build` — зелёное.
- [ ] `grep -rn "bonus_granted" app/services/` — присваивание `True` теперь ЕСТЬ (в `maybe_grant_referral_bonus`).
- [ ] Ручная проверка на живом бэке: у приглашённого сделать успешную генерацию → `GET /api/referral/me` пригласившего показывает `earned_credits > 0`, `bonus_count` вырос.

## Осознанно не делаем (спек §)
- Приветственный грант приглашённому.
- Изменение `free_tier_credit_cap`.
- Telegram-уведомление о начислении.
