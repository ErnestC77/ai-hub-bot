# Frontend Integration — Phase 3: Generate (image/video)

## Контекст

Продолжение проекта связывания `frontend-next/` с бэкендом credit-system-v2
(под-фазы [1 (Account)](2026-07-11-frontend-integration-phase1-account-api-design.md)
и [2 (Chat)](2026-07-11-frontend-integration-phase2-chat-design.md) уже
смёржены). Пользователь выбрал следующим **generate-image/video** — сейчас
это компилируемые заглушки из под-фазы 2 (`.filter(() => false)`, список
моделей всегда пуст).

В отличие от предыдущих под-фаз, здесь обнаружены реальные **пробелы на
бэкенде**, не только устаревшие типы на фронте:

1. **Нет эндпойнта каталога image/video-моделей.** `GET /api/models`
   (`app/api/routes/chat.py:50-77`) жёстко фильтрует `AiModel.category ==
   ModelCategory.text` — способа получить список image/video-моделей с
   фронта не существует вообще.
2. **Нет эндпойнта загрузки файла.** `PhotoUploadBox.tsx` собирает
   `File[]` в браузере, но `POST /api/generate`'s `image_url: str | None`
   (`app/api/routes/generate.py:34`) ожидает уже готовый URL — на бэкенде
   нет ни одного `UploadFile`/`multipart`-роута и ни файловой, ни
   S3-инфраструктуры вообще (проверено).
3. **`GenerationStatus.status` на фронте не соответствует реальному
   `RequestStatus`.** Фронт ждёт `"processing" | "success" | "error"`;
   бэкенд (`app/db/enums.py:48-54`) отдаёт одно из `pending/reserved/
   processing/completed/failed/refunded`.
4. **UI aspect/resolution (чипы 1K/2K/4K, `AspectRatioSheet`) активируется
   только для `model.code === "dall-e-3"`** — такой модели в новом каталоге
   нет (реальные image-модели: Qwen Image, Seedream, Flux Kontext Pro, Nano
   Banana), ветка навсегда мертва.
5. **`api.generate()` всё ещё шлёт `credit_cost_override`** — поле,
   удалённое как security-фикс ещё в фазе 3 бэкенда (сентябрь-фазе rebuild'а,
   не этого проекта); FastAPI молча игнорирует лишние поля, но это мусор.

## Scope

**В скоупе:**
- **Бэкенд (два маленьких, аддитивных изменения, без миграций):**
  - `GET /api/models` получает опциональный query-параметр `category`
    (`text` по умолчанию — существующий вызов из Chat не ломается).
  - Новый `POST /api/upload/image` — принимает `UploadFile`, сохраняет на
    диск, отдаёт `{"url": "..."}` через примонтированный `StaticFiles`.
- **`client.ts`:** `api.models(category?)`, `api.uploadImage(file)`, фикс
  `api.generate()` (убрать `credit_cost_override`, поддержать `image_url`/
  `duration_seconds`/`confirm`), фикс `GenerationStatus.status`, обработка
  `ConfirmationRequiredError` (уже существует с фазы 2 — переиспользуется
  как задумано) в обоих экранах. Удаление `ImageAspect`/`ImageResolution`.
- **`generate-image/page.tsx`:** реальный список моделей, реальная загрузка
  первого фото из `PhotoUploadBox` в `image_url`, полное удаление
  `isDalle3`/aspect/resolution-UI, баннер подтверждения (как в Chat), фикс
  поллинга статуса.
- **`generate-video/page.tsx`:** реальный список моделей, баннер
  подтверждения, фикс поллинга статуса.
- Удаление файлов `AspectRatioSheet.tsx`, `lib/imageCost.ts` (больше нигде
  не используются — проверено).

**Вне скоупа:**
- Множественная загрузка фото: `PhotoUploadBox` продолжает позволять
  выбрать до 10 фото (существующая возможность, не трогаем), но бэкенд
  поддерживает только один `image_url` — при генерации используется
  **только первое** фото. Не редизайн этого компонента.
- Admin-панель, Trends/Tariffs/Referral/Settings — отдельные будущие
  под-фазы.
- Долговременное хранилище файлов (S3 и т.п.) — загруженные картинки
  хранятся на локальном диске бэкенда; на Render это эфемерное хранилище
  (переживёт один процесс, не переживёт передеплой) — приемлемо, потому что
  файл нужен только на время одного запроса к fal.ai, не постоянно.
- Визуальный редизайн — как и раньше, отдельный проект.

## Изменения — бэкенд

### 1. `GET /api/models` — параметр `category`

`app/api/routes/chat.py`, текущий роут:
```python
@router.get("/models", response_model=list[ModelOut])
async def list_models(session: AsyncSession = Depends(get_db)) -> list[ModelOut]:
    models = (
        (await session.execute(
            select(AiModel).where(
                AiModel.category == ModelCategory.text,
                AiModel.is_active.is_(True),
                AiModel.is_visible.is_(True),
            ).order_by(AiModel.sort_order)
        )).scalars().all()
    )
    ...
```

Добавить query-параметр:
```python
@router.get("/models", response_model=list[ModelOut])
async def list_models(
    category: ModelCategory = ModelCategory.text,
    session: AsyncSession = Depends(get_db),
) -> list[ModelOut]:
    models = (
        (await session.execute(
            select(AiModel).where(
                AiModel.category == category,
                AiModel.is_active.is_(True),
                AiModel.is_visible.is_(True),
            ).order_by(AiModel.sort_order)
        )).scalars().all()
    )
    ...
```
`ModelOut` (`code/display_name/tier/min_credits/recommended_credits`) не
меняется — поля одинаково осмысленны для всех трёх категорий (проверено по
ТЗ `promt.md`: image/video-модели тоже имеют `tier`). FastAPI сам
провалидирует `category` как `ModelCategory` (400 на невалидное значение).

### 2. `POST /api/upload/image` — новый роут

Новый файл `app/api/routes/upload.py`:
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

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Файл больше 30 МБ")

    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[file.content_type]
    filename = f"{uuid.uuid4().hex}.{ext}"
    (UPLOAD_DIR / filename).write_bytes(data)

    return UploadResponse(url=f"{settings.backend_public_url}/uploads/{filename}")
```

`app/main.py` — подключить роутер и примонтировать статику. Текущая строка
импорта роутеров (`app/main.py:9`):
```python
from app.api.routes import admin, banners, chat, generate, me, payments, referral, tools
```
добавить `upload` в этот же импорт (алфавитный порядок, как остальные):
```python
from app.api.routes import admin, banners, chat, generate, me, payments, referral, tools, upload
```
и добавить `from fastapi.staticfiles import StaticFiles` к существующим
импортам FastAPI. Рядом с существующим блоком регистрации роутеров
(`app/main.py:67-76`, `app.include_router(generate.router, prefix="/api")` —
последняя строка перед вебхуками) добавить:
```python
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.include_router(upload.router, prefix="/api")
```

Проверка размера через `await file.read()` целиком в память — приемлемо при
лимите 30 МБ (тот же лимит, что уже в `PhotoUploadBox.tsx`), стриминговая
проверка не нужна для этого объёма.

## Изменения — `client.ts`

- `api.models` получает необязательный параметр:
  ```ts
  models: (category: "text" | "image" | "video" = "text") =>
    request<ModelOut[]>(`/api/models?category=${category}`),
  ```
- `GenerationStatus.status` — привести к реальным значениям бэкенда:
  ```ts
  export interface GenerationStatus {
    status: "pending" | "reserved" | "processing" | "completed" | "failed" | "refunded";
    result_url: string | null;
    error_message: string | null;
    charged_credits: number;
  }
  ```
  (было `"processing" | "success" | "error"` + `credit_cost`).
- `api.generate` — убрать `credit_cost_override`, поддержать реальные поля
  `GenerateRequest` (`app/api/routes/generate.py:28-36`), вернуть
  `estimated_credits` (нужен для баннера подтверждения):
  ```ts
  generate: (modelCode: string, prompt: string, imageUrl?: string, durationSeconds?: number, confirm = false) =>
    request<{ request_id: number; estimated_credits: number }>("/api/generate", {
      method: "POST",
      body: JSON.stringify({
        model_code: modelCode, prompt, image_url: imageUrl ?? null,
        duration_seconds: durationSeconds ?? null, confirm,
      }),
    }),
  ```
- Новый метод загрузки:
  ```ts
  uploadImage: async (file: File): Promise<{ url: string }> => {
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
    return res.json();
  },
  ```
  (не через общий `request()` — `Content-Type` для `FormData` браузер
  проставляет сам с правильным `boundary`, общий хелпер жёстко ставит
  `application/json`).
- Удалить `export type ImageAspect = ...` и `export type ImageResolution =
  "1k" | "2k" | "4k"` — больше нигде не используются после рерайта экрана.

## Изменения — `generate-image/page.tsx`

Полный рерайт по образцу уже смёржённого `chat/page.tsx` (баннер
подтверждения, состояние `pendingConfirmation`) и `generate-video/page.tsx`
(проще по структуре, без чипов):

- Модели — `api.models("image")`, без фильтра-заглушки.
- Убрать целиком: `isDalle3`, `RESOLUTIONS`/`RESOLUTION_LABELS`/`chipClass`,
  оба блока с чипами 1K/2K/4K и aspect, `computeImageCreditCost`,
  `AspectRatioSheet` (импорт и рендер), состояния `aspect`/`resolution`/
  `aspectSheetOpen`. Стоимость — просто `model.recommended_credits`.
- `PhotoUploadBox` остаётся как есть (компонент не трогаем); при генерации,
  если `photos.length > 0`, сначала `await api.uploadImage(photos[0])`,
  полученный `url` передаётся как `image_url` в `api.generate(...)`.
- `generate()`: `ConfirmationRequiredError` → `pendingConfirmation`-баннер
  (тот же паттерн, что в `chat/page.tsx`: сохранить `prompt`/`modelCode`/
  `imageUrl` в состоянии, повторный вызов с `confirm=true`). Остальные
  ошибки (`ApiError`) — как сейчас, в `setError`.
- Поллинг статуса: `if (status.status === "completed") { ...success... }`;
  `if (status.status === "failed" || status.status === "refunded") {
  ...error... }`; во всех остальных случаях (`pending`/`reserved`/
  `processing`) — продолжать поллинг.

## Изменения — `generate-video/page.tsx`

Тот же набор правок, без aspect/resolution (их там и не было):
- `api.models("video")` вместо заглушки.
- `api.generate(model.code, prompt.trim(), undefined, durationSeconds,
  confirm)` — `duration_seconds` не собирается в UI в этой под-фазе (нет
  слайдера длительности в текущей разметке экрана; бэкенд применит дефолт
  модели). Добавление слайдера длительности — не в скоупе, экран и раньше
  его не имел.
- Тот же баннер подтверждения и та же поправка статуса, что в generate-image.

## Тестирование

- Бэкенд: `pytest tests/api/` — новый тест на `GET /api/models?category=image`
  (возвращает только image-модели) и на `POST /api/upload/image` (валидный
  файл → 200 + URL, файл больше лимита → 413, неверный content-type → 422).
  Существующие тесты `/api/models` (без параметра, дефолт `text`) не должны
  сломаться.
- Фронтенд: `npx tsc --noEmit` + `npm run build` (как во всех предыдущих
  под-фазах — здесь нет pytest/jest, только typecheck+build). Ручной
  smoke-тест (требует поднятого бэкенда, как в под-фазах 1-2): выбрать
  image-модель, сгенерировать без фото, сгенерировать с фото (проверить
  реальную загрузку), проверить баннер подтверждения на дорогой модели,
  проверить video-экран аналогично.
- **e2e (`generate-image.spec.ts`/`generate-video.spec.ts`) — важное
  отличие от предыдущих под-фаз.** Оба теста уже существуют и используют
  **`page.route()`** для полного перехвата `/api/models`/`/api/generate`/
  `/api/generate/:id` (в отличие от `account.spec.ts`/`chat.spec.ts`,
  которые бьют в живой бэкенд). Раз ответы подставляются перехватом
  независимо от заголовков запроса, предсуществующий баг мока Telegram
  ([[ai_hub_bot_e2e_mock_bug]]) их **не блокирует** — реальный
  `window.Telegram.WebApp.initData` для этих тестов не важен, бэкенд
  вообще не участвует. Оба файла нужно обновить под новые контракты
  (`ModelOut.code`/`.tier`, `GenerationStatus.status` со значением
  `"completed"` вместо `"success"` и т.д.) и **реально прогнать** как
  часть этой под-фазы — это не «build-зелёный и с тем и смирились», а
  честная поведенческая проверка.
  - `generate-video.spec.ts` уже мокает весь happy-path (`/api/models` →
    одна video-модель, `/api/generate` → `request_id`, поллинг `/api/generate/1`
    → сначала `processing`, потом финальный статус) — обновить под новые
    поля и запустить.
  - `generate-image.spec.ts` сейчас (без `page.route`, читает реальный DOM)
    проверяет только тёмный textarea и кнопки 1K/2K/4K; кнопки удаляются
    этой спекой — заменить их проверку на что-то из оставшегося реального
    UI (например, видимость плейсхолдера textarea уже покрыта, добавить
    проверку кнопки "✨ Generate" в нижней панели). Тест не мокает
    `/api/models`/`/api/generate` и не проверял happy-path генерации — не
    заводить его моки в рамках этой правки, только привести проверяемый
    текст в соответствие с новым UI (тот же принцип, что и в `account.spec.ts`/
    `chat.spec.ts` из под-фаз 1-2: копия подгоняется под реализацию).

## Известные ограничения после этой фазы

- Загруженные файлы живут на локальном диске бэкенда — приемлемо для
  Render в текущем масштабе, но если понадобится персистентность между
  деплоями или горизонтальное масштабирование бэкенда, потребуется
  переезд на объектное хранилище (S3-совместимое) — отдельная будущая
  задача, не блокирует эту фазу.
- Множественная загрузка фото в `PhotoUploadBox` визуально доступна, но
  функционально используется только первое фото — известное упрощение,
  описано выше.
- Остальные экраны (Trends/Tariffs/Referral/Settings) и admin-панель —
  как и раньше, отдельные под-фазы.
