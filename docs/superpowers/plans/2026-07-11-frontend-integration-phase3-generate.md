# Frontend Integration Phase 3 — Generate (image/video) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Третья под-фаза связывания `frontend-next/` с бэкендом credit-system-v2: экраны generate-image/generate-video переезжают с компилируемых заглушек фазы 2 на реальные контракты; бэкенд получает два аддитивных изменения — `GET /api/models?category=` и новый `POST /api/upload/image` (+ статика `/uploads`).

**Architecture:** Бэкенд: параметр `category: ModelCategory = ModelCategory.text` в существующем `list_models` (`app/api/routes/chat.py`) и новый роут-файл `app/api/routes/upload.py` (UploadFile → локальный диск → `{"url": ...}` через `StaticFiles`), регистрация в `app/main.py`. Фронтенд: `client.ts` — `api.models(category)`, `api.uploadImage`, реальные `GenerationStatus`/`api.generate`; полный рерайт обоих generate-экранов по паттерну `pendingConfirmation`-баннера из смёрженного `chat/page.tsx`; удаление мёртвых `AspectRatioSheet.tsx`/`lib/imageCost.ts`. e2e: оба spec-файла обновляются под новые контракты и **реально прогоняются** (перехват `page.route()`, бэкенд не нужен).

**Tech Stack:** Бэкенд: FastAPI + SQLAlchemy 2 async + pytest (`asyncio_mode = auto`, aiosqlite в тестах). Фронтенд: Next.js 16.2.10 (App Router) + React 19.2.4 + TypeScript 5 strict + Tailwind CSS 4 + Playwright 1.61.

**Design spec (единственный источник истины):** `docs/superpowers/specs/2026-07-11-frontend-integration-phase3-generate-design.md`

## Global Constraints

- **Гейты.** Бэкенд-задачи (1–2): `python -m pytest tests/api/ -v` из корня репо (TDD RED→GREEN, тестовые файлы сами выставляют `BOT_TOKEN`/`DATABASE_URL` через `os.environ.setdefault` до импорта `app.*`). Фронтенд-задачи (3–5): быстрая проверка `npx tsc --noEmit`, канонический гейт `npm run build` из `frontend-next/` — ожидаемый итог **12 роутов** (как в фазах 1–2). e2e-задача (6): реальный прогон `npx playwright test generate-image.spec.ts generate-video.spec.ts` — **в отличие от фаз 1–2 это обязательный гейт**: оба теста самодостаточны (`page.route()`-перехват / DOM-only), бэкенд и докер не нужны, предсуществующий баг мока Telegram (`[[ai_hub_bot_e2e_mock_bug]]`) их не блокирует.
- **Миграций НЕТ.** Оба бэкенд-изменения аддитивны, схема БД не меняется — никаких Alembic-ревизий.
- **Задачи 3–5 — один атомарный typecheck-юнит** (прецедент фазы 2): после Task 3 `npx tsc --noEmit` ОЖИДАЕМО красный с выверенным списком файлов, после Task 4 список сужается до одного файла, зелёным он обязан стать ровно в конце Task 5. Промежуточные коммиты — `wip(frontend)`, это осознанно.
- **Порядок: сначала бэкенд (Tasks 1–2), потом фронтенд (Tasks 3–6)** — фронтенд-код зависит от контрактов `GET /api/models?category=` и `POST /api/upload/image`.
- **Имена контракта одинаковы на обеих сторонах:** query-параметр называется `category` и в роуте (`category: ModelCategory`), и в клиенте (`/api/models?category=${category}`); ответ upload — ровно `{"url": string}` (`UploadResponse.url` ↔ `api.uploadImage(): Promise<{ url: string }>`); лимит 30 МБ — тот же, что уже проверяет `PhotoUploadBox.tsx` (`MAX_SIZE_BYTES = 30 * 1024 * 1024`).
- **Невалидный `category` → 422, не 400.** Спека в скобках говорит «400 на невалидное значение», но FastAPI на невалидный enum-query возвращает `RequestValidationError` → **422**; тест закрепляет фактическое поведение (задокументированное отступление от спеки).
- **НЕ трогать:** `app/api/routes/generate.py` (`GenerateRequest`/`GenerateResponse`/`GenerationStatusOut` — только референс контракта), `tests/api/test_generate_routes.py`, `frontend-next/src/components/PhotoUploadBox.tsx` (используется как есть: `{photos, onChange}`), `frontend-next/src/components/chat/ModelPicker.tsx`, `frontend-next/src/app/chat/page.tsx` (образец паттерна, не правится), `mock-telegram.ts`, `playwright.config.ts`, `adminApi`/`AdminModelOut`, легаси-тип `ModelCategory` в `client.ts:48` (`"fast" | "medium" | "premium" | "image" | "video"` — его используют `ToolOut.recommended_category` и `AdminModelOut.category`, вне скоупа; для параметра `api.models` используется inline-union, НЕ этот тип).
- **Playwright glob:** экран video теперь ходит на `/api/models?category=video`; паттерн `"**/api/models"` query-string НЕ матчит (glob должен покрыть URL целиком), а `?` в glob — метасимвол и буквально в паттерн не вписывается. Использовать `"**/api/models*"` (хвостовая `*` покрывает и пустую строку, и `?category=...`). `"**/api/generate"` при этом НЕ матчит `/api/generate/1` — существующее поведение сохраняется.
- **`onClick={() => generate()}`, НЕ `onClick={generate}`** — после рерайта `generate` принимает `confirm?: boolean`; прямая передача в `onClick` подсунет `MouseEvent` первым аргументом (правило фазы 2 для `send`).
- **Стиль баннера подтверждения** — байт-в-байт классы из смёрженного `chat/page.tsx:120-133`: контейнер `relative overflow-hidden rounded-lg border border-border-soft bg-surface p-[14px]` + полоска `absolute inset-x-0 top-0 h-[3px] bg-[image:var(--brand-gradient)]`, кнопки «Отправить» (дефолтный `filled`) / «Отмена» (`mode="gray"`), обе `size="s" stretched`. Текст: `Примерная стоимость: {N} кредитов. Продолжить?`. Новых визуальных стилей не выдумывать.
- **`uploads/` попадает в `.gitignore`** (Task 2) — рабочие файлы загрузок не коммитятся.
- **Next.js 16 (`frontend-next/AGENTS.md`):** конвенции могут отличаться от training data; эта фаза не создаёт новых роутов — сверяться с `node_modules/next/dist/docs/` только при ошибке сборки, не похожей на TS-ошибку типов.
- Номера строк актуальны на master `1ed11d3` (2026-07-11). Внутри задачи более ранние правки сдвигают последующие строки — ориентироваться на якорные сниппеты.
- **Критерий готовности фазы:** `python -m pytest tests/api/ -v` зелёный; `npx tsc --noEmit` и `npm run build` зелёные (12 роутов); `npx playwright test generate-image.spec.ts generate-video.spec.ts` — 2 passed; ручной smoke generate-flow передан пользователю с инструкцией (единственная часть, требующая реального бэкенда).

## File Structure

| Файл | Действие |
|---|---|
| `app/api/routes/chat.py:50-51` | сигнатура `list_models` + фильтр по `category` — Task 1 |
| `tests/api/test_chat_routes.py` | 2 новых теста на `?category=` — Task 1 |
| `app/api/routes/upload.py` | НОВЫЙ: `POST /upload/image` — Task 2 |
| `tests/api/test_upload_routes.py` | НОВЫЙ: 5 тестов (200/413/422/расширения/уникальность) — Task 2 |
| `app/main.py:9,7,74` | импорт `upload` + `StaticFiles` + регистрация — Task 2 |
| `.gitignore` | строка `uploads/` — Task 2 |
| `frontend-next/src/api/client.ts` | `api.models(category)`, `GenerationStatus`, `api.generate`, `api.uploadImage`, минус `ImageAspect`/`ImageResolution` — Task 3 |
| `frontend-next/src/components/AspectRatioSheet.tsx` | УДАЛИТЬ — Task 4 |
| `frontend-next/src/lib/imageCost.ts` | УДАЛИТЬ — Task 4 |
| `frontend-next/src/app/generate-image/page.tsx` | рерайт целиком — Task 4 |
| `frontend-next/src/app/generate-video/page.tsx` | рерайт целиком — Task 5 |
| `frontend-next/e2e/generate-image.spec.ts` | новая версия + реальный прогон — Task 6 |
| `frontend-next/e2e/generate-video.spec.ts` | новая версия + реальный прогон — Task 6 |
| — | финальная верификация: pytest + чистый build + playwright + `import app.main` + ручной smoke — Task 7 |

---

### Task 1: Бэкенд — `GET /api/models` получает query-параметр `category`

**Files:**
- Modify: `app/api/routes/chat.py:50-61` (роут `list_models`)
- Test: `tests/api/test_chat_routes.py` (добавить после `test_models_returns_visible_active_text_models_sorted`, строка ~119)

**Interfaces:**
- Consumes: `ModelCategory` (`app/db/enums.py:26-29`: `text`/`image`/`video`) — уже импортирован в `chat.py:8`; fixture `client`/`db_sessionmaker` и хелпер `_text_model(..., category=...)` из `tests/api/test_chat_routes.py:59-89` (уже принимает `category`).
- Produces (Task 3 полагается на это): `GET /api/models?category=image|video|text` — тот же `list[ModelOut]` (`code/display_name/tier/min_credits/recommended_credits`), отфильтрованный по категории; без параметра — прежнее поведение (`text`), существующий вызов из Chat не ломается. Невалидное значение → 422.

- [ ] **Step 1: Написать падающие тесты**

В `tests/api/test_chat_routes.py`, сразу после `test_models_returns_visible_active_text_models_sorted` (после строки 119, перед секцией `# --- POST /api/chat ---`):

```python
async def test_models_category_image_returns_only_visible_active_image_models(client, db_sessionmaker):
    async with db_sessionmaker() as s:
        s.add_all([
            _text_model("txt", sort_order=10),
            _text_model("img_b", sort_order=30, category=ModelCategory.image),
            _text_model("img_a", sort_order=20, category=ModelCategory.image, tier=ModelTier.standard),
            _text_model("img_hidden", sort_order=40, category=ModelCategory.image, is_visible=False),
            _text_model("vid", sort_order=50, category=ModelCategory.video),
        ])
        await s.commit()

    response = await client.get("/api/models", params={"category": "image"})

    assert response.status_code == 200
    payload = response.json()
    assert [m["code"] for m in payload] == ["img_a", "img_b"]  # sort_order, text/video/hidden отфильтрованы
    assert payload[0] == {
        "code": "img_a",
        "display_name": "IMG_A",
        "tier": "standard",
        "min_credits": 3,
        "recommended_credits": 5,
    }


async def test_models_invalid_category_is_422(client):
    # FastAPI валидирует enum-query сам: невалидное значение -> 422
    # (спека в скобках говорит "400", фактическое поведение FastAPI -- 422).
    response = await client.get("/api/models", params={"category": "audio"})
    assert response.status_code == 422
```

- [ ] **Step 2: Убедиться, что тесты падают (RED)**

Run: `python -m pytest tests/api/test_chat_routes.py -v -k "category"`

Expected: `test_models_category_image_returns_only_visible_active_image_models` FAIL — параметр сейчас игнорируется, роут возвращает text-модель `txt` (assert по списку `code` не совпадает). `test_models_invalid_category_is_422` тоже FAIL (200 вместо 422, параметр не объявлен).

- [ ] **Step 3: Реализация — параметр `category` в `list_models`**

В `app/api/routes/chat.py` текущий код (строки 50–61):

```python
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
```

заменить на:

```python
@router.get("/models", response_model=list[ModelOut])
async def list_models(
    category: ModelCategory = ModelCategory.text,
    session: AsyncSession = Depends(get_db),
) -> list[ModelOut]:
    models = (
        (
            await session.execute(
                select(AiModel)
                .where(
                    AiModel.category == category,
                    AiModel.is_active.is_(True),
                    AiModel.is_visible.is_(True),
                )
                .order_by(AiModel.sort_order)
            )
        )
```

Остальное тело роута (`.scalars().all()`, комментарий про `provider_model_id`, list comprehension с `ModelOut`) — без изменений. `ModelOut` не меняется: поля одинаково осмысленны для всех трёх категорий (спека).

- [ ] **Step 4: Убедиться, что тесты зелёные и ничего не сломалось (GREEN)**

Run: `python -m pytest tests/api/test_chat_routes.py -v`

Expected: PASS все, включая существующий `test_models_returns_visible_active_text_models_sorted` (дефолт `text` сохранён — запрос без параметра отдаёт только text-модели).

- [ ] **Step 5: Commit**

```bash
git add app/api/routes/chat.py tests/api/test_chat_routes.py
git commit -m "feat(api): GET /api/models -- опциональный query-параметр category (text по умолчанию)"
```

---

### Task 2: Бэкенд — новый `POST /api/upload/image` + статика `/uploads` в `app/main.py`

**Files:**
- Create: `app/api/routes/upload.py`
- Create: `tests/api/test_upload_routes.py`
- Modify: `app/main.py:7,9,74` (импорт `StaticFiles`, импорт `upload`, регистрация)
- Modify: `.gitignore` (строка `uploads/`)

**Interfaces:**
- Consumes: `current_user` (`app/api/deps.py:13-36`, router-level dependency — как в `chat.py:27`/`generate.py:25`); `settings.backend_public_url` (`app/config.py:133`, в тестах monkeypatch'ится — прецедент `tests/api/test_generate_routes.py:171`).
- Produces (Task 3 полагается на ТОЧНУЮ форму): `POST /api/upload/image` c multipart-полем `file` → `200 {"url": "<backend_public_url>/uploads/<uuid>.<ext>"}`; `413 {"detail": "Файл больше 30 МБ"}`; `422 {"detail": "Поддерживаются только JPEG/PNG/WEBP"}`. Файл читается по URL через `app.mount("/uploads", StaticFiles(...))`.

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/api/test_upload_routes.py` целиком:

```python
import os

os.environ.setdefault("BOT_TOKEN", "123456:TEST-token")
# postgresql+asyncpg:// (не голый postgresql://): app.api.deps -> app.db.session
# строит create_async_engine при импорте модуля -- см. комментарий в
# tests/api/test_chat_routes.py.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test")

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import current_user
from app.api.routes import upload
from app.config import settings
from app.db.models import User

# Минимальное приложение из тестируемого роутера (конвенция test_chat_routes.py).
app = FastAPI()
app.include_router(upload.router, prefix="/api")

_test_user = User(
    id=1, telegram_id=1, username="u", first_name="U", is_admin=False,
    default_model_code=None, credits_balance=100,
    total_credits_purchased=0, total_credits_spent=0,
)


async def _fake_user():
    return _test_user


@pytest.fixture
async def client(tmp_path, monkeypatch):
    # Файлы пишем во временную директорию pytest, а не в рабочий uploads/.
    # get_db переопределять не нужно: current_user переопределён целиком,
    # его под-зависимости FastAPI не резолвит.
    monkeypatch.setattr(upload, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(settings, "backend_public_url", "https://backend.example.com")
    app.dependency_overrides[current_user] = _fake_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_upload_image_saves_file_and_returns_public_url(client, tmp_path):
    data = b"\xff\xd8\xff fake-jpeg-bytes"

    response = await client.post(
        "/api/upload/image", files={"file": ("cat.jpg", data, "image/jpeg")},
    )

    assert response.status_code == 200
    url = response.json()["url"]
    assert url.startswith("https://backend.example.com/uploads/")
    filename = url.rsplit("/", 1)[1]
    assert filename.endswith(".jpg")
    # Файл реально лежит на диске с тем же содержимым (его отдаст StaticFiles).
    assert (tmp_path / filename).read_bytes() == data


async def test_upload_image_maps_content_type_to_extension(client):
    for content_type, ext in (("image/png", "png"), ("image/webp", "webp")):
        response = await client.post(
            "/api/upload/image", files={"file": ("x", b"data", content_type)},
        )
        assert response.status_code == 200
        assert response.json()["url"].endswith("." + ext)


async def test_upload_image_generates_unique_filenames(client):
    r1 = await client.post("/api/upload/image", files={"file": ("a.png", b"one", "image/png")})
    r2 = await client.post("/api/upload/image", files={"file": ("a.png", b"two", "image/png")})
    assert r1.json()["url"] != r2.json()["url"]  # uuid, не имя из запроса


async def test_upload_image_rejects_oversized_file_with_413(client):
    big = b"x" * (30 * 1024 * 1024 + 1)  # ровно на байт больше лимита PhotoUploadBox
    response = await client.post(
        "/api/upload/image", files={"file": ("big.png", big, "image/png")},
    )
    assert response.status_code == 413
    assert response.json()["detail"] == "Файл больше 30 МБ"


async def test_upload_image_rejects_wrong_content_type_with_422(client):
    response = await client.post(
        "/api/upload/image", files={"file": ("x.gif", b"GIF89a", "image/gif")},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Поддерживаются только JPEG/PNG/WEBP"
```

- [ ] **Step 2: Убедиться, что тесты падают (RED)**

Run: `python -m pytest tests/api/test_upload_routes.py -v`

Expected: FAIL на этапе сборки — `ImportError: cannot import name 'upload' from 'app.api.routes'` (модуля ещё нет).

- [ ] **Step 3: Реализация — `app/api/routes/upload.py`**

Создать файл целиком (сниппет из спеки, 1:1):

```python
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.deps import current_user
from app.config import settings

router = APIRouter(dependencies=[Depends(current_user)])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_UPLOAD_BYTES = 30 * 1024 * 1024  # тот же лимит, что уже проверяет PhotoUploadBox.tsx
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


class UploadResponse(BaseModel):
    url: str


@router.post("/upload/image", response_model=UploadResponse)
async def upload_image(file: UploadFile) -> UploadResponse:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="Поддерживаются только JPEG/PNG/WEBP")

    # Чтение целиком в память приемлемо при лимите 30 МБ (спека) --
    # стриминговая проверка для этого объёма не нужна.
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Файл больше 30 МБ")

    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[file.content_type]
    filename = f"{uuid.uuid4().hex}.{ext}"
    (UPLOAD_DIR / filename).write_bytes(data)

    # Файл живёт на локальном диске (эфемерно на Render) -- нужен только на
    # время одного запроса к fal.ai, персистентность не требуется (спека).
    return UploadResponse(url=f"{settings.backend_public_url}/uploads/{filename}")
```

- [ ] **Step 4: Убедиться, что тесты зелёные (GREEN)**

Run: `python -m pytest tests/api/test_upload_routes.py -v`

Expected: PASS все 5.

- [ ] **Step 5: Регистрация в `app/main.py`**

Три точечные правки.

1. Строка 7 — текущий код:

```python
from fastapi.responses import HTMLResponse
```

заменить на:

```python
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
```

2. Строка 9 (после правки выше — строка 10) — текущий код:

```python
from app.api.routes import admin, banners, chat, generate, me, payments, referral, tools
```

заменить на (алфавитный порядок):

```python
from app.api.routes import admin, banners, chat, generate, me, payments, referral, tools, upload
```

3. После `app.include_router(generate.router, prefix="/api")` (строка 74, последняя перед вебхуками `yookassa_webhook`/`fal_webhook`) добавить:

```python
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.include_router(upload.router, prefix="/api")
```

`StaticFiles(directory="uploads")` требует существующей директории на момент выполнения — её создаёт `UPLOAD_DIR.mkdir(exist_ok=True)` при импорте `upload` (строка импорта роутеров идёт раньше `app.mount`), поэтому порядок корректен.

- [ ] **Step 6: `.gitignore` — не коммитить загруженные файлы**

В `.gitignore` после строки `frontend/dist/` добавить:

```
uploads/
```

- [ ] **Step 7: Проверить импортируемость app.main и полную регрессию API-тестов**

Run (PowerShell, из корня репо):

```powershell
python -c "import os; os.environ.setdefault('BOT_TOKEN','123456:TEST-token'); os.environ.setdefault('DATABASE_URL','postgresql+asyncpg://test'); import app.main; print('ok:', [r.path for r in app.main.app.routes if 'upload' in r.path])"
python -m pytest tests/api/ -v
```

Expected: первая команда печатает `ok: ['/api/upload/image']` (mount `/uploads` — отдельный тип Route, главное — отсутствие исключений при импорте, т.е. StaticFiles нашёл директорию); pytest — PASS все.

- [ ] **Step 8: Commit**

```bash
git add app/api/routes/upload.py tests/api/test_upload_routes.py app/main.py .gitignore
git commit -m "feat(api): POST /api/upload/image + статика /uploads (локальный диск, лимит 30 МБ)"
```

---

### Task 3: `client.ts` — `api.models(category)`, `api.uploadImage`, реальные `GenerationStatus`/`api.generate`, минус `ImageAspect`/`ImageResolution`

**Files:**
- Modify: `frontend-next/src/api/client.ts:75-94` (типы), `:156` (`api.models`), `:163-173` (`api.generate`/`generationStatus` + новый `uploadImage`)

**Interfaces:**
- Consumes: контракты бэкенда — `GET /api/models?category=` (Task 1), `POST /api/upload/image` → `{"url": string}` (Task 2), `POST /api/generate` (`app/api/routes/generate.py:28-41`: `model_code/prompt/image_url/duration_seconds/confirm` → `{request_id, estimated_credits}`; поля `credit_cost_override` в схеме больше нет — security-фикс), `GET /api/generate/{id}` (`generate.py:44-48`: `status` — значение `RequestStatus` из `app/db/enums.py:48-54`, `result_url`, `error_message`, `charged_credits`); существующий `ConfirmationRequiredError` в `request()` (`client.ts:14-46`, фаза 2) — переиспользуется как задумано, НЕ меняется.
- Produces (Tasks 4–5 полагаются на ТОЧНЫЕ имена): `api.models(category?: "text" | "image" | "video")` (дефолт `"text"` — вызов `api.models()` из `ModelPicker` не меняется); `api.uploadImage(file: File): Promise<{ url: string }>`; `api.generate(modelCode: string, prompt: string, imageUrl?: string, durationSeconds?: number, confirm?: boolean): Promise<{ request_id: number; estimated_credits: number }>`; `GenerationStatus.status: "pending" | "reserved" | "processing" | "completed" | "failed" | "refunded"`, `.charged_credits: number`. Типов `ImageAspect`/`ImageResolution` больше НЕТ.

- [ ] **Step 1: `api.models` с параметром `category`**

Текущий код (`frontend-next/src/api/client.ts`, строка 156):

```ts
  models: () => request<ModelOut[]>("/api/models"),
```

заменить на:

```ts
  models: (category: "text" | "image" | "video" = "text") =>
    request<ModelOut[]>(`/api/models?category=${category}`),
```

(Inline-union, НЕ легаси-тип `ModelCategory` со строки 48 — тот описывает старые значения `fast/medium/premium/...` и принадлежит `ToolOut`/`AdminModelOut`, вне скоупа.)

- [ ] **Step 2: Удалить `ImageAspect`/`ImageResolution`, привести `GenerationStatus` к реальному `RequestStatus`**

Текущий код (`frontend-next/src/api/client.ts`, строки 75–94):

```ts
export type ImageAspect =
  | "auto"
  | "1:1"
  | "3:2"
  | "2:3"
  | "4:3"
  | "3:4"
  | "4:5"
  | "5:4"
  | "9:16"
  | "16:9"
  | "21:9";
export type ImageResolution = "1k" | "2k" | "4k";

export interface GenerationStatus {
  status: "processing" | "success" | "error";
  result_url: string | null;
  error_message: string | null;
  credit_cost: number;
}
```

заменить целиком на (1:1 с `GenerationStatusOut` + `RequestStatus` бэкенда):

```ts
export interface GenerationStatus {
  status: "pending" | "reserved" | "processing" | "completed" | "failed" | "refunded";
  result_url: string | null;
  error_message: string | null;
  charged_credits: number;
}
```

- [ ] **Step 3: `api.generate` по реальному `GenerateRequest` + новый `api.uploadImage`**

Текущий код (`frontend-next/src/api/client.ts`, строки 163–173):

```ts
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

заменить на:

```ts
  generate: (modelCode: string, prompt: string, imageUrl?: string, durationSeconds?: number, confirm = false) =>
    request<{ request_id: number; estimated_credits: number }>("/api/generate", {
      method: "POST",
      body: JSON.stringify({
        model_code: modelCode,
        prompt,
        image_url: imageUrl ?? null,
        duration_seconds: durationSeconds ?? null,
        confirm,
      }),
    }),
  generationStatus: (requestId: number) => request<GenerationStatus>(`/api/generate/${requestId}`),
  uploadImage: async (file: File): Promise<{ url: string }> => {
    // НЕ через общий request(): для FormData браузер сам проставляет
    // Content-Type с правильным boundary, а общий хелпер жёстко шлёт
    // application/json.
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_BASE_URL}/api/upload/image`, {
      method: "POST",
      headers: { "X-Telegram-Init-Data": getInitData() },
      body: form,
    });
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
      throw new ApiError(res.status, typeof body.detail === "string" ? body.detail : res.statusText);
    }
    return res.json() as Promise<{ url: string }>;
  },
```

(`credit_cost_override` удалён — поля нет в `GenerateRequest` с security-фикса; `estimated_credits` в ответе нужен формально по контракту, баннер подтверждения берёт сумму из `ConfirmationRequiredError.estimatedCredits`.)

- [ ] **Step 4: Проверить, что сломались ТОЛЬКО ожидаемые потребители (красный прогон)**

Run (из `frontend-next/`): `npx tsc --noEmit`

Expected: FAIL, ошибки ТОЛЬКО в четырёх файлах (список выверен grep'ом по master `1ed11d3`):
- `src/app/generate-image/page.tsx` — импорт `ImageAspect`/`ImageResolution` (строка 13, TS2305), тип 3-го аргумента `api.generate` (строки 73–77: объект вместо `string | undefined`), сравнения `status.status === "success"`/`"error"` (строки 82, 87, TS2367);
- `src/app/generate-video/page.tsx` — сравнения `"success"`/`"error"` (строки 54, 59, TS2367);
- `src/components/AspectRatioSheet.tsx` — импорт `ImageAspect` (строка 4, TS2305);
- `src/lib/imageCost.ts` — импорт `ImageAspect`/`ImageResolution` (строка 1, TS2305).

Если ошибки есть в других файлах `src/` — СТОП, разобрать расхождение до продолжения. (Шум от stale-типов в `.next/` лечится `Remove-Item -Recurse -Force .next`.)

- [ ] **Step 5: Промежуточный коммит (typecheck осознанно красный до Task 5)**

Из корня репо:

```bash
git add frontend-next/src/api/client.ts
git commit -m "wip(frontend): client.ts под generate-контракты v2 -- api.models(category), api.uploadImage, реальные GenerationStatus/api.generate (typecheck красный до починки generate-экранов)"
```

---

### Task 4: Удаление `AspectRatioSheet.tsx`/`lib/imageCost.ts` + рерайт `generate-image/page.tsx`

**Files:**
- Delete: `frontend-next/src/components/AspectRatioSheet.tsx`
- Delete: `frontend-next/src/lib/imageCost.ts`
- Modify: `frontend-next/src/app/generate-image/page.tsx` (переписывается целиком)

**Interfaces:**
- Consumes: `api.models("image")`, `api.uploadImage(file).url`, `api.generate(modelCode, prompt, imageUrl, undefined, confirm)`, `GenerationStatus.status` (значения `completed`/`failed`/`refunded`/остальные), `ConfirmationRequiredError.estimatedCredits` — всё из Task 3; `PhotoUploadBox` (`{photos: File[], onChange}` — НЕ трогается, `frontend-next/src/components/PhotoUploadBox.tsx:8-11`); паттерн `pendingConfirmation`-баннера из `chat/page.tsx:21-25,73-77,119-134` (образец, не правится); `useMe`, `haptic`, `cn`, UI-примитивы `Button/Cell/List/Section/Sheet/Spinner/Textarea` — без изменений.
- Produces (Task 6 полагается на ТОЧНЫЙ отображаемый текст): плейсхолдер `Опишите, что хотите создать` (байт-в-байт как сейчас), кнопка нижней панели с текстом `✨ Generate` (+ `· {N} 💎` при выбранной модели), баннер `Примерная стоимость: {N} кредитов. Продолжить?` с кнопками «Отправить»/«Отмена». Grep по `src/` больше не находит `AspectRatioSheet`, `imageCost`, `ImageAspect`, `ImageResolution`, `isDalle3`.

- [ ] **Step 1: Удалить оба мёртвых файла**

Из корня репо:

```bash
git rm frontend-next/src/components/AspectRatioSheet.tsx frontend-next/src/lib/imageCost.ts
```

(Единственный их потребитель — `generate-image/page.tsx`, переписываемый в Step 2; проверено grep'ом: `ImageAspect|ImageResolution|AspectRatioSheet|imageCost` встречаются только в этих трёх файлах и в `client.ts`, уже почищенном в Task 3.)

- [ ] **Step 2: Переписать `generate-image/page.tsx` целиком**

Заменить всё содержимое `frontend-next/src/app/generate-image/page.tsx` на:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Cell } from "@/components/ui/cell";
import { List } from "@/components/ui/list";
import { Section } from "@/components/ui/section";
import { Sheet } from "@/components/ui/sheet";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { ApiError, ConfirmationRequiredError, api, type ModelOut } from "@/api/client";
import PhotoUploadBox from "@/components/PhotoUploadBox";
import { useMe } from "@/context/MeContext";
import { haptic } from "@/lib/telegram";
import { cn } from "@/lib/cn";

const POLL_INTERVAL_MS = 2000;
const POLL_ATTEMPTS = 60;

interface PendingConfirmation {
  prompt: string;
  modelCode: string;
  imageUrl: string | undefined;
  estimatedCredits: number;
}

export default function GenerateImage() {
  const router = useRouter();
  const { me } = useMe();
  const [models, setModels] = useState<ModelOut[] | null>(null);
  const [model, setModel] = useState<ModelOut | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [photos, setPhotos] = useState<File[]>([]);
  const [prompt, setPrompt] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);

  useEffect(() => {
    api
      .models("image")
      .then((list) => {
        setModels(list);
        setModel((prev) => prev ?? list[0] ?? null);
      })
      .catch(() => setModels([]));
  }, []);

  const cost = model?.recommended_credits ?? 0;

  async function generate(confirm = false) {
    let question: string;
    let modelCode: string;
    let imageUrl: string | undefined;

    if (confirm) {
      // Повторная отправка после баннера: фото уже загружено при первой
      // попытке (файл лежит на бэкенде), повторный upload не нужен --
      // переиспользуем сохранённый url.
      if (!pendingConfirmation || generating) return;
      question = pendingConfirmation.prompt;
      modelCode = pendingConfirmation.modelCode;
      imageUrl = pendingConfirmation.imageUrl;
      setPendingConfirmation(null);
    } else {
      if (!model || !prompt.trim() || generating) return;
      question = prompt.trim();
      modelCode = model.code;
      // Новый запуск отменяет неподтверждённый предыдущий.
      setPendingConfirmation(null);
    }

    setGenerating(true);
    setError("");
    setResultUrl(null);

    try {
      if (!confirm && photos.length > 0) {
        // Бэкенд принимает один image_url -- используется только ПЕРВОЕ фото
        // (известное упрощение спеки; PhotoUploadBox не трогаем).
        imageUrl = (await api.uploadImage(photos[0])).url;
      }

      const { request_id } = await api.generate(modelCode, question, imageUrl, undefined, confirm);

      for (let i = 0; i < POLL_ATTEMPTS; i++) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        const status = await api.generationStatus(request_id);
        if (status.status === "completed") {
          setResultUrl(status.result_url);
          haptic("medium");
          return;
        }
        if (status.status === "failed" || status.status === "refunded") {
          setError(status.error_message ?? "Не удалось сгенерировать изображение");
          return;
        }
        // pending / reserved / processing -- продолжаем поллинг.
      }
      setError("Генерация занимает дольше обычного, попробуйте позже");
    } catch (err) {
      if (err instanceof ConfirmationRequiredError) {
        // Не ошибка: показываем баннер, повторный вызов уйдёт с confirm=true.
        setPendingConfirmation({ prompt: question, modelCode, imageUrl, estimatedCredits: err.estimatedCredits });
      } else {
        setError(err instanceof ApiError ? err.message : "Не удалось сгенерировать изображение");
      }
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
        <h2 className="heading-font mr-[22px] flex-1 text-center text-lg font-bold">Generate Image</h2>
      </div>

      <div className="flex flex-col gap-3.5 px-4">
        <div className="rounded-lg border border-border-soft bg-surface p-3.5">
          <PhotoUploadBox photos={photos} onChange={setPhotos} />
        </div>

        <div className="relative rounded-lg border border-border-soft bg-surface p-3.5">
          <Textarea
            placeholder="Опишите, что хотите создать"
            rows={expanded ? 10 : 4}
            maxLength={6000}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            className="resize-none"
          />
          <div className="mt-1.5 flex items-center justify-end gap-2">
            <span className="text-xs text-foreground-muted">{prompt.length}/6000</span>
            <button
              onClick={() => setExpanded((v) => !v)}
              aria-label={expanded ? "Свернуть поле" : "Развернуть поле"}
              className="press-scale border-none bg-none p-0 text-base text-foreground-muted"
            >
              ⤢
            </button>
          </div>
        </div>

        {model && (
          <div
            onClick={() => models && models.length > 1 && setPickerOpen(true)}
            className={cn(
              "press-scale flex items-center gap-3 rounded-lg border border-border-soft bg-surface p-3.5",
              models && models.length > 1 ? "cursor-pointer" : "cursor-default",
            )}
          >
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[image:var(--brand-gradient)] text-lg">
              🎨
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[15px] font-semibold">{model.display_name}</div>
              <div className="text-xs text-foreground-muted">Генерация изображений</div>
            </div>
            <div className="flex shrink-0 items-center gap-1 text-[13px] text-foreground-muted">
              от {model.min_credits} 💎
              {models && models.length > 1 && <span className="ml-0.5">›</span>}
            </div>
          </div>
        )}

        {generating && (
          <div className="flex justify-center p-6">
            <Spinner size="m" />
          </div>
        )}

        {error && <div className="text-center text-[13px] text-red-400">{error}</div>}

        {pendingConfirmation && (
          <div className="relative overflow-hidden rounded-lg border border-border-soft bg-surface p-[14px]">
            <div className="absolute inset-x-0 top-0 h-[3px] bg-[image:var(--brand-gradient)]" />
            <div className="text-[13px]">
              Примерная стоимость: {pendingConfirmation.estimatedCredits} кредитов. Продолжить?
            </div>
            <div className="mt-2.5 flex gap-2">
              <Button size="s" stretched onClick={() => generate(true)}>
                Отправить
              </Button>
              <Button size="s" stretched mode="gray" onClick={() => setPendingConfirmation(null)}>
                Отмена
              </Button>
            </div>
          </div>
        )}

        {resultUrl && (
          <div className="rounded-lg border border-border-soft bg-surface p-3">
            <img src={resultUrl} alt="" className="block w-full rounded-[14px]" />
          </div>
        )}
      </div>

      <div className="fixed inset-x-0 bottom-0 bg-[rgba(10,10,12,0.85)] p-4 backdrop-blur-xl">
        <div className="mb-2 text-center text-xs text-foreground-muted">Баланс: {me?.credits_balance ?? 0} 💎</div>
        <Button
          mode="filled"
          stretched
          disabled={!prompt.trim() || generating || !model}
          onClick={() => generate()}
          className="py-3.5 text-base"
          style={{ opacity: prompt.trim() && model ? 1 : 0.4 }}
        >
          ✨ Generate {model && <span>· {cost} 💎</span>}
        </Button>
      </div>

      <Sheet open={pickerOpen} onOpenChange={setPickerOpen} header={<Sheet.Header>Выберите модель</Sheet.Header>}>
        <List>
          <Section>
            {(models ?? []).map((m) => (
              <Cell
                key={m.code}
                onClick={() => {
                  setModel(m);
                  setPickerOpen(false);
                }}
                after={`от ${m.min_credits} 💎`}
              >
                {m.display_name}
              </Cell>
            ))}
          </Section>
        </List>
      </Sheet>
    </div>
  );
}
```

Что изменилось относительно текущего файла (для ревьюера): `api.models("image")` без фильтра-заглушки; целиком удалены `isDalle3`, `RESOLUTIONS`/`RESOLUTION_LABELS`/`chipClass`, оба блока чипов 1K/2K/4K и aspect, `computeImageCreditCost`, `AspectRatioSheet` (импорт и рендер), состояния `aspect`/`resolution`/`aspectSheetOpen`; стоимость на кнопке — `model.recommended_credits`, в карточке/пикере — `от {min_credits} 💎` (без множителей); первое фото из `PhotoUploadBox` грузится через `api.uploadImage` и уходит `image_url`'ом; `ConfirmationRequiredError` → баннер (паттерн `chat/page.tsx`, с сохранением `imageUrl` — при подтверждении фото повторно не грузится); поллинг — `completed`/`failed|refunded`/иначе продолжать; `onClick={() => generate()}` — стрелка, не прямая передача. Разметка header/textarea/карточки модели/нижней панели/пикера — без визуальных изменений.

- [ ] **Step 3: Проверить сузившийся красный прогон**

Run (из `frontend-next/`): `npx tsc --noEmit`

Expected: FAIL, все оставшиеся ошибки — ТОЛЬКО в `src/app/generate-video/page.tsx` (строки 54, 59: сравнения `"success"`/`"error"`, TS2367). `generate-image/page.tsx`, `AspectRatioSheet.tsx`, `imageCost.ts` в выводе отсутствуют.

- [ ] **Step 4: Промежуточный коммит**

```bash
git add frontend-next/src/app/generate-image/page.tsx
git commit -m "wip(frontend): рерайт generate-image под credit-system v2 -- реальные модели, загрузка фото, баннер подтверждения; удалены AspectRatioSheet и imageCost"
```

(`git rm` из Step 1 уже в индексе — коммит заберёт и удаления.)

---

### Task 5: Рерайт `generate-video/page.tsx` — первый зелёный build

**Files:**
- Modify: `frontend-next/src/app/generate-video/page.tsx` (переписывается целиком)

**Interfaces:**
- Consumes: `api.models("video")`, `api.generate(modelCode, prompt, undefined, undefined, confirm)`, `GenerationStatus`, `ConfirmationRequiredError.estimatedCredits` — из Task 3; тот же баннер, что в Task 4.
- Produces (Task 6 полагается на ТОЧНЫЙ отображаемый текст): плейсхолдер `Опишите видео, которое хотите создать` (байт-в-байт), кнопка `Создать видео`, `<video controls src={...}>` при успехе.

- [ ] **Step 1: Переписать файл целиком**

Заменить всё содержимое `frontend-next/src/app/generate-video/page.tsx` на:

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
import { ApiError, ConfirmationRequiredError, api, type ModelOut } from "@/api/client";
import { haptic } from "@/lib/telegram";

const POLL_INTERVAL_MS = 2000;
const POLL_ATTEMPTS = Math.max(60, 20 * 15); // generous ceiling; video can take minutes

interface PendingConfirmation {
  prompt: string;
  modelCode: string;
  estimatedCredits: number;
}

export default function GenerateVideo() {
  const router = useRouter();
  const [models, setModels] = useState<ModelOut[] | null>(null);
  const [model, setModel] = useState<ModelOut | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);

  useEffect(() => {
    api
      .models("video")
      .then((list) => {
        setModels(list);
        setModel((prev) => prev ?? list[0] ?? null);
      })
      .catch(() => setModels([]));
  }, []);

  async function generate(confirm = false) {
    let question: string;
    let modelCode: string;

    if (confirm) {
      // Повторная отправка после баннера: берём сохранённые prompt/modelCode.
      if (!pendingConfirmation || generating) return;
      question = pendingConfirmation.prompt;
      modelCode = pendingConfirmation.modelCode;
      setPendingConfirmation(null);
    } else {
      if (!model || !prompt.trim() || generating) return;
      question = prompt.trim();
      modelCode = model.code;
      // Новый запуск отменяет неподтверждённый предыдущий.
      setPendingConfirmation(null);
    }

    setGenerating(true);
    setError("");
    setResultUrl(null);
    try {
      // duration_seconds в UI этой под-фазы не собирается (слайдера
      // длительности на экране нет и не было) -- бэкенд применит дефолт модели.
      const { request_id } = await api.generate(modelCode, question, undefined, undefined, confirm);

      for (let i = 0; i < POLL_ATTEMPTS; i++) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        const status = await api.generationStatus(request_id);
        if (status.status === "completed") {
          setResultUrl(status.result_url);
          haptic("medium");
          return;
        }
        if (status.status === "failed" || status.status === "refunded") {
          setError(status.error_message ?? "Не удалось сгенерировать видео");
          return;
        }
        // pending / reserved / processing -- продолжаем поллинг.
      }
      setError("Генерация занимает дольше обычного, попробуйте позже");
    } catch (err) {
      if (err instanceof ConfirmationRequiredError) {
        // Не ошибка: показываем баннер, повторный вызов уйдёт с confirm=true.
        setPendingConfirmation({ prompt: question, modelCode, estimatedCredits: err.estimatedCredits });
      } else {
        setError(err instanceof ApiError ? err.message : "Не удалось сгенерировать видео");
      }
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

        <Cell subtitle={model ? `${model.min_credits} кредитов` : undefined} onClick={() => setPickerOpen(true)}>
          {model ? model.display_name : "Выберите модель"}
        </Cell>

        {pendingConfirmation && (
          <div className="relative overflow-hidden rounded-lg border border-border-soft bg-surface p-[14px]">
            <div className="absolute inset-x-0 top-0 h-[3px] bg-[image:var(--brand-gradient)]" />
            <div className="text-[13px]">
              Примерная стоимость: {pendingConfirmation.estimatedCredits} кредитов. Продолжить?
            </div>
            <div className="mt-2.5 flex gap-2">
              <Button size="s" stretched onClick={() => generate(true)}>
                Отправить
              </Button>
              <Button size="s" stretched mode="gray" onClick={() => setPendingConfirmation(null)}>
                Отмена
              </Button>
            </div>
          </div>
        )}

        <Button stretched disabled={!model || !prompt.trim() || generating} onClick={() => generate()}>
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
                  key={m.code}
                  subtitle={`${m.min_credits} кредитов`}
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

Что изменилось относительно текущего файла (для ревьюера): `api.models("video")` без фильтра-заглушки; `generate(confirm = false)` + `pendingConfirmation`-баннер над кнопкой «Создать видео» (тот же паттерн и классы, что в Task 4 / `chat/page.tsx`); `api.generate(modelCode, question, undefined, undefined, confirm)` — `duration_seconds` не передаётся (в скоупе нет слайдера); поллинг переведён на `completed`/`failed|refunded`; `onClick={() => generate()}` — стрелка. Разметка header/textarea/Cell/пикера — без визуальных изменений.

- [ ] **Step 2: Typecheck зелёный**

Run (из `frontend-next/`): `npx tsc --noEmit`

Expected: PASS, exit code 0, пустой вывод.

- [ ] **Step 3: Канонический гейт — сборка**

Run (из `frontend-next/`): `npm run build`

Expected: PASS — `Compiled successfully`, 12 роутов (включая `/generate-image`, `/generate-video`).

- [ ] **Step 4: Коммит (первый зелёный)**

```bash
git add frontend-next/src/app/generate-video/page.tsx
git commit -m "feat(frontend): generate-экраны на credit-system v2 -- реальные модели, upload фото, баннер подтверждения, реальные статусы поллинга"
```

---

### Task 6: e2e — новые версии `generate-image.spec.ts`/`generate-video.spec.ts` + реальный прогон

**Files:**
- Modify: `frontend-next/e2e/generate-image.spec.ts` (переписывается целиком)
- Modify: `frontend-next/e2e/generate-video.spec.ts` (переписывается целиком)

**Interfaces:**
- Consumes: отображаемые тексты из Tasks 4–5 (`Опишите, что хотите создать`, `✨ Generate`, `Опишите видео, которое хотите создать`, `Создать видео`); контракты Task 3 для моков (`ModelOut.code/tier/min_credits/recommended_credits`, `{request_id, estimated_credits}`, `GenerationStatus` со статусом `"completed"`); `mockTelegramWebApp` из `e2e/mock-telegram.ts` (НЕ трогается).
- Produces: критерий готовности e2e-части фазы — оба теста проходят локально без бэкенда/докера (Playwright сам поднимает `npm run dev` через `webServer` из `playwright.config.ts`; порт 3000 должен быть свободен, либо уже запущен dev-сервер — `reuseExistingServer` вне CI).

Почему прогон реален, а не «build-зелёный и смирились» (в отличие от фаз 1–2): `generate-video.spec.ts` перехватывает ВСЕ свои запросы через `page.route()` — ответы подставляются независимо от заголовков, реальный `initData` и бэкенд не участвуют; `generate-image.spec.ts` проверяет только DOM (его единственный неперехваченный запрос `/api/models?category=image` без бэкенда падает и штатно гасится `.catch(() => setModels([]))` — на проверяемые элементы это не влияет: кнопка «✨ Generate» рендерится и без модели, просто disabled). Предсуществующий баг мока Telegram (`[[ai_hub_bot_e2e_mock_bug]]`) блокирует только тесты, бьющие в живой бэкенд (`account.spec.ts`/`chat.spec.ts`) — эти два к ним не относятся.

- [ ] **Step 1: Новая версия `generate-image.spec.ts`**

Заменить всё содержимое `frontend-next/e2e/generate-image.spec.ts` на:

```ts
// frontend-next/e2e/generate-image.spec.ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("generate-image screen has a dark textarea and a generate button", async ({ page }) => {
  await page.goto("/generate-image");
  const textarea = page.getByPlaceholder("Опишите, что хотите создать");
  await expect(textarea).toBeVisible();
  const bg = await textarea.evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(bg).not.toBe("rgb(255, 255, 255)");

  // Кнопки 1K/2K/4K и aspect-чипы удалены вместе с мёртвой dall-e-3-веткой
  // (фаза 3 generate). Проверяем оставшийся реальный UI -- кнопку генерации
  // в нижней панели (задизейблена без модели/промпта, но видима).
  await expect(page.getByRole("button", { name: "Generate" })).toBeVisible();
});
```

(Тест по-прежнему НЕ мокает `/api/models`/`/api/generate` и не проверяет happy-path — спека явно запрещает заводить ему моки в этой правке; только проверяемый текст приведён к новому UI, тот же принцип «копия подгоняется под реализацию», что в `account.spec.ts`/`chat.spec.ts` фаз 1–2. `getByRole("button", { name: "Generate" })` матчит только нижнюю кнопку `✨ Generate`: имя ищется подстрокой без учёта регистра, заголовок `Generate Image` — это `<h2>`, не button.)

- [ ] **Step 2: Новая версия `generate-video.spec.ts`**

Заменить всё содержимое `frontend-next/e2e/generate-video.spec.ts` на:

```ts
// frontend-next/e2e/generate-video.spec.ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("generates a video end to end", async ({ page }) => {
  // "**/api/models*" (с хвостовой звёздочкой): экран теперь ходит на
  // /api/models?category=video; glob без "*" query-string не матчит,
  // а "?" -- glob-метасимвол, буквально в паттерн не вписывается.
  await page.route("**/api/models*", (route) =>
    route.fulfill({
      json: [
        {
          code: "veo3_fast",
          display_name: "AI Video Fast",
          tier: "standard",
          min_credits: 51,
          recommended_credits: 51,
        },
      ],
    }),
  );

  await page.route("**/api/generate", (route) =>
    route.fulfill({ json: { request_id: 1, estimated_credits: 51 } }),
  );

  let pollCount = 0;
  await page.route("**/api/generate/1", (route) => {
    pollCount += 1;
    if (pollCount < 2) {
      return route.fulfill({
        json: { status: "processing", result_url: null, error_message: null, charged_credits: 0 },
      });
    }
    return route.fulfill({
      json: {
        status: "completed",
        result_url: "https://cdn.example.com/out.mp4",
        error_message: null,
        charged_credits: 51,
      },
    });
  });

  await page.goto("/generate-video");

  await page.getByPlaceholder("Опишите видео, которое хотите создать").fill("a sunset over mountains");
  await page.getByText("Создать видео").click();

  await expect(page.locator("video")).toHaveAttribute("src", "https://cdn.example.com/out.mp4", { timeout: 15000 });
});
```

(Обновления против старой версии: мок модели — новый `ModelOut` (`code/tier/min_credits/recommended_credits` вместо `model_code/category/is_premium/credit_cost`), ответ `/api/generate` — с `estimated_credits`, поллинг — `charged_credits` и финальный статус `"completed"` вместо `"success"`, паттерн `**/api/models*` из-за `?category=video`.)

- [ ] **Step 3: Реальный прогон обоих тестов**

Run (из `frontend-next/`): `npx playwright test generate-image.spec.ts generate-video.spec.ts`

Expected: `2 passed`. Бэкенд/докер НЕ поднимать — не нужны. Playwright сам стартует `npm run dev` (webServer); если порт 3000 занят чужим процессом — освободить, если уже запущен наш dev-сервер — переиспользуется. При падении — разбирать через `npx playwright show-report`, НЕ помечать шаг выполненным на красном прогоне.

- [ ] **Step 4: Commit**

```bash
git add frontend-next/e2e/generate-image.spec.ts frontend-next/e2e/generate-video.spec.ts
git commit -m "test(frontend): e2e generate-image/generate-video под контракты credit-system v2 (реально прогнаны, page.route-моки)"
```

---

### Task 7: Финальная верификация — pytest + чистый build + playwright + ручной smoke

**Files:**
- Никаких правок кода. Только запуск проверок.

**Interfaces:**
- Consumes: всё из Tasks 1–6.
- Produces: критерий готовности фазы.

- [ ] **Step 1: Полная регрессия бэкенда**

Run (из корня репо):

```powershell
python -m pytest tests/api/ -v
python -c "import os; os.environ.setdefault('BOT_TOKEN','123456:TEST-token'); os.environ.setdefault('DATABASE_URL','postgresql+asyncpg://test'); import app.main; print('app.main ok')"
```

Expected: pytest PASS все (включая нетронутый `tests/api/test_generate_routes.py` — контракт `/api/generate` этой фазой не менялся); `app.main ok` (регистрация `upload.router` и mount `/uploads` не ломают импорт).

- [ ] **Step 2: Чистая сборка фронтенда с нуля**

Run (из `frontend-next/`, PowerShell): `Remove-Item -Recurse -Force .next; npm run build`

Expected: PASS без TS-ошибок, в сводке роутов — 12 строк (`/`, `/_not-found`, `/account`, `/admin`, `/chat`, `/generate-image`, `/generate-video`, `/login-failed`, `/referral`, `/settings`, `/tariffs`, `/trends`). Бэкенд не требуется.

- [ ] **Step 3: Повторный прогон e2e на чистой сборке окружения**

Run (из `frontend-next/`): `npx playwright test generate-image.spec.ts generate-video.spec.ts`

Expected: `2 passed` — подтверждение самодостаточности тестов (моки `page.route()` / DOM-only), без бэкенда и докера.

- [ ] **Step 4: Ручной smoke-тест (единственная часть с реальным бэкендом; если поднять нельзя — передать пользователю этой инструкцией)**

Предусловия — те же, что в фазах 1–2: бэкенд `python -m uvicorn app.main:app --port 8000` (Postgres 16 + Redis, `FRONTEND_URL=http://localhost:3000`, для проверки upload дополнительно `BACKEND_PUBLIC_URL=http://localhost:8000` — иначе `image_url` уйдёт относительным и fal.ai его не достанет), в `frontend-next/.env.local` — `NEXT_PUBLIC_API_URL=http://localhost:8000`, затем `npm run dev`:

1. `/generate-image`: пикер показывает реальные image-модели из БД (Qwen Image, Seedream, Flux Kontext Pro, Nano Banana — что засеяно), на кнопке — `✨ Generate · {recommended_credits} 💎`.
2. Сгенерировать без фото: спиннер → готовая картинка; статусы `pending/reserved/processing` не роняют поллинг.
3. Сгенерировать с фото: добавить фото в `PhotoUploadBox`, запустить — в network виден `POST /api/upload/image` → 200 с URL, затем `POST /api/generate` с этим `image_url`; открыть URL в браузере — файл отдаётся статикой `/uploads/...`.
4. Дорогая модель / порог подтверждения: вместо генерации — баннер «Примерная стоимость: N кредитов. Продолжить?»; «Отмена» убирает баннер без запроса; «Отправить» запускает генерацию (фото повторно НЕ загружается — в network один upload).
5. `/generate-video`: реальные video-модели, генерация с поллингом до `<video>`, баннер подтверждения аналогично.
6. Ошибочный сценарий (исчерпанный баланс / отключённая модель): красный текст ошибки с русским `detail` бэкенда.

- [ ] **Step 5: Финальный статус**

`git status` — чистое дерево по файлам фазы; `git log --oneline -6` — все 6 коммитов задач на месте. Известные ограничения после фазы (спека, зафиксировано осознанно): файлы upload'а живут на локальном диске (эфемерно на Render — достаточно, файл нужен только на время запроса к fal.ai); из нескольких фото используется только первое; `duration_seconds` для видео не собирается в UI (дефолт модели на бэкенде); Trends/Tariffs/Referral/Settings и admin-панель — будущие под-фазы.
