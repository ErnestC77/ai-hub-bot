# PiAPI Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the bot real image and video generation through PiAPI (single-key aggregator), async because most PiAPI models take longer than an HTTP request can block for.

**Architecture:** A new `PiAPIClient` wraps PiAPI's two-endpoint unified task API. A new `POST /api/generate` endpoint creates an `AIRequest` row and either starts a PiAPI task (returns immediately, result arrives via webhook) or runs the existing synchronous `dall-e-3` path in a FastAPI background task — both converge on the same `AIRequest` row so the frontend has one polling contract (`GET /api/generate/{id}`) regardless of provider. `POST /api/piapi/webhook` receives PiAPI's completion callback.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, httpx, pytest + pytest-asyncio + respx (new dev deps), Next.js/TypeScript on the frontend.

## Global Constraints

- PiAPI base URL: `https://api.piapi.ai/api/v1`, auth header `X-API-Key: <key>`.
- Create task: `POST /task` with body `{"model": ..., "task_type": ..., "input": {...}, "config": {"webhook_config": {"endpoint": ..., "secret": ...}}}`.
- Get task / webhook payload data shape: `{"task_id": ..., "model": ..., "task_type": ..., "status": "pending"|"processing"|"completed"|"failed", "input": {...}, "output": {...}, "meta": {...}, "error": {"code": int, "message": str}}`. Webhook body wraps this as `{"timestamp": int, "data": {...}}`.
- Money is on the line: every new backend module touching credits or the PiAPI HTTP boundary gets pytest coverage (this codebase has zero existing backend tests, so this plan introduces `pytest`, `pytest-asyncio`, `respx` as dev dependencies in Task 1).
- Video is credits-only, never tariff quota — `ModelCategory.video` is deliberately absent from `app/services/limit_fields.py:CATEGORY_LIMIT_FIELD`, and `access_service.check_access()` must never index that dict with `ModelCategory.video`.
- Do not touch the existing `dall-e-3` row, `/api/chat` (text), or any admin/tariffs/referral code — out of scope for this plan.
- CreditKind / split image-video credit pools are **out of scope for this plan** — everything here spends from the single existing flat credit pool via the unmodified `credit_service.spend_credits()`. The next plan (Credits & Bundles) adds the split on top.

---

### Task 1: Dev dependencies + foundational schema (enums, PiAPI columns)

**Files:**
- Modify: `requirements.txt`
- Modify: `app/db/enums.py`
- Modify: `app/services/keys/enums.py`
- Modify: `app/db/models/model_config.py`
- Modify: `app/db/models/ai_request.py`
- Create: `alembic/versions/a1f2c3d4e5f6_add_piapi_schema.py`
- Test: `tests/db/test_piapi_schema.py`

**Interfaces:**
- Produces: `ModelCategory.video`, `ModelProvider.piapi` (both `app/db/enums.py`), `Provider.PIAPI` (`app/services/keys/enums.py`), `ModelConfig.piapi_model: str | None`, `ModelConfig.piapi_task_type: str | None`, `ModelConfig.piapi_extra_input: dict | None`, `ModelConfig.duration_seconds: int | None`, `AIRequest.provider_task_id: str | None`.

- [ ] **Step 1: Add test dependencies**

Add to `requirements.txt` (append, don't reorder existing lines):
```
pytest>=8.0
pytest-asyncio>=0.24
respx>=0.21
aiosqlite>=0.20
```

Run: `pip install -r requirements.txt`

- [ ] **Step 2: Add `pytest.ini`**

Create `pytest.ini` at repo root:
```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 3: Extend the enums**

In `app/db/enums.py`, change:
```python
class ModelCategory(str, enum.Enum):
    fast = "fast"
    medium = "medium"
    premium = "premium"
    image = "image"
```
to:
```python
class ModelCategory(str, enum.Enum):
    fast = "fast"
    medium = "medium"
    premium = "premium"
    image = "image"
    video = "video"
```
and:
```python
class ModelProvider(str, enum.Enum):
    openai = "openai"
    anthropic = "anthropic"
    google = "google"
    deepseek = "deepseek"
```
to:
```python
class ModelProvider(str, enum.Enum):
    openai = "openai"
    anthropic = "anthropic"
    google = "google"
    deepseek = "deepseek"
    piapi = "piapi"
```

In `app/services/keys/enums.py`, add `PIAPI = "piapi"` to the `Provider` StrEnum (after `OPENROUTER = "openrouter"`).

- [ ] **Step 4: Add new columns to `ModelConfig`**

In `app/db/models/model_config.py`, add imports `JSON` from `sqlalchemy` (alongside the existing `Boolean, Integer, Numeric, String` import), and add these fields after `max_context_tokens`:
```python
    # PiAPI unified task API identifiers. None for non-PiAPI rows (e.g. dall-e-3).
    piapi_model: Mapped[str | None] = mapped_column(String(64))
    piapi_task_type: Mapped[str | None] = mapped_column(String(64))
    # Fixed request fields PiAPI needs beyond "prompt" (resolution, duration, etc).
    piapi_extra_input: Mapped[dict | None] = mapped_column(JSON)
    # Video only -- informational + drives the frontend poll timeout.
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
```

- [ ] **Step 5: Add `provider_task_id` to `AIRequest`**

In `app/db/models/ai_request.py`, add after `error_message`:
```python
    # PiAPI's own task id -- the webhook payload only carries this, not our AIRequest.id.
    provider_task_id: Mapped[str | None] = mapped_column(String(128), index=True, unique=True)
```

- [ ] **Step 6: Write the migration**

Create `alembic/versions/a1f2c3d4e5f6_add_piapi_schema.py`:
```python
"""add piapi schema: video category, piapi provider, model_configs piapi columns, ai_requests.provider_task_id

Revision ID: a1f2c3d4e5f6
Revises: 749f76e9eaca
Create Date: 2026-07-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1f2c3d4e5f6'
down_revision: Union[str, None] = '749f76e9eaca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block in Postgres.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE modelcategory ADD VALUE IF NOT EXISTS 'video'")
        op.execute("ALTER TYPE modelprovider ADD VALUE IF NOT EXISTS 'piapi'")

    op.add_column('model_configs', sa.Column('piapi_model', sa.String(length=64), nullable=True))
    op.add_column('model_configs', sa.Column('piapi_task_type', sa.String(length=64), nullable=True))
    op.add_column('model_configs', sa.Column('piapi_extra_input', sa.JSON(), nullable=True))
    op.add_column('model_configs', sa.Column('duration_seconds', sa.Integer(), nullable=True))
    op.add_column('ai_requests', sa.Column('provider_task_id', sa.String(length=128), nullable=True))
    op.create_index('ix_ai_requests_provider_task_id', 'ai_requests', ['provider_task_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_ai_requests_provider_task_id', table_name='ai_requests')
    op.drop_column('ai_requests', 'provider_task_id')
    op.drop_column('model_configs', 'duration_seconds')
    op.drop_column('model_configs', 'piapi_extra_input')
    op.drop_column('model_configs', 'piapi_task_type')
    op.drop_column('model_configs', 'piapi_model')
    # Postgres has no ALTER TYPE ... DROP VALUE -- enum values from upgrade() are left in place.
```

Run: `alembic upgrade head`
Expected: no errors, `alembic current` shows `a1f2c3d4e5f6 (head)`.

- [ ] **Step 7: Write the round-trip test**

Create `tests/db/test_piapi_schema.py`:
```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db.base import Base
from app.db.enums import ModelCategory, ModelProvider, RequestStatus
from app.db.models import AIRequest, ModelConfig, User


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def test_model_config_piapi_columns_round_trip(session):
    model = ModelConfig(
        model_code="piapi-flux-dev",
        provider=ModelProvider.piapi,
        display_name="AI Photo Fast",
        category=ModelCategory.image,
        credit_cost=3,
        key_purpose="image",
        piapi_model="Qubico/flux1-dev",
        piapi_task_type="txt2img",
        piapi_extra_input={"width": 1024, "height": 1024},
        duration_seconds=None,
    )
    session.add(model)
    await session.commit()

    fetched = await session.get(ModelConfig, model.id)
    assert fetched.piapi_model == "Qubico/flux1-dev"
    assert fetched.piapi_task_type == "txt2img"
    assert fetched.piapi_extra_input == {"width": 1024, "height": 1024}
    assert fetched.category == ModelCategory.video or fetched.category == ModelCategory.image  # sanity: enum usable


async def test_ai_request_provider_task_id_round_trip(session):
    user = User(telegram_id=1, username="u")
    session.add(user)
    await session.flush()

    request = AIRequest(
        user_id=user.id,
        model_code="piapi-veo3-fast",
        model_category=ModelCategory.video,
        prompt="a sunset",
        status=RequestStatus.processing,
        provider_task_id="58cb41b7-556d-46c0-b82e-1e116aa1a31a",
    )
    session.add(request)
    await session.commit()

    fetched = await session.get(AIRequest, request.id)
    assert fetched.provider_task_id == "58cb41b7-556d-46c0-b82e-1e116aa1a31a"
```

Note: SQLite (used here for a fast in-memory test) doesn't enforce Postgres native enum constraints, so this test only verifies column persistence/round-trip, not the `ALTER TYPE` migration itself — that's verified by Step 6's `alembic upgrade head` running clean against the real Postgres dev database.

- [ ] **Step 8: Run the test**

Run: `pytest tests/db/test_piapi_schema.py -v`
Expected: 2 passed

- [ ] **Step 9: Commit**

```bash
git add requirements.txt pytest.ini app/db/enums.py app/services/keys/enums.py app/db/models/model_config.py app/db/models/ai_request.py alembic/versions/a1f2c3d4e5f6_add_piapi_schema.py tests/db/test_piapi_schema.py
git commit -m "feat: add PiAPI schema foundations (video category, piapi provider, model_configs/ai_requests columns)"
```

---

### Task 2: PiAPI key management

**Files:**
- Modify: `app/config.py`
- Modify: `app/services/keys/api_key_manager.py`

**Interfaces:**
- Consumes: `Provider.PIAPI` from Task 1.
- Produces: `settings.piapi.api_key` (`SecretStr | None`), `settings.piapi.webhook_secret` (`str`), `get_key_manager().get_key(Provider.PIAPI, KeyPurpose.IMAGE)` and `get_key_manager().get_key(Provider.PIAPI, KeyPurpose.VIDEO)` both resolve to the same key.

- [ ] **Step 1: Add `PiApiSettings`**

In `app/config.py`, add after `class OpenRouterSettings(_ProviderSettings): ...`:
```python
class PiApiSettings(_ProviderSettings):
    api_key: SecretStr | None = Field(default=None, alias="PIAPI_API_KEY")
    dev_key: SecretStr | None = Field(default=None, alias="PIAPI_DEV_KEY")
```

In `class Settings`, add after `openrouter: OpenRouterSettings = Field(default_factory=OpenRouterSettings)`:
```python
    piapi: PiApiSettings = Field(default_factory=PiApiSettings)
```

And after `frontend_url: str = ""`, add:
```python
    piapi_webhook_secret: str = ""
```

- [ ] **Step 2: Wire the key manager**

In `app/services/keys/api_key_manager.py`, add to `_PURPOSE_ATTR` (after the `Provider.OPENROUTER: {...}` entry):
```python
    Provider.PIAPI: {
        KeyPurpose.IMAGE: "api_key",
        KeyPurpose.VIDEO: "api_key",
    },
```

- [ ] **Step 3: Write the test**

Create `tests/services/keys/test_piapi_key.py`:
```python
from app.config import Settings
from app.services.keys.api_key_manager import ApiKeyManager
from app.services.keys.enums import KeyPurpose, Provider


def test_piapi_key_shared_across_purposes(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("PIAPI_API_KEY", "sk-test-123")
    settings = Settings()
    manager = ApiKeyManager(settings)

    assert manager.get_key(Provider.PIAPI, KeyPurpose.IMAGE) == "sk-test-123"
    assert manager.get_key(Provider.PIAPI, KeyPurpose.VIDEO) == "sk-test-123"
```

- [ ] **Step 4: Run the test**

Run: `pytest tests/services/keys/test_piapi_key.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add app/config.py app/services/keys/api_key_manager.py tests/services/keys/test_piapi_key.py
git commit -m "feat: wire PiAPI key into ApiKeyManager"
```

---

### Task 3: PiAPI HTTP client

**Files:**
- Create: `app/services/ai/piapi_client.py`
- Test: `tests/services/ai/test_piapi_client.py`

**Interfaces:**
- Consumes: `get_key_manager().get_key(Provider.PIAPI, KeyPurpose.IMAGE)` from Task 2.
- Produces:
  - `@dataclass class PiAPITaskResult: task_id: str; status: str; result_url: str | None; error_message: str | None`
  - `class PiAPIClient: async def create_task(self, model: str, task_type: str, input_: dict, webhook_url: str) -> str` (returns `task_id`)
  - `class PiAPIClient: async def get_task(self, task_id: str) -> PiAPITaskResult`
  - `def extract_result_url(data: dict) -> str | None` (module-level function, also used by the webhook handler in Task 6)

- [ ] **Step 1: Write the failing tests**

Create `tests/services/ai/test_piapi_client.py`:
```python
import httpx
import pytest
import respx

from app.services.ai.piapi_client import PiAPIClient, extract_result_url


@respx.mock
async def test_create_task_returns_task_id():
    respx.post("https://api.piapi.ai/api/v1/task").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 200,
                "message": "success",
                "data": {"task_id": "49638cd2-4689-4f33-9336-164a8f6b1111", "status": "pending"},
            },
        )
    )
    client = PiAPIClient(api_key="sk-test")
    task_id = await client.create_task(
        model="Qubico/flux1-dev",
        task_type="txt2img",
        input_={"prompt": "a bear"},
        webhook_url="https://example.com/webhook",
    )
    assert task_id == "49638cd2-4689-4f33-9336-164a8f6b1111"

    request = respx.calls.last.request
    assert request.headers["x-api-key"] == "sk-test"
    import json
    body = json.loads(request.content)
    assert body["model"] == "Qubico/flux1-dev"
    assert body["task_type"] == "txt2img"
    assert body["input"] == {"prompt": "a bear"}
    assert body["config"]["webhook_config"]["endpoint"] == "https://example.com/webhook"


@respx.mock
async def test_get_task_completed_with_image_url():
    respx.get("https://api.piapi.ai/api/v1/task/abc-123").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 200,
                "message": "success",
                "data": {
                    "task_id": "abc-123",
                    "status": "completed",
                    "output": {"image_url": "https://cdn.example.com/out.png"},
                    "error": {"code": 0, "message": ""},
                },
            },
        )
    )
    client = PiAPIClient(api_key="sk-test")
    result = await client.get_task("abc-123")
    assert result.status == "completed"
    assert result.result_url == "https://cdn.example.com/out.png"
    assert result.error_message is None


@respx.mock
async def test_get_task_failed_with_error_message():
    respx.get("https://api.piapi.ai/api/v1/task/abc-456").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 200,
                "message": "success",
                "data": {
                    "task_id": "abc-456",
                    "status": "failed",
                    "output": None,
                    "error": {"code": 10000, "message": "content policy violation"},
                },
            },
        )
    )
    client = PiAPIClient(api_key="sk-test")
    result = await client.get_task("abc-456")
    assert result.status == "failed"
    assert result.result_url is None
    assert result.error_message == "content policy violation"


def test_extract_result_url_flat_image_url():
    assert extract_result_url({"output": {"image_url": "https://x/a.png"}}) == "https://x/a.png"


def test_extract_result_url_image_urls_array():
    assert extract_result_url({"output": {"image_urls": ["https://x/a.png", "https://x/b.png"]}}) == "https://x/a.png"


def test_extract_result_url_video_url():
    assert extract_result_url({"output": {"video_url": "https://x/a.mp4"}}) == "https://x/a.mp4"


def test_extract_result_url_nested_luma_shape():
    data = {"output": {"generation": {"video": {"url": "https://x/a.mp4", "url_no_watermark": "https://x/b.mp4"}}}}
    assert extract_result_url(data) == "https://x/b.mp4"


def test_extract_result_url_none_when_missing():
    assert extract_result_url({"output": None}) is None
    assert extract_result_url({"output": {}}) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/ai/test_piapi_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.ai.piapi_client'`

- [ ] **Step 3: Implement the client**

Create `app/services/ai/piapi_client.py`:
```python
from dataclasses import dataclass

import httpx

BASE_URL = "https://api.piapi.ai/api/v1"


@dataclass
class PiAPITaskResult:
    task_id: str
    status: str  # "pending" | "processing" | "completed" | "failed"
    result_url: str | None
    error_message: str | None


def extract_result_url(data: dict) -> str | None:
    """Different PiAPI model families nest the result URL differently.
    Tries each known shape in order; returns None if nothing matches."""
    output = data.get("output") or {}

    if url := output.get("image_url"):
        return url
    if urls := output.get("image_urls"):
        return urls[0] if urls else None
    if url := output.get("video_url"):
        return url

    generation = output.get("generation") or {}
    video = generation.get("video") or {}
    if url := video.get("url_no_watermark"):
        return url
    if url := video.get("url"):
        return url

    return None


class PiAPIClient:
    def __init__(self, api_key: str):
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self._api_key, "Content-Type": "application/json"}

    async def create_task(self, model: str, task_type: str, input_: dict, webhook_url: str) -> str:
        body = {
            "model": model,
            "task_type": task_type,
            "input": input_,
            "config": {"webhook_config": {"endpoint": webhook_url, "secret": ""}},
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{BASE_URL}/task", headers=self._headers(), json=body)
            response.raise_for_status()
        return response.json()["data"]["task_id"]

    async def get_task(self, task_id: str) -> PiAPITaskResult:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{BASE_URL}/task/{task_id}", headers=self._headers())
            response.raise_for_status()
        data = response.json()["data"]
        error = data.get("error") or {}
        return PiAPITaskResult(
            task_id=data["task_id"],
            status=data["status"],
            result_url=extract_result_url(data) if data["status"] == "completed" else None,
            error_message=error.get("message") or None,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/ai/test_piapi_client.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/ai/piapi_client.py tests/services/ai/test_piapi_client.py
git commit -m "feat: add PiAPI HTTP client (create_task/get_task/extract_result_url)"
```

---

### Task 4: `access_service` — video is credits-only

**Files:**
- Modify: `app/services/access_service.py:101-152` (the `check_access` function)
- Test: `tests/services/test_access_service.py`

**Interfaces:**
- Consumes: `ModelCategory.video` from Task 1.
- Produces: `check_access()` never indexes `CATEGORY_LIMIT_FIELD` with `ModelCategory.video` — callers can rely on `AccessContext.use_credits == True` for any video-category model whenever the user's credit balance covers it, and on `ModelNotAllowedError` (not a `KeyError`) when it doesn't.

- [ ] **Step 1: Write the failing test**

Create `tests/services/test_access_service.py`:
```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db.base import Base
from app.db.enums import ModelCategory, ModelProvider
from app.db.models import CreditTransaction, ModelConfig, Tariff, User
from app.db.enums import CreditTxType
from app.services.access_service import ModelNotAllowedError, check_access


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _make_free_tariff(session):
    tariff = Tariff(
        code="free", name="Free", price_rub=0, price_stars=0, period_days=36500,
        fast_limit=5, medium_limit=0, premium_limit=0, image_limit=0, daily_limit=5,
        max_input_tokens=2000, max_output_tokens=1000,
    )
    session.add(tariff)
    await session.commit()
    return tariff


async def test_video_model_with_no_credits_raises_not_allowed(session):
    await _make_free_tariff(session)
    user = User(telegram_id=1, username="u")
    session.add(user)
    await session.flush()

    model = ModelConfig(
        model_code="piapi-veo3-fast", provider=ModelProvider.piapi, display_name="AI Video Fast",
        category=ModelCategory.video, credit_cost=51, key_purpose="video",
    )
    session.add(model)
    await session.commit()

    with pytest.raises(ModelNotAllowedError):
        await check_access(session, user, model, "a sunset")


async def test_video_model_with_enough_credits_uses_credits(session):
    await _make_free_tariff(session)
    user = User(telegram_id=2, username="u2")
    session.add(user)
    await session.flush()

    session.add(CreditTransaction(user_id=user.id, type=CreditTxType.deposit, amount=100, reason="test"))
    await session.commit()

    model = ModelConfig(
        model_code="piapi-veo3-fast", provider=ModelProvider.piapi, display_name="AI Video Fast",
        category=ModelCategory.video, credit_cost=51, key_purpose="video",
    )
    session.add(model)
    await session.commit()

    ctx = await check_access(session, user, model, "a sunset")
    assert ctx.use_credits is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_access_service.py -v`
Expected: FAIL — `test_video_model_with_no_credits_raises_not_allowed` raises `KeyError: <ModelCategory.video: 'video'>` instead of `ModelNotAllowedError` (current code indexes `CATEGORY_LIMIT_FIELD[model.category]` unconditionally).

- [ ] **Step 3: Fix `check_access`**

In `app/services/access_service.py`, replace:
```python
    limit_field, used_field = CATEGORY_LIMIT_FIELD[model.category]
    category_limit = getattr(tariff, limit_field)

    tariff_has_quota = (
        category_limit > 0
        and usage.daily_used < tariff.daily_limit
        and getattr(usage, used_field) < category_limit
    )
```
with:
```python
    # Video is never covered by tariff quota, only by credits -- CATEGORY_LIMIT_FIELD
    # has no entry for it by design (see app/services/limit_fields.py).
    if model.category == ModelCategory.video:
        category_limit = 0
        tariff_has_quota = False
    else:
        limit_field, used_field = CATEGORY_LIMIT_FIELD[model.category]
        category_limit = getattr(tariff, limit_field)
        tariff_has_quota = (
            category_limit > 0
            and usage.daily_used < tariff.daily_limit
            and getattr(usage, used_field) < category_limit
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_access_service.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/access_service.py tests/services/test_access_service.py
git commit -m "fix: make check_access treat video category as credits-only, not a KeyError"
```

---

### Task 5: `generation_service` — unified start/poll for sync and async providers

**Files:**
- Create: `app/services/generation_service.py`
- Test: `tests/services/test_generation_service.py`

**Interfaces:**
- Consumes: `PiAPIClient`, `extract_result_url` (Task 3), `check_access` (Task 4, unmodified interface), `spend_credits` (existing, unmodified — general kind only, per Global Constraints), `get_key_manager()` (Task 2).
- Produces:
  - `async def start_generation(session: AsyncSession, user: User, model_code: str, prompt: str, extra: dict | None, credit_cost_override: int | None, background_tasks: BackgroundTasks) -> AIRequest` — always returns with `status == RequestStatus.processing` (or raises `ModelNotFoundError`/`AccessError` synchronously, same as today's `AIRouter.generate`).
  - `async def get_generation(session: AsyncSession, user: User, request_id: int) -> AIRequest | None` — `None` if not found or not owned by `user`.
  - `async def handle_piapi_webhook(session: AsyncSession, payload: dict) -> None` — idempotent; looks up by `provider_task_id`, no-ops if already terminal.

- [ ] **Step 1: Write the failing tests**

Create `tests/services/test_generation_service.py`:
```python
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db.base import Base
from app.db.enums import ModelCategory, ModelProvider, RequestStatus
from app.db.models import ModelConfig, Tariff, User
from app.services.generation_service import get_generation, handle_piapi_webhook, start_generation


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _setup(session, credit_cost=51):
    tariff = Tariff(
        code="free", name="Free", price_rub=0, price_stars=0, period_days=36500,
        fast_limit=5, medium_limit=0, premium_limit=0, image_limit=0, daily_limit=5,
        max_input_tokens=2000, max_output_tokens=1000,
    )
    session.add(tariff)
    user = User(telegram_id=1, username="u")
    session.add(user)
    await session.flush()
    from app.db.models import CreditTransaction
    from app.db.enums import CreditTxType
    session.add(CreditTransaction(user_id=user.id, type=CreditTxType.deposit, amount=1000, reason="test"))
    model = ModelConfig(
        model_code="piapi-veo3-fast", provider=ModelProvider.piapi, display_name="AI Video Fast",
        category=ModelCategory.video, credit_cost=credit_cost, key_purpose="video",
        piapi_model="veo3.1", piapi_task_type="veo3.1-video-fast", piapi_extra_input={"duration": "5s"},
    )
    session.add(model)
    await session.commit()
    return user, model


@patch("app.services.generation_service.PiAPIClient")
async def test_start_generation_piapi_creates_processing_request_with_task_id(mock_client_cls, session):
    mock_client = AsyncMock()
    mock_client.create_task.return_value = "task-123"
    mock_client_cls.return_value = mock_client

    user, model = await _setup(session)
    bg = BackgroundTasks()

    request = await start_generation(
        session, user, model.model_code, "a sunset", extra=None, credit_cost_override=None, background_tasks=bg
    )

    assert request.status == RequestStatus.processing
    assert request.provider_task_id == "task-123"
    mock_client.create_task.assert_awaited_once()
    call_kwargs = mock_client.create_task.await_args.kwargs
    assert call_kwargs["model"] == "veo3.1"
    assert call_kwargs["task_type"] == "veo3.1-video-fast"
    assert call_kwargs["input_"]["prompt"] == "a sunset"
    assert call_kwargs["input_"]["duration"] == "5s"


async def test_get_generation_returns_none_for_other_users_request(session):
    user, model = await _setup(session)
    other = User(telegram_id=2, username="other")
    session.add(other)
    await session.commit()

    from unittest.mock import AsyncMock, patch
    with patch("app.services.generation_service.PiAPIClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.create_task.return_value = "task-456"
        mock_client_cls.return_value = mock_client
        request = await start_generation(
            session, user, model.model_code, "x", extra=None, credit_cost_override=None,
            background_tasks=BackgroundTasks(),
        )

    result = await get_generation(session, other, request.id)
    assert result is None


async def test_webhook_completed_marks_success_and_spends_credits(session):
    user, model = await _setup(session)
    with patch("app.services.generation_service.PiAPIClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.create_task.return_value = "task-789"
        mock_client_cls.return_value = mock_client
        request = await start_generation(
            session, user, model.model_code, "x", extra=None, credit_cost_override=None,
            background_tasks=BackgroundTasks(),
        )

    from app.services.credit_service import get_balance
    balance_before = await get_balance(session, user)

    await handle_piapi_webhook(session, {
        "data": {
            "task_id": "task-789",
            "status": "completed",
            "output": {"video_url": "https://cdn.example.com/out.mp4"},
            "error": {"code": 0, "message": ""},
        }
    })

    await session.refresh(request)
    assert request.status == RequestStatus.success
    assert request.answer == "https://cdn.example.com/out.mp4"

    balance_after = await get_balance(session, user)
    assert balance_after == balance_before - model.credit_cost


async def test_webhook_is_idempotent(session):
    user, model = await _setup(session)
    with patch("app.services.generation_service.PiAPIClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.create_task.return_value = "task-idem"
        mock_client_cls.return_value = mock_client
        request = await start_generation(
            session, user, model.model_code, "x", extra=None, credit_cost_override=None,
            background_tasks=BackgroundTasks(),
        )

    payload = {
        "data": {
            "task_id": "task-idem", "status": "completed",
            "output": {"video_url": "https://cdn.example.com/out.mp4"},
            "error": {"code": 0, "message": ""},
        }
    }
    await handle_piapi_webhook(session, payload)
    from app.services.credit_service import get_balance
    balance_after_first = await get_balance(session, user)

    await handle_piapi_webhook(session, payload)  # PiAPI may retry webhooks
    balance_after_second = await get_balance(session, user)

    assert balance_after_first == balance_after_second
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_generation_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.generation_service'`

- [ ] **Step 3: Implement `generation_service.py`**

Create `app/services/generation_service.py`:
```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import BackgroundTasks

from app.db.enums import ModelProvider, RequestStatus
from app.db.models import AIRequest, ModelConfig, User
from app.services.access_service import check_access
from app.services.ai.base import AIError
from app.services.ai.image_service import ImageProvider
from app.services.ai.piapi_client import PiAPIClient
from app.services.credit_service import spend_credits
from app.services.keys.api_key_manager import get_key_manager
from app.services.keys.enums import KeyPurpose, Provider
from app.config import settings


class ModelNotFoundError(Exception):
    pass


def _webhook_url() -> str:
    return f"{settings.backend_public_url}/api/piapi/webhook?secret={settings.piapi_webhook_secret}"


async def _get_model(session: AsyncSession, model_code: str) -> ModelConfig:
    model = (
        await session.execute(select(ModelConfig).where(ModelConfig.model_code == model_code))
    ).scalar_one_or_none()
    if model is None:
        raise ModelNotFoundError(model_code)
    return model


async def _run_sync_provider_in_background(
    session_factory, request_id: int, model: ModelConfig, prompt: str, extra: dict | None,
    credit_cost: int, user_id: int,
) -> None:
    """Runs the existing synchronous ImageProvider (dall-e-3) after the endpoint has
    already returned, then updates the same AIRequest row the async PiAPI path uses."""
    async with session_factory() as session:
        request = await session.get(AIRequest, request_id)
        try:
            result = await ImageProvider().generate(model, prompt, max_output_tokens=0, extra=extra)
        except AIError as exc:
            request.status = RequestStatus.error
            request.error_message = str(exc)
            await session.commit()
            return

        request.status = RequestStatus.success
        request.answer = result.answer
        await session.commit()

        user = await session.get(User, user_id)
        await spend_credits(session, user, credit_cost, reason=f"AI request: {model.model_code}")


async def start_generation(
    session: AsyncSession,
    user: User,
    model_code: str,
    prompt: str,
    extra: dict | None,
    credit_cost_override: int | None,
    background_tasks: BackgroundTasks,
) -> AIRequest:
    model = await _get_model(session, model_code)
    await check_access(session, user, model, prompt, credit_cost=credit_cost_override)
    credit_cost = credit_cost_override if credit_cost_override is not None else model.credit_cost

    request = AIRequest(
        user_id=user.id,
        model_code=model.model_code,
        model_category=model.category,
        prompt=prompt,
        status=RequestStatus.processing,
    )
    session.add(request)
    await session.commit()

    if model.provider == ModelProvider.piapi:
        purpose = KeyPurpose.IMAGE if model.category.value == "image" else KeyPurpose.VIDEO
        api_key = get_key_manager().get_key(Provider.PIAPI, purpose)
        client = PiAPIClient(api_key=api_key)
        input_ = {"prompt": prompt, **(model.piapi_extra_input or {})}
        task_id = await client.create_task(
            model=model.piapi_model,
            task_type=model.piapi_task_type,
            input_=input_,
            webhook_url=_webhook_url(),
        )
        request.provider_task_id = task_id
        await session.commit()
    else:
        from app.db.session import get_session
        background_tasks.add_task(
            _run_sync_provider_in_background, get_session, request.id, model, prompt, extra, credit_cost, user.id,
        )

    return request


async def get_generation(session: AsyncSession, user: User, request_id: int) -> AIRequest | None:
    request = await session.get(AIRequest, request_id)
    if request is None or request.user_id != user.id:
        return None
    return request


async def handle_piapi_webhook(session: AsyncSession, payload: dict) -> None:
    from app.services.ai.piapi_client import extract_result_url

    data = payload.get("data") or {}
    task_id = data.get("task_id")
    if not task_id:
        return

    request = (
        await session.execute(select(AIRequest).where(AIRequest.provider_task_id == task_id))
    ).scalar_one_or_none()
    if request is None or request.status != RequestStatus.processing:
        return  # unknown task, or already handled (webhook retry) -- idempotent no-op

    status = data.get("status")
    if status == "completed":
        request.answer = extract_result_url(data)
        request.status = RequestStatus.success
        await session.commit()

        model = await _get_model(session, request.model_code)
        user = await session.get(User, request.user_id)
        await spend_credits(session, user, model.credit_cost, reason=f"AI request: {model.model_code}")
    elif status == "failed":
        error = data.get("error") or {}
        request.status = RequestStatus.error
        request.error_message = error.get("message") or "generation failed"
        await session.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_generation_service.py -v`
Expected: 4 passed

Note: `_webhook_url()` references `settings.backend_public_url`, a new field — add it in Task 6 alongside the route registration (it's the backend's own public URL, needed to build the webhook callback address; not needed until a real request is fired, so tests mock `PiAPIClient` entirely and never call `_webhook_url()` for real).

- [ ] **Step 5: Commit**

```bash
git add app/services/generation_service.py tests/services/test_generation_service.py
git commit -m "feat: add generation_service — unified start/poll for sync and PiAPI async generation"
```

---

### Task 6: API routes — `/api/generate`, `/api/generate/{id}`, `/api/piapi/webhook`

**Files:**
- Create: `app/api/routes/generate.py`
- Create: `app/webhooks/piapi.py`
- Modify: `app/config.py` (add `backend_public_url`)
- Modify: `app/main.py` (register both routers)
- Modify: `app/api/routes/chat.py` (remove the now-retired `/chat/image` endpoint and its dead helpers)
- Test: `tests/api/test_generate_routes.py`

**Interfaces:**
- Consumes: `start_generation`, `get_generation`, `handle_piapi_webhook` from Task 5.
- Produces: `POST /api/generate` → `{"request_id": int}`; `GET /api/generate/{id}` → `{"status": str, "result_url": str | None, "error_message": str | None, "credit_cost": int}`; `POST /api/piapi/webhook?secret=...` → `{"ok": true}` or 403.

- [ ] **Step 1: Add `backend_public_url` setting**

In `app/config.py`, add after `piapi_webhook_secret: str = ""`:
```python
    # This backend's own public URL -- used to build the PiAPI webhook callback address.
    # Render sets this via the service's own external hostname (see render.yaml).
    backend_public_url: str = ""
```

Update `app/services/generation_service.py`'s `_webhook_url()`:
```python
def _webhook_url() -> str:
    return f"{settings.backend_public_url}/api/piapi/webhook?secret={settings.piapi_webhook_secret}"
```

- [ ] **Step 2: Write the failing route test**

Create `tests/api/test_generate_routes.py`:
```python
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture
def mock_current_user():
    from app.db.models import User
    from app.api.deps import current_user

    async def _fake_user():
        return User(id=1, telegram_id=1, username="u")

    app.dependency_overrides[current_user] = _fake_user
    yield
    app.dependency_overrides.pop(current_user, None)


async def test_webhook_rejects_wrong_secret():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/piapi/webhook?secret=wrong", json={"data": {"task_id": "x"}})
    assert response.status_code == 403


async def test_webhook_accepts_correct_secret(monkeypatch):
    monkeypatch.setattr("app.config.settings.piapi_webhook_secret", "correct")
    with patch("app.webhooks.piapi.handle_piapi_webhook", new=AsyncMock()) as mock_handle:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/piapi/webhook?secret=correct", json={"data": {"task_id": "x", "status": "completed"}}
            )
        assert response.status_code == 200
        mock_handle.assert_awaited_once()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/api/test_generate_routes.py -v`
Expected: FAIL — `404` (route doesn't exist yet) instead of `403`/`200`.

- [ ] **Step 4: Implement the routes**

Create `app/api/routes/generate.py`:
```python
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_db
from app.db.models import User
from app.services.access_service import AccessError
from app.services.generation_service import ModelNotFoundError, get_generation, start_generation

router = APIRouter(dependencies=[Depends(current_user)])


class GenerateRequest(BaseModel):
    model_code: str
    prompt: str
    extra: dict | None = None
    credit_cost_override: int | None = None


class GenerateResponse(BaseModel):
    request_id: int


class GenerationStatusOut(BaseModel):
    status: str
    result_url: str | None
    error_message: str | None
    credit_cost: int


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    body: GenerateRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> GenerateResponse:
    try:
        request = await start_generation(
            session, user, body.model_code, body.prompt, body.extra, body.credit_cost_override, background_tasks,
        )
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail="model not found") from exc
    except AccessError as exc:
        raise HTTPException(status_code=403, detail=exc.user_message) from exc

    return GenerateResponse(request_id=request.id)


@router.get("/generate/{request_id}", response_model=GenerationStatusOut)
async def generation_status(
    request_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> GenerationStatusOut:
    request = await get_generation(session, user, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="request not found")

    return GenerationStatusOut(
        status=request.status.value,
        result_url=request.answer,
        error_message=request.error_message,
        credit_cost=0,
    )
```

Create `app/webhooks/piapi.py`:
```python
from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.db.session import get_session
from app.services.generation_service import handle_piapi_webhook

router = APIRouter()


@router.post("/api/piapi/webhook")
async def piapi_webhook(request: Request, secret: str = "") -> dict:
    if secret != settings.piapi_webhook_secret or not settings.piapi_webhook_secret:
        raise HTTPException(status_code=403, detail="invalid secret")

    payload = await request.json()
    async with get_session() as session:
        await handle_piapi_webhook(session, payload)

    return {"ok": True}
```

- [ ] **Step 5: Register both routers**

In `app/main.py`, change:
```python
from app.api.routes import admin, banners, chat, me, payments, referral, tariffs, tools
```
to:
```python
from app.api.routes import admin, banners, chat, generate, me, payments, referral, tariffs, tools
```
and add, alongside the other `app.include_router(...)` calls:
```python
app.include_router(generate.router, prefix="/api")
```
Find the existing `from app.webhooks import yookassa as yookassa_webhook` line and add directly below it:
```python
from app.webhooks import piapi as piapi_webhook
```
and next to `app.include_router(yookassa_webhook.router)`, add:
```python
app.include_router(piapi_webhook.router)
```

- [ ] **Step 6: Retire `/api/chat/image`**

In `app/api/routes/chat.py`, delete the `IMAGE_ASPECT_TO_BUCKET`, `IMAGE_BUCKET_TO_SIZE`, `_RESOLUTION_TO_QUALITY`, `_COST_MULTIPLIER`, `_compute_image_credit_cost`, `ASPECT_OPTIONS`, `RESOLUTION_OPTIONS`, `ImageGenerateRequest`, `ImageGenerateResponse`, and `generate_image` — all of it, from the `ASPECT_OPTIONS = Literal[...]` line through the end of the `generate_image` function. The `dall-e-3` aspect/resolution → credit-cost logic moves into `generation_service.py` in Task 7, scoped to that one model code only, since PiAPI rows use a flat `credit_cost` with no aspect/resolution multiplier.

Leave `/chat` (text) and `/models` untouched in this file.

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/api/test_generate_routes.py -v`
Expected: 2 passed

- [ ] **Step 8: Commit**

```bash
git add app/api/routes/generate.py app/webhooks/piapi.py app/config.py app/main.py app/api/routes/chat.py tests/api/test_generate_routes.py
git commit -m "feat: add /api/generate + /api/piapi/webhook, retire synchronous /api/chat/image"
```

---

### Task 7: dall-e-3 aspect/resolution cost logic moves into `generation_service`

**Files:**
- Modify: `app/services/generation_service.py`
- Test: `tests/services/test_generation_service.py` (extend)

**Interfaces:**
- Consumes: nothing new.
- Produces: `start_generation()` computes the dall-e-3-specific credit multiplier internally when `model.model_code == "dall-e-3"`, so the frontend's `extra` payload for that one model still carries `{aspect, resolution}` and gets the correct `size`/`quality` mapping — this preserves Task 6's deletion without losing the feature.

- [ ] **Step 1: Write the failing test**

Add to `tests/services/test_generation_service.py`:
```python
@patch("app.services.generation_service.ImageProvider")
async def test_dalle3_aspect_resolution_credit_multiplier(mock_image_provider_cls, session):
    tariff = Tariff(
        code="free", name="Free", price_rub=0, price_stars=0, period_days=36500,
        fast_limit=5, medium_limit=0, premium_limit=0, image_limit=0, daily_limit=5,
        max_input_tokens=2000, max_output_tokens=1000,
    )
    session.add(tariff)
    user = User(telegram_id=9, username="u9")
    session.add(user)
    await session.flush()
    from app.db.models import CreditTransaction
    from app.db.enums import CreditTxType
    session.add(CreditTransaction(user_id=user.id, type=CreditTxType.deposit, amount=1000, reason="test"))
    model = ModelConfig(
        model_code="dall-e-3", provider=ModelProvider.openai, display_name="Генерация картинок",
        category=ModelCategory.image, credit_cost=15, key_purpose="image",
    )
    session.add(model)
    await session.commit()

    mock_provider = AsyncMock()
    from app.services.ai.base import AIResult
    mock_provider.generate.return_value = AIResult(answer="https://x/out.png", input_tokens=0, output_tokens=0)
    mock_image_provider_cls.return_value = mock_provider

    from app.services.generation_service import compute_dalle3_credit_cost
    # landscape + 4k = multiplier 4 (see app/services/generation_service.py table)
    assert compute_dalle3_credit_cost(15, aspect="16:9", resolution="4k") == 60
    assert compute_dalle3_credit_cost(15, aspect="1:1", resolution="1k") == 15
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_generation_service.py -v`
Expected: FAIL with `ImportError: cannot import name 'compute_dalle3_credit_cost'`

- [ ] **Step 3: Add the dall-e-3 cost table and wire it into `start_generation`**

In `app/services/generation_service.py`, add near the top (after the imports):
```python
_IMAGE_ASPECT_TO_BUCKET: dict[str, str] = {
    "auto": "square", "1:1": "square", "4:3": "square", "4:5": "square", "5:4": "square",
    "3:2": "landscape", "16:9": "landscape", "21:9": "landscape",
    "2:3": "portrait", "3:4": "portrait", "9:16": "portrait",
}
_IMAGE_BUCKET_TO_SIZE = {"square": "1024x1024", "portrait": "1024x1792", "landscape": "1792x1024"}
_RESOLUTION_TO_QUALITY = {"1k": "standard", "2k": "hd", "4k": "hd"}
_COST_MULTIPLIER: dict[tuple[str, str], int] = {
    ("square", "1k"): 1, ("square", "2k"): 2, ("square", "4k"): 3,
    ("landscape", "1k"): 2, ("landscape", "2k"): 3, ("landscape", "4k"): 4,
    ("portrait", "1k"): 2, ("portrait", "2k"): 3, ("portrait", "4k"): 4,
}


def compute_dalle3_credit_cost(base_cost: int, aspect: str, resolution: str) -> int:
    bucket = _IMAGE_ASPECT_TO_BUCKET.get(aspect, "square")
    multiplier = _COST_MULTIPLIER[(bucket, resolution)]
    return max(1, round(base_cost * multiplier))
```

In `start_generation`, replace:
```python
    model = await _get_model(session, model_code)
    await check_access(session, user, model, prompt, credit_cost=credit_cost_override)
    credit_cost = credit_cost_override if credit_cost_override is not None else model.credit_cost
```
with:
```python
    model = await _get_model(session, model_code)

    if model.model_code == "dall-e-3" and extra and "aspect" in extra and "resolution" in extra:
        aspect, resolution = extra["aspect"], extra["resolution"]
        credit_cost_override = compute_dalle3_credit_cost(model.credit_cost, aspect, resolution)
        bucket = _IMAGE_ASPECT_TO_BUCKET.get(aspect, "square")
        extra = {
            "size": _IMAGE_BUCKET_TO_SIZE[bucket],
            "quality": _RESOLUTION_TO_QUALITY[resolution],
            "resolution": resolution,
        }

    await check_access(session, user, model, prompt, credit_cost=credit_cost_override)
    credit_cost = credit_cost_override if credit_cost_override is not None else model.credit_cost
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_generation_service.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/generation_service.py tests/services/test_generation_service.py
git commit -m "feat: preserve dall-e-3 aspect/resolution credit multiplier inside generation_service"
```

---

### Task 8: PiAPI model catalog seed data

**Files:**
- Modify: `app/db/seed.py`

**Interfaces:**
- Consumes: `piapi_model`/`piapi_task_type`/`piapi_extra_input`/`duration_seconds` columns from Task 1.
- Produces: 11 new `MODEL_CONFIGS` rows (5 image, 6 video), all `provider=ModelProvider.piapi`, `is_active=True`.

- [ ] **Step 1: Verify the 5 unconfirmed identifiers**

Before writing the seed rows, fetch each of these PiAPI doc pages and record the exact `model`/`task_type`/`input` fields used in their example request (the design research already confirmed the other 6 rows verbatim — see Task 8 table below for those):
- Qwen Image: `https://piapi.ai/docs/qwen-api/text-to-image` (or the sidebar-linked create-task page under `qwen-api`)
- GPT Image 1.5: `https://piapi.ai/docs/gpt-image-api/*` (OpenAI-compatible endpoint — check whether it uses the unified `/task` endpoint or `piapi.ai`'s OpenAI-compatible `/v1/images/generations`-style endpoint instead; if the latter, `PiAPIClient` needs a second method — add it following the same pattern as `create_task`/`get_task` before writing this row)
- Nano Banana Pro: `https://piapi.ai/docs/gemini-api/nano-banana-pro` (confirmed sibling `nano-banana-2` uses `model="gemini"`, `task_type="nano-banana-2"` — Pro almost certainly follows `task_type="nano-banana-pro"`, confirm before committing)
- Sora2: `https://piapi.ai/docs/sora2-api/*` or `https://piapi.ai/docs/sora-2/*`
- Kling 3.0 Omni: `https://piapi.ai/docs/kling-api/*` (the generic `create-task` page's `version` enum tops out at `"2.6"` — 3.0 Omni may need a different `task_type` entirely rather than a `version` value; check the Kling 3.0 Omni-specific sidebar page, not just the generic one)
- Luma: `https://piapi.ai/docs/dream-machine/create-task` — model likely `"luma"`, task_type likely `"video_generation"` per the webhook example already captured in the design spec; confirm the exact `task_type` string on the create-task page itself (the webhook example only proves the *response* shape, not the *request* field value).

- [ ] **Step 2: Add the seed rows**

In `app/db/seed.py`, add to `MODEL_CONFIGS` (after the existing `dall-e-3` entry):
```python
    # --- PiAPI image models (30% margin, 77₽/$, floor 0.65₽/credit) ---
    dict(model_code="piapi-flux-dev", provider=ModelProvider.piapi, display_name="AI Photo Fast",
         category=ModelCategory.image, key_purpose="image", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=3, is_active=True, is_premium=False, max_context_tokens=4000,
         piapi_model="Qubico/flux1-dev", piapi_task_type="txt2img",
         piapi_extra_input={"width": 1024, "height": 1024}),
    dict(model_code="piapi-qwen-image", provider=ModelProvider.piapi, display_name="AI Photo Edit",
         category=ModelCategory.image, key_purpose="image", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=3, is_active=True, is_premium=False, max_context_tokens=4000,
         piapi_model="<confirmed in Step 1>", piapi_task_type="<confirmed in Step 1>",
         piapi_extra_input={}),
    dict(model_code="piapi-gpt-image-1-5", provider=ModelProvider.piapi, display_name="AI Photo Pro",
         category=ModelCategory.image, key_purpose="image", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=8, is_active=True, is_premium=True, max_context_tokens=4000,
         piapi_model="<confirmed in Step 1>", piapi_task_type="<confirmed in Step 1>",
         piapi_extra_input={"size": "1024x1024", "quality": "medium"}),
    dict(model_code="piapi-seedream5-lite", provider=ModelProvider.piapi, display_name="AI Photo Lite",
         category=ModelCategory.image, key_purpose="image", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=6, is_active=True, is_premium=False, max_context_tokens=4000,
         piapi_model="<confirmed in Step 1>", piapi_task_type="<confirmed in Step 1>",
         piapi_extra_input={}),
    dict(model_code="piapi-nano-banana-pro", provider=ModelProvider.piapi, display_name="AI Photo Ultra",
         category=ModelCategory.image, key_purpose="image", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=18, is_active=True, is_premium=True, max_context_tokens=4000,
         piapi_model="gemini", piapi_task_type="<confirmed in Step 1, likely nano-banana-pro>",
         piapi_extra_input={"resolution": "2K", "aspect_ratio": "1:1", "output_format": "jpg"}),
    # --- PiAPI video models ---
    dict(model_code="piapi-veo3-fast", provider=ModelProvider.piapi, display_name="AI Video Fast",
         category=ModelCategory.video, key_purpose="video", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=51, is_active=True, is_premium=False, max_context_tokens=4000, duration_seconds=5,
         piapi_model="veo3.1", piapi_task_type="veo3.1-video-fast",
         piapi_extra_input={"aspect_ratio": "16:9", "duration": "5s", "resolution": "720p", "generate_audio": False}),
    dict(model_code="piapi-wan26", provider=ModelProvider.piapi, display_name="AI Video Standard",
         category=ModelCategory.video, key_purpose="video", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=68, is_active=True, is_premium=False, max_context_tokens=4000, duration_seconds=5,
         piapi_model="Wan", piapi_task_type="<confirm txt2video variant in Step 1; img2video confirmed as wan26-img2video>",
         piapi_extra_input={"resolution": "720p", "duration": 5}),
    dict(model_code="piapi-sora2", provider=ModelProvider.piapi, display_name="AI Video Sora",
         category=ModelCategory.video, key_purpose="video", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=68, is_active=True, is_premium=True, max_context_tokens=4000, duration_seconds=5,
         piapi_model="<confirmed in Step 1>", piapi_task_type="<confirmed in Step 1>",
         piapi_extra_input={"duration": 5}),
    dict(model_code="piapi-hailuo", provider=ModelProvider.piapi, display_name="AI Video Hailuo",
         category=ModelCategory.video, key_purpose="video", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=39, is_active=True, is_premium=False, max_context_tokens=4000, duration_seconds=6,
         piapi_model="hailuo", piapi_task_type="video_generation",
         piapi_extra_input={"model": "v2.3", "duration": 6, "resolution": 768, "expand_prompt": True}),
    dict(model_code="piapi-kling3-omni", provider=ModelProvider.piapi, display_name="AI Video Kling",
         category=ModelCategory.video, key_purpose="video", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=85, is_active=True, is_premium=True, max_context_tokens=4000, duration_seconds=5,
         piapi_model="<confirmed in Step 1>", piapi_task_type="<confirmed in Step 1>",
         piapi_extra_input={"resolution": "720p", "duration": 5}),
    dict(model_code="piapi-seedance2-fast", provider=ModelProvider.piapi, display_name="AI Video Seedance",
         category=ModelCategory.video, key_purpose="video", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=119, is_active=True, is_premium=False, max_context_tokens=4000, duration_seconds=5,
         piapi_model="seedance", piapi_task_type="seedance-2-fast",
         piapi_extra_input={"duration": 5, "aspect_ratio": "16:9"}),
    dict(model_code="piapi-luma", provider=ModelProvider.piapi, display_name="AI Video Luma",
         category=ModelCategory.video, key_purpose="video", cost_input_per_1m=0, cost_output_per_1m=0,
         credit_cost=34, is_active=True, is_premium=False, max_context_tokens=4000, duration_seconds=5,
         piapi_model="<confirmed in Step 1>", piapi_task_type="<confirmed in Step 1>",
         piapi_extra_input={}),
```
Replace every `<confirmed in Step 1>` placeholder with the value found in Step 1 before committing — `seed.py` is executed against production data, so a wrong `piapi_model`/`piapi_task_type` string means every purchase of that model fails at generation time (the webhook never fires; the user is stuck on "processing" until the poll timeout). Double-check each one against a real `curl` call to PiAPI's `/task` endpoint with a throwaway prompt if there's any doubt, not just the docs page — docs pages were observed to lag behind what the API actually accepts during this plan's research (Task 8, Step 1's Kling note).

- [ ] **Step 3: Run the seed script against the dev database**

Run: `python -m app.db.seed`
Expected: no errors; `SELECT model_code FROM model_configs WHERE provider = 'piapi';` returns 11 rows.

- [ ] **Step 4: Commit**

```bash
git add app/db/seed.py
git commit -m "feat: seed PiAPI model catalog (5 image + 6 video models, 30% margin pricing)"
```

---

### Task 9: Frontend — `api/client.ts` generate/poll functions

**Files:**
- Modify: `frontend-next/src/api/client.ts`

**Interfaces:**
- Produces: `GenerationStatus` type, `api.generate(modelCode, prompt, extra?, creditCostOverride?) -> Promise<{request_id: number}>`, `api.generationStatus(id) -> Promise<GenerationStatus>`.

- [ ] **Step 1: Add the types and API methods**

In `frontend-next/src/api/client.ts`, add after `export interface ImageGenerateResponse { ... }`:
```typescript
export interface GenerationStatus {
  status: "processing" | "success" | "error";
  result_url: string | null;
  error_message: string | null;
  credit_cost: number;
}
```

In the `export const api = { ... }` object, replace the existing `generateImage: (...) => request<ImageGenerateResponse>("/api/chat/image", ...)` entry with:
```typescript
  generate: (modelCode: string, prompt: string, extra?: Record<string, unknown>, creditCostOverride?: number) =>
    request<{ request_id: number }>("/api/generate", {
      method: "POST",
      body: JSON.stringify({
        model_code: modelCode,
        prompt,
        extra: extra ?? null,
        credit_cost_override: creditCostOverride ?? null,
      }),
    }),
  generationStatus: (requestId: number) => request<GenerationStatus>(`/api/generate/${requestId}`),
```

- [ ] **Step 2: Verify the frontend still type-checks**

Run: `cd frontend-next && npx tsc --noEmit`
Expected: errors in `generate-image/page.tsx` only (it still calls the retired `api.generateImage` — fixed in Task 10). No errors anywhere else.

- [ ] **Step 3: Commit**

```bash
git add frontend-next/src/api/client.ts
git commit -m "feat: add api.generate/api.generationStatus, retire api.generateImage"
```

---

### Task 10: Frontend — rework `generate-image/page.tsx` to the async poll contract

**Files:**
- Modify: `frontend-next/src/app/generate-image/page.tsx`

**Interfaces:**
- Consumes: `api.generate`, `api.generationStatus` from Task 9.

- [ ] **Step 1: Replace the `generate()` function**

In `frontend-next/src/app/generate-image/page.tsx`, replace:
```typescript
  async function generate() {
    if (!model || !prompt.trim() || generating) return;
    setGenerating(true);
    setError("");
    setResultUrl(null);
    try {
      const result = await api.generateImage(model.model_code, prompt.trim(), aspect, resolution);
      setResultUrl(result.image_url);
      haptic("medium");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сгенерировать изображение");
    } finally {
      setGenerating(false);
    }
  }
```
with:
```typescript
  const POLL_INTERVAL_MS = 2000;
  const POLL_ATTEMPTS = 60;

  async function generate() {
    if (!model || !prompt.trim() || generating) return;
    setGenerating(true);
    setError("");
    setResultUrl(null);
    try {
      const isDalle3 = model.model_code === "dall-e-3";
      const { request_id } = await api.generate(
        model.model_code,
        prompt.trim(),
        isDalle3 ? { aspect, resolution } : undefined,
      );

      for (let i = 0; i < POLL_ATTEMPTS; i++) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        const status = await api.generationStatus(request_id);
        if (status.status === "success") {
          setResultUrl(status.result_url);
          haptic("medium");
          return;
        }
        if (status.status === "error") {
          setError(status.error_message ?? "Не удалось сгенерировать изображение");
          return;
        }
      }
      setError("Генерация занимает дольше обычного, попробуйте позже");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сгенерировать изображение");
    } finally {
      setGenerating(false);
    }
  }
```

- [ ] **Step 2: Verify the frontend type-checks and lints clean**

Run: `cd frontend-next && npx tsc --noEmit && npm run lint`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend-next/src/app/generate-image/page.tsx
git commit -m "feat: rework GenerateImage to the async generate+poll contract"
```

---

### Task 11: Frontend — new `generate-video` screen

**Files:**
- Create: `frontend-next/src/app/generate-video/page.tsx`
- Modify: `frontend-next/src/components/shell.tsx` (fullscreen route + FAB long-press entry point)

**Interfaces:**
- Consumes: `api.models()` (existing, filter `category === "video"`), `api.generate`, `api.generationStatus` (Task 9).

- [ ] **Step 1: Write the screen**

Create `frontend-next/src/app/generate-video/page.tsx`:
```tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Section } from "@/components/ui/section";
import { List } from "@/components/ui/list";
import { Cell } from "@/components/ui/cell";
import { Sheet } from "@/components/ui/sheet";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { ApiError, api, type ModelOut } from "@/api/client";
import { haptic } from "@/lib/telegram";

const POLL_INTERVAL_MS = 2000;

export default function GenerateVideo() {
  const router = useRouter();
  const [models, setModels] = useState<ModelOut[] | null>(null);
  const [model, setModel] = useState<ModelOut | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .models()
      .then((all) => {
        const videos = all.filter((m) => m.category === "video");
        setModels(videos);
        setModel((prev) => prev ?? videos[0] ?? null);
      })
      .catch(() => setModels([]));
  }, []);

  async function generate() {
    if (!model || !prompt.trim() || generating) return;
    setGenerating(true);
    setError("");
    setResultUrl(null);
    try {
      const { request_id } = await api.generate(model.model_code, prompt.trim());
      const pollAttempts = Math.max(60, 20 * 15); // generous ceiling; video can take minutes

      for (let i = 0; i < pollAttempts; i++) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        const status = await api.generationStatus(request_id);
        if (status.status === "success") {
          setResultUrl(status.result_url);
          haptic("medium");
          return;
        }
        if (status.status === "error") {
          setError(status.error_message ?? "Не удалось сгенерировать видео");
          return;
        }
      }
      setError("Генерация занимает дольше обычного, попробуйте позже");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сгенерировать видео");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="flex min-h-[100dvh] flex-col pb-[90px]">
      <div className="flex items-center gap-3 p-4">
        <button
          onClick={() => router.back()}
          aria-label="Назад"
          className="press-scale border-none bg-none p-0 text-[22px] text-white"
        >
          ←
        </button>
        <h2 className="heading-font mr-[22px] flex-1 text-center text-lg font-bold">Generate Video</h2>
      </div>

      <div className="flex flex-col gap-3.5 px-4">
        <div className="rounded-lg border border-border-soft bg-surface p-3.5">
          <Textarea
            placeholder="Опишите видео, которое хотите создать"
            rows={4}
            maxLength={2000}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
        </div>

        <Cell subtitle={model ? `${model.credit_cost} кредитов` : undefined} onClick={() => setPickerOpen(true)}>
          {model ? model.display_name : "Выберите модель"}
        </Cell>

        <Button stretched disabled={!model || !prompt.trim() || generating} onClick={generate}>
          {generating ? <Spinner size="s" /> : "Создать видео"}
        </Button>

        {error && <div className="text-sm text-red-400">{error}</div>}

        {resultUrl && (
          // eslint-disable-next-line jsx-a11y/media-has-caption
          <video controls src={resultUrl} className="w-full rounded-lg" />
        )}
      </div>

      {pickerOpen && (
        <Sheet open onOpenChange={(open) => !open && setPickerOpen(false)} header={<Sheet.Header>Модель</Sheet.Header>}>
          <List>
            <Section>
              {models === null && <Cell before={<Spinner size="s" />}>Загрузка…</Cell>}
              {models?.map((m) => (
                <Cell
                  key={m.model_code}
                  subtitle={`${m.credit_cost} кредитов`}
                  onClick={() => {
                    setModel(m);
                    setPickerOpen(false);
                  }}
                >
                  {m.display_name}
                </Cell>
              ))}
            </Section>
          </List>
        </Sheet>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add the route to fullscreen routes and the FAB long-press entry point**

In `frontend-next/src/components/shell.tsx`, change:
```typescript
const FULLSCREEN_ROUTES = ["/chat", "/generate-image"];
```
to:
```typescript
const FULLSCREEN_ROUTES = ["/chat", "/generate-image", "/generate-video"];
```

Replace the `Fab` component's single-tap-only button with a long-press-for-video variant:
```tsx
function Fab() {
  const router = useRouter();
  const pressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const longPressed = useRef(false);

  function startPress() {
    longPressed.current = false;
    pressTimer.current = setTimeout(() => {
      longPressed.current = true;
      haptic("medium");
      router.push("/generate-video");
    }, 500);
  }

  function endPress() {
    if (pressTimer.current) clearTimeout(pressTimer.current);
    if (!longPressed.current) router.push("/chat");
  }

  return (
    <button
      onPointerDown={startPress}
      onPointerUp={endPress}
      onPointerLeave={() => pressTimer.current && clearTimeout(pressTimer.current)}
      aria-label="Открыть чат с нейросетью (удержите для генерации видео)"
      className="press-scale fixed bottom-20 right-4 z-[2] flex h-[58px] w-[58px] items-center justify-center rounded-full bg-[image:var(--brand-gradient)] text-2xl shadow-glow"
    >
      ✨
    </button>
  );
}
```
Add `useRef` to the `react` import at the top of the file, and `haptic` to the `@/lib/telegram` import (add it alongside `initTelegram`).

- [ ] **Step 3: Verify the frontend type-checks and lints clean**

Run: `cd frontend-next && npx tsc --noEmit && npm run lint`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend-next/src/app/generate-video/page.tsx frontend-next/src/components/shell.tsx
git commit -m "feat: add Generate Video screen, reachable via FAB long-press"
```

---

### Task 12: E2E Playwright spec for video generation

**Files:**
- Create: `frontend-next/e2e/generate-video.spec.ts`

**Interfaces:**
- Consumes: existing `frontend-next/e2e/mock-telegram.ts` fixture and Playwright route-mocking conventions already used by the other specs in `frontend-next/e2e/`.

- [ ] **Step 1: Write the spec**

Create `frontend-next/e2e/generate-video.spec.ts`:
```typescript
import { test, expect } from "./mock-telegram";

test("generates a video end to end", async ({ page }) => {
  await page.route("**/api/models", (route) =>
    route.fulfill({
      json: [
        { model_code: "piapi-veo3-fast", display_name: "AI Video Fast", category: "video", is_premium: false, credit_cost: 51 },
      ],
    }),
  );

  await page.route("**/api/generate", (route) =>
    route.fulfill({ json: { request_id: 1 } }),
  );

  let pollCount = 0;
  await page.route("**/api/generate/1", (route) => {
    pollCount += 1;
    if (pollCount < 2) {
      return route.fulfill({ json: { status: "processing", result_url: null, error_message: null, credit_cost: 51 } });
    }
    return route.fulfill({
      json: { status: "success", result_url: "https://cdn.example.com/out.mp4", error_message: null, credit_cost: 51 },
    });
  });

  await page.goto("/generate-video");
  await page.getByText("AI Video Fast").waitFor({ state: "hidden" }).catch(() => {});

  await page.getByPlaceholder("Опишите видео, которое хотите создать").fill("a sunset over mountains");
  await page.getByText("Создать видео").click();

  await expect(page.locator("video")).toHaveAttribute("src", "https://cdn.example.com/out.mp4", { timeout: 15000 });
});
```

- [ ] **Step 2: Run the spec**

Run: `cd frontend-next && npx playwright test e2e/generate-video.spec.ts`
Expected: 1 passed

- [ ] **Step 3: Commit**

```bash
git add frontend-next/e2e/generate-video.spec.ts
git commit -m "test: add e2e spec for the video generation flow"
```

---

## Final Review

After all 12 tasks are complete and individually reviewed, dispatch the final whole-branch code reviewer (per subagent-driven-development) before handing off to `superpowers:finishing-a-development-branch`. Pay special attention to:
- Every `<confirmed in Step 1>` placeholder in Task 8's seed data was actually replaced with a real value (grep the committed `app/db/seed.py` for the literal string `<confirmed` — zero matches expected).
- The webhook secret check in `app/webhooks/piapi.py` fails closed (rejects) when `settings.piapi_webhook_secret` is empty, not just when it mismatches — an unset secret must never mean "accept anything."
- `PIAPI_API_KEY`, `PIAPI_WEBHOOK_SECRET`, and `BACKEND_PUBLIC_URL` need to be added to `render.yaml`'s `ai-hub-bot` service envVars before this is deployable — flag this to the human partner as a manual Render dashboard step (the webhook secret should be a freshly generated random value, not something the plan invents).
