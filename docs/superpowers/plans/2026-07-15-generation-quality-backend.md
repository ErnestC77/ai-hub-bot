# Качество и длительность генерации — backend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать API принимать качество и длительность генерации как коды опций, считать по ним честную цену и передавать провайдеру ровно те параметры, которые он понимает.

**Architecture:** Наборы допустимых значений диктует **модель, а не мы**: у Wan разрешение `480p/580p/720p` плюс отдельная ось `video_quality`, у Kling длительность — строки `"5"`/`"10"`, у Veo — `"4s"/"6s"/"8s"` плюс `generate_audio`, у Ovi ручек нет вовсе. Контракты несводимы, поэтому опции живут в таблице `model_options`: каждая несёт `provider_params` (JSON — что уходит провайдеру) и `credits_multiplier` (во сколько раз дороже дефолта). `pricing.py` не переписываем — множитель ложится **слоем поверх** существующих формул.

**Tech Stack:** Python 3.12, SQLAlchemy 2 (async), Alembic, FastAPI, pytest (+ `sqlite+aiosqlite` in-memory).

**Спек:** `docs/superpowers/specs/2026-07-15-generation-quality-design.md` (этапы 2–5).
**Предыдущий план:** `docs/superpowers/plans/2026-07-15-fal-catalog-fix.md` (этап 1, завершён).

## Global Constraints

- **Голова миграций — `b2c3d4e5f6a8`**. Первая новая миграция ставит `down_revision = 'b2c3d4e5f6a8'`.
- **Все множители выведены из замеров живого fal 2026-07-15, а не назначены.** Kling 5с = $1.40, 10с = $2.80 → ×2.0. Veo $0.40/с со звуком, $0.20/с без → ×0.5. Wan 480p $0.04/с, 580p $0.06/с, 720p $0.08/с → ×0.5 / ×0.75 / ×1.0. qwen_image $0.02/МП, 2048² = 4.19 МП против 1.05 МП → ×4.0. **Новых чисел не изобретать: неизмеренная опция не заводится.**
- **`recommended_credits` = цена дефолтной комбинации** (этап 1 её уже выставил: wan 932, kling 3220, veo 7360, qwen_image 50). Множитель дефолтной опции обязан быть `1.0`, иначе дефолт разъедется с каталогом.
- **Порядок в формуле обязателен**: множитель применяется ДО минимумов (`max(credits, min_credits, VIDEO_MIN_CREDITS)`), иначе дешёвая опция пробьёт пол и станет бесплатной.
- **Клиент шлёт код опции, не сырое значение.** Иначе он сможет прислать произвольный `num_frames`.
- **Неизвестный / неактивный / чужой код → 400**, не тихий дефолт. Тихий откат вернёт нас ровно к тому, от чего уходим.
- Комментарии и docstring — на русском, как в остальном `app/`.
- Ветка `aurora-glass`, рабочее дерево делят с другой сессией: **никогда `git add -A` / `git add .`**, только поимённо.
- Не трогать фронт (`frontend-next/`) и админку — это следующий план.

## Что НЕ делает этот план

Фронт (сегменты вместо слайдера 2–15) и админка CRUD опций — следующий план. До него слайдер длительности на фронте остаётся, и переплата за длительность у Wan/Ovi живёт: пользователь платит `ceil(duration/5 × recommended)`, а получает дефолтную длину. Этот план даёт API возможность делать правильно; фронт начнёт ей пользоваться в следующем.

---

### Task 1: Таблица `model_options`

**Files:**
- Modify: `app/db/enums.py` (новый enum после `CostUnit`)
- Create: `app/db/models/model_options.py`
- Modify: `app/db/models/__init__.py` (экспорт)
- Create: `alembic/versions/c3d4e5f6a9b0_add_model_options.py`
- Test: `tests/db/test_model_options.py`

**Interfaces:**
- Consumes: `AiModel` (`app/db/models/ai_models.py`), `Base` (`app/db/base.py`).
- Produces: `ModelOptionKind` (enum: `quality`, `duration`, `audio`), `ModelOption` ORM-класс с полями `id, model_id, kind, code, label, provider_params, credits_multiplier, is_default, sort_order, is_active`. Ревизия `c3d4e5f6a9b0` — новая голова. Task 2 сеет данные в эту таблицу, Task 3–5 её читают.

- [ ] **Step 1: Написать падающий тест**

Создать `tests/db/test_model_options.py`:

```python
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.enums import CostUnit, ModelCategory, ModelOptionKind, ModelProvider, ModelTier
from app.db.models import AiModel, ModelOption


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _model(session) -> AiModel:
    m = AiModel(
        provider=ModelProvider.fal, category=ModelCategory.video, code="vid",
        display_name="Vid", provider_model_id="fal-ai/vid", tier=ModelTier.standard,
        cost_unit=CostUnit.second, min_credits=100, recommended_credits=200,
    )
    session.add(m)
    await session.commit()
    return m


async def test_option_roundtrips_with_json_params(session):
    """provider_params -- JSON, а не строка: типы значений обязаны пережить
    round-trip. Kling ждёт duration строкой "10", Wan -- num_frames числом 161.
    Если типы поедут, fal отвергнет запрос (или, хуже, молча проигнорирует)."""
    m = await _model(session)
    session.add(ModelOption(
        model_id=m.id, kind=ModelOptionKind.duration, code="10s", label="10 сек",
        provider_params={"duration": "10", "num_frames": 161},
        credits_multiplier=2.0, is_default=False, sort_order=20,
    ))
    await session.commit()

    row = (await session.execute(select(ModelOption))).scalar_one()
    assert row.provider_params == {"duration": "10", "num_frames": 161}
    assert isinstance(row.provider_params["duration"], str)
    assert isinstance(row.provider_params["num_frames"], int)
    assert float(row.credits_multiplier) == 2.0


async def test_defaults_are_sane(session):
    m = await _model(session)
    session.add(ModelOption(
        model_id=m.id, kind=ModelOptionKind.quality, code="720p", label="720p",
        provider_params={"resolution": "720p"},
    ))
    await session.commit()
    row = (await session.execute(select(ModelOption))).scalar_one()
    assert float(row.credits_multiplier) == 1.0
    assert row.is_default is False
    assert row.is_active is True
    assert row.sort_order == 0


async def test_code_unique_per_model_and_kind(session):
    m = await _model(session)
    session.add(ModelOption(model_id=m.id, kind=ModelOptionKind.duration, code="5s",
                            label="5 сек", provider_params={}))
    await session.commit()
    session.add(ModelOption(model_id=m.id, kind=ModelOptionKind.duration, code="5s",
                            label="дубль", provider_params={}))
    with pytest.raises(IntegrityError):
        await session.commit()
```

- [ ] **Step 2: Прогнать тест и убедиться, что падает**

Run: `python -m pytest tests/db/test_model_options.py -v`
Expected: FAIL — `ImportError: cannot import name 'ModelOptionKind'`.

- [ ] **Step 3: Добавить enum**

В `app/db/enums.py` после класса `CostUnit`:

```python
class ModelOptionKind(str, enum.Enum):
    quality = "quality"    # разрешение/размер: resolution, image_size, video_quality
    duration = "duration"  # длина видео: duration, num_frames+frames_per_second
    audio = "audio"        # generate_audio у Veo -- удваивает цену, см. спек
```

- [ ] **Step 4: Добавить ORM-модель**

Создать `app/db/models/model_options.py`:

```python
from sqlalchemy import Boolean, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import ModelOptionKind


class ModelOption(Base):
    """Опция модели: набор допустимых значений диктует сам провайдер, а не мы.

    Контракты fal несводимы между собой (проверено по схемам 2026-07-15):
    Wan берёт resolution=480p/580p/720p И отдельно video_quality; Kling --
    duration строкой "5"/"10"; Veo -- "4s"/"6s"/"8s" плюс generate_audio;
    Ovi -- сырые пиксели. Поэтому provider_params -- JSON, а не колонки:
    одна пользовательская опция может выставлять несколько полей провайдера
    (у Wan «720p» задаёт и resolution, и video_quality).
    """

    __tablename__ = "model_options"
    __table_args__ = (UniqueConstraint("model_id", "kind", "code", name="uq_model_option_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("ai_models.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[ModelOptionKind] = mapped_column()
    code: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(64))
    # JSONB на Postgres, JSON на sqlite (тесты). Внутрь никогда не запрашиваем --
    # читаем целиком и мержим в тело запроса к провайдеру.
    provider_params: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    # Во сколько раз опция дороже дефолтной комбинации модели.
    # Выводится из замеров провайдера, не назначается (см. Global Constraints).
    credits_multiplier: Mapped[float] = mapped_column(Numeric(6, 3), default=1.0)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
```

В `app/db/models/__init__.py` добавить `ModelOption` в импорт и в `__all__` — **прочитать файл и повторить его стиль**.

- [ ] **Step 5: Прогнать тесты**

Run: `python -m pytest tests/db/test_model_options.py -v`
Expected: PASS, все три.

- [ ] **Step 6: Написать миграцию**

Создать `alembic/versions/c3d4e5f6a9b0_add_model_options.py`:

```python
"""add model_options -- опции качества/длительности/звука, задаваемые моделью.

Наборы значений диктует провайдер и они несводимы между моделями, поэтому
provider_params -- JSONB, а не колонки. Частичный уникальный индекс гарантирует
ровно один дефолт на (модель, вид): без него «дефолтная комбинация», от которой
считается recommended_credits, была бы неоднозначной.

Revision ID: c3d4e5f6a9b0
Revises: b2c3d4e5f6a8
Create Date: 2026-07-15 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c3d4e5f6a9b0'
down_revision: Union[str, None] = 'b2c3d4e5f6a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'model_options',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('model_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.Enum('quality', 'duration', 'audio', name='modeloptionkind'), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('label', sa.String(length=64), nullable=False),
        sa.Column('provider_params', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('credits_multiplier', sa.Numeric(precision=6, scale=3), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['model_id'], ['ai_models.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('model_id', 'kind', 'code', name='uq_model_option_code'),
    )
    op.create_index(op.f('ix_model_options_model_id'), 'model_options', ['model_id'])
    # По нему читает GET /api/models.
    op.create_index('ix_model_options_lookup', 'model_options', ['model_id', 'kind', 'sort_order'])
    # Ровно один дефолт на (модель, вид) -- констрейнтом, а не соглашением.
    op.execute(
        "CREATE UNIQUE INDEX uq_model_option_default ON model_options (model_id, kind) "
        "WHERE is_default"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_model_option_default")
    op.drop_index('ix_model_options_lookup', table_name='model_options')
    op.drop_index(op.f('ix_model_options_model_id'), table_name='model_options')
    op.drop_table('model_options')
    sa.Enum(name='modeloptionkind').drop(op.get_bind(), checkfirst=True)
```

- [ ] **Step 7: Проверить миграцию на живом Postgres**

`postgres` работает в docker (`ai-hub-bot-postgres-1`), но **не публикует хост-порт** — alembic запускать через одноразовый контейнер в compose-сети. Рецепт: `.superpowers/sdd/task-3-report.md` из предыдущего плана.

Run: `python -m alembic heads` → одна голова `c3d4e5f6a9b0`. Затем `upgrade head` → `downgrade -1` → `upgrade head` — чисто.

- [ ] **Step 8: Коммит**

```bash
git add app/db/enums.py app/db/models/model_options.py app/db/models/__init__.py alembic/versions/c3d4e5f6a9b0_add_model_options.py tests/db/test_model_options.py
git commit -m "feat(db): таблица model_options -- опции задаёт модель, а не мы

Наборы значений диктует провайдер и они несводимы: Wan берёт resolution
и отдельно video_quality, Kling -- duration строкой, Veo -- строкой с
суффиксом плюс generate_audio, Ovi не управляется вовсе. Отсюда JSONB
для provider_params: одна пользовательская опция может задавать несколько
полей провайдера. Частичный уникальный индекс -- ровно один дефолт на
(модель, вид), иначе 'дефолтная комбинация' неоднозначна."
```

---

### Task 2: Завести Nano Banana Pro в каталог

Каталог неполон, и это вскрылось поздно: проверка велась ПО восьми моделям каталога вместо того, чтобы спросить, правильный ли сам каталог. `fal-ai/nano-banana-pro` (Gemini 3 Pro Image) существует, у неё есть `/edit`-маршрут и — главное — `resolution: enum ["1K","2K","4K"]`. **Это буквально селектор из дизайн-макета**, который спек объявил нереализуемым: дизайнер рисовал не фантазию, а модель, которую не завели.

**Files:**
- Modify: `app/db/seed.py` (`AI_MODELS`, секция IMAGE)
- Create: `alembic/versions/e5f6a9b0c1d2_add_nano_banana_pro.py`
- Test: `tests/db/test_seed_catalog.py`

**Interfaces:**
- Consumes: `AiModel` с колонкой `provider_model_id_edit` (добавлена предыдущим планом), `_MEDIA` из `app/db/seed.py`.
- Produces: строка каталога `nano_banana_pro`. Task 3 навесит на неё опции 1K/2K/4K.

**Измерено живым fal (списание с баланса):** 1K = $0.15, 2K = $0.15, 4K = $0.30. Обычная `nano_banana` = $0.0398 (её 100 кредитов в каталоге сходятся с формулой: 92). По формуле `usd × 2300`: дефолт 1K → **345**, самая дешёвая комбинация тоже 1K → `min_credits` = **345**.

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/db/test_seed_catalog.py`:

```python
def test_nano_banana_pro_in_catalog():
    """Модель из дизайн-макета: у неё resolution=["1K","2K","4K"] -- ровно тот
    селектор, который рисовал дизайнер. Цена измерена живым fal 2026-07-15:
    1K=$0.15 -> 345 кредитов по формуле usd*2300."""
    by_code = {m["code"]: m for m in AI_MODELS}
    pro = by_code["nano_banana_pro"]
    assert pro["provider_model_id"] == "fal-ai/nano-banana-pro"
    assert pro["provider_model_id_edit"] == "fal-ai/nano-banana-pro/edit"
    assert pro["category"] == ModelCategory.image
    assert pro["cost_unit"] == CostUnit.image
    assert (pro["min_credits"], pro["recommended_credits"]) == (345, 345)
    # вчетверо дороже обычной ($0.15 против $0.0398) -- цена, а не вкус
    assert pro["recommended_credits"] > by_code["nano_banana"]["recommended_credits"] * 3
```

Обновить `test_twenty_models_split_12_text_4_image_4_video`: моделей становится **21**, image — **5**. Переименовать тест в `test_catalog_split_12_text_5_image_4_video`.

Обновить `expected` в `test_model_codes_and_credit_floors_match_tz`: добавить `"nano_banana_pro": (345, 345)`.

Обновить `test_media_prices_follow_the_project_formula`: добавить `"nano_banana_pro": 0.15` в `measured_usd`.

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/db/test_seed_catalog.py -v -k nano_banana_pro`
Expected: FAIL — `KeyError: 'nano_banana_pro'`.

- [ ] **Step 3: Добавить модель в сид**

В `app/db/seed.py` после `nano_banana`:

```python
    # Gemini 3 Pro Image. Единственная модель каталога с настоящим селектором
    # 1K/2K/4K (resolution в схеме) -- тем самым, что рисовал дизайн-макет.
    # Измерено 2026-07-15: 1K=$0.15, 2K=$0.15 (бесплатно!), 4K=$0.30.
    # $0.15 * 2300 = 345. Вчетверо дороже обычной nano_banana ($0.0398).
    dict(**_MEDIA, category=ModelCategory.image, code="nano_banana_pro",
         display_name="Nano Banana Pro", tier=ModelTier.pro, cost_unit=CostUnit.image,
         provider_model_id="fal-ai/nano-banana-pro",
         provider_model_id_edit="fal-ai/nano-banana-pro/edit",
         min_credits=345, recommended_credits=345, sort_order=165),
```

`sort_order=165` — между `nano_banana` (160) и `ovi_video` (170).
`tier=ModelTier.pro` — по названию модели. **Не `ultra`**: `check_tier_allowed`
(`app/services/antifraud_service.py:129`) закрывает `ultra` бесплатным пользователям, а здесь
гейт не нужен — 345 кредитов и так недостижимы при `free_tier_credit_cap = 100`.

- [ ] **Step 4: Прогнать тесты**

Run: `python -m pytest tests/db/test_seed_catalog.py -v`
Expected: PASS, все.

- [ ] **Step 5: Написать миграцию**

Создать `alembic/versions/e5f6a9b0c1d2_add_nano_banana_pro.py`, `down_revision = 'd4e5f6a9b0c1'`. INSERT строки каталога, `downgrade()` — DELETE по коду. Значения скопировать из `app/db/seed.py` дословно.

```python
def upgrade() -> None:
    op.execute(sa.text(
        "INSERT INTO ai_models (provider, category, code, display_name, provider_model_id, "
        "provider_model_id_edit, tier, cost_unit, input_price_usd_per_1m_tokens, "
        "output_price_usd_per_1m_tokens, fixed_cost_usd, min_credits, recommended_credits, "
        "max_context_tokens, is_active, is_visible, sort_order) "
        "VALUES ('fal', 'image', 'nano_banana_pro', 'Nano Banana Pro', 'fal-ai/nano-banana-pro', "
        "'fal-ai/nano-banana-pro/edit', 'pro', 'image', 0, 0, 0, 345, 345, 4000, true, true, 165) "
        "ON CONFLICT (code) DO NOTHING"
    ))


def downgrade() -> None:
    op.execute("DELETE FROM ai_models WHERE code = 'nano_banana_pro'")
```

**Перед написанием прочитать `app/db/models/ai_models.py`** и сверить список колонок и их nullable — VALUES обязан совпасть. Значения enum в SQL пишутся строками (`'fal'`, `'image'`, `'pro'`) — сверить с тем, как их хранит SQLAlchemy (значение enum, не имя).

- [ ] **Step 6: Проверить миграцию на живом Postgres**

`upgrade head` → `downgrade -1` → `upgrade head`. Убедиться запросом, что строка появилась и `provider_model_id_edit` заполнен.

- [ ] **Step 7: Коммит**

```bash
git add app/db/seed.py alembic/versions/e5f6a9b0c1d2_add_nano_banana_pro.py tests/db/test_seed_catalog.py
git commit -m "feat(catalog): Nano Banana Pro -- модель с настоящим селектором 1K/2K/4K

fal-ai/nano-banana-pro (Gemini 3 Pro Image) существует и имеет
resolution=['1K','2K','4K'] -- ровно тот селектор, который рисовал
дизайн-макет и который спек объявил нереализуемым. Он был нереализуем
внутри каталога: модель просто не завели.

Цена измерена живым fal: 1K=\$0.15 -> 345 кредитов (usd*2300).
Вчетверо дороже обычной nano_banana (\$0.0398 -> 92, в каталоге 100)."
```

---

### Task 3: Сид опций из измеренных данных

**Files:**
- Modify: `app/db/seed.py` (константа `MODEL_OPTIONS` + вставка в `apply_seed`)
- Create: `alembic/versions/d4e5f6a9b0c1_seed_model_options.py`
- Test: `tests/db/test_seed_catalog.py`

**Interfaces:**
- Consumes: `ModelOption`, `ModelOptionKind` (Task 1); `AI_MODELS` и `apply_seed` из `app/db/seed.py`.
- Produces: `MODEL_OPTIONS: list[dict]` с ключом `model_code` вместо `model_id` (id известен только после вставки моделей). Task 4–5 читают эти строки из БД.

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/db/test_seed_catalog.py`:

```python
def test_option_multipliers_follow_measured_provider_costs():
    """Множители выведены из замеров живого fal 2026-07-15, а не назначены:
      kling  10с $2.80 / 5с $1.40         -> 2.0
      veo    без звука $0.20/с / со звуком $0.40/с -> 0.5
      veo    4с / 8с                       -> 0.5;  6с / 8с -> 0.75
      wan    480p $0.04/с / 720p $0.08/с   -> 0.5;  580p $0.06 -> 0.75
      qwen   2048^2 = 4.19 МП / 1024^2 = 1.05 МП -> 4.0
    """
    by = {(o["model_code"], o["kind"], o["code"]): o for o in MODEL_OPTIONS}
    assert by[("kling_video", ModelOptionKind.duration, "10s")]["credits_multiplier"] == 2.0
    assert by[("veo_video", ModelOptionKind.audio, "off")]["credits_multiplier"] == 0.5
    assert by[("veo_video", ModelOptionKind.duration, "4s")]["credits_multiplier"] == 0.5
    assert by[("wan_video", ModelOptionKind.quality, "480p")]["credits_multiplier"] == 0.5
    assert by[("qwen_image", ModelOptionKind.quality, "2k")]["credits_multiplier"] == 4.0


def test_exactly_one_default_per_model_and_kind():
    """recommended_credits каталога -- цена ДЕФОЛТНОЙ комбинации. Если дефолтов
    два или ноль, эта величина теряет смысл."""
    seen = {}
    for o in MODEL_OPTIONS:
        if o.get("is_default"):
            key = (o["model_code"], o["kind"])
            assert key not in seen, f"два дефолта: {key}"
            seen[key] = o
    kinds = {(o["model_code"], o["kind"]) for o in MODEL_OPTIONS}
    assert set(seen) == kinds, f"без дефолта: {kinds - set(seen)}"


def test_default_option_multiplier_is_one():
    """Дефолт стоит ровно recommended_credits -- значит его множитель 1.0,
    иначе каталог и опции разъедутся."""
    for o in MODEL_OPTIONS:
        if o.get("is_default"):
            assert o["credits_multiplier"] == 1.0, o["model_code"]


def test_no_options_for_models_without_provider_knobs():
    """У flux-pro/kontext, nano-banana и kling нет ручки размера (только
    aspect_ratio) -- опций качества у них быть не должно. У Ovi нет и длительности.
    Нарисовать контрол, которого провайдер не понимает, хуже, чем не рисовать."""
    codes_with_quality = {o["model_code"] for o in MODEL_OPTIONS
                          if o["kind"] == ModelOptionKind.quality}
    assert "flux_kontext_pro" not in codes_with_quality
    assert "nano_banana" not in codes_with_quality
    assert "kling_video" not in codes_with_quality
    codes_with_duration = {o["model_code"] for o in MODEL_OPTIONS
                           if o["kind"] == ModelOptionKind.duration}
    assert "ovi_video" not in codes_with_duration


def test_veo_resolution_multipliers_match_measurements():
    """Измерено 3 генерациями veo 4с без звука: 720p $0.80, 1080p $0.80, 4k $1.60.
    1080p БЕСПЛАТЕН -- ровно как 720p; дорожает только 4K, вдвое. Угадать это было
    нельзя: доки о разнице 720p/1080p молчат, а «три градации = три цены» неверно."""
    by = {o["code"]: o for o in MODEL_OPTIONS
          if o["model_code"] == "veo_video" and o["kind"] == ModelOptionKind.quality}
    assert by["720p"]["credits_multiplier"] == 1.0
    assert by["1080p"]["credits_multiplier"] == 1.0
    assert by["4k"]["credits_multiplier"] == 2.0


def test_nano_banana_pro_resolution_multipliers_match_measurements():
    """Селектор 1K/2K/4K из дизайн-макета -- на модели, для которой он и создан.
    Измерено: 1K $0.15, 2K $0.15, 4K $0.30. 2K БЕСПЛАТЕН.

    Этот тест защищает от «здравого смысла»: 1K/2K/4K -> 1/2/4 выглядит очевидно
    и означало бы вдвое лишнего с пользователя за каждую генерацию в 2K.
    """
    by = {o["code"]: o for o in MODEL_OPTIONS
          if o["model_code"] == "nano_banana_pro" and o["kind"] == ModelOptionKind.quality}
    assert set(by) == {"1k", "2k", "4k"}
    assert by["1k"]["credits_multiplier"] == 1.0
    assert by["2k"]["credits_multiplier"] == 1.0
    assert by["4k"]["credits_multiplier"] == 2.0


def test_seedream_resolution_is_free():
    """Измерено: square_hd + auto_2K + auto_4K = ровно $0.09 на троих, т.е. $0.03
    за картинку независимо от разрешения (cost_unit=image -- плоский тариф).
    Множители 1.0: 2K и 4K достаются пользователю даром."""
    by = {o["code"]: o for o in MODEL_OPTIONS
          if o["model_code"] == "seedream" and o["kind"] == ModelOptionKind.quality}
    assert set(by) == {"1k", "2k", "4k"}
    assert all(o["credits_multiplier"] == 1.0 for o in by.values())


def test_unmeasured_options_are_absent():
    """НЕ заводим то, чего не мерили. Опция с выдуманным множителем хуже
    отсутствующей -- она молча ошибётся в деньгах. Ovi: цена плоская, но влияние
    resolution не измеряли; длительность у него не управляется вовсе."""
    ovi = {o["code"] for o in MODEL_OPTIONS if o["model_code"] == "ovi_video"}
    assert ovi == set(), "влияние resolution на цену ovi не измерено"


async def test_apply_seed_inserts_options_and_is_idempotent(session):
    await apply_seed(session)
    await apply_seed(session)
    count = (await session.execute(select(func.count()).select_from(ModelOption))).scalar_one()
    assert count == len(MODEL_OPTIONS)
```

Дописать импорты: `ModelOptionKind` из `app.db.enums`, `ModelOption` из `app.db.models`, `MODEL_OPTIONS` из `app.db.seed`.

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/db/test_seed_catalog.py -v -k option`
Expected: FAIL — `ImportError: cannot import name 'MODEL_OPTIONS'`.

- [ ] **Step 3: Добавить константу в сид**

В `app/db/seed.py` после `AI_MODELS` добавить:

```python
# Опции моделей. Каждый множитель ВЫВЕДЕН из замера живого fal 2026-07-15
# (списание с баланса), а не назначен -- см. спек, раздел «Цены».
# provider_params сверены со схемами fal: типы значений обязаны совпадать
# (Kling ждёт duration строкой, Wan -- num_frames числом).
MODEL_OPTIONS = [
    # --- Wan: две независимые оси качества (resolution + video_quality) ---
    # 480p $0.04/с, 580p $0.06/с, 720p $0.08/с -> 0.5 / 0.75 / 1.0
    dict(model_code="wan_video", kind=ModelOptionKind.quality, code="480p", label="480p",
         provider_params={"resolution": "480p", "video_quality": "high"},
         credits_multiplier=0.5, is_default=False, sort_order=10),
    dict(model_code="wan_video", kind=ModelOptionKind.quality, code="580p", label="580p",
         provider_params={"resolution": "580p", "video_quality": "high"},
         credits_multiplier=0.75, is_default=False, sort_order=20),
    dict(model_code="wan_video", kind=ModelOptionKind.quality, code="720p", label="720p",
         provider_params={"resolution": "720p", "video_quality": "maximum"},
         credits_multiplier=1.0, is_default=True, sort_order=30),
    # У Wan поля duration нет: длина = num_frames / frames_per_second.
    # 81/16 = 5.0625с (дефолт модели), 161/16 = 10.0625с -> 10.0625/5.0625 = 1.988.
    dict(model_code="wan_video", kind=ModelOptionKind.duration, code="5s", label="5 сек",
         provider_params={"num_frames": 81, "frames_per_second": 16},
         credits_multiplier=1.0, is_default=True, sort_order=10),
    dict(model_code="wan_video", kind=ModelOptionKind.duration, code="10s", label="10 сек",
         provider_params={"num_frames": 161, "frames_per_second": 16},
         credits_multiplier=1.988, is_default=False, sort_order=20),
    # --- Kling: duration СТРОКОЙ, размером управлять нельзя (только aspect_ratio) ---
    # $1.40 за 5с, $2.80 за 10с -> 2.0 (нелинейно по секундам: $1.40 + $0.28/с,
    # формулой не выражается -- ровно поэтому множитель, а не расчёт).
    dict(model_code="kling_video", kind=ModelOptionKind.duration, code="5s", label="5 сек",
         provider_params={"duration": "5"},
         credits_multiplier=1.0, is_default=True, sort_order=10),
    dict(model_code="kling_video", kind=ModelOptionKind.duration, code="10s", label="10 сек",
         provider_params={"duration": "10"},
         credits_multiplier=2.0, is_default=False, sort_order=20),
    # --- Veo: duration строкой с суффиксом; звук удваивает цену ---
    # $0.40/с со звуком, $0.20/с без (оба измерены) -> off = 0.5.
    dict(model_code="veo_video", kind=ModelOptionKind.duration, code="4s", label="4 сек",
         provider_params={"duration": "4s"},
         credits_multiplier=0.5, is_default=False, sort_order=10),
    dict(model_code="veo_video", kind=ModelOptionKind.duration, code="6s", label="6 сек",
         provider_params={"duration": "6s"},
         credits_multiplier=0.75, is_default=False, sort_order=20),
    dict(model_code="veo_video", kind=ModelOptionKind.duration, code="8s", label="8 сек",
         provider_params={"duration": "8s"},
         credits_multiplier=1.0, is_default=True, sort_order=30),
    dict(model_code="veo_video", kind=ModelOptionKind.audio, code="on", label="Со звуком",
         provider_params={"generate_audio": True},
         credits_multiplier=1.0, is_default=True, sort_order=10),
    dict(model_code="veo_video", kind=ModelOptionKind.audio, code="off", label="Без звука",
         provider_params={"generate_audio": False},
         credits_multiplier=0.5, is_default=False, sort_order=20),
    # Разрешение Veo измерено (3 генерации 4с без звука): 720p $0.80, 1080p $0.80, 4k $1.60.
    # 1080p БЕСПЛАТЕН -- стоит ровно как 720p. Дорожает только 4K, ровно вдвое.
    dict(model_code="veo_video", kind=ModelOptionKind.quality, code="720p", label="720p",
         provider_params={"resolution": "720p"},
         credits_multiplier=1.0, is_default=True, sort_order=10),
    dict(model_code="veo_video", kind=ModelOptionKind.quality, code="1080p", label="1080p",
         provider_params={"resolution": "1080p"},
         credits_multiplier=1.0, is_default=False, sort_order=20),
    dict(model_code="veo_video", kind=ModelOptionKind.quality, code="4k", label="4K",
         provider_params={"resolution": "4k"},
         credits_multiplier=2.0, is_default=False, sort_order=30),
    # --- qwen_image: image_size пресетом или объектом ---
    # $0.02/МП. square_hd = 1024^2 = 1.05 МП (дефолт), 2048^2 = 4.19 МП -> 4.0.
    dict(model_code="qwen_image", kind=ModelOptionKind.quality, code="1k", label="1K",
         provider_params={"image_size": "square_hd"},
         credits_multiplier=1.0, is_default=True, sort_order=10),
    dict(model_code="qwen_image", kind=ModelOptionKind.quality, code="2k", label="2K",
         provider_params={"image_size": {"width": 2048, "height": 2048}},
         credits_multiplier=4.0, is_default=False, sort_order=20),
    # --- seedream v4: разрешение бесплатно ---
    # Измерено: square_hd, auto_2K и auto_4K списали ровно $0.09 на троих, т.е.
    # $0.03 за картинку независимо от разрешения (cost_unit=image -- плоский тариф).
    # Множители 1.0: 2K и 4K достаются пользователю даром.
    dict(model_code="seedream", kind=ModelOptionKind.quality, code="1k", label="1K",
         provider_params={"image_size": "square_hd"},
         credits_multiplier=1.0, is_default=True, sort_order=10),
    dict(model_code="seedream", kind=ModelOptionKind.quality, code="2k", label="2K",
         provider_params={"image_size": "auto_2K"},
         credits_multiplier=1.0, is_default=False, sort_order=20),
    dict(model_code="seedream", kind=ModelOptionKind.quality, code="4k", label="4K",
         provider_params={"image_size": "auto_4K"},
         credits_multiplier=1.0, is_default=False, sort_order=30),
    # --- nano_banana_pro: тот самый селектор 1K/2K/4K из дизайн-макета ---
    # Измерено: 1K $0.15, 2K $0.15, 4K $0.30. 2K БЕСПЛАТЕН -- ровно как 1K;
    # дорожает только 4K, вдвое. Тот же узор, что у Veo (720p = 1080p < 4k x2).
    # Здравый смысл сказал бы 1/2/4 -- и мы брали бы вдвое лишнего за 2K.
    dict(model_code="nano_banana_pro", kind=ModelOptionKind.quality, code="1k", label="1K",
         provider_params={"resolution": "1K"},
         credits_multiplier=1.0, is_default=True, sort_order=10),
    dict(model_code="nano_banana_pro", kind=ModelOptionKind.quality, code="2k", label="2K",
         provider_params={"resolution": "2K"},
         credits_multiplier=1.0, is_default=False, sort_order=20),
    dict(model_code="nano_banana_pro", kind=ModelOptionKind.quality, code="4k", label="4K",
         provider_params={"resolution": "4K"},
         credits_multiplier=2.0, is_default=False, sort_order=30),
    # НЕ заведены намеренно:
    #  - ovi: цена плоская ($0.20/видео), но влияние resolution не мерили; длительность
    #    не управляется вовсе (в схеме нет ни duration, ни num_frames);
    #  - flux_kontext_pro, nano_banana (обычная), kling quality: у провайдера НЕТ ручки
    #    размера, только aspect_ratio.
]
```

Импортировать `ModelOptionKind` и `ModelOption` в начале `app/db/seed.py`.

- [ ] **Step 4: Вставлять опции в `apply_seed`**

В `app/db/seed.py`, в `apply_seed`, ПОСЛЕ блока вставки моделей (модели должны получить id) и ДО `await session.commit()`:

```python
    # Опции вставляем после моделей: model_id известен только после их flush.
    await session.flush()
    model_ids = {
        row[0]: row[1]
        for row in (await session.execute(select(AiModel.code, AiModel.id))).all()
    }
    existing_options = {
        (row[0], row[1], row[2])
        for row in (
            await session.execute(
                select(ModelOption.model_id, ModelOption.kind, ModelOption.code)
            )
        ).all()
    }
    for data in MODEL_OPTIONS:
        model_id = model_ids.get(data["model_code"])
        if model_id is None:
            continue  # модель скрыта/удалена -- опции ей не нужны
        key = (model_id, data["kind"], data["code"])
        if key in existing_options:
            continue
        payload = {k: v for k, v in data.items() if k != "model_code"}
        session.add(ModelOption(model_id=model_id, **payload))
```

- [ ] **Step 5: Прогнать тесты**

Run: `python -m pytest tests/db/test_seed_catalog.py tests/db/test_model_options.py -v`
Expected: PASS.

- [ ] **Step 6: Написать миграцию сида опций**

Создать `alembic/versions/d4e5f6a9b0c1_seed_model_options.py` с `down_revision = 'c3d4e5f6a9b0'`. `apply_seed` вставляет только отсутствующие строки, но на существующей БД он не гоняется автоматически — миграция должна засеять `model_options` для уже существующих моделей.

Написать `upgrade()`, который INSERT'ит те же строки, что `MODEL_OPTIONS`, разрешая `model_code` → `id` через подзапрос:

```python
def upgrade() -> None:
    for o in _OPTIONS:
        op.execute(
            sa.text(
                "INSERT INTO model_options "
                "(model_id, kind, code, label, provider_params, credits_multiplier, "
                " is_default, sort_order, is_active) "
                "SELECT id, :kind, :code, :label, CAST(:params AS JSONB), :mult, "
                "       :is_default, :sort_order, true "
                "FROM ai_models WHERE code = :model_code"
            ).bindparams(**o)
        )


def downgrade() -> None:
    op.execute("DELETE FROM model_options")
```

`_OPTIONS` — список тех же данных, что `MODEL_OPTIONS`, но `kind` строкой и `params` через `json.dumps`. **Скопировать значения из `app/db/seed.py` дословно, не набирать заново.**

- [ ] **Step 7: Тест совпадения миграции и сида**

Добавить в `tests/db/test_seed_catalog.py` тест, который **импортирует модуль миграции** (не читает как текст — прошлый план на этом обжёгся: поиск подстроки по файлу не отличает `_FIXES` от `_ROLLBACK`) и сверяет `_OPTIONS` с `MODEL_OPTIONS` по всем полям:

```python
def test_option_migration_matches_seed_constants():
    import importlib.util, json
    from pathlib import Path

    path = Path("alembic/versions/d4e5f6a9b0c1_seed_model_options.py")
    spec_ = importlib.util.spec_from_file_location("seed_options_migration", path)
    mod = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(mod)

    from_migration = {
        (o["model_code"], o["kind"], o["code"]): (float(o["mult"]), json.loads(o["params"]), o["is_default"])
        for o in mod._OPTIONS
    }
    from_seed = {
        (o["model_code"], o["kind"].value, o["code"]):
            (float(o["credits_multiplier"]), o["provider_params"], o["is_default"])
        for o in MODEL_OPTIONS
    }
    assert from_migration == from_seed
```

- [ ] **Step 8: Проверить миграцию на живом Postgres**

`upgrade head` → `downgrade -1` → `upgrade head`. Затем убедиться запросом, что у `kling_video` ровно две опции `duration` и что `provider_params->>'duration'` = строка `"10"`, а не число.

- [ ] **Step 9: Коммит**

```bash
git add app/db/seed.py alembic/versions/d4e5f6a9b0c1_seed_model_options.py tests/db/test_seed_catalog.py
git commit -m "feat(db): сид опций -- множители выведены из замеров fal

Каждый множитель получен делением измеренных цен, а не назначен:
kling 10с \$2.80/\$1.40 -> 2.0; veo без звука \$0.20//\$0.40/с -> 0.5;
wan 480p \$0.04//\$0.08/с -> 0.5; qwen 2048^2/1024^2 МП -> 4.0.
Нелинейность Kling (\$1.40 за первые 5с + \$0.28/с) формулой не выражается,
а множителем -- выражается.

Намеренно НЕ заведены: veo 1080p/4k и seedream auto_2K/auto_4K (цена по
разрешению не измерена), ovi duration (в схеме поля нет), quality у
flux_kontext_pro/nano_banana/kling (у провайдера нет ручки размера)."
```

---

### Task 4: Множители в `pricing.py`

**Files:**
- Modify: `app/services/pricing.py:42-64`
- Test: `tests/services/test_pricing.py`

**Interfaces:**
- Consumes: ничего из Task 1–2 (чистые функции, опции приходят числом).
- Produces: `calculate_image_credits(model, quantity, megapixels, *, is_edit=False, options_multiplier=1.0)` и `calculate_video_credits(model, *, options_multiplier=1.0)` — **у видео параметр `duration_seconds` УДАЛЯЕТСЯ**, его работу берёт множитель опции длительности. Task 5 вызывает обе.

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/services/test_pricing.py` (прочитать файл, повторить его стиль и хелперы):

```python
def test_options_multiplier_applies_before_floors():
    """Порядок обязателен: множитель ДО минимумов. Иначе дешёвая опция
    пробьёт пол и станет бесплатной, а дорогая -- недоплаченной."""
    model = _video_model(recommended=1000, min_credits=400)
    # 0.5 * 1000 = 500 -- выше пола 400, пол не срабатывает
    assert calculate_video_credits(model, options_multiplier=0.5) == 500
    # 0.1 * 1000 = 100 -- ниже пола: возвращается пол, а не 100
    assert calculate_video_credits(model, options_multiplier=0.1) == max(400, VIDEO_MIN_CREDITS)


def test_default_multiplier_equals_recommended_credits():
    """Дефолтная комбинация стоит ровно recommended_credits."""
    model = _video_model(recommended=3220, min_credits=3220)
    assert calculate_video_credits(model, options_multiplier=1.0) == 3220


def test_kling_ten_seconds_doubles():
    """Нелинейность провайдера ($1.40 за 5с, $2.80 за 10с) выражена множителем."""
    kling = _video_model(recommended=3220, min_credits=3220)
    assert calculate_video_credits(kling, options_multiplier=2.0) == 6440


def test_image_options_multiplier_composes_with_edit():
    """2K (×4) на редактировании (×1.5) -- множители перемножаются."""
    model = _image_model(cost_unit=CostUnit.megapixel, recommended=50, min_credits=50)
    plain = calculate_image_credits(model, quantity=1, megapixels=1.0, options_multiplier=4.0)
    assert plain == 200
    edited = calculate_image_credits(
        model, quantity=1, megapixels=1.0, is_edit=True, options_multiplier=4.0
    )
    assert edited == 300  # ceil(200 * 1.5)
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/services/test_pricing.py -v -k multiplier`
Expected: FAIL — `TypeError: calculate_video_credits() got an unexpected keyword argument 'options_multiplier'`.

- [ ] **Step 3: Изменить формулы**

В `app/services/pricing.py` заменить обе функции:

```python
def calculate_image_credits(
    model: AiModel, quantity: int, megapixels: float, *, is_edit: bool = False,
    options_multiplier: float = 1.0,
) -> int:
    if model.cost_unit == CostUnit.image:
        credits = quantity * model.recommended_credits
    elif model.cost_unit == CostUnit.megapixel:
        credits = math.ceil(quantity * megapixels * model.recommended_credits)
    else:
        raise ValueError(f"model {model.code}: cost_unit {model.cost_unit!r} не поддерживается для image")
    # Множитель опций -- ДО минимумов (см. ниже).
    credits = math.ceil(credits * options_multiplier)
    credits = max(credits, model.min_credits)
    if is_edit:
        credits = max(math.ceil(credits * IMAGE_EDIT_MULTIPLIER), IMAGE_EDIT_MIN_CREDITS)
    return credits


def calculate_video_credits(model: AiModel, *, options_multiplier: float = 1.0) -> int:
    """recommended_credits -- цена ДЕФОЛТНОЙ комбинации опций модели.
    Длительность больше не параметр формулы: её задаёт опция, и её же множитель
    выражает разницу в цене. Прежнее `duration/5` было неверным вдвойне --
    5 секунд не производит ни одна модель каталога (Kling умеет 5 или 10,
    Veo 4/6/8, Wan считает кадрами, Ovi не управляется), а у Wan и Ovi
    длительность вообще не уходила провайдеру: юзер платил за 15с и получал 5.
    """
    credits = math.ceil(model.recommended_credits * options_multiplier)
    return max(credits, model.min_credits, VIDEO_MIN_CREDITS)
```

Удалить константу `VIDEO_BASE_SECONDS` (`pricing.py:13`) — её комментарий («recommended_credits видео-моделей заданы "за 5 секунд"») теперь ложь. Прогнать `grep -rn "VIDEO_BASE_SECONDS" app/ tests/` и убрать все использования.

`calculate_video_api_cost_usd(model, duration_seconds)` **не трогать** — она про себестоимость, у неё своя жизнь.

- [ ] **Step 4: Прогнать тесты**

Run: `python -m pytest tests/services/test_pricing.py -v`
Expected: PASS. **Старые тесты, завязанные на `duration_seconds`, упадут — это ожидаемо**: параметр удалён намеренно. Переписать их под множитель, **не возвращать параметр обратно**.

- [ ] **Step 5: Коммит**

```bash
git add app/services/pricing.py tests/services/test_pricing.py
git commit -m "feat(pricing): множитель опций вместо duration/5

Множитель применяется ДО минимумов -- иначе дешёвая опция пробивает пол.
duration_seconds удалён из calculate_video_credits: 5 секунд не производит
ни одна модель каталога, а у Wan и Ovi длительность вообще не уходила
провайдеру -- юзер платил за 15с и всегда получал ~5."
```

---

### Task 5: `FalClient` мержит `provider_params`

**Files:**
- Modify: `app/services/ai/fal_client.py` (`submit_image`, `submit_video`)
- Test: `tests/services/ai/test_fal_client.py`

**Interfaces:**
- Consumes: `ModelOption.provider_params` (Task 1) — но приходит уже готовым `dict`, клиент про БД не знает.
- Produces: `submit_image(model, prompt, *, image_url=None, provider_params=None, webhook_url)` и `submit_video(model, prompt, *, provider_params=None, webhook_url)`. **`duration_seconds` из `submit_video` УДАЛЯЕТСЯ.** Task 6 их вызывает.

- [ ] **Step 1: Написать падающий тест**

Файл уже тестирует реальный клиент через `respx` — прочитать его и повторить стиль. Добавить:

```python
@respx.mock
async def test_submit_video_merges_provider_params_preserving_types():
    """Типы обязаны пережить merge: Kling ждёт duration СТРОКОЙ "10",
    Wan -- num_frames числом. Прежний код слал {"duration": <int>} --
    Veo такой запрос отвергает, Wan молча игнорирует."""
    route = respx.post(host="queue.fal.run", path="/fal-ai/kling").mock(
        return_value=httpx.Response(200, json={"request_id": "req-1"})
    )
    client = FalClient("k")
    await client.submit_video(
        _model(provider_model_id="fal-ai/kling"), "a cube",
        provider_params={"duration": "10"}, webhook_url="https://wh",
    )
    body = json.loads(route.calls.last.request.content)
    assert body == {"prompt": "a cube", "duration": "10"}
    assert isinstance(body["duration"], str)


@respx.mock
async def test_submit_video_without_params_sends_only_prompt():
    """Опций нет (Ovi) -- шлём голый промпт, а не выдуманные поля."""
    route = respx.post(host="queue.fal.run", path="/fal-ai/ovi").mock(
        return_value=httpx.Response(200, json={"request_id": "req-1"})
    )
    await FalClient("k").submit_video(
        _model(provider_model_id="fal-ai/ovi"), "a cube", webhook_url="https://wh"
    )
    assert json.loads(route.calls.last.request.content) == {"prompt": "a cube"}


@respx.mock
async def test_submit_image_merges_params_and_keeps_edit_route():
    """Опции не должны сломать выбор i2i-маршрута (сделан прошлым планом)."""
    edit = respx.post(host="queue.fal.run", path="/fal-ai/kontext").mock(
        return_value=httpx.Response(200, json={"request_id": "req-edit"})
    )
    await FalClient("k").submit_image(
        _model(provider_model_id="fal-ai/kontext/text-to-image",
               provider_model_id_edit="fal-ai/kontext"),
        "make it night", image_url="https://img", 
        provider_params={"image_size": {"width": 2048, "height": 2048}},
        webhook_url="https://wh",
    )
    body = json.loads(edit.calls.last.request.content)
    assert body["image_url"] == "https://img"
    assert body["image_size"] == {"width": 2048, "height": 2048}
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/services/ai/test_fal_client.py -v -k provider_params`
Expected: FAIL — `TypeError: submit_video() got an unexpected keyword argument 'provider_params'`.

- [ ] **Step 3: Изменить клиент**

В `app/services/ai/fal_client.py`:

```python
    async def submit_image(
        self, model: AiModel, prompt: str, *, image_url: str | None = None,
        provider_params: dict | None = None, webhook_url: str,
    ) -> str:
        body: dict = {"prompt": prompt}
        # У некоторых fal-моделей t2i и i2i -- разные маршруты (проверено по
        # схеме fal 2026-07-15): fal-ai/flux-pro/kontext требует image_url
        # (required: ["prompt","image_url"]), его t2i-версия -- отдельный
        # /text-to-image эндпоинт без этого поля; nano-banana аналогично
        # разделяется на .../edit. provider_model_id_edit = None у моделей
        # с единственным маршрутом -- тогда используем provider_model_id как обычно.
        if image_url is not None:
            body["image_url"] = image_url
            endpoint = model.provider_model_id_edit or model.provider_model_id
        else:
            endpoint = model.provider_model_id
        # Параметры опций приходят из model_options.provider_params как есть:
        # адаптер НЕ знает про resolution/duration/num_frames -- контракты
        # у моделей несводимы, и знание о них живёт в БД, а не в коде.
        if provider_params:
            body.update(provider_params)
        return await self._submit(endpoint, body, webhook_url)

    async def submit_video(
        self, model: AiModel, prompt: str, *, provider_params: dict | None = None,
        webhook_url: str,
    ) -> str:
        body: dict = {"prompt": prompt}
        if provider_params:
            body.update(provider_params)
        return await self._submit(model.provider_model_id, body, webhook_url)
```

**Удалить PLACEHOLDER-комментарий** про имя поля длительности — угадывания больше нет, поле приходит из БД.

- [ ] **Step 4: Прогнать тесты**

Run: `python -m pytest tests/services/ai/test_fal_client.py -v`
Expected: PASS. Старые тесты, передававшие `duration_seconds`, упадут — переписать под `provider_params`.

- [ ] **Step 5: Коммит**

```bash
git add app/services/ai/fal_client.py tests/services/ai/test_fal_client.py
git commit -m "feat(fal): merge provider_params вместо угаданных полей

Адаптер больше не знает про duration/resolution/num_frames: контракты
моделей несводимы (Kling -- duration строкой, Wan -- num_frames+fps,
Veo -- строка с суффиксом, Ovi -- ничего), и знание о них живёт в БД.
Удалён PLACEHOLDER 'имя поля длительности уточнить перед продакшном' --
угадывать больше нечего."
```

---

### Task 6: Резолв опций в `media_generation_service`

**Files:**
- Modify: `app/services/media_generation_service.py` (`start_media_generation`, новая функция резолва)
- Test: `tests/services/test_media_generation_service.py`

**Interfaces:**
- Consumes: `ModelOption` (Task 1), `calculate_image_credits`/`calculate_video_credits` с `options_multiplier` (Task 3), `FalClient.submit_*` с `provider_params` (Task 4).
- Produces: `start_media_generation(session, user, model_code, prompt, *, image_url=None, option_codes=None, confirm=False)`. **`duration_seconds` УДАЛЯЕТСЯ** — его заменяет `option_codes: dict[str, str] | None` вида `{"quality": "480p", "duration": "10s"}`. Плюс `UnknownOptionError`. Task 7 (API) их использует.

- [ ] **Step 1: Написать падающий тест**

```python
async def test_options_multiply_price_and_reach_provider(session, fal):
    model = _video_model(recommended=3220, min_credits=3220)
    user = await _seed(session, model, balance=10000)
    await _add_option(session, model, kind=ModelOptionKind.duration, code="10s",
                      params={"duration": "10"}, mult=2.0)

    request = await start_media_generation(
        session, user, model.code, "a cube", option_codes={"duration": "10s"}
    )

    assert request.estimated_credits == 6440  # 3220 * 2.0
    assert fal.video_calls[-1]["provider_params"] == {"duration": "10"}


async def test_default_option_used_when_code_absent(session, fal):
    model = _video_model(recommended=3220, min_credits=3220)
    user = await _seed(session, model, balance=10000)
    await _add_option(session, model, kind=ModelOptionKind.duration, code="5s",
                      params={"duration": "5"}, mult=1.0, is_default=True)

    request = await start_media_generation(session, user, model.code, "a cube")

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


async def test_multiple_kinds_compose(session, fal):
    """Veo: длительность и звук -- независимые оси, множители перемножаются,
    provider_params сливаются."""
    model = _video_model(recommended=7360, min_credits=1840)
    user = await _seed(session, model, balance=100000)
    await _add_option(session, model, kind=ModelOptionKind.duration, code="4s",
                      params={"duration": "4s"}, mult=0.5)
    await _add_option(session, model, kind=ModelOptionKind.audio, code="off",
                      params={"generate_audio": False}, mult=0.5)

    request = await start_media_generation(
        session, user, model.code, "a cube",
        option_codes={"duration": "4s", "audio": "off"},
    )

    assert request.estimated_credits == 1840  # 7360 * 0.5 * 0.5
    assert fal.video_calls[-1]["provider_params"] == {"duration": "4s", "generate_audio": False}
```

Написать хелпер `_add_option(session, model, *, kind, code, params, mult, is_default=False, is_active=True)` рядом с `_image_model`/`_video_model`. Расширить `FakeFalClient`, чтобы он писал `provider_params` в `video_calls`/`image_calls`; **все существующие ассерты файла обязаны остаться зелёными**.

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/services/test_media_generation_service.py -v -k option`
Expected: FAIL — `ImportError: cannot import name 'UnknownOptionError'`.

- [ ] **Step 3: Реализовать резолв**

В `app/services/media_generation_service.py`:

```python
class UnknownOptionError(Exception):
    """Клиент прислал код опции, которого у модели нет или который выключен."""

    def __init__(self, kind: str, code: str):
        self.kind = kind
        self.code = code
        super().__init__(f"unknown option {kind}={code}")


async def _resolve_options(
    session: AsyncSession, model: AiModel, option_codes: dict[str, str] | None
) -> tuple[float, dict]:
    """Коды опций -> (произведение множителей, слитые provider_params).

    Коды, а не сырые значения: иначе клиент пришлёт произвольный num_frames.
    Неизвестный код -> UnknownOptionError (400), а НЕ тихий откат на дефолт:
    молчаливая подмена вернула бы нас к контролу, который делает не то,
    что показывает.
    """
    rows = (
        await session.execute(
            select(ModelOption)
            .where(ModelOption.model_id == model.id, ModelOption.is_active.is_(True))
            .order_by(ModelOption.sort_order)
        )
    ).scalars().all()

    by_kind: dict[ModelOptionKind, list[ModelOption]] = {}
    for row in rows:
        by_kind.setdefault(row.kind, []).append(row)

    requested = option_codes or {}
    for kind_str in requested:
        if kind_str not in {k.value for k in by_kind}:
            raise UnknownOptionError(kind_str, requested[kind_str])

    multiplier = 1.0
    params: dict = {}
    for kind, options in by_kind.items():
        code = requested.get(kind.value)
        if code is None:
            chosen = next((o for o in options if o.is_default), None)
            if chosen is None:
                continue  # у вида нет дефолта -- ничего не навязываем
        else:
            chosen = next((o for o in options if o.code == code), None)
            if chosen is None:
                raise UnknownOptionError(kind.value, code)
        multiplier *= float(chosen.credits_multiplier)
        params.update(chosen.provider_params or {})
    return multiplier, params
```

В `start_media_generation` заменить сигнатуру (`duration_seconds` → `option_codes: dict[str, str] | None = None`) и блок оценки:

```python
    options_multiplier, provider_params = await _resolve_options(session, model, option_codes)

    if model.category == ModelCategory.image:
        estimated = calculate_image_credits(
            model, quantity=1, megapixels=1.0, is_edit=image_url is not None,
            options_multiplier=options_multiplier,
        )
        provider_cost_usd = calculate_image_api_cost_usd(model, quantity=1, megapixels=1.0)
        threshold = IMAGE_CONFIRM_THRESHOLD_CREDITS
    else:
        estimated = calculate_video_credits(model, options_multiplier=options_multiplier)
        provider_cost_usd = calculate_video_api_cost_usd(model, VIDEO_DEFAULT_DURATION_SECONDS)
        threshold = VIDEO_CONFIRM_THRESHOLD_CREDITS
```

И передать `provider_params=provider_params` в оба `submit_*`. Прочитать место вызова и убрать `duration_seconds=`.

- [ ] **Step 4: Прогнать тесты**

Run: `python -m pytest tests/services/test_media_generation_service.py -v`
Expected: PASS, включая все существующие. Тесты с `duration_seconds` переписать под `option_codes`.

- [ ] **Step 5: Коммит**

```bash
git add app/services/media_generation_service.py tests/services/test_media_generation_service.py
git commit -m "feat(media): резолв опций -- цена и параметры провайдера из БД

option_codes вместо duration_seconds: клиент шлёт код, не сырое значение
(иначе пришлёт произвольный num_frames). Неизвестный код -> ошибка, а не
тихий дефолт. Множители независимых осей перемножаются (Veo: длительность
x звук), provider_params сливаются."
```

---

### Task 7: API — `option_codes` и список опций в `ModelOut`

**Files:**
- Modify: `app/api/routes/generate.py:28-37` (`GenerateRequest`), обработчик
- Modify: `app/api/routes/chat.py:42-48` (`ModelOut`), `list_models`
- Test: `tests/api/` (прочитать, повторить стиль существующих тестов роутов)

**Interfaces:**
- Consumes: `start_media_generation(..., option_codes=...)` и `UnknownOptionError` (Task 6); `ModelOption` (Task 1).
- Produces: `GenerateRequest.option_codes: dict[str,str] | None`; `ModelOut.options: list[ModelOptionOut]`. Фронт (следующий план) читает `options` и шлёт `option_codes`.

- [ ] **Step 1: Написать падающий тест**

Прочитать `tests/api/` и повторить стиль. Тесты:

```python
async def test_models_endpoint_exposes_options(client, session):
    """Фронт рисует сегменты ИЗ ПРИШЕДШИХ опций: у модели без ручки размера
    (nano_banana) секции качества не будет вовсе."""
    # ... сид модели с двумя duration-опциями ...
    body = (await client.get("/api/models?category=video")).json()
    kling = next(m for m in body if m["code"] == "kling_video")
    assert [o["code"] for o in kling["options"]] == ["5s", "10s"]
    assert kling["options"][0]["is_default"] is True
    assert kling["options"][0]["kind"] == "duration"
    assert float(kling["options"][1]["credits_multiplier"]) == 2.0


async def test_models_endpoint_hides_inactive_options(client, session):
    # ... опция с is_active=False не должна попасть в ответ ...


async def test_generate_rejects_unknown_option_code(client, session):
    resp = await client.post("/api/generate", json={
        "model_code": "kling_video", "prompt": "x",
        "option_codes": {"duration": "99s"},
    })
    assert resp.status_code == 400
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/api/ -v -k option`
Expected: FAIL — в ответе нет ключа `options`.

- [ ] **Step 3: Расширить `GenerateRequest`**

`app/api/routes/generate.py`:

```python
class GenerateRequest(BaseModel):
    # Security-фикс фазы 3: поля credit_cost_override больше НЕТ -- стоимость
    # считается только на бэкенде (media_generation_service). Неизвестные поля
    # в JSON pydantic молча игнорирует.
    model_code: str
    prompt: str
    image_url: str | None = None         # для image-edit
    # Коды опций: {"quality": "480p", "duration": "10s", "audio": "off"}.
    # Именно коды, а не сырые значения -- иначе клиент пришлёт произвольный
    # num_frames. Наборы задаёт модель, см. GET /api/models.
    option_codes: dict[str, str] | None = None
    confirm: bool = False
```

**Удалить `duration_seconds`.**

В обработчике ловить `UnknownOptionError` → `HTTPException(400, detail=...)`. Прочитать, как соседние ошибки превращаются в HTTP, и повторить.

- [ ] **Step 4: Расширить `ModelOut`**

`app/api/routes/chat.py`:

```python
class ModelOptionOut(BaseModel):
    kind: str
    code: str
    label: str
    credits_multiplier: float
    is_default: bool
    sort_order: int


class ModelOut(BaseModel):
    code: str
    display_name: str
    tier: str
    min_credits: int
    recommended_credits: int
    # Наборы значений диктует модель: у nano_banana опций качества не будет
    # вовсе (у fal нет ручки размера), у Wan их три. provider_params наружу
    # НЕ отдаём -- клиент шлёт код, а не сырые параметры.
    options: list[ModelOptionOut] = []
```

В `list_models` подгрузить опции **одним запросом на всю выдачу** (не по модели на строку — это N+1), отфильтровать `is_active`, отсортировать по `sort_order`.

- [ ] **Step 5: Прогнать тесты**

Run: `python -m pytest tests/api/ -v`, затем `python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 6: Коммит**

```bash
git add app/api/routes/generate.py app/api/routes/chat.py tests/api/
git commit -m "feat(api): option_codes в запросе, options в списке моделей

Клиент шлёт коды опций, не сырые значения. Неизвестный код -> 400, не
тихий дефолт. GET /api/models отдаёт набор опций каждой модели -- фронт
рисует то, что модель реально умеет, а не общий enum.
provider_params наружу не отдаём. duration_seconds удалён."
```

---

## Приёмка плана

- [ ] `python -m pytest tests/ -q` — зелёный (базовая линия перед планом: 299 passed, 2 skipped).
- [ ] `python -m alembic heads` — одна голова, `d4e5f6a9b0c1`.
- [ ] `upgrade head` → `downgrade -4` → `upgrade head` — чисто.
- [ ] `grep -rn "duration_seconds" app/` — остались только `calculate_video_api_cost_usd` (себестоимость) и `VIDEO_DEFAULT_DURATION_SECONDS` при её вызове. В пути ЦЕНЫ для юзера этого параметра быть не должно.
- [ ] `grep -rn "PLACEHOLDER" app/services/ai/fal_client.py` — пусто.
- [ ] `grep -rn "VIDEO_BASE_SECONDS" app/ tests/` — пусто.

## Известные хвосты после этого плана

- **Фронт ещё шлёт слайдер 2–15** и не знает про `option_codes`. До следующего плана переплата за длительность у Wan/Ovi живёт. `duration_seconds` удалён из API — **фронт сломается на генерации видео, пока следующий план не выйдет**. Планировать выкат вместе.
- **Цена veo на 1080p/4k и seedream на auto_2K/auto_4K не измерена** — опции не заведены. Мерить по отработанной методике: одна генерация на разрешение, разница балансов. ~$2–4.
- **Ovi**: влияние `resolution` на цену не мерили; длительность не управляется вовсе.
