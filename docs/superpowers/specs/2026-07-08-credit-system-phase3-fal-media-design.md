# Кредитная система v2 — Фаза 3: fal.ai + изображения/видео

## Контекст

Фаза 1 построила фундамент (схема, движок кредитов, `calculate_image_credits`/
`calculate_video_credits` уже готовы в `app/services/pricing.py`). Фаза 2
заменила текстовый pipeline на OpenRouter. Эта фаза заменяет медиа-pipeline
(изображения/видео) на fal.ai, следуя тому же принципу полной замены.

Полное ТЗ: `C:\Users\mccaq\Desktop\promt.md`. Backend-only, без изменений
`frontend-next` (то же решение, что и в фазе 2).

## Решения, принятые до этого документа

- **PiAPI и OpenAI DALL-E удаляются полностью** (`PiAPIClient`, `ImageProvider`,
  `app/webhooks/piapi.py`, связанные тесты). Каталог `ai_models` из фазы 1
  содержит только 4 fal-image + 4 fal-video модели — ни одной строки под
  PiAPI/OpenAI, так что это не работающий провайдер, который нужно сохранять,
  а мёртвый код.
- **fal.ai — асинхронный API, завершение через webhook** (тот же паттерн,
  что был у PiAPI: `backend_public_url` + secret в URL), а не поллинг с
  клиента. `app/api/routes/generate.py` уже даёт `request_id` и клиент может
  поллить `GET /api/generate/{id}` — это поведение сохраняется, меняется
  только то, что доставляет финальный результат на бэкенд.
- **Редактирование изображения принимает только `image_url`** (уже
  доступный URL — результат прошлой генерации, Telegram file URL и т.п.).
  В проекте нет файлового хранилища (`image_service.py` содержал явный
  комментарий об этом), и заводить upload-эндпоинт — отдельная, вне рамок
  фазы 3 задача.

## Модель данных

Изменений не требуется. `ai_models.cost_unit` (`image`/`megapixel`/`video`/
`second`) и `ai_requests` (`category`, `estimated_credits`/`reserved_credits`/
`charged_credits`, `provider_response_id`, `status`) из фазы 1 уже достаточны
для image/video-запросов — они были спроектированы под все три категории
сразу. `FalSettings` в `app/config.py` (`image_key`/`video_key`/`dev_key`) и
`_PURPOSE_ATTR[Provider.FAL]` в `api_key_manager.py` (`KeyPurpose.IMAGE`/
`KeyPurpose.VIDEO`) уже существуют и не меняются.

**Важное отличие от текста:** для image/video quantity/megapixels/duration
известны на этапе запроса (пользователь их задаёт), а не постфактум, как
токены у LLM. Поэтому в норме `estimated_credits == reserved_credits ==
charged_credits`, и `settle_request(actual == reserved)` возвращает `None`
(корректировка не создаётся) — это штатный путь, не деградация.

## Удаляемые файлы

- `app/services/ai/piapi_client.py`, `app/services/ai/image_service.py`
- `app/webhooks/piapi.py`
- `app/services/generation_service.py` (замена — `media_generation_service.py`)
- `tests/services/ai/test_piapi_client.py`, `tests/services/keys/test_piapi_key.py`

## Новые файлы

### `app/services/ai/fal_client.py`

```python
class FalClient:
    def __init__(self, api_key: str): ...
    async def submit_image(
        self, model: AiModel, prompt: str, *, image_url: str | None, webhook_url: str
    ) -> str: ...  # -> fal request_id
    async def submit_video(
        self, model: AiModel, prompt: str, *, duration_seconds: int, webhook_url: str
    ) -> str: ...
```

`POST https://queue.fal.run/{model.provider_model_id}?fal_webhook={webhook_url}`
(эндпоинт из `provider_model_id`, как и у OpenRouter — не хардкодится в
бизнес-логике). Тело запроса: `{"prompt": prompt}` + `{"image_url": ...}` для
edit-моделей + `{"duration": duration_seconds}` для видео. Ответ содержит
`request_id` — сохраняется в `ai_requests.provider_response_id`.

### `app/webhooks/fal.py`

Взамен `app/webhooks/piapi.py`: тот же паттерн (`secret` в query, сверка с
`settings.fal_webhook_secret` — новая настройка, аналог
`piapi_webhook_secret`). Тело fal-вебхука: `{"request_id", "status": "OK"|
"ERROR", "payload": {...}}`. `extract_result_url(payload)` — функция по
образцу `piapi_client.extract_result_url`, перебирает известные формы ответа
fal-моделей (`images[0].url` для image-моделей, `video.url` для
video-моделей); неизвестные/неподтверждённые форматы отмечаются PLACEHOLDER-
комментарием с "уточнить перед продакшн-запуском", как и провайдерские ID в
фазе 1 — ТЗ прямо допускает такие плейсхолдеры.

### `app/services/media_generation_service.py`

Общий флоу для image и video (замена `generation_service.py`):

```python
async def start_media_generation(
    session: AsyncSession, user: User, model_code: str, prompt: str, *,
    image_url: str | None = None, duration_seconds: int | None = None, confirm: bool = False,
) -> AIRequest
```

Поток: резолв `AiModel` по `model_code` (у каждой строки каталога `category`
зафиксирована — `image` или `video`, клиент её не выбирает отдельно) →
расчёт кредитов: для `category=image` —
`calculate_image_credits(model, quantity=1, megapixels=1.0, is_edit=image_url is not None)`
(множитель за редактирование включается всегда, когда передан `image_url`,
без дополнительной проверки "поддерживает ли эта конкретная модель edit" —
и Qwen Image/Seedream, и Flux Kontext Pro/Nano Banana технически принимают
входное изображение у fal, разница только в качестве результата); для
`category=video` — `calculate_video_credits(model, duration_seconds or 5)`
(5 секунд — дефолт по ТЗ). → подтверждение
если `estimated > 300` (image) или `> 1000` (video) и `confirm=False` →
per-user Redis-лок → `reserve_credits` → `FalClient.submit_*` → `AIRequest.status
= reserved`, `provider_response_id = fal_request_id` → commit → возврат
`AIRequest` клиенту как `request_id` (генерация продолжается асинхронно,
лок остаётся до вебхука — совпадает с тем, как PiAPI держал
`ai_lock:{user.id}` до `handle_piapi_webhook`).

```python
async def handle_fal_webhook(session: AsyncSession, payload: dict) -> None
```

Находит `AIRequest` по `provider_response_id`, при `status=OK` —
`settle_request(request, actual=estimated_credits)` (обычно без корректировки,
см. выше), при `status=ERROR` — `refund_request`. Снимает Redis-лок в обоих
случаях. Идемпотентность через атомарный `UPDATE ... WHERE status=reserved`
(тот же приём, что был в `handle_piapi_webhook`, — защита от повторной
доставки вебхука).

## API-поверхность

`POST /api/generate` (переписывается, закрывает найденную ранее
security-уязвимость: `credit_cost_override` от клиента полностью убирается
из запроса — сумма списания вычисляется только на бэкенде):

```python
class GenerateRequest(BaseModel):
    model_code: str
    prompt: str
    image_url: str | None = None       # для image-edit моделей
    duration_seconds: int | None = None  # для video, per-second моделей
    confirm: bool = False

class GenerateResponse(BaseModel):
    request_id: int
    estimated_credits: int
```

`GET /api/generate/{request_id}` — без изменений в контракте (status/
result_url/error_message), `credit_cost` в ответе заменяется на
`charged_credits` (реальное поле из `AIRequest`, не хардкод `0`, как было
раньше).

`POST /api/fal/webhook?secret=...` — новый роутер взамен
`/api/piapi/webhook`.

## Явно вне рамок фазы 3

Файловое хранилище/upload изображений, пакеты и оплата (фаза 4), админка и
антифрод (фаза 5), `/admin_stats` (фаза 6), `frontend-next`.

## Тесты

- `tests/services/ai/test_fal_client.py` — `submit_image`/`submit_video`,
  замоканный HTTP (`respx`, как у `piapi_client`/`openrouter_service`),
  корректная сборка payload и URL из `provider_model_id`.
- `tests/services/test_media_generation_service.py` — reserve→submit flow на
  sqlite-фикстуре: успешный webhook (settle без корректировки),
  webhook с ошибкой (refund), `estimated > 300/1000` без confirm →
  `ConfirmationRequiredError`, недостаточный баланс, повторная доставка
  webhook (идемпотентность).
- `tests/api/test_generate_routes.py` (новый, взамен фактически неработавшего
  старого) — `/api/generate`, `/api/generate/{id}`, `/api/fal/webhook`,
  включая явную проверку, что `credit_cost_override`/аналог в теле запроса
  ни на что не влияет (клиент не может задать свою стоимость).
