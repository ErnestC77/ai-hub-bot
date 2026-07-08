# Credit System Phase 3 — fal.ai Media Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dead PiAPI/DALL-E media pipeline with a fal.ai webhook-based image/video generation flow on top of the phase-1 credit ledger, storing the generated result URL durably in a new `ai_requests.result_url` column and removing the client-supplied `credit_cost_override` security hole.

**Architecture:** `POST /api/generate` resolves an `AiModel`, computes the credit cost **server-side only**, reserves credits, submits to fal.ai's queue API with a webhook callback, and returns a `request_id` the client polls via `GET /api/generate/{id}`. fal.ai calls back `POST /api/fal/webhook?secret=...`, which writes the result URL into `ai_requests.result_url` and settles (success) or refunds (error) the reservation idempotently, releasing the per-user Redis lock that was held across the whole async round-trip — the same structure the old PiAPI flow used, rebuilt on the phase-1 `reserve → settle/refund` credit engine. One small migration adds the nullable `result_url` column: the user's credits are already charged when the webhook delivers the result, so the URL must survive Redis restarts/evictions — it lives in Postgres, never in a TTL'd cache.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, Postgres (prod) / aiosqlite (tests), Redis (`redis.asyncio`, used for the per-user in-flight lock only), raw `httpx` for fal.ai, `pytest` + `pytest-asyncio` (auto mode) + `respx`.

## Global Constraints

- Spec (ground truth): `docs/superpowers/specs/2026-07-08-credit-system-phase3-fal-media-design.md`. Backend-only; **no `frontend-next` changes**.
- **Exactly one migration this phase:** nullable `ai_requests.result_url` — ORM: `result_url: Mapped[str | None] = mapped_column(String(1024))`; migration revision `d5e6f7a8b9c0` with `down_revision = 'c4d5e6f7a8b9'` (verified current head via `python -m alembic heads` → `c4d5e6f7a8b9 (head)`).
- **The generation result URL is stored ONLY in `ai_requests.result_url`** (durable, no TTL). Redis is used for the `ai_lock:{user.id}` in-flight lock only — never for result storage.
- **No new pip dependencies.** `httpx>=0.27` and `respx>=0.21` are already in `requirements.txt` (verified).
- Credit cost is computed **only on the backend**. The request body has no `credit_cost_override`; unknown JSON fields are ignored by Pydantic and must be proven (by test) to have zero effect on the charge.
- Pricing calls (exact, from spec): image → `calculate_image_credits(model, quantity=1, megapixels=1.0, is_edit=image_url is not None)`; video → `calculate_video_credits(model, duration_seconds or 5)` (5 s is the spec default). Both already exist in `app/services/pricing.py` — do not modify them.
- Confirmation thresholds (strictly greater): image `estimated > 300`, video `estimated > 1000`; without `confirm=True` raise `ConfirmationRequiredError(estimated)`. The check runs **before** the Redis lock is taken (spec flow order: resolve → estimate → confirm → lock → reserve → submit).
- In the normal media path `estimated == reserved == charged` and `settle_request(..., actual == reserved)` returns `None` (no adjustment transaction) — this is the expected path, not a degradation.
- fal.ai submit endpoint: `POST https://queue.fal.run/{model.provider_model_id}?fal_webhook={webhook_url}`; auth header `Authorization: Key <api_key>`; response field `request_id` → stored in `ai_requests.provider_response_id`.
- fal webhook body: `{"request_id": ..., "status": "OK"|"ERROR", "payload": {...}}`. Unconfirmed fal payload shapes get a `PLACEHOLDER` comment with «уточнить перед продакшн-запуском» — do not fabricate confidence.
- Config: new top-level `Settings.fal_webhook_secret: str = ""` (same pattern as the existing `piapi_webhook_secret`). `FalSettings` (`image_key`/`video_key`/`dev_key`) and `_PURPOSE_ATTR[Provider.FAL]` already exist — **no key-manager changes** (verified: `Provider.FAL` maps `KeyPurpose.IMAGE→image_key`, `KeyPurpose.VIDEO→video_key`).
- Per-user Redis lock `ai_lock:{user.id}` (TTL 900 s safety net) is held from `start_media_generation` until `handle_fal_webhook` completes; it IS released immediately on any synchronous failure before the fal submit succeeds. This differs from phase 2's text flow (which releases in `finally`).
- Webhook idempotency: atomic `UPDATE ai_requests ... WHERE id=? AND status='reserved'`; `rowcount == 0` → duplicate delivery, no-op (same trick as the old `handle_piapi_webhook`). Settle/refund run in the **same transaction** as the claim UPDATE, so on Postgres the claim's row lock serializes concurrent deliveries.
- Files deleted in this phase (exact list from spec, Task 7): `app/services/ai/piapi_client.py`, `app/services/ai/image_service.py`, `app/webhooks/piapi.py`, `app/services/generation_service.py`, `tests/services/ai/test_piapi_client.py`, `tests/services/keys/test_piapi_key.py`. Everything else PiAPI-related (`PiApiSettings`, `piapi_webhook_secret` in config, `Provider.PIAPI` in key enums/manager) **stays untouched** — out of scope.
- `app.main` is NOT importable and stays that way (its `admin`/`key_healthcheck` imports still reference the deleted `ModelConfig`; fixed in phases 4–5 — verified `admin.py:10` imports `ModelConfig, Tariff` from `app.db.models`). API tests therefore build a minimal standalone `FastAPI()` app with `dependency_overrides`, exactly like `tests/api/test_chat_routes.py`. Do NOT use `python -c "import app.main"` as a verification step — it is expected to fail for reasons outside this phase.
- `pytest.ini` sets `asyncio_mode = auto` — async test functions need no decorators. There is no `conftest.py`; each test file is self-contained (fixtures repeated per file, per project convention).
- Existing user-facing strings are copied verbatim: `"Дождитесь ответа на предыдущий запрос."`, `"Недостаточно кредитов"`, `"Модель временно недоступна, попробуйте позже"`, `"model not found"`, `"request not found"`, `"invalid secret"`.
- `POST /api/generate` 409-convention matches `/api/chat` (phase 2): `ConfirmationRequiredError` → 409 with body exactly `{"estimated_credits": N}` (no `"detail"`); `RequestInProgressError` → 409 with `"detail"`.
- Work on a feature branch (e.g. `feature/credit-system-phase3-fal-media`); commit after every task.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `alembic/versions/d5e6f7a8b9c0_phase3_result_url.py` | Create | Adds nullable `ai_requests.result_url` (String(1024)) |
| `app/db/models/ai_request.py` | Modify | ORM column `result_url: Mapped[str \| None]` |
| `app/config.py` | Modify | `Settings.fal_webhook_secret: str = ""` |
| `.env.example` | Modify | Document `FAL_WEBHOOK_SECRET`, `BACKEND_PUBLIC_URL` |
| `app/services/ai/fal_client.py` | Create | Raw-httpx transport to fal.ai queue API + `extract_result_url` |
| `app/services/media_generation_service.py` | Create | Business flow: estimate → confirm → lock → reserve → submit; webhook settle/refund; owner-scoped lookup |
| `app/api/routes/generate.py` | Rewrite | `POST /api/generate` (no `credit_cost_override`), `GET /api/generate/{id}` (real `charged_credits`, `result_url` from DB) |
| `app/webhooks/fal.py` | Create | `POST /api/fal/webhook?secret=...` → `handle_fal_webhook` |
| `app/main.py` | Modify | Swap `piapi_webhook` router for `fal_webhook` |
| `tests/db/test_credit_schema_v2.py` | Modify | `result_url` round-trip test |
| `tests/test_config.py` | Create | `FAL_WEBHOOK_SECRET` env read test |
| `tests/services/ai/test_fal_client.py` | Create | respx tests for `FalClient` + `extract_result_url` |
| `tests/services/test_media_generation_service.py` | Create | sqlite-fixture tests for the whole service flow |
| `tests/api/test_generate_routes.py` | Create | Route mapping + end-to-end (generate → webhook → poll) tests |
| 6 legacy files (see Global Constraints) | Delete | PiAPI/DALL-E pipeline removal |

---

### Task 1: Migration + ORM column `ai_requests.result_url`

**Files:**
- Modify: `app/db/models/ai_request.py`
- Create: `alembic/versions/d5e6f7a8b9c0_phase3_result_url.py`
- Test: `tests/db/test_credit_schema_v2.py`

**Interfaces:**
- Consumes: phase-1 `AIRequest` model (`app/db/models/ai_request.py`), current alembic head `c4d5e6f7a8b9` (`alembic/versions/c4d5e6f7a8b9_phase2_fallback_model_code.py`).
- Produces: `AIRequest.result_url: Mapped[str | None]` — read by Task 5 (`handle_fal_webhook` writes it) and Task 6 (`GET /api/generate/{id}` returns it); migration revision `d5e6f7a8b9c0`.

- [ ] **Step 1: Write the failing test**

Append to `tests/db/test_credit_schema_v2.py` (the file already has the `session` fixture and all needed imports):

```python
async def test_ai_request_result_url_round_trip(session):
    user = User(telegram_id=3)
    session.add(user)
    await session.flush()

    request = AIRequest(
        user_id=user.id,
        provider="fal",
        model_code="flux_dev",
        category=ModelCategory.image,
        status=RequestStatus.reserved,
        prompt_preview="a bear",
        estimated_credits=100,
        reserved_credits=100,
    )
    session.add(request)
    await session.commit()

    fetched = await session.get(AIRequest, request.id)
    assert fetched.result_url is None  # nullable, пусто до вебхука

    fetched.result_url = "https://cdn.fal.media/out.png"
    await session.commit()

    again = await session.get(AIRequest, request.id)
    assert again.result_url == "https://cdn.fal.media/out.png"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/db/test_credit_schema_v2.py::test_ai_request_result_url_round_trip -v`
Expected: FAIL with `AttributeError: 'AIRequest' object has no attribute 'result_url'`

- [ ] **Step 3: Add the ORM column**

In `app/db/models/ai_request.py`, directly below the `provider_response_id` line, add:

```python
    provider_response_id: Mapped[str | None] = mapped_column(String(128))
    # URL готового изображения/видео от fal.ai (фаза 3). Durable-хранилище:
    # кредиты за генерацию уже списаны, поэтому результат должен переживать
    # рестарты/евикции Redis -- хранится в Postgres, без TTL.
    result_url: Mapped[str | None] = mapped_column(String(1024))
```

(The first line already exists — shown for placement only; add the comment + `result_url` line after it.)

- [ ] **Step 4: Write the migration**

Create `alembic/versions/d5e6f7a8b9c0_phase3_result_url.py`:

```python
"""phase3: add ai_requests.result_url (nullable String(1024)) -- durable storage
for the fal.ai generation result URL. Credits are already charged when the
webhook delivers the result, so the URL must survive Redis restarts/TTL.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-07-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ai_requests', sa.Column('result_url', sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column('ai_requests', 'result_url')
```

- [ ] **Step 5: Run test to verify it passes, and verify the migration chain**

Run: `python -m pytest tests/db/test_credit_schema_v2.py -v`
Expected: PASS (all tests in the file, including the new one)

Run: `python -m alembic heads`
Expected output: `d5e6f7a8b9c0 (head)` — exactly one head. (A real `alembic upgrade` needs Postgres and is not required here; the sqlite `create_all` in tests exercises the ORM column.)

- [ ] **Step 6: Commit**

```bash
git add app/db/models/ai_request.py alembic/versions/d5e6f7a8b9c0_phase3_result_url.py tests/db/test_credit_schema_v2.py
git commit -m "feat: add ai_requests.result_url column (phase 3 migration)"
```

---

### Task 2: `FalClient` — raw httpx transport to fal.ai queue API

**Files:**
- Create: `app/services/ai/fal_client.py`
- Test: `tests/services/ai/test_fal_client.py`

**Interfaces:**
- Consumes: `AiModel.provider_model_id: str` (`app/db/models/ai_models.py`).
- Produces (used by Tasks 4–5):
  - `class FalClient: def __init__(self, api_key: str)`
  - `async def submit_image(self, model: AiModel, prompt: str, *, image_url: str | None = None, webhook_url: str) -> str` — returns fal `request_id`
  - `async def submit_video(self, model: AiModel, prompt: str, *, duration_seconds: int, webhook_url: str) -> str` — returns fal `request_id`
  - module-level `def extract_result_url(payload: dict) -> str | None`

- [ ] **Step 1: Write the failing tests**

Create `tests/services/ai/test_fal_client.py` (mirrors the respx pattern of the soon-to-be-deleted `test_piapi_client.py` — `FalClient` is a raw httpx client, NOT an AsyncOpenAI wrapper):

```python
import json

import httpx
import pytest
import respx

from app.db.enums import CostUnit, ModelCategory, ModelProvider, ModelTier
from app.db.models import AiModel
from app.services.ai.fal_client import FalClient, extract_result_url


def _model(code="flux_dev", *, provider_model_id="fal-ai/flux/dev",
           category=ModelCategory.image) -> AiModel:
    return AiModel(
        provider=ModelProvider.fal, category=category, code=code, display_name=code,
        provider_model_id=provider_model_id, tier=ModelTier.standard,
        cost_unit=CostUnit.image, min_credits=0, recommended_credits=100,
    )


@respx.mock
async def test_submit_image_posts_prompt_and_returns_request_id():
    route = respx.post(host="queue.fal.run", path="/fal-ai/flux/dev").mock(
        return_value=httpx.Response(200, json={"request_id": "req-123"})
    )
    client = FalClient(api_key="fal-test-key")

    request_id = await client.submit_image(
        _model(), "a bear",
        webhook_url="https://backend.example.com/api/fal/webhook?secret=s",
    )

    assert request_id == "req-123"
    request = route.calls.last.request
    assert request.headers["authorization"] == "Key fal-test-key"
    # webhook уходит query-параметром fal_webhook, не в теле
    assert request.url.params["fal_webhook"] == "https://backend.example.com/api/fal/webhook?secret=s"
    assert json.loads(request.content) == {"prompt": "a bear"}


@respx.mock
async def test_submit_image_includes_image_url_for_edit():
    route = respx.post(host="queue.fal.run", path="/fal-ai/flux-kontext/pro").mock(
        return_value=httpx.Response(200, json={"request_id": "req-124"})
    )
    client = FalClient(api_key="k")

    await client.submit_image(
        _model(provider_model_id="fal-ai/flux-kontext/pro"), "make it night",
        image_url="https://cdn.example.com/in.png",
        webhook_url="https://backend.example.com/api/fal/webhook?secret=s",
    )

    body = json.loads(route.calls.last.request.content)
    assert body == {"prompt": "make it night", "image_url": "https://cdn.example.com/in.png"}


@respx.mock
async def test_submit_video_includes_duration():
    route = respx.post(host="queue.fal.run", path="/fal-ai/kling-video/v2/master").mock(
        return_value=httpx.Response(200, json={"request_id": "req-125"})
    )
    client = FalClient(api_key="k")

    request_id = await client.submit_video(
        _model(code="kling", provider_model_id="fal-ai/kling-video/v2/master",
               category=ModelCategory.video),
        "a bear runs", duration_seconds=10,
        webhook_url="https://backend.example.com/api/fal/webhook?secret=s",
    )

    assert request_id == "req-125"
    body = json.loads(route.calls.last.request.content)
    assert body == {"prompt": "a bear runs", "duration": 10}


@respx.mock
async def test_submit_raises_on_http_error():
    respx.post(host="queue.fal.run", path="/fal-ai/flux/dev").mock(
        return_value=httpx.Response(401, json={"detail": "invalid key"})
    )
    client = FalClient(api_key="bad")

    with pytest.raises(httpx.HTTPStatusError):
        await client.submit_image(
            _model(), "a bear", webhook_url="https://b/api/fal/webhook?secret=s"
        )


def test_extract_result_url_image_shape():
    payload = {"images": [{"url": "https://x/a.png"}, {"url": "https://x/b.png"}]}
    assert extract_result_url(payload) == "https://x/a.png"


def test_extract_result_url_video_shape():
    assert extract_result_url({"video": {"url": "https://x/a.mp4"}}) == "https://x/a.mp4"


def test_extract_result_url_none_when_unknown_shape():
    assert extract_result_url({}) is None
    assert extract_result_url({"images": []}) is None
    assert extract_result_url({"video": {}}) is None
    assert extract_result_url({"unexpected": {"url": "https://x/a.png"}}) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/services/ai/test_fal_client.py -v`
Expected: FAIL (collection error) with `ModuleNotFoundError: No module named 'app.services.ai.fal_client'`

- [ ] **Step 3: Write the implementation**

Create `app/services/ai/fal_client.py`:

```python
"""Тонкий HTTP-клиент fal.ai queue API. Только транспорт: расчёт кредитов,
резервы и обработка вебхука живут в media_generation_service."""

import httpx

from app.db.models import AiModel

BASE_URL = "https://queue.fal.run"


def extract_result_url(payload: dict) -> str | None:
    """Разные fal-модели кладут URL результата по-разному. Перебираем известные
    формы по порядку; None, если ничего не подошло (по образцу удалённого
    piapi_client.extract_result_url).

    Подтверждённые формы:
    - image-модели: {"images": [{"url": ...}, ...]}
    - video-модели: {"video": {"url": ...}}

    PLACEHOLDER: перед продакшн-запуском уточнить формы ответа всех 8 моделей
    каталога (fal-ai/*) и дополнить перебор.
    """
    images = payload.get("images") or []
    if images and isinstance(images[0], dict) and images[0].get("url"):
        return images[0]["url"]

    video = payload.get("video") or {}
    if isinstance(video, dict) and video.get("url"):
        return video["url"]

    return None


class FalClient:
    def __init__(self, api_key: str):
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Key {self._api_key}", "Content-Type": "application/json"}

    async def _submit(self, provider_model_id: str, body: dict, webhook_url: str) -> str:
        # Эндпоинт собирается из provider_model_id (как у OpenRouter в фазе 2):
        # модельные ID не хардкодятся в бизнес-логике.
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{BASE_URL}/{provider_model_id}",
                params={"fal_webhook": webhook_url},
                headers=self._headers(),
                json=body,
            )
            response.raise_for_status()
        return response.json()["request_id"]

    async def submit_image(
        self, model: AiModel, prompt: str, *, image_url: str | None = None, webhook_url: str
    ) -> str:
        body: dict = {"prompt": prompt}
        if image_url is not None:
            body["image_url"] = image_url
        return await self._submit(model.provider_model_id, body, webhook_url)

    async def submit_video(
        self, model: AiModel, prompt: str, *, duration_seconds: int, webhook_url: str
    ) -> str:
        # PLACEHOLDER: имя поля длительности ("duration") уточнить перед
        # продакшн-запуском для каждой video-модели каталога.
        body = {"prompt": prompt, "duration": duration_seconds}
        return await self._submit(model.provider_model_id, body, webhook_url)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/services/ai/test_fal_client.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add app/services/ai/fal_client.py tests/services/ai/test_fal_client.py
git commit -m "feat: add FalClient for fal.ai queue submissions"
```

---

### Task 3: Config — `fal_webhook_secret` + `.env.example`

**Files:**
- Modify: `app/config.py` (the `Settings` class, next to `piapi_webhook_secret`)
- Modify: `.env.example`
- Test: `tests/test_config.py` (new file)

**Interfaces:**
- Consumes: existing `Settings` (pydantic-settings; field name → env var `FAL_WEBHOOK_SECRET` automatically, same as `piapi_webhook_secret`).
- Produces: `settings.fal_webhook_secret: str` (default `""`) — used by Task 4 (`_webhook_url()`) and Task 6 (`app/webhooks/fal.py` secret check).

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
from app.config import Settings


def test_fal_webhook_secret_read_from_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("FAL_WEBHOOK_SECRET", "whsec-123")

    settings = Settings()

    assert settings.fal_webhook_secret == "whsec-123"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'fal_webhook_secret'`

- [ ] **Step 3: Add the setting**

In `app/config.py`, in the `Settings` class, change:

```python
    frontend_url: str = ""
    piapi_webhook_secret: str = ""
```

to:

```python
    frontend_url: str = ""
    piapi_webhook_secret: str = ""
    fal_webhook_secret: str = ""
```

- [ ] **Step 4: Document env vars in `.env.example`**

`BACKEND_PUBLIC_URL` is currently NOT documented in `.env.example` (verified) — add it together with the new secret. Append after the `OPENROUTER_DEV_KEY=` block:

```
# fal.ai webhook (фаза 3): секрет сверяется в POST /api/fal/webhook?secret=...
FAL_WEBHOOK_SECRET=

# Публичный URL этого бэкенда -- из него собирается webhook-callback для fal.ai
# (на Render задаётся через external hostname сервиса, см. render.yaml)
BACKEND_PUBLIC_URL=
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (1 test)

- [ ] **Step 6: Commit**

```bash
git add app/config.py .env.example tests/test_config.py
git commit -m "feat: add FAL_WEBHOOK_SECRET setting"
```

---

### Task 4: `media_generation_service` — start flow (estimate → confirm → lock → reserve → submit)

**Files:**
- Create: `app/services/media_generation_service.py`
- Test: `tests/services/test_media_generation_service.py`

**Interfaces:**
- Consumes:
  - `FalClient(api_key)`, `submit_image(model, prompt, *, image_url=None, webhook_url) -> str`, `submit_video(model, prompt, *, duration_seconds, webhook_url) -> str` (Task 2)
  - `settings.fal_webhook_secret`, `settings.backend_public_url` (Task 3 / existing)
  - `calculate_image_credits(model, quantity, megapixels, *, is_edit=False) -> int`, `calculate_video_credits(model, duration_seconds) -> int` (`app/services/pricing.py`, phase 1)
  - `reserve_credits(session, user_id, amount, *, request_id, provider, model_code)`, `refund_request(session, request, *, reason)`, `InsufficientBalanceError` (`app/services/credit_service.py`, phase 1 — `flush()` only, caller owns the transaction)
  - `get_key_manager().get_key(Provider.FAL, KeyPurpose.IMAGE | KeyPurpose.VIDEO) -> str` (`app/services/keys/api_key_manager.py`, unchanged)
  - `redis_client` (`app/redis_client.py`), `AIError` (`app/services/ai/base.py`)
- Produces (used by Tasks 5–6):
  - `async def start_media_generation(session: AsyncSession, user: User, model_code: str, prompt: str, *, image_url: str | None = None, duration_seconds: int | None = None, confirm: bool = False) -> AIRequest`
  - `async def get_generation(session: AsyncSession, user: User, request_id: int) -> AIRequest | None`
  - Exceptions: `ModelNotFoundError`, `RequestInProgressError` (with `user_message = "Дождитесь ответа на предыдущий запрос."`), `ConfirmationRequiredError(estimated_credits: int)` (attribute `.estimated_credits`)
  - Constants: `AI_LOCK_TTL_SECONDS = 900`, `VIDEO_DEFAULT_DURATION_SECONDS = 5`, `IMAGE_CONFIRM_THRESHOLD_CREDITS = 300`, `VIDEO_CONFIRM_THRESHOLD_CREDITS = 1000`

- [ ] **Step 1: Write the failing tests**

Create `tests/services/test_media_generation_service.py`:

```python
import os

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("DATABASE_URL", "postgresql://test")

import pytest
from sqlalchemy import select
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
from app.services import media_generation_service as mgs
from app.services.ai.base import AIError
from app.services.credit_service import InsufficientBalanceError
from app.services.media_generation_service import (
    ConfirmationRequiredError,
    ModelNotFoundError,
    RequestInProgressError,
    get_generation,
    start_media_generation,
)


class FakeRedis:
    """Как в test_text_generation_service.py: set(nx) + delete с записью вызовов."""

    def __init__(self, locked: bool = False):
        self.locked = locked
        self.deleted: list[str] = []

    async def set(self, key, value, nx=False, ex=None):
        return None if self.locked else True

    async def delete(self, key):
        self.deleted.append(key)


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

    async def submit_image(self, model, prompt, *, image_url=None, webhook_url):
        if self.error is not None:
            raise self.error
        self.image_calls.append({
            "model": model.code, "prompt": prompt,
            "image_url": image_url, "webhook_url": webhook_url,
        })
        return self.request_id

    async def submit_video(self, model, prompt, *, duration_seconds, webhook_url):
        if self.error is not None:
            raise self.error
        self.video_calls.append({
            "model": model.code, "prompt": prompt,
            "duration_seconds": duration_seconds, "webhook_url": webhook_url,
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
                 min_credits=0) -> AiModel:
    return AiModel(
        provider=ModelProvider.fal, category=ModelCategory.image, code=code,
        display_name=code, provider_model_id=f"fal-ai/{code}", tier=ModelTier.standard,
        cost_unit=cost_unit, min_credits=min_credits, recommended_credits=recommended,
    )


def _video_model(code="vid", *, cost_unit=CostUnit.second, recommended=600,
                 min_credits=0) -> AiModel:
    return AiModel(
        provider=ModelProvider.fal, category=ModelCategory.video, code=code,
        display_name=code, provider_model_id=f"fal-ai/{code}", tier=ModelTier.premium,
        cost_unit=cost_unit, min_credits=min_credits, recommended_credits=recommended,
    )


async def _seed(session, *models, balance=1000) -> User:
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
    }]
    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 900
    assert await _tx_types(session) == [CreditTxType.reserve]
    assert fake_redis.deleted == []  # лок держится до вебхука, НЕ снимается здесь


async def test_image_edit_multiplier_applied_when_image_url_given(session, fal):
    user = await _seed(session, _image_model())

    request = await start_media_generation(
        session, user, "img", "make it night",
        image_url="https://cdn.example.com/in.png",
    )

    # calculate_image_credits(..., is_edit=True): max(ceil(100 * 1.5), 100) = 150
    assert request.estimated_credits == 150
    assert fal.image_calls[0]["image_url"] == "https://cdn.example.com/in.png"


async def test_video_uses_default_duration_of_five_seconds(session, fal):
    user = await _seed(session, _video_model())

    request = await start_media_generation(session, user, "vid", "a bear runs")

    assert request.estimated_credits == 600  # ceil(5/5 * 600)
    assert fal.video_calls == [{
        "model": "vid", "prompt": "a bear runs",
        "duration_seconds": 5, "webhook_url": EXPECTED_WEBHOOK_URL,
    }]


async def test_video_duration_scales_credits_and_is_passed_to_fal(session, fal):
    user = await _seed(session, _video_model(), balance=2000)

    request = await start_media_generation(
        session, user, "vid", "a bear runs", duration_seconds=10, confirm=True
    )

    assert request.estimated_credits == 1200  # ceil(10/5 * 600); >1000 -> нужен confirm
    assert fal.video_calls[0]["duration_seconds"] == 10


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
    user = await _seed(session, _image_model())
    broken = FakeFalClient(error=RuntimeError("fal down"))
    monkeypatch.setattr(mgs, "FalClient", broken)

    with pytest.raises(AIError):
        await start_media_generation(session, user, "img", "a bear")

    [request] = await _request_rows(session)
    assert request.status == RequestStatus.refunded
    assert request.charged_credits == 0
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/services/test_media_generation_service.py -v`
Expected: FAIL (collection error) with `ModuleNotFoundError: No module named 'app.services.media_generation_service'`

- [ ] **Step 3: Write the implementation**

Create `app/services/media_generation_service.py`:

```python
"""Медиа-flow (image/video) поверх движка кредитов -- фаза 3, замена
generation_service.py (PiAPI/DALL-E) на fal.ai.

Отличие от текстового flow (фаза 2): вызов провайдера асинхронный. fal.ai
принимает задачу сразу, а результат доставляет вебхуком (handle_fal_webhook),
поэтому per-user Redis-лок НЕ снимается в конце start_media_generation --
он живёт до обработки вебхука (тот же паттерн, что у старого PiAPI-flow).
Синхронная ошибка ДО успешного submit снимает лок немедленно.

Стоимость считается ТОЛЬКО здесь, на бэкенде: клиентского
credit_cost_override из старого API больше не существует (security-фикс).
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.enums import ModelCategory, RequestStatus
from app.db.models import AIRequest, AiModel, User
from app.redis_client import redis_client
from app.services.ai.base import AIError
from app.services.ai.fal_client import FalClient
from app.services.credit_service import (
    InsufficientBalanceError,
    refund_request,
    reserve_credits,
)
from app.services.keys.api_key_manager import get_key_manager
from app.services.keys.enums import KeyPurpose, Provider
from app.services.pricing import calculate_image_credits, calculate_video_credits

logger = logging.getLogger(__name__)

# Страховочный TTL на медленную видео-генерацию (несколько минут) -- штатно лок
# снимается явно в handle_fal_webhook, не по TTL (как в старом PiAPI-flow).
AI_LOCK_TTL_SECONDS = 900
VIDEO_DEFAULT_DURATION_SECONDS = 5  # дефолт длительности из ТЗ
IMAGE_CONFIRM_THRESHOLD_CREDITS = 300
VIDEO_CONFIRM_THRESHOLD_CREDITS = 1000


class ModelNotFoundError(Exception):
    """model_code отсутствует в каталоге image/video-моделей."""


class RequestInProgressError(Exception):
    user_message = "Дождитесь ответа на предыдущий запрос."


class ConfirmationRequiredError(Exception):
    """Оценка дороже порога (300 image / 1000 video) без confirm=True."""

    def __init__(self, estimated_credits: int):
        self.estimated_credits = estimated_credits
        super().__init__(f"confirmation required: estimated {estimated_credits} credits")


def _webhook_url() -> str:
    return f"{settings.backend_public_url}/api/fal/webhook?secret={settings.fal_webhook_secret}"


async def _get_media_model(session: AsyncSession, model_code: str) -> AiModel:
    model = (
        await session.execute(
            select(AiModel).where(
                AiModel.code == model_code,
                AiModel.category.in_((ModelCategory.image, ModelCategory.video)),
            )
        )
    ).scalar_one_or_none()
    if model is None:
        raise ModelNotFoundError(model_code)
    return model


async def start_media_generation(
    session: AsyncSession,
    user: User,
    model_code: str,
    prompt: str,
    *,
    image_url: str | None = None,
    duration_seconds: int | None = None,
    confirm: bool = False,
) -> AIRequest:
    model = await _get_media_model(session, model_code)

    # category зафиксирована в строке каталога -- клиент её не выбирает.
    # Для image множитель редактирования включается всегда, когда передан
    # image_url, без проверки "поддерживает ли модель edit" (см. спеку фазы 3).
    if model.category == ModelCategory.image:
        estimated = calculate_image_credits(
            model, quantity=1, megapixels=1.0, is_edit=image_url is not None
        )
        threshold = IMAGE_CONFIRM_THRESHOLD_CREDITS
    else:
        estimated = calculate_video_credits(
            model, duration_seconds or VIDEO_DEFAULT_DURATION_SECONDS
        )
        threshold = VIDEO_CONFIRM_THRESHOLD_CREDITS

    if estimated > threshold and not confirm:
        # Ничего не создано, лок ещё не брался.
        raise ConfirmationRequiredError(estimated)

    lock_key = f"ai_lock:{user.id}"
    acquired = await redis_client.set(lock_key, "1", nx=True, ex=AI_LOCK_TTL_SECONDS)
    if not acquired:
        raise RequestInProgressError()

    try:
        request = AIRequest(
            user_id=user.id,
            provider="fal",
            model_code=model.code,
            category=model.category,
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
                provider="fal",
                model_code=model.code,
            )
        except InsufficientBalanceError:
            # Убрать pending-AIRequest вместе с несостоявшимся резервом.
            await session.rollback()
            raise
        request.status = RequestStatus.reserved
        await session.commit()  # резерв фиксируется ДО внешнего HTTP-вызова
    except Exception:
        # Любая синхронная ошибка до submit -- лок снимается сразу.
        await redis_client.delete(lock_key)
        raise

    purpose = KeyPurpose.IMAGE if model.category == ModelCategory.image else KeyPurpose.VIDEO
    try:
        api_key = get_key_manager().get_key(Provider.FAL, purpose)
        client = FalClient(api_key=api_key)
        if model.category == ModelCategory.image:
            fal_request_id = await client.submit_image(
                model, prompt, image_url=image_url, webhook_url=_webhook_url()
            )
        else:
            fal_request_id = await client.submit_video(
                model,
                prompt,
                duration_seconds=duration_seconds or VIDEO_DEFAULT_DURATION_SECONDS,
                webhook_url=_webhook_url(),
            )
    except Exception as exc:
        # Резерв уже закоммичен -- возвращаем его и снимаем лок.
        request.error_message = str(exc)
        await refund_request(session, request, reason=f"fal submit failed: {exc}")
        await session.commit()
        await redis_client.delete(lock_key)
        raise AIError(f"fal submit failed: {exc}") from exc

    request.provider_response_id = fal_request_id
    await session.commit()
    # Лок НЕ снимается: генерация продолжается асинхронно до handle_fal_webhook.
    return request


async def get_generation(session: AsyncSession, user: User, request_id: int) -> AIRequest | None:
    request = await session.get(AIRequest, request_id)
    if request is None or request.user_id != user.id:
        return None
    return request
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/services/test_media_generation_service.py -v`
Expected: PASS (14 tests)

- [ ] **Step 5: Commit**

```bash
git add app/services/media_generation_service.py tests/services/test_media_generation_service.py
git commit -m "feat: add media_generation_service start flow (reserve + fal submit)"
```

---

### Task 5: `media_generation_service` — `handle_fal_webhook` (settle / refund / idempotency)

**Files:**
- Modify: `app/services/media_generation_service.py` (add imports + one function)
- Test: `tests/services/test_media_generation_service.py` (append tests)

**Interfaces:**
- Consumes:
  - Everything Task 4 produced (same file; fixtures `session`, `fake_redis`, `fal`, helpers `_image_model`, `_video_model`, `_seed`, `_request_rows`, `_tx_types`, constant `EXPECTED_WEBHOOK_URL` already exist in the test file)
  - `settle_request(session, request, actual_credits) -> CreditTransaction | None` — requires `request.status == RequestStatus.reserved`, sets `completed` + `charged_credits` + `completed_at` (`app/services/credit_service.py`)
  - `refund_request(session, request, *, reason)` — requires status `reserved`/`completed`, sets `refunded`, `charged_credits = 0`
  - `extract_result_url(payload: dict) -> str | None` (Task 2)
  - `AIRequest.result_url` column (Task 1)
- Produces (used by Task 6): `async def handle_fal_webhook(session: AsyncSession, payload: dict) -> None`

- [ ] **Step 1: Write the failing tests**

In `tests/services/test_media_generation_service.py`, extend the service import to include the new function — change:

```python
from app.services.media_generation_service import (
    ConfirmationRequiredError,
    ModelNotFoundError,
    RequestInProgressError,
    get_generation,
    start_media_generation,
)
```

to:

```python
from app.services.media_generation_service import (
    ConfirmationRequiredError,
    ModelNotFoundError,
    RequestInProgressError,
    get_generation,
    handle_fal_webhook,
    start_media_generation,
)
```

Then append to the end of the file:

```python
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
    user = await _seed(session, _image_model())
    request = await start_media_generation(session, user, "img", "a bear")

    await handle_fal_webhook(
        session, {"request_id": "fal-req-1", "status": "ERROR", "error": "nsfw content"}
    )

    await session.refresh(request)
    assert request.status == RequestStatus.refunded
    assert request.charged_credits == 0
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
    user = await _seed(session, _image_model())
    request = await start_media_generation(session, user, "img", "a bear")

    await handle_fal_webhook(
        session,
        {"request_id": "fal-req-1", "status": "OK", "payload": {"unexpected": True}},
    )

    await session.refresh(request)
    # URL извлечь не удалось -> кредиты за недоставленный результат не списываем
    assert request.status == RequestStatus.refunded
    assert request.charged_credits == 0
    assert request.result_url is None
    assert request.error_message == "fal webhook: could not extract result url"
    fetched = await session.get(User, user.id)
    assert fetched.credits_balance == 1000
    assert fake_redis.deleted == [f"ai_lock:{user.id}"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/services/test_media_generation_service.py -v`
Expected: FAIL (collection error) with `ImportError: cannot import name 'handle_fal_webhook'`

- [ ] **Step 3: Write the implementation**

In `app/services/media_generation_service.py`, update three import lines:

Change `from sqlalchemy import select` to:

```python
from sqlalchemy import select, update
```

Change the fal_client import to:

```python
from app.services.ai.fal_client import FalClient, extract_result_url
```

Change the credit_service import to:

```python
from app.services.credit_service import (
    InsufficientBalanceError,
    refund_request,
    reserve_credits,
    settle_request,
)
```

Then append this function at the end of the file (after `get_generation`):

```python
async def handle_fal_webhook(session: AsyncSession, payload: dict) -> None:
    """Обрабатывает доставку fal-вебхука: {"request_id", "status": "OK"|"ERROR",
    "payload": {...}}.

    Идемпотентность: атомарный UPDATE ... WHERE status=reserved "закрепляет"
    запрос за первой доставкой (тот же приём, что в старом handle_piapi_webhook);
    повторная доставка получает rowcount=0 и выходит, не трогая ни кредиты,
    ни лок. Claim и settle/refund выполняются в ОДНОЙ транзакции: на Postgres
    UPDATE берёт блокировку строки, конкурентная доставка дожидается commit
    и видит уже не-reserved статус.
    """
    fal_request_id = payload.get("request_id")
    if not fal_request_id:
        return

    request = (
        await session.execute(
            select(AIRequest).where(AIRequest.provider_response_id == fal_request_id)
        )
    ).scalar_one_or_none()
    if request is None:
        return  # неизвестный request_id -- не наш запрос

    status = payload.get("status")
    result_payload = payload.get("payload") or {}
    lock_key = f"ai_lock:{request.user_id}"

    if status == "OK":
        result_url = extract_result_url(result_payload)
        claimed = await session.execute(
            update(AIRequest)
            .where(AIRequest.id == request.id, AIRequest.status == RequestStatus.reserved)
            .values(result_url=result_url)
        )
        if claimed.rowcount == 0:
            return  # повторная доставка -- идемпотентный no-op
        try:
            if result_url is None:
                # Форму ответа извлечь не удалось: кредиты за недоставленный
                # результат не списываем. PLACEHOLDER: дополнить
                # fal_client.extract_result_url новой формой и уточнить перед
                # продакшн-запуском.
                request.error_message = "fal webhook: could not extract result url"
                await refund_request(
                    session, request, reason="fal webhook: could not extract result url"
                )
            else:
                # quantity/duration известны на этапе запроса, поэтому
                # actual == estimated == reserved: settle_request штатно вернёт
                # None (без корректирующей транзакции) -- см. спеку фазы 3.
                await settle_request(session, request, request.estimated_credits)
            await session.commit()
        finally:
            await redis_client.delete(lock_key)
    elif status == "ERROR":
        # PLACEHOLDER: точная форма тела ошибки fal не подтверждена (уточнить
        # перед продакшн-запуском); перебираем известных кандидатов.
        error_message = str(
            payload.get("error") or result_payload.get("detail") or "generation failed"
        )
        claimed = await session.execute(
            update(AIRequest)
            .where(AIRequest.id == request.id, AIRequest.status == RequestStatus.reserved)
            .values(error_message=error_message)
        )
        if claimed.rowcount == 0:
            return  # повторная доставка -- идемпотентный no-op
        try:
            await refund_request(session, request, reason=f"fal error: {error_message}")
            await session.commit()
        finally:
            await redis_client.delete(lock_key)
    else:
        logger.warning(
            "fal webhook: unknown status %r for request_id=%s", status, fal_request_id
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/services/test_media_generation_service.py -v`
Expected: PASS (21 tests)

- [ ] **Step 5: Commit**

```bash
git add app/services/media_generation_service.py tests/services/test_media_generation_service.py
git commit -m "feat: settle/refund media generations from fal webhook"
```

---

### Task 6: API surface — rewrite `POST/GET /api/generate`, new `POST /api/fal/webhook`

**Files:**
- Rewrite: `app/api/routes/generate.py` (full replacement of file contents)
- Create: `app/webhooks/fal.py`
- Test: `tests/api/test_generate_routes.py`

**Interfaces:**
- Consumes:
  - `start_media_generation(session, user, model_code, prompt, *, image_url=None, duration_seconds=None, confirm=False) -> AIRequest`, `get_generation(session, user, request_id) -> AIRequest | None`, `handle_fal_webhook(session, payload) -> None`, `ModelNotFoundError`, `RequestInProgressError` (`.user_message`), `ConfirmationRequiredError` (`.estimated_credits`) (Tasks 4–5)
  - `InsufficientBalanceError` (`app/services/credit_service.py`), `AIError` (`app/services/ai/base.py`)
  - `settings.fal_webhook_secret` (Task 3), `get_session` (`app/db/session.py` — webhook opens its own session outside a FastAPI dependency, same as the old piapi webhook), `current_user`/`get_db` (`app/api/deps.py`)
- Produces (used by Task 7's `main.py` wiring):
  - `app.api.routes.generate.router` — `POST /generate`, `GET /generate/{request_id}` (mounted under `/api` prefix by main)
  - `app.webhooks.fal.router` — `POST /api/fal/webhook` (mounted without prefix, path is absolute in the module, same as the old piapi webhook)
  - Pydantic models: `GenerateRequest(model_code: str, prompt: str, image_url: str | None = None, duration_seconds: int | None = None, confirm: bool = False)` — NO `credit_cost_override`; `GenerateResponse(request_id: int, estimated_credits: int)`; `GenerationStatusOut(status: str, result_url: str | None, error_message: str | None, charged_credits: int)`

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_generate_routes.py` (standalone-`FastAPI()` pattern from `tests/api/test_chat_routes.py` — `app.main` is still unimportable this phase):

```python
import os

os.environ.setdefault("BOT_TOKEN", "test-token")
# postgresql+asyncpg:// (не голый postgresql://): app.api.deps -> app.db.session
# строит create_async_engine при импорте модуля -- см. комментарий в
# tests/api/test_chat_routes.py.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test")

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import current_user, get_db
from app.api.routes import generate
from app.config import settings
from app.db.base import Base
from app.db.enums import CostUnit, ModelCategory, ModelProvider, ModelTier, RequestStatus
from app.db.models import AIRequest, AiModel, User
from app.services import media_generation_service as mgs
from app.services.ai.base import AIError
from app.services.credit_service import InsufficientBalanceError
from app.services.media_generation_service import (
    ConfirmationRequiredError,
    ModelNotFoundError,
    RequestInProgressError,
)
from app.webhooks import fal as fal_webhook

# app.main пока неимпортируем (admin/key_healthcheck чинятся в фазах 4-5),
# поэтому собираем минимальное приложение из тестируемых роутеров.
app = FastAPI()
app.include_router(generate.router, prefix="/api")
app.include_router(fal_webhook.router)

_test_user = User(
    id=1, telegram_id=1, username="u", first_name="U", is_admin=False,
    default_model_code=None, credits_balance=1000,
    total_credits_purchased=0, total_credits_spent=0,
)


async def _fake_user():
    return _test_user


class FakeRedis:
    def __init__(self, locked: bool = False):
        self.locked = locked
        self.deleted: list[str] = []

    async def set(self, key, value, nx=False, ex=None):
        return None if self.locked else True

    async def delete(self, key):
        self.deleted.append(key)


class FakeKeyManager:
    def get_key(self, provider, purpose):
        return f"key-{provider.value}-{purpose.value}"


class FakeFalClient:
    """См. tests/services/test_media_generation_service.py: fake -- одновременно
    и фабрика (__call__ возвращает self), и клиент."""

    def __init__(self, request_id: str = "fal-req-1"):
        self.request_id = request_id
        self.image_calls: list[dict] = []
        self.video_calls: list[dict] = []

    def __call__(self, api_key: str):
        return self

    async def submit_image(self, model, prompt, *, image_url=None, webhook_url):
        self.image_calls.append({
            "model": model.code, "prompt": prompt,
            "image_url": image_url, "webhook_url": webhook_url,
        })
        return self.request_id

    async def submit_video(self, model, prompt, *, duration_seconds, webhook_url):
        self.video_calls.append({
            "model": model.code, "prompt": prompt,
            "duration_seconds": duration_seconds, "webhook_url": webhook_url,
        })
        return self.request_id


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


@pytest.fixture
async def real_service(db_sessionmaker, monkeypatch):
    """Интеграционный режим: реальные start_media_generation/handle_fal_webhook,
    фейки только на границах (Redis, fal HTTP, key manager, сессия вебхука)."""
    fal = FakeFalClient()
    monkeypatch.setattr(mgs, "redis_client", FakeRedis())
    monkeypatch.setattr(mgs, "FalClient", fal)
    monkeypatch.setattr(mgs, "get_key_manager", lambda: FakeKeyManager())
    monkeypatch.setattr(settings, "backend_public_url", "https://backend.example.com")
    monkeypatch.setattr(settings, "fal_webhook_secret", "whsec")

    @asynccontextmanager
    async def _test_session():
        async with db_sessionmaker() as s:
            yield s

    # Вебхук открывает СВОЮ сессию через get_session (вне DI) -- подменяем её.
    monkeypatch.setattr(fal_webhook, "get_session", _test_session)

    async with db_sessionmaker() as s:
        s.add(User(id=1, telegram_id=1, username="u", credits_balance=1000))
        s.add(AiModel(
            provider=ModelProvider.fal, category=ModelCategory.image, code="img",
            display_name="IMG", provider_model_id="fal-ai/flux/dev",
            tier=ModelTier.standard, cost_unit=CostUnit.image,
            min_credits=0, recommended_credits=100,
        ))
        await s.commit()
    return fal


def _stub_request() -> AIRequest:
    return AIRequest(
        id=7, user_id=1, provider="fal", model_code="img",
        category=ModelCategory.image, status=RequestStatus.reserved,
        prompt_preview="a bear", estimated_credits=100, reserved_credits=100,
    )


# --- POST /api/generate: контракт и маппинг ошибок (сервис замокан) ---

async def test_generate_success_returns_request_id_and_estimate(client, monkeypatch):
    mock = AsyncMock(return_value=_stub_request())
    monkeypatch.setattr(generate, "start_media_generation", mock)

    response = await client.post("/api/generate", json={"model_code": "img", "prompt": "a bear"})

    assert response.status_code == 200
    assert response.json() == {"request_id": 7, "estimated_credits": 100}
    assert mock.await_args.kwargs == {"image_url": None, "duration_seconds": None, "confirm": False}


async def test_generate_passes_media_params(client, monkeypatch):
    mock = AsyncMock(return_value=_stub_request())
    monkeypatch.setattr(generate, "start_media_generation", mock)

    response = await client.post("/api/generate", json={
        "model_code": "vid", "prompt": "a bear", "image_url": "https://x/in.png",
        "duration_seconds": 10, "confirm": True,
    })

    assert response.status_code == 200
    assert mock.await_args.kwargs == {
        "image_url": "https://x/in.png", "duration_seconds": 10, "confirm": True,
    }


async def test_generate_request_schema_has_no_credit_cost_override():
    # Security-фикс фазы 3: клиентского поля стоимости в схеме нет вообще.
    assert "credit_cost_override" not in generate.GenerateRequest.model_fields


async def test_generate_unknown_model_maps_to_404(client, monkeypatch):
    monkeypatch.setattr(
        generate, "start_media_generation", AsyncMock(side_effect=ModelNotFoundError("nope"))
    )
    response = await client.post("/api/generate", json={"model_code": "nope", "prompt": "hi"})
    assert response.status_code == 404
    assert response.json()["detail"] == "model not found"


async def test_generate_confirmation_required_maps_to_409_with_estimate(client, monkeypatch):
    monkeypatch.setattr(
        generate, "start_media_generation",
        AsyncMock(side_effect=ConfirmationRequiredError(1500)),
    )
    response = await client.post("/api/generate", json={"model_code": "vid", "prompt": "hi"})
    assert response.status_code == 409
    assert response.json() == {"estimated_credits": 1500}  # ровно это тело, без "detail"


async def test_generate_request_in_progress_maps_to_409_detail(client, monkeypatch):
    monkeypatch.setattr(
        generate, "start_media_generation", AsyncMock(side_effect=RequestInProgressError())
    )
    response = await client.post("/api/generate", json={"model_code": "img", "prompt": "hi"})
    assert response.status_code == 409
    payload = response.json()
    assert "estimated_credits" not in payload
    assert payload["detail"] == "Дождитесь ответа на предыдущий запрос."


async def test_generate_insufficient_balance_maps_to_402(client, monkeypatch):
    monkeypatch.setattr(
        generate, "start_media_generation",
        AsyncMock(side_effect=InsufficientBalanceError(balance=5, required=100)),
    )
    response = await client.post("/api/generate", json={"model_code": "img", "prompt": "hi"})
    assert response.status_code == 402
    assert response.json()["detail"] == "Недостаточно кредитов"


async def test_generate_provider_error_maps_to_502(client, monkeypatch):
    monkeypatch.setattr(
        generate, "start_media_generation", AsyncMock(side_effect=AIError("boom"))
    )
    response = await client.post("/api/generate", json={"model_code": "img", "prompt": "hi"})
    assert response.status_code == 502
    assert response.json()["detail"] == "Модель временно недоступна, попробуйте позже"


# --- GET /api/generate/{id} ---

async def test_generate_status_404_for_unknown_request(client, monkeypatch):
    monkeypatch.setattr(generate, "get_generation", AsyncMock(return_value=None))
    response = await client.get("/api/generate/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "request not found"


# --- POST /api/fal/webhook: секрет ---

async def test_fal_webhook_rejects_wrong_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "fal_webhook_secret", "whsec")
    response = await client.post("/api/fal/webhook?secret=wrong", json={})
    assert response.status_code == 403
    assert response.json()["detail"] == "invalid secret"


async def test_fal_webhook_rejects_when_secret_unconfigured(client, monkeypatch):
    monkeypatch.setattr(settings, "fal_webhook_secret", "")
    response = await client.post("/api/fal/webhook?secret=", json={})
    assert response.status_code == 403


# --- интеграционные сценарии (реальный сервис поверх sqlite) ---

async def test_credit_cost_override_field_has_no_effect_on_charge(
    client, db_sessionmaker, real_service
):
    response = await client.post("/api/generate", json={
        "model_code": "img", "prompt": "a bear",
        "credit_cost_override": 1,  # поле старого API: должно полностью игнорироваться
    })

    assert response.status_code == 200
    assert response.json()["estimated_credits"] == 100  # серверный расчёт, не 1
    async with db_sessionmaker() as s:
        [request] = (await s.execute(select(AIRequest))).scalars().all()
        assert request.estimated_credits == 100
        assert request.reserved_credits == 100
        user = await s.get(User, 1)
        assert user.credits_balance == 900  # зарезервировано 100, а не 1


async def test_full_flow_get_returns_result_url_from_db_column(
    client, db_sessionmaker, real_service
):
    create = await client.post("/api/generate", json={"model_code": "img", "prompt": "a bear"})
    assert create.status_code == 200
    request_id = create.json()["request_id"]

    hook = await client.post(
        "/api/fal/webhook?secret=whsec",
        json={
            "request_id": "fal-req-1", "status": "OK",
            "payload": {"images": [{"url": "https://cdn.fal.media/out.png"}]},
        },
    )
    assert hook.status_code == 200
    assert hook.json() == {"ok": True}

    status = await client.get(f"/api/generate/{request_id}")
    assert status.status_code == 200
    assert status.json() == {
        "status": "completed",
        "result_url": "https://cdn.fal.media/out.png",
        "error_message": None,
        "charged_credits": 100,  # реальное поле, не хардкод 0 из старого API
    }
    # Результат живёт в durable-колонке ai_requests.result_url.
    async with db_sessionmaker() as s:
        request = await s.get(AIRequest, request_id)
        assert request.result_url == "https://cdn.fal.media/out.png"


async def test_full_flow_error_webhook_visible_in_status(
    client, db_sessionmaker, real_service
):
    create = await client.post("/api/generate", json={"model_code": "img", "prompt": "a bear"})
    request_id = create.json()["request_id"]

    hook = await client.post(
        "/api/fal/webhook?secret=whsec",
        json={"request_id": "fal-req-1", "status": "ERROR", "error": "nsfw content"},
    )
    assert hook.status_code == 200

    status = await client.get(f"/api/generate/{request_id}")
    assert status.json() == {
        "status": "refunded",
        "result_url": None,
        "error_message": "nsfw content",
        "charged_credits": 0,
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_generate_routes.py -v`
Expected: FAIL (collection error) with `ModuleNotFoundError: No module named 'app.webhooks.fal'`. (The old `app/api/routes/generate.py` still imports fine at this point — it is replaced in Step 3, which is also what gives it the `start_media_generation`/`GenerateRequest` attributes the tests monkeypatch and inspect.)

- [ ] **Step 3: Write the implementation**

Replace the ENTIRE contents of `app/api/routes/generate.py` with:

```python
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_db
from app.db.models import User
from app.services.ai.base import AIError
from app.services.credit_service import InsufficientBalanceError
from app.services.media_generation_service import (
    ConfirmationRequiredError,
    ModelNotFoundError,
    RequestInProgressError,
    get_generation,
    start_media_generation,
)

router = APIRouter(dependencies=[Depends(current_user)])


class GenerateRequest(BaseModel):
    # Security-фикс фазы 3: поля credit_cost_override больше НЕТ -- стоимость
    # считается только на бэкенде (media_generation_service). Неизвестные поля
    # в JSON pydantic молча игнорирует.
    model_code: str
    prompt: str
    image_url: str | None = None         # для image-edit
    duration_seconds: int | None = None  # для video (per-second модели)
    confirm: bool = False


class GenerateResponse(BaseModel):
    request_id: int
    estimated_credits: int


class GenerationStatusOut(BaseModel):
    status: str
    result_url: str | None
    error_message: str | None
    charged_credits: int


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    body: GenerateRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> GenerateResponse | JSONResponse:
    try:
        request = await start_media_generation(
            session, user, body.model_code, body.prompt,
            image_url=body.image_url,
            duration_seconds=body.duration_seconds,
            confirm=body.confirm,
        )
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail="model not found") from exc
    except ConfirmationRequiredError as exc:
        # Тело ровно {"estimated_credits": N} (без "detail") -- конвенция фазы 2
        # (/api/chat): клиент отличает этот 409 от "запрос уже выполняется".
        return JSONResponse(status_code=409, content={"estimated_credits": exc.estimated_credits})
    except RequestInProgressError as exc:
        raise HTTPException(status_code=409, detail=exc.user_message) from exc
    except InsufficientBalanceError as exc:
        raise HTTPException(status_code=402, detail="Недостаточно кредитов") from exc
    except AIError as exc:
        raise HTTPException(
            status_code=502, detail="Модель временно недоступна, попробуйте позже"
        ) from exc

    return GenerateResponse(request_id=request.id, estimated_credits=request.estimated_credits)


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
        result_url=request.result_url,  # durable-колонка ai_requests.result_url
        error_message=request.error_message,
        charged_credits=request.charged_credits,  # реальное списание, не хардкод 0
    )
```

Create `app/webhooks/fal.py` (mirrors the old `app/webhooks/piapi.py` shape):

```python
from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.db.session import get_session
from app.services.media_generation_service import handle_fal_webhook

router = APIRouter()


@router.post("/api/fal/webhook")
async def fal_webhook(request: Request, secret: str = "") -> dict:
    if secret != settings.fal_webhook_secret or not settings.fal_webhook_secret:
        raise HTTPException(status_code=403, detail="invalid secret")

    payload = await request.json()
    async with get_session() as session:
        await handle_fal_webhook(session, payload)

    return {"ok": True}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_generate_routes.py -v`
Expected: PASS (14 tests)

Also confirm phase-2 API tests still pass: `python -m pytest tests/api/ -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add app/api/routes/generate.py app/webhooks/fal.py tests/api/test_generate_routes.py
git commit -m "feat: rewrite /api/generate on fal.ai; remove credit_cost_override"
```

---

### Task 7: Delete the PiAPI/DALL-E pipeline, swap router wiring in `main.py`

**Files:**
- Modify: `app/main.py:17,76`
- Delete: `app/services/ai/piapi_client.py`, `app/services/ai/image_service.py`, `app/webhooks/piapi.py`, `app/services/generation_service.py`, `tests/services/ai/test_piapi_client.py`, `tests/services/keys/test_piapi_key.py`

**Interfaces:**
- Consumes: `app.webhooks.fal.router` (Task 6). `app.api.routes.generate` is already imported in `main.py` line 9 and mounted at line 74 — the module was rewritten in place, so that wiring does not change.
- Produces: a codebase with no PiAPI/DALL-E media code. `PiApiSettings` / `piapi_webhook_secret` in `app/config.py` and `Provider.PIAPI` in `app/services/keys/` stay (explicitly out of scope per spec).

- [ ] **Step 1: Swap the webhook router in `app/main.py`**

Change line 17:

```python
from app.webhooks import piapi as piapi_webhook
```

to:

```python
from app.webhooks import fal as fal_webhook
```

Change line 76:

```python
app.include_router(piapi_webhook.router)
```

to:

```python
app.include_router(fal_webhook.router)
```

- [ ] **Step 2: Delete the six legacy files**

```bash
git rm app/services/ai/piapi_client.py app/services/ai/image_service.py app/webhooks/piapi.py app/services/generation_service.py tests/services/ai/test_piapi_client.py tests/services/keys/test_piapi_key.py
```

- [ ] **Step 3: Verify no dangling references to the deleted modules**

Run:

```bash
grep -rn "piapi_client\|image_service\|handle_piapi_webhook\|ImageProvider\|services.generation_service\|services import generation_service" app tests
```

Expected: no output. (References to `PiApiSettings`/`piapi_webhook_secret`/`PIAPI` inside `app/config.py` and `app/services/keys/` are allowed and intentionally kept — the pattern above does not match them. Do NOT use `python -c "import app.main"` as a check: `app.main` is still unimportable because `admin.py`/`key_healthcheck.py` reference the deleted `ModelConfig`, which is fixed in phases 4–5.)

- [ ] **Step 4: Run the full test suite**

Run: `python -m pytest tests/ -q`
Expected: all tests pass (the two deleted PiAPI test files are gone; everything else — phase 1/2 suites plus the new fal/media/generate suites — is green).

- [ ] **Step 5: Commit**

```bash
git add app/main.py
git commit -m "chore: delete PiAPI/DALL-E pipeline, wire fal webhook router"
```

---

## Spec Coverage Checklist (self-review record)

| Spec section | Covered by |
|---|---|
| Модель данных: `result_url` migration + ORM (`String(1024)`, nullable, durable — не Redis) | Task 1 |
| Модель данных: `estimated == reserved == charged`, settle returns `None` штатно | Task 5 (comment + `test_webhook_ok_settles_and_stores_result_url` asserting only `[reserve]` tx) |
| `FalSettings`/`_PURPOSE_ATTR[Provider.FAL]` не меняются | Verified; no task touches them (Task 4 only consumes) |
| Удаляемые файлы (6 шт.) | Task 7 |
| `fal_client.py`: `submit_image`/`submit_video`, queue.fal.run из `provider_model_id`, тело `{"prompt"}` + `image_url` + `duration` | Task 2 |
| `extract_result_url` (`images[0].url`, `video.url`, PLACEHOLDER для неподтверждённых форм) | Task 2 |
| `webhooks/fal.py`: secret в query, сверка с `settings.fal_webhook_secret` | Tasks 3, 6 |
| `media_generation_service.start_media_generation` (резолв → расчёт → confirm 300/1000 → лок → reserve → submit → reserved+provider_response_id → лок до вебхука) | Task 4 |
| `handle_fal_webhook` (OK→settle, ERROR→refund, снятие лока, идемпотентный атомарный UPDATE WHERE status=reserved) | Task 5 |
| `POST /api/generate` без `credit_cost_override`; `GenerateRequest`/`GenerateResponse` ровно по спеке | Task 6 |
| `GET /api/generate/{id}`: `charged_credits` вместо хардкода `0`, `result_url` из колонки | Task 6 |
| Тесты: fal_client (respx), media service (sqlite: settle/refund/confirm/balance/идемпотентность), API (routes + webhook + «клиент не может задать стоимость») | Tasks 2, 4, 5, 6 |
| Вне рамок: upload/хранилище файлов, фазы 4-6, frontend-next | No task touches them |
