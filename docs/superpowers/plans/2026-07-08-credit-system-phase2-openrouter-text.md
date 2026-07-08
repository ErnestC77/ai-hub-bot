# Credit System Phase 2 — OpenRouter + Text Generation Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate OpenRouter as the single text-model provider and rebuild the text-generation request flow (reserve → call provider → settle/refund) on top of phase 1's credit engine, replacing the deleted tariff-era pipeline.

**Architecture:** A new `OpenRouterProvider` (OpenAI-compatible chat-completions client pointed at `https://openrouter.ai/api/v1`, exact `DeepSeekProvider` pattern) is driven by a new `app/services/text_generation_service.py` that owns the whole flow: model resolution with `fallback_model_code`, per-user Redis lock, credit estimation with a >100-credit confirmation gate, `reserve_credits` → provider call → `settle_request`/`refund_request`. `POST /api/chat`, `GET /api/models` and `GET /api/me` are rewritten on top of it; the old text pipeline (`ai_router.py`, `access_service.py`, `cost_service.py`, `registry.py`, four per-provider services, `tariffs.py`) is deleted.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async + asyncpg/aiosqlite, Alembic, aiogram 3, `openai>=1.40` (AsyncOpenAI client), redis-py asyncio, pytest (`asyncio_mode = auto`), respx for HTTP mocking.

## Global Constraints

- Spec (ground truth): `docs/superpowers/specs/2026-07-08-credit-system-phase2-openrouter-text-design.md`. Backend only — **no `frontend-next` changes**.
- **No new pip dependencies.** `openai>=1.40` and `respx>=0.21` are already in `requirements.txt`.
- New migration's `down_revision` MUST be `'b2c3d4e5f6a7'` (current head, `alembic/versions/b2c3d4e5f6a7_phase1_credit_system_v2.py`).
- `ai_models.fallback_model_code`: nullable `String(64)`, **no FK constraint** — fallback existence is validated at the service layer, not the DB layer.
- `provider_model_id` is never returned by any API endpoint and never means the user-facing code; the provider call uses `model=model.provider_model_id`, credit-ledger rows use `model.code`.
- Estimation defaults from the spec: `input_tokens=2000`, `output_tokens=1000`; confirmation threshold: `estimated_credits > 100`.
- `TIER_MAX` output-token caps (from the spec): `{economy: 1000, standard: 2000, premium: 4000, pro: 8000, ultra: 12000}`.
- Per-user Redis lock: key `ai_lock:{user.id}`, `AI_LOCK_TTL_SECONDS = 120` (same values as the old `ai_router.py`).
- User-facing copy, verbatim: 402 → `"Недостаточно кредитов"`; AIError 502 → `"Модель временно недоступна, попробуйте позже"`; busy 409 → `"Дождитесь ответа на предыдущий запрос."`.
- Confirmation 409 body is exactly `{"estimated_credits": N}` (top level, NOT wrapped in `"detail"`); the busy 409 uses the standard `{"detail": "..."}` shape so clients distinguish them by the presence of `estimated_credits`.
- Seed fallback pairs (only these two): `gpt_premium` → `gemini_flash`, `claude_opus` → `claude_sonnet`.
- Default model when `user.default_model_code` is unset: `"deepseek_v3"`.
- `credit_service` functions `flush()` but never `commit()` — `text_generation_service` owns the transaction and must commit the reserve BEFORE the external HTTP call.
- `app/api/deps.py` is NOT modified. `app/services/ai/image_service.py` and `piapi_client.py` are NOT touched (phase 3).
- Out of scope: fal.ai/images/video (phase 3), `/api/buy` and packages (phase 4), admin endpoints / rate limits / daily spend (phase 5), `/admin_stats` (phase 6).
- Known accepted breakage (pre-existing since phase 1, NOT fixed here): `app/main.py` still imports `admin`, `generate`, `payments`, `key_healthcheck`, etc., whose own imports are broken until phases 3–5. Therefore **API tests must NOT import `app.main`** — they build a minimal `FastAPI()` app from the routers under test (see Task 6).
- Test conventions: per-test-file `session` fixture on `sqlite+aiosqlite://` (no `conftest.py` in this project); test files whose import chain reaches `app.config` start with `os.environ.setdefault("BOT_TOKEN", ...)` / `os.environ.setdefault("DATABASE_URL", ...)` before any `app.*` import, because `app/config.py` instantiates `Settings()` at import time.

## File Map

| File | Action | Task |
|---|---|---|
| `alembic/versions/c4d5e6f7a8b9_phase2_fallback_model_code.py` | Create | 1 |
| `app/db/models/ai_models.py` | Modify (add column) | 1 |
| `app/db/seed.py` | Modify (2 fallback pairs) | 1 |
| `tests/db/test_seed_catalog.py` | Modify (add tests) | 1 |
| `app/config.py` | Modify (`OpenRouterSettings.api_key`) | 2 |
| `app/services/keys/api_key_manager.py` | Modify (`KeyPurpose.TEXT` mapping) | 2 |
| `.env.example` | Modify (`OPENROUTER_API_KEY`) | 2 |
| `tests/services/keys/test_openrouter_key.py` | Create | 2 |
| `app/services/ai/base.py` | Modify (import `AiModel`) | 3 |
| `app/services/ai/openrouter_service.py` | Create | 3 |
| `tests/services/ai/test_openrouter_service.py` | Create | 3 |
| `app/services/text_generation_service.py` | Create | 4 |
| `tests/services/test_text_generation_service.py` | Create | 4 |
| `app/services/ai/{ai_router,registry,claude_service,deepseek_service,gemini_service,openai_service}.py`, `app/services/{access_service,cost_service}.py`, `app/api/routes/tariffs.py` | Delete | 5 |
| `app/main.py` | Modify (drop `tariffs` import/router) | 5 |
| `app/api/routes/chat.py` | Rewrite | 6 |
| `tests/api/__init__.py`, `tests/api/test_chat_routes.py` | Create | 6 |
| `app/api/routes/me.py` | Rewrite | 7 |
| `app/api/schemas.py` | Rewrite (simplified `MeOut` only) | 7 |
| `tests/api/test_chat_routes.py` | Modify (add `/api/me` tests) | 7 |

---

### Task 1: `ai_models.fallback_model_code` — migration, ORM column, seed pairs

**Files:**
- Create: `alembic/versions/c4d5e6f7a8b9_phase2_fallback_model_code.py`
- Modify: `app/db/models/ai_models.py` (add one column after `sort_order`)
- Modify: `app/db/seed.py:68-82` (the `gpt_premium` and `claude_opus` entries)
- Test: `tests/db/test_seed_catalog.py` (append tests)

**Interfaces:**
- Consumes: `AiModel` ORM model (phase 1), `AI_MODELS` seed list, `apply_seed(session)`.
- Produces: `AiModel.fallback_model_code: Mapped[str | None]` — read by `text_generation_service._resolve_model` (Task 4). Seed rows: `gpt_premium.fallback_model_code == "gemini_flash"`, `claude_opus.fallback_model_code == "claude_sonnet"`, all other models `None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/db/test_seed_catalog.py`:

```python
def test_fallback_pairs_from_phase2_spec():
    by_code = {m["code"]: m for m in AI_MODELS}
    assert by_code["gpt_premium"]["fallback_model_code"] == "gemini_flash"
    assert by_code["claude_opus"]["fallback_model_code"] == "claude_sonnet"
    with_fallback = {m["code"] for m in AI_MODELS if m.get("fallback_model_code")}
    assert with_fallback == {"gpt_premium", "claude_opus"}


async def test_fallback_column_roundtrips_through_orm(session):
    await apply_seed(session)
    row = (
        await session.execute(select(AiModel).where(AiModel.code == "gpt_premium"))
    ).scalar_one()
    assert row.fallback_model_code == "gemini_flash"
    deepseek = (
        await session.execute(select(AiModel).where(AiModel.code == "deepseek_v3"))
    ).scalar_one()
    assert deepseek.fallback_model_code is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/db/test_seed_catalog.py -v`
Expected: FAIL — `test_fallback_pairs_from_phase2_spec` with `KeyError: 'fallback_model_code'` (or assertion on missing key), `test_fallback_column_roundtrips_through_orm` with `AttributeError`/`TypeError` (column does not exist).

- [ ] **Step 3: Add the ORM column**

In `app/db/models/ai_models.py`, after the `sort_order` line, add:

```python
    # Код резервной модели той же категории (без FK: существование fallback-модели
    # валидируется в text_generation_service, не на уровне БД -- см. спеку фазы 2).
    fallback_model_code: Mapped[str | None] = mapped_column(String(64))
```

- [ ] **Step 4: Update the two seed entries**

In `app/db/seed.py`, change exactly these two dicts (add the `fallback_model_code` key; everything else untouched):

```python
    dict(**_TEXT, code="gpt_premium", display_name="GPT Premium", tier=ModelTier.premium,
         provider_model_id="openai/gpt-4o",  # PLACEHOLDER
         min_credits=20, recommended_credits=30, sort_order=80,
         fallback_model_code="gemini_flash"),
```

```python
    dict(**_TEXT, code="claude_opus", display_name="Claude Opus", tier=ModelTier.ultra,
         provider_model_id="anthropic/claude-3-opus",  # PLACEHOLDER
         min_credits=70, recommended_credits=90, sort_order=120,
         fallback_model_code="claude_sonnet"),
```

- [ ] **Step 5: Write the migration**

Create `alembic/versions/c4d5e6f7a8b9_phase2_fallback_model_code.py`:

```python
"""phase2: add ai_models.fallback_model_code (nullable, no FK --
validated at the service layer, see phase 2 spec).

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-07-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ai_models', sa.Column('fallback_model_code', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('ai_models', 'fallback_model_code')
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/db/ -v`
Expected: PASS (all, including pre-existing seed/schema tests — the new dict key must not break `test_model_codes_and_credit_floors_match_tz`).

- [ ] **Step 7: Commit**

```bash
git add alembic/versions/c4d5e6f7a8b9_phase2_fallback_model_code.py app/db/models/ai_models.py app/db/seed.py tests/db/test_seed_catalog.py
git commit -m "feat: add ai_models.fallback_model_code with seed fallback pairs"
```

---

### Task 2: OpenRouter API key — config field, key-manager mapping, .env.example

**Files:**
- Modify: `app/config.py:82-84` (`OpenRouterSettings`)
- Modify: `app/services/keys/api_key_manager.py:62-64` (`_PURPOSE_ATTR[Provider.OPENROUTER]`)
- Modify: `.env.example:69-71` (OpenRouter block)
- Test: `tests/services/keys/test_openrouter_key.py`

**Interfaces:**
- Consumes: `ApiKeyManager.get_key(provider: Provider, purpose: KeyPurpose) -> str`, `Provider.OPENROUTER`, `KeyPurpose.TEXT` (all already exist).
- Produces: `get_key_manager().get_key(Provider.OPENROUTER, KeyPurpose.TEXT)` resolves to the `OPENROUTER_API_KEY` env var — used by `OpenRouterProvider` (Task 3). New field: `OpenRouterSettings.api_key: SecretStr | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/services/keys/test_openrouter_key.py` (pattern copied from `tests/services/keys/test_piapi_key.py`):

```python
from app.config import Settings
from app.services.keys.api_key_manager import ApiKeyManager
from app.services.keys.enums import KeyPurpose, Provider


def test_openrouter_text_purpose_uses_api_key(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-123")
    settings = Settings()
    manager = ApiKeyManager(settings)

    assert manager.get_key(Provider.OPENROUTER, KeyPurpose.TEXT) == "sk-or-test-123"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/services/keys/test_openrouter_key.py -v`
Expected: FAIL with `ApiKeyPurposeNotSupportedError: Provider.OPENROUTER has no key configured for purpose=KeyPurpose.TEXT`.

- [ ] **Step 3: Implement**

In `app/config.py`, replace the `OpenRouterSettings` class with:

```python
class OpenRouterSettings(_ProviderSettings):
    api_key: SecretStr | None = Field(default=None, alias="OPENROUTER_API_KEY")
    fallback_key: SecretStr | None = Field(default=None, alias="OPENROUTER_FALLBACK_KEY")
    dev_key: SecretStr | None = Field(default=None, alias="OPENROUTER_DEV_KEY")
```

In `app/services/keys/api_key_manager.py`, replace the `Provider.OPENROUTER` entry of `_PURPOSE_ATTR` with:

```python
    Provider.OPENROUTER: {
        KeyPurpose.TEXT: "api_key",
        KeyPurpose.FALLBACK: "fallback_key",
    },
```

In `.env.example`, replace the OpenRouter block with:

```
# OpenRouter
OPENROUTER_API_KEY=
OPENROUTER_FALLBACK_KEY=
OPENROUTER_DEV_KEY=
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/services/keys/ -v`
Expected: PASS (new test + existing `test_piapi_key.py`).

- [ ] **Step 5: Commit**

```bash
git add app/config.py app/services/keys/api_key_manager.py .env.example tests/services/keys/test_openrouter_key.py
git commit -m "feat: wire OPENROUTER_API_KEY through settings and key manager"
```

---

### Task 3: `OpenRouterProvider` + `base.py` import fix

**Files:**
- Modify: `app/services/ai/base.py:4,21` (`ModelConfig` → `AiModel`)
- Create: `app/services/ai/openrouter_service.py`
- Test: `tests/services/ai/test_openrouter_service.py`

**Interfaces:**
- Consumes: `AIProvider`/`AIResult`/`AIError` from `app/services/ai/base.py`; `get_key_manager().get_key(Provider.OPENROUTER, KeyPurpose.TEXT)` (Task 2); `AiModel.provider_model_id`.
- Produces: `class OpenRouterProvider(AIProvider)` with `async def generate(self, model: AiModel, prompt: str, max_output_tokens: int, extra: dict | None = None) -> AIResult` — instantiated as the module-level `_provider` in `text_generation_service` (Task 4). Raises `AIError` on any provider failure.

- [ ] **Step 1: Fix `base.py`**

In `app/services/ai/base.py`, change line 4 from `from app.db.models import ModelConfig` to `from app.db.models import AiModel`, and in the `generate` signature change `model: ModelConfig` to `model: AiModel`.

- [ ] **Step 2: Write the failing tests**

Create `tests/services/ai/test_openrouter_service.py`. Mocking approach: `respx` intercepting the AsyncOpenAI client's underlying httpx transport, same library as `tests/services/ai/test_piapi_client.py` (the openai SDK is httpx-based, so `@respx.mock` catches its requests). The key manager is monkeypatched so the test never depends on a developer's real `.env`.

```python
import json
import os

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("DATABASE_URL", "postgresql://test")

import httpx
import pytest
import respx

from app.db.enums import CostUnit, ModelCategory, ModelProvider, ModelTier
from app.db.models import AiModel
from app.services.ai import openrouter_service
from app.services.ai.base import AIError
from app.services.ai.openrouter_service import OpenRouterProvider

COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"


class _FakeKeyManager:
    def get_key(self, provider, purpose):
        return "sk-or-test"


@pytest.fixture(autouse=True)
def fake_key_manager(monkeypatch):
    monkeypatch.setattr(openrouter_service, "get_key_manager", lambda: _FakeKeyManager())
    openrouter_service._clients.clear()
    yield
    openrouter_service._clients.clear()


def _text_model() -> AiModel:
    return AiModel(
        provider=ModelProvider.openrouter, category=ModelCategory.text,
        code="deepseek_v3", display_name="DeepSeek V3",
        provider_model_id="deepseek/deepseek-chat", tier=ModelTier.economy,
        cost_unit=CostUnit.tokens, min_credits=3, recommended_credits=3,
    )


@respx.mock
async def test_generate_success_returns_answer_and_usage():
    route = respx.post(COMPLETIONS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "gen-1",
                "object": "chat.completion",
                "created": 1720000000,
                "model": "deepseek/deepseek-chat",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Привет!"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 34, "total_tokens": 46},
            },
        )
    )

    result = await OpenRouterProvider().generate(_text_model(), "hi", 1000)

    assert result.answer == "Привет!"
    assert result.input_tokens == 12
    assert result.output_tokens == 34

    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer sk-or-test"
    body = json.loads(request.content)
    assert body["model"] == "deepseek/deepseek-chat"  # provider_model_id, НЕ model.code
    assert body["max_tokens"] == 1000
    assert body["messages"] == [{"role": "user", "content": "hi"}]


@respx.mock
async def test_generate_wraps_http_error_as_aierror():
    # 400 не ретраится openai-SDK -- тест мгновенный.
    respx.post(COMPLETIONS_URL).mock(return_value=httpx.Response(400, json={"error": "bad"}))
    with pytest.raises(AIError):
        await OpenRouterProvider().generate(_text_model(), "hi", 1000)


@respx.mock
async def test_generate_wraps_timeout_as_aierror():
    # Таймауты SDK ретраит (max_retries=2 по умолчанию) -- тест занимает ~1-2 c.
    respx.post(COMPLETIONS_URL).mock(side_effect=httpx.TimeoutException("timed out"))
    with pytest.raises(AIError):
        await OpenRouterProvider().generate(_text_model(), "hi", 1000)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/services/ai/test_openrouter_service.py -v`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'app.services.ai.openrouter_service'`.

- [ ] **Step 4: Implement the provider**

Create `app/services/ai/openrouter_service.py` (exact `DeepSeekProvider` pattern from the now-legacy `deepseek_service.py`, plus logging of the real cause per the spec):

```python
import logging

from openai import AsyncOpenAI

from app.db.models import AiModel
from app.services.ai.base import AIError, AIProvider, AIResult
from app.services.keys.api_key_manager import get_key_manager
from app.services.keys.enums import KeyPurpose, Provider

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

_clients: dict[str, AsyncOpenAI] = {}


def _get_client() -> AsyncOpenAI:
    api_key = get_key_manager().get_key(Provider.OPENROUTER, KeyPurpose.TEXT)
    client = _clients.get(api_key)
    if client is None:
        client = AsyncOpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)
        _clients[api_key] = client
    return client


class OpenRouterProvider(AIProvider):
    """OpenRouter даёт OpenAI-совместимый chat-completions API (тот же паттерн,
    что был у DeepSeekProvider). Единственный текстовый провайдер с фазы 2."""

    async def generate(
        self, model: AiModel, prompt: str, max_output_tokens: int, extra: dict | None = None
    ) -> AIResult:
        try:
            client = _get_client()
            response = await client.chat.completions.create(
                model=model.provider_model_id,
                max_tokens=max_output_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return AIResult(
                answer=response.choices[0].message.content or "",
                input_tokens=response.usage.prompt_tokens if response.usage else 0,
                output_tokens=response.usage.completion_tokens if response.usage else 0,
            )
        except Exception as exc:
            # Реальная причина -- только в лог; пользователю уходит нейтральный текст.
            logger.exception("OpenRouter request failed for model %s", model.code)
            raise AIError("OpenRouter API error") from exc
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/services/ai/test_openrouter_service.py -v`
Expected: PASS (3 tests; the timeout test may take ~1–2 s due to SDK retries — that is expected).

- [ ] **Step 6: Commit**

```bash
git add app/services/ai/base.py app/services/ai/openrouter_service.py tests/services/ai/test_openrouter_service.py
git commit -m "feat: add OpenRouterProvider and switch AIProvider base to AiModel"
```

---

### Task 4: `text_generation_service` — the reserve → call → settle/refund flow

**Files:**
- Create: `app/services/text_generation_service.py`
- Test: `tests/services/test_text_generation_service.py`

**Interfaces:**
- Consumes: `reserve_credits(session, user_id, amount, *, request_id, provider, model_code)`, `settle_request(session, request, actual_credits)`, `refund_request(session, request, *, reason)`, `InsufficientBalanceError` (`app/services/credit_service.py`); `calculate_text_credits(model, input_tokens, output_tokens, *, settings)` (`app/services/pricing.py`); `load_pricing_settings(session)` (`app/services/settings_service.py`); `OpenRouterProvider` (Task 3); `redis_client` (`app/redis_client.py`); `AiModel.fallback_model_code` (Task 1).
- Produces (consumed by Task 6's `chat.py`):
  - `async def generate_text(session: AsyncSession, user: User, model_code: str, prompt: str, *, confirm: bool = False) -> TextGenerationResult`
  - `@dataclass TextGenerationResult(answer: str, charged_credits: int, balance_after: int)`
  - Exceptions: `ModelNotFoundError`, `ModelUnavailableError`, `RequestInProgressError`, `ConfirmationRequiredError(estimated_credits: int)` (attribute `.estimated_credits`); re-raises `InsufficientBalanceError` and `AIError`.
  - Constants: `TIER_MAX: dict[ModelTier, int]`, `AI_LOCK_TTL_SECONDS = 120`, `ESTIMATE_INPUT_TOKENS = 2000`, `ESTIMATE_OUTPUT_TOKENS = 1000`, `CONFIRM_THRESHOLD_CREDITS = 100`.
  - Module attribute `_provider: AIProvider` (an `OpenRouterProvider()` instance) — tests monkeypatch it.

**Pricing arithmetic used by the tests below** (defaults: `usd_to_rub_rate=80`, `rub_per_credit=0.10`, `provider_fee_multiplier=1.15`, `margin_multiplier=2.5`, `minimum_text_credits=3`; empty `settings` table → these defaults):
- Cheap model, both prices `1` USD/1M: estimate (2000 in / 1000 out) → `ceil(0.003 × 80 × 1.15 × 2.5 / 0.10) = 7` credits; actual usage 500/200 → `max(ceil(0.0007 × 2300), 3) = 3` credits.
- Expensive model, both prices `20`: estimate → `ceil(0.06 × 2300) = 138` credits (> 100 → confirmation); actual 500/200 → `ceil(0.014 × 2300) = 33` credits.

- [ ] **Step 1: Write the failing tests**

Create `tests/services/test_text_generation_service.py`:

```python
import os

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("DATABASE_URL", "postgresql://test")

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.enums import (
    CostUnit,
    CreditTxType,
    ModelCategory,
    ModelProvider,
    ModelTier,
    RequestStatus,
)
from app.db.models import AIRequest, AiModel, CreditTransaction, User
from app.services import text_generation_service as tgs
from app.services.ai.base import AIError, AIProvider, AIResult
from app.services.credit_service import InsufficientBalanceError
from app.services.text_generation_service import (
    ConfirmationRequiredError,
    ModelNotFoundError,
    ModelUnavailableError,
    RequestInProgressError,
    TextGenerationResult,
    generate_text,
)


class FakeRedis:
    def __init__(self, locked: bool = False):
        self.locked = locked
        self.deleted: list[str] = []

    async def set(self, key, value, nx=False, ex=None):
        return None if self.locked else True

    async def delete(self, key):
        self.deleted.append(key)


class FakeProvider(AIProvider):
    def __init__(self, result: AIResult | None = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[tuple[str, str, int]] = []

    async def generate(self, model, prompt, max_output_tokens, extra=None):
        self.calls.append((model.code, prompt, max_output_tokens))
        if self.error is not None:
            raise self.error
        return self.result


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
    monkeypatch.setattr(tgs, "redis_client", fake)
    return fake


def _model(code="cheap", *, tier=ModelTier.economy, price=1, min_credits=3,
           recommended=3, is_active=True, fallback=None) -> AiModel:
    return AiModel(
        provider=ModelProvider.openrouter, category=ModelCategory.text, code=code,
        display_name=code, provider_model_id=f"vendor/{code}", tier=tier,
        input_price_usd_per_1m_tokens=price, output_price_usd_per_1m_tokens=price,
        cost_unit=CostUnit.tokens, min_credits=min_credits,
        recommended_credits=recommended, is_active=is_active,
        fallback_model_code=fallback,
    )


async def _seed(session, *models, balance=100) -> User:
    user = User(telegram_id=1, username="u", credits_balance=balance)
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
            await session.execute(select(CreditTransaction.type).order_by(CreditTransaction.id))
        ).all()
    ]


# --- успешная генерация ---

async def test_success_reserves_settles_and_returns_result(session, fake_redis, monkeypatch):
    user = await _seed(session, _model())  # цена 1 -> оценка 7 кредитов
    provider = FakeProvider(result=AIResult(answer="ответ", input_tokens=500, output_tokens=200))
    monkeypatch.setattr(tgs, "_provider", provider)

    result = await generate_text(session, user, "cheap", "привет")

    assert isinstance(result, TextGenerationResult)
    assert result.answer == "ответ"
    assert result.charged_credits == 3      # actual по факту (500/200) = 3
    assert result.balance_after == 97       # 100 - 3

    assert provider.calls == [("cheap", "привет", 1000)]  # TIER_MAX[economy]

    [request] = await _request_rows(session)
    assert request.status == RequestStatus.completed
    assert request.model_code == "cheap"
    assert request.provider == "openrouter"
    assert request.estimated_credits == 7
    assert request.reserved_credits == 7
    assert request.charged_credits == 3
    assert request.input_tokens == 500
    assert request.output_tokens == 200
    assert request.prompt_preview == "привет"

    assert await _tx_types(session) == [CreditTxType.reserve, CreditTxType.release]
    assert fake_redis.deleted == [f"ai_lock:{user.id}"]


async def test_tier_max_caps_output_tokens(session, monkeypatch):
    user = await _seed(session, _model(code="big", tier=ModelTier.ultra))
    provider = FakeProvider(result=AIResult(answer="a", input_tokens=1, output_tokens=1))
    monkeypatch.setattr(tgs, "_provider", provider)

    await generate_text(session, user, "big", "hi")

    assert provider.calls[0][2] == 12000  # TIER_MAX[ultra]


# --- ошибка провайдера -> refund ---

async def test_provider_error_refunds_and_reraises(session, fake_redis, monkeypatch):
    user = await _seed(session, _model())
    monkeypatch.setattr(tgs, "_provider", FakeProvider(error=AIError("boom")))

    with pytest.raises(AIError):
        await generate_text(session, user, "cheap", "привет")

    [request] = await _request_rows(session)
    assert request.status == RequestStatus.refunded
    assert request.charged_credits == 0
    assert request.error_message == "boom"

    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 100  # резерв возвращён полностью
    assert await _tx_types(session) == [CreditTxType.reserve, CreditTxType.refund]
    assert fake_redis.deleted == [f"ai_lock:{user.id}"]  # лок снят и при ошибке


# --- подтверждение дорогого запроса ---

async def test_expensive_estimate_without_confirm_raises_confirmation(session, fake_redis, monkeypatch):
    user = await _seed(session, _model(code="exp", price=20, min_credits=20, recommended=30), balance=500)
    provider = FakeProvider(result=AIResult(answer="a", input_tokens=1, output_tokens=1))
    monkeypatch.setattr(tgs, "_provider", provider)

    with pytest.raises(ConfirmationRequiredError) as exc_info:
        await generate_text(session, user, "exp", "hi")

    assert exc_info.value.estimated_credits == 138  # оценка 2000/1000 при цене 20
    assert provider.calls == []                      # до провайдера не дошли
    assert await _request_rows(session) == []        # ничего не создано
    assert await _tx_types(session) == []            # ничего не зарезервировано
    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 500
    assert fake_redis.deleted == [f"ai_lock:{user.id}"]  # лок снят


async def test_expensive_estimate_with_confirm_proceeds(session, monkeypatch):
    user = await _seed(session, _model(code="exp", price=20, min_credits=20, recommended=30), balance=500)
    provider = FakeProvider(result=AIResult(answer="a", input_tokens=500, output_tokens=200))
    monkeypatch.setattr(tgs, "_provider", provider)

    result = await generate_text(session, user, "exp", "hi", confirm=True)

    assert result.charged_credits == 33   # actual при цене 20 и usage 500/200
    assert result.balance_after == 467    # 500 - 33


# --- недостаточный баланс ---

async def test_insufficient_balance_rolls_back_pending_request(session, monkeypatch):
    user = await _seed(session, _model(), balance=5)  # оценка 7 > 5
    user_id = user.id  # захват ДО rollback: после него доступ к user.id -- sync
    # lazy-load (MissingGreenlet), см. комментарий в test_credit_service.py:82.
    monkeypatch.setattr(tgs, "_provider", FakeProvider())

    with pytest.raises(InsufficientBalanceError):
        await generate_text(session, user, "cheap", "hi")

    assert await _request_rows(session) == []  # pending-запись откатилась
    assert await _tx_types(session) == []
    fetched = await session.get(User, user_id)
    assert fetched.credits_balance == 5


# --- fallback ---

async def test_inactive_model_falls_back_to_fallback_code(session, monkeypatch):
    primary = _model(code="dead", is_active=False, fallback="alive")
    fallback = _model(code="alive")
    user = await _seed(session, primary, fallback)
    provider = FakeProvider(result=AIResult(answer="a", input_tokens=500, output_tokens=200))
    monkeypatch.setattr(tgs, "_provider", provider)

    result = await generate_text(session, user, "dead", "hi")

    assert result.charged_credits == 3
    assert provider.calls == [("alive", "hi", 1000)]
    [request] = await _request_rows(session)
    assert request.model_code == "alive"  # биллинг на фактическую модель


async def test_more_expensive_fallback_without_confirm_raises_confirmation(session, monkeypatch):
    primary = _model(code="dead", recommended=3, is_active=False, fallback="pricey")
    fallback = _model(code="pricey", recommended=10)  # дороже по recommended_credits
    user = await _seed(session, primary, fallback)
    monkeypatch.setattr(tgs, "_provider", FakeProvider())

    with pytest.raises(ConfirmationRequiredError) as exc_info:
        await generate_text(session, user, "dead", "hi")

    assert exc_info.value.estimated_credits == 7  # оценка по fallback-модели (цена 1)
    assert await _request_rows(session) == []


async def test_more_expensive_fallback_with_confirm_proceeds(session, monkeypatch):
    primary = _model(code="dead", recommended=3, is_active=False, fallback="pricey")
    fallback = _model(code="pricey", recommended=10)
    user = await _seed(session, primary, fallback)
    provider = FakeProvider(result=AIResult(answer="a", input_tokens=500, output_tokens=200))
    monkeypatch.setattr(tgs, "_provider", provider)

    result = await generate_text(session, user, "dead", "hi", confirm=True)

    assert result.charged_credits == 3
    assert provider.calls[0][0] == "pricey"


# --- ошибки резолва модели ---

async def test_unknown_code_raises_model_not_found(session, monkeypatch):
    user = await _seed(session, _model())
    monkeypatch.setattr(tgs, "_provider", FakeProvider())
    with pytest.raises(ModelNotFoundError):
        await generate_text(session, user, "no_such_model", "hi")


async def test_inactive_without_fallback_raises_model_unavailable(session, monkeypatch):
    user = await _seed(session, _model(code="dead", is_active=False))
    monkeypatch.setattr(tgs, "_provider", FakeProvider())
    with pytest.raises(ModelUnavailableError):
        await generate_text(session, user, "dead", "hi")


async def test_inactive_fallback_chain_raises_aierror(session, monkeypatch):
    primary = _model(code="dead", is_active=False, fallback="also_dead")
    fallback = _model(code="also_dead", is_active=False)
    user = await _seed(session, primary, fallback)
    monkeypatch.setattr(tgs, "_provider", FakeProvider())
    with pytest.raises(AIError):
        await generate_text(session, user, "dead", "hi")


# --- per-user лок ---

async def test_busy_lock_raises_request_in_progress(session, monkeypatch):
    user = await _seed(session, _model())
    monkeypatch.setattr(tgs, "redis_client", FakeRedis(locked=True))
    monkeypatch.setattr(tgs, "_provider", FakeProvider())

    with pytest.raises(RequestInProgressError):
        await generate_text(session, user, "cheap", "hi")

    assert await _request_rows(session) == []
    assert await _tx_types(session) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/services/test_text_generation_service.py -v`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'app.services.text_generation_service'`.

- [ ] **Step 3: Implement the service**

Create `app/services/text_generation_service.py`:

```python
"""Текстовый flow поверх движка кредитов (фаза 2, замена ai_router.py).

Порядок (спека фазы 2): резолв модели (+fallback) -> Redis-лок -> оценка ->
подтверждение дорогого запроса -> AIRequest + reserve (commit ДО внешнего
HTTP-вызова) -> OpenRouter -> settle / refund -> снятие лока (finally).
"""

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ModelCategory, ModelTier, RequestStatus
from app.db.models import AIRequest, AiModel, User
from app.redis_client import redis_client
from app.services.ai.base import AIError, AIProvider
from app.services.ai.openrouter_service import OpenRouterProvider
from app.services.credit_service import (
    InsufficientBalanceError,
    refund_request,
    reserve_credits,
    settle_request,
)
from app.services.pricing import calculate_text_credits
from app.services.settings_service import load_pricing_settings

logger = logging.getLogger(__name__)

AI_LOCK_TTL_SECONDS = 120  # как в старом ai_router.py
ESTIMATE_INPUT_TOKENS = 2000   # дефолты оценки из ТЗ
ESTIMATE_OUTPUT_TOKENS = 1000
CONFIRM_THRESHOLD_CREDITS = 100

# Потолок max_output_tokens по tier (ТЗ: "Ограничить max_output_tokens по tier").
TIER_MAX: dict[ModelTier, int] = {
    ModelTier.economy: 1000,
    ModelTier.standard: 2000,
    ModelTier.premium: 4000,
    ModelTier.pro: 8000,
    ModelTier.ultra: 12000,
}

# Единственный текстовый провайдер фазы 2. Тесты подменяют monkeypatch'ем.
_provider: AIProvider = OpenRouterProvider()


class ModelNotFoundError(Exception):
    """model_code отсутствует в каталоге текстовых моделей."""


class ModelUnavailableError(Exception):
    """Модель выключена (is_active=False), fallback не задан."""


class RequestInProgressError(Exception):
    user_message = "Дождитесь ответа на предыдущий запрос."


class ConfirmationRequiredError(Exception):
    """Оценка дороже порога (или fallback дороже основной модели) без confirm=True."""

    def __init__(self, estimated_credits: int):
        self.estimated_credits = estimated_credits
        super().__init__(f"confirmation required: estimated {estimated_credits} credits")


@dataclass
class TextGenerationResult:
    answer: str
    charged_credits: int
    balance_after: int


async def _get_text_model(session: AsyncSession, code: str) -> AiModel | None:
    return (
        await session.execute(
            select(AiModel).where(AiModel.code == code, AiModel.category == ModelCategory.text)
        )
    ).scalar_one_or_none()


async def _resolve_model(session: AsyncSession, model_code: str) -> tuple[AiModel, AiModel]:
    """Возвращает (эффективная модель, запрошенная модель).

    Активная модель -> она сама. Неактивная с fallback_model_code -> активная
    fallback-модель. Иначе ModelNotFoundError / ModelUnavailableError / AIError
    (fallback тоже недоступен -- по спеке).
    """
    requested = await _get_text_model(session, model_code)
    if requested is None:
        raise ModelNotFoundError(model_code)
    if requested.is_active:
        return requested, requested
    if not requested.fallback_model_code:
        raise ModelUnavailableError(model_code)
    fallback = await _get_text_model(session, requested.fallback_model_code)
    if fallback is None or not fallback.is_active:
        raise AIError(f"model {model_code} and its fallback {requested.fallback_model_code} are unavailable")
    logger.info("model %s is inactive, falling back to %s", model_code, fallback.code)
    return fallback, requested


async def generate_text(
    session: AsyncSession, user: User, model_code: str, prompt: str, *, confirm: bool = False
) -> TextGenerationResult:
    model, requested = await _resolve_model(session, model_code)

    lock_key = f"ai_lock:{user.id}"
    acquired = await redis_client.set(lock_key, "1", nx=True, ex=AI_LOCK_TTL_SECONDS)
    if not acquired:
        raise RequestInProgressError()

    try:
        pricing = await load_pricing_settings(session)
        estimated = calculate_text_credits(
            model, ESTIMATE_INPUT_TOKENS, ESTIMATE_OUTPUT_TOKENS, settings=pricing
        )

        fallback_used = model is not requested
        needs_confirmation = estimated > CONFIRM_THRESHOLD_CREDITS or (
            fallback_used and model.recommended_credits > requested.recommended_credits
        )
        if needs_confirmation and not confirm:
            # Ничего не создано и не зарезервировано; лок снимется в finally.
            raise ConfirmationRequiredError(estimated)

        request = AIRequest(
            user_id=user.id,
            provider="openrouter",
            model_code=model.code,
            category=ModelCategory.text,
            status=RequestStatus.pending,
            prompt_preview=prompt[:200],
            estimated_credits=estimated,
            reserved_credits=estimated,
        )
        session.add(request)
        await session.flush()

        try:
            await reserve_credits(
                session,
                user.id,
                estimated,
                request_id=request.id,
                provider="openrouter",
                model_code=model.code,
            )
        except InsufficientBalanceError:
            await session.rollback()  # убрать pending-AIRequest вместе с несостоявшимся резервом
            raise
        # reserve_credits не трогает статус AIRequest -- это ответственность вызывающего.
        request.status = RequestStatus.reserved
        await session.commit()  # резерв фиксируется ДО долгого внешнего вызова

        try:
            result = await _provider.generate(model, prompt, TIER_MAX[model.tier])
        except AIError as exc:
            request.error_message = str(exc)
            await refund_request(session, request, reason=f"provider error: {exc}")
            await session.commit()
            raise

        request.input_tokens = result.input_tokens
        request.output_tokens = result.output_tokens
        actual = calculate_text_credits(
            model, result.input_tokens, result.output_tokens, settings=pricing
        )
        await settle_request(session, request, actual)
        charged = request.charged_credits
        balance_after = user.credits_balance
        await session.commit()

        return TextGenerationResult(
            answer=result.answer, charged_credits=charged, balance_after=balance_after
        )
    finally:
        await redis_client.delete(lock_key)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/services/test_text_generation_service.py -v`
Expected: PASS (13 tests).

- [ ] **Step 5: Run the whole services suite for regressions**

Run: `python -m pytest tests/services/ tests/db/ -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/text_generation_service.py tests/services/test_text_generation_service.py
git commit -m "feat: add text_generation_service with reserve/settle/refund flow"
```

---

### Task 5: Delete the legacy text pipeline and the tariffs route

**Files:**
- Delete: `app/services/ai/ai_router.py`, `app/services/ai/registry.py`, `app/services/ai/claude_service.py`, `app/services/ai/deepseek_service.py`, `app/services/ai/gemini_service.py`, `app/services/ai/openai_service.py`, `app/services/access_service.py`, `app/services/cost_service.py`, `app/api/routes/tariffs.py`
- Modify: `app/main.py:9,72` (drop the `tariffs` import and its `include_router`)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing — pure removal. `app/api/routes/chat.py` and `me.py` still reference deleted symbols after this task; they are already unimportable since phase 1 and are rewritten in Tasks 6–7. `app/services/generation_service.py`, `admin.py`, `payments*` etc. stay broken as accepted phase-1 breakage (rebuilt in phases 3–5).

- [ ] **Step 1: Delete the files**

```bash
git rm app/services/ai/ai_router.py app/services/ai/registry.py app/services/ai/claude_service.py app/services/ai/deepseek_service.py app/services/ai/gemini_service.py app/services/ai/openai_service.py app/services/access_service.py app/services/cost_service.py app/api/routes/tariffs.py
```

- [ ] **Step 2: Remove tariffs from `app/main.py`**

Change line 9 from:

```python
from app.api.routes import admin, banners, chat, generate, me, payments, referral, tariffs, tools
```

to:

```python
from app.api.routes import admin, banners, chat, generate, me, payments, referral, tools
```

and delete the line:

```python
app.include_router(tariffs.router, prefix="/api")
```

- [ ] **Step 3: Verify nothing under test references the deleted modules**

Run: `python -m pytest tests/ -v`
Expected: PASS — the existing suite never imports the deleted modules.

Run: `grep -rn "ai_router\|access_service\|cost_service\|ai.registry\|claude_service\|deepseek_service\|gemini_service\|openai_service\|routes import.*tariffs\|tariffs.router" app/api/routes/chat.py app/main.py`
Expected: hits ONLY in `app/api/routes/chat.py` (rewritten in Task 6); zero hits in `app/main.py`.

- [ ] **Step 4: Commit**

```bash
git add app/main.py
git commit -m "chore: delete legacy text pipeline, per-provider services and tariffs route"
```

---

### Task 6: Rewrite `chat.py` — `GET /api/models` + `POST /api/chat`

**Files:**
- Modify (full rewrite): `app/api/routes/chat.py`
- Create: `tests/api/__init__.py` (empty file, matching `tests/services/__init__.py`)
- Test: `tests/api/test_chat_routes.py`

**Interfaces:**
- Consumes: `generate_text`, `TextGenerationResult`, `ConfirmationRequiredError` (attr `.estimated_credits`), `ModelNotFoundError`, `ModelUnavailableError`, `RequestInProgressError` (Task 4); `InsufficientBalanceError` (`credit_service`); `AIError` (`ai/base.py`); `current_user`, `get_db` (`app/api/deps.py`, unmodified); `AiModel` catalog columns.
- Produces: `router: APIRouter` with `GET /models` and `POST /chat` (mounted under `/api` by `main.py`, unchanged); Pydantic models `ChatRequest(model_code, prompt, confirm)`, `ChatResponse(answer, charged_credits, balance_after)`, `ModelOut(code, display_name, tier, min_credits, recommended_credits)`.
- Error mapping: `ConfirmationRequiredError` → 409 body `{"estimated_credits": N}`; `RequestInProgressError` → 409 `{"detail": "Дождитесь ответа на предыдущий запрос."}`; `InsufficientBalanceError` → 402 `"Недостаточно кредитов"`; `ModelNotFoundError` → 404 `"model not found"`; `ModelUnavailableError` → 404 `"Эта модель временно отключена."`; `AIError` → 502 `"Модель временно недоступна, попробуйте позже"`.

- [ ] **Step 1: Write the failing tests**

Create empty `tests/api/__init__.py`, then create `tests/api/test_chat_routes.py`. Pattern restored from git history (`git show 9d3997b^:tests/api/test_generate_routes.py`): `httpx.AsyncClient(transport=ASGITransport(app=app))` + `app.dependency_overrides[current_user]`. Difference: `app.main` is unimportable until phases 3–5 (it imports `admin`/`generate`/`key_healthcheck`, broken since phase 1), so the test builds a minimal `FastAPI()` app from the routers under test — `dependency_overrides` work identically.

```python
import os

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("DATABASE_URL", "postgresql://test")

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import current_user, get_db
from app.api.routes import chat
from app.db.base import Base
from app.db.enums import CostUnit, ModelCategory, ModelProvider, ModelTier
from app.db.models import AiModel, User
from app.services.ai.base import AIError
from app.services.credit_service import InsufficientBalanceError
from app.services.text_generation_service import (
    ConfirmationRequiredError,
    ModelNotFoundError,
    ModelUnavailableError,
    RequestInProgressError,
    TextGenerationResult,
)

# app.main пока неимпортируем (admin/generate/payments чинятся в фазах 3-5),
# поэтому собираем минимальное приложение из тестируемых роутеров.
app = FastAPI()
app.include_router(chat.router, prefix="/api")

_test_user = User(
    id=1, telegram_id=1, username="u", first_name="U", is_admin=False,
    default_model_code=None, credits_balance=100,
    total_credits_purchased=0, total_credits_spent=0,
)


async def _fake_user():
    return _test_user


@pytest.fixture
async def db_sessionmaker():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


@pytest.fixture
async def client(db_sessionmaker):
    async def _get_db():
        async with db_sessionmaker() as s:
            yield s

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[current_user] = _fake_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


def _text_model(code, *, sort_order, tier=ModelTier.economy, is_active=True, is_visible=True,
                category=ModelCategory.text) -> AiModel:
    return AiModel(
        provider=ModelProvider.openrouter, category=category, code=code,
        display_name=code.upper(), provider_model_id=f"vendor/{code}", tier=tier,
        cost_unit=CostUnit.tokens, min_credits=3, recommended_credits=5,
        is_active=is_active, is_visible=is_visible, sort_order=sort_order,
    )


# --- GET /api/models ---

async def test_models_returns_visible_active_text_models_sorted(client, db_sessionmaker):
    async with db_sessionmaker() as s:
        s.add_all([
            _text_model("second", sort_order=20),
            _text_model("first", sort_order=10),
            _text_model("hidden", sort_order=30, is_visible=False),
            _text_model("inactive", sort_order=40, is_active=False),
            _text_model("image", sort_order=50, category=ModelCategory.image),
        ])
        await s.commit()

    response = await client.get("/api/models")

    assert response.status_code == 200
    payload = response.json()
    assert [m["code"] for m in payload] == ["first", "second"]
    assert payload[0] == {
        "code": "first",
        "display_name": "FIRST",
        "tier": "economy",
        "min_credits": 3,
        "recommended_credits": 5,
    }
    # provider_model_id никогда не уходит наружу (ТЗ).
    assert "provider_model_id" not in response.text


# --- POST /api/chat ---

async def test_chat_success_returns_answer_and_billing(client, monkeypatch):
    mock = AsyncMock(return_value=TextGenerationResult(answer="привет", charged_credits=5, balance_after=95))
    monkeypatch.setattr(chat, "generate_text", mock)

    response = await client.post("/api/chat", json={"model_code": "deepseek_v3", "prompt": "hi"})

    assert response.status_code == 200
    assert response.json() == {"answer": "привет", "charged_credits": 5, "balance_after": 95}
    # confirm по умолчанию False и прокидывается в сервис.
    assert mock.await_args.kwargs["confirm"] is False


async def test_chat_passes_confirm_true(client, monkeypatch):
    mock = AsyncMock(return_value=TextGenerationResult(answer="ok", charged_credits=110, balance_after=390))
    monkeypatch.setattr(chat, "generate_text", mock)

    response = await client.post(
        "/api/chat", json={"model_code": "claude_opus", "prompt": "hi", "confirm": True}
    )

    assert response.status_code == 200
    assert mock.await_args.kwargs["confirm"] is True


async def test_chat_confirmation_required_maps_to_409_with_estimate(client, monkeypatch):
    monkeypatch.setattr(chat, "generate_text", AsyncMock(side_effect=ConfirmationRequiredError(138)))

    response = await client.post("/api/chat", json={"model_code": "claude_opus", "prompt": "hi"})

    assert response.status_code == 409
    assert response.json() == {"estimated_credits": 138}  # ровно это тело, без "detail"


async def test_chat_request_in_progress_maps_to_409_detail(client, monkeypatch):
    monkeypatch.setattr(chat, "generate_text", AsyncMock(side_effect=RequestInProgressError()))

    response = await client.post("/api/chat", json={"model_code": "deepseek_v3", "prompt": "hi"})

    assert response.status_code == 409
    payload = response.json()
    assert "estimated_credits" not in payload  # отличимо от confirmation-409
    assert payload["detail"] == "Дождитесь ответа на предыдущий запрос."


async def test_chat_insufficient_balance_maps_to_402(client, monkeypatch):
    monkeypatch.setattr(
        chat, "generate_text",
        AsyncMock(side_effect=InsufficientBalanceError(balance=5, required=7)),
    )

    response = await client.post("/api/chat", json={"model_code": "deepseek_v3", "prompt": "hi"})

    assert response.status_code == 402
    assert response.json()["detail"] == "Недостаточно кредитов"


async def test_chat_unknown_model_maps_to_404(client, monkeypatch):
    monkeypatch.setattr(chat, "generate_text", AsyncMock(side_effect=ModelNotFoundError("nope")))
    response = await client.post("/api/chat", json={"model_code": "nope", "prompt": "hi"})
    assert response.status_code == 404


async def test_chat_unavailable_model_maps_to_404(client, monkeypatch):
    monkeypatch.setattr(chat, "generate_text", AsyncMock(side_effect=ModelUnavailableError("dead")))
    response = await client.post("/api/chat", json={"model_code": "dead", "prompt": "hi"})
    assert response.status_code == 404


async def test_chat_provider_error_maps_to_502(client, monkeypatch):
    monkeypatch.setattr(chat, "generate_text", AsyncMock(side_effect=AIError("boom")))
    response = await client.post("/api/chat", json={"model_code": "deepseek_v3", "prompt": "hi"})
    assert response.status_code == 502
    assert response.json()["detail"] == "Модель временно недоступна, попробуйте позже"


async def test_chat_empty_prompt_is_422(client):
    response = await client.post("/api/chat", json={"model_code": "deepseek_v3", "prompt": ""})
    assert response.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_chat_routes.py -v`
Expected: FAIL at collection with `ImportError` — current `app/api/routes/chat.py` still imports the deleted `ModelConfig`/`ai_router`/`access_service`.

- [ ] **Step 3: Rewrite `app/api/routes/chat.py`**

Replace the entire file with:

```python
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_db
from app.db.enums import ModelCategory
from app.db.models import AiModel, User
from app.services.ai.base import AIError
from app.services.credit_service import InsufficientBalanceError
from app.services.text_generation_service import (
    ConfirmationRequiredError,
    ModelNotFoundError,
    ModelUnavailableError,
    RequestInProgressError,
    generate_text,
)

router = APIRouter(dependencies=[Depends(current_user)])


class ChatRequest(BaseModel):
    model_code: str
    prompt: str = Field(min_length=1, max_length=4000)
    confirm: bool = False


class ChatResponse(BaseModel):
    answer: str
    charged_credits: int
    balance_after: int


class ModelOut(BaseModel):
    code: str
    display_name: str
    tier: str
    min_credits: int
    recommended_credits: int


@router.get("/models", response_model=list[ModelOut])
async def list_models(session: AsyncSession = Depends(get_db)) -> list[ModelOut]:
    models = (
        (
            await session.execute(
                select(AiModel)
                .where(
                    AiModel.category == ModelCategory.text,
                    AiModel.is_active.is_(True),
                    AiModel.is_visible.is_(True),
                )
                .order_by(AiModel.sort_order)
            )
        )
        .scalars()
        .all()
    )
    # provider_model_id намеренно не отдаётся клиенту (ТЗ).
    return [
        ModelOut(
            code=m.code,
            display_name=m.display_name,
            tier=m.tier.value,
            min_credits=m.min_credits,
            recommended_credits=m.recommended_credits,
        )
        for m in models
    ]


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> ChatResponse | JSONResponse:
    try:
        result = await generate_text(
            session, user, body.model_code, body.prompt, confirm=body.confirm
        )
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail="model not found") from exc
    except ModelUnavailableError as exc:
        raise HTTPException(status_code=404, detail="Эта модель временно отключена.") from exc
    except ConfirmationRequiredError as exc:
        # Тело ровно {"estimated_credits": N} (без "detail") -- клиент отличает
        # этот 409 от "запрос уже выполняется" по наличию estimated_credits.
        return JSONResponse(status_code=409, content={"estimated_credits": exc.estimated_credits})
    except RequestInProgressError as exc:
        raise HTTPException(status_code=409, detail=exc.user_message) from exc
    except InsufficientBalanceError as exc:
        raise HTTPException(status_code=402, detail="Недостаточно кредитов") from exc
    except AIError as exc:
        raise HTTPException(
            status_code=502, detail="Модель временно недоступна, попробуйте позже"
        ) from exc

    return ChatResponse(
        answer=result.answer,
        charged_credits=result.charged_credits,
        balance_after=result.balance_after,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_chat_routes.py -v`
Expected: PASS (10 tests).

- [ ] **Step 5: Commit**

```bash
git add app/api/routes/chat.py tests/api/__init__.py tests/api/test_chat_routes.py
git commit -m "feat: rewrite /api/models and /api/chat on the credit-based text flow"
```

---

### Task 7: Rewrite `me.py` + simplify `MeOut`, drop `/api/subscription/me`

**Files:**
- Modify (full rewrite): `app/api/schemas.py`
- Modify (full rewrite): `app/api/routes/me.py`
- Test: `tests/api/test_chat_routes.py` (append `/api/me` tests and mount `me.router`)

**Interfaces:**
- Consumes: `current_user` (`app/api/deps.py`, unmodified); `User` columns `telegram_id/username/first_name/is_admin/default_model_code/credits_balance/total_credits_purchased/total_credits_spent`.
- Produces: `GET /api/me` → `MeOut(telegram_id, username, first_name, is_admin, default_model_code, credits_balance, total_credits_purchased, total_credits_spent)` with `default_model_code` defaulting to `"deepseek_v3"`. `GET /api/subscription/me` and schemas `CategoryLimitOut`/`LimitsOut`/`SubscriptionStatusOut` are gone.

- [ ] **Step 1: Write the failing tests**

In `tests/api/test_chat_routes.py`, add the `me` import and router mount right after the existing `chat` mount:

```python
from app.api.routes import me
```

```python
app.include_router(me.router, prefix="/api")
```

and append the tests:

```python
# --- GET /api/me ---

async def test_me_returns_simplified_profile_with_default_model(client):
    response = await client.get("/api/me")

    assert response.status_code == 200
    assert response.json() == {
        "telegram_id": 1,
        "username": "u",
        "first_name": "U",
        "is_admin": False,
        "default_model_code": "deepseek_v3",  # у _test_user не задана -> дефолт из ТЗ
        "credits_balance": 100,
        "total_credits_purchased": 0,
        "total_credits_spent": 0,
    }


async def test_me_keeps_explicit_default_model(client):
    _test_user.default_model_code = "claude_sonnet"
    try:
        response = await client.get("/api/me")
        assert response.json()["default_model_code"] == "claude_sonnet"
    finally:
        _test_user.default_model_code = None


async def test_subscription_me_is_gone(client):
    response = await client.get("/api/subscription/me")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_chat_routes.py -v`
Expected: FAIL at collection with `ImportError` — current `me.py` imports the deleted `limit_service`/`subscription_service` and the removed `get_balance`.

- [ ] **Step 3: Rewrite `app/api/schemas.py`**

Replace the entire file with:

```python
from pydantic import BaseModel


class MeOut(BaseModel):
    telegram_id: int
    username: str | None
    first_name: str | None
    is_admin: bool
    default_model_code: str | None
    credits_balance: int
    total_credits_purchased: int
    total_credits_spent: int
```

- [ ] **Step 4: Rewrite `app/api/routes/me.py`**

Replace the entire file with:

```python
from fastapi import APIRouter, Depends

from app.api.deps import current_user
from app.api.schemas import MeOut
from app.db.models import User

router = APIRouter(dependencies=[Depends(current_user)])

# ТЗ: если у пользователя не выбрана модель -- DeepSeek V3 (sort_order=10,
# самая дешёвая и первая в каталоге).
DEFAULT_MODEL_CODE = "deepseek_v3"


@router.get("/me", response_model=MeOut)
async def get_me(user: User = Depends(current_user)) -> MeOut:
    return MeOut(
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        is_admin=user.is_admin,
        default_model_code=user.default_model_code or DEFAULT_MODEL_CODE,
        credits_balance=user.credits_balance,
        total_credits_purchased=user.total_credits_purchased,
        total_credits_spent=user.total_credits_spent,
    )
```

(`/api/subscription/me` is deleted by not re-adding it.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_chat_routes.py -v`
Expected: PASS (13 tests).

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest tests/ -v`
Expected: PASS — every test file in the tree (`tests/db`, `tests/services`, `tests/services/ai`, `tests/services/keys`, `tests/api`).

- [ ] **Step 7: Commit**

```bash
git add app/api/schemas.py app/api/routes/me.py tests/api/test_chat_routes.py
git commit -m "feat: simplify /api/me to credit-based profile, drop subscription endpoint"
```
