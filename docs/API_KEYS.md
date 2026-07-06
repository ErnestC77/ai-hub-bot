# Управление API-ключами

## Зачем несколько ключей на провайдера

Один общий ключ на всё — это единая точка отказа и единый счёт за все функции сразу.
Разделение по `provider` + `purpose` даёт:

- отдельный биллинг/лимиты на дорогие функции (видео, premium-текст) отдельно от дешёвых (fast text);
- возможность отключить конкретную функцию (например видео), просто не задавая её ключ — остальные продолжают работать;
- изоляцию dev/prod: локальная разработка не тратит прод-квоту и не может случайно попасть в прод-биллинг;
- точку расширения: новый провайдер = новый файл настроек + запись в `ApiKeyManager`, без изменений в остальном коде.

## Как это устроено

- `app/config.py` — `Settings` содержит вложенные `*Settings` группы (`OpenAISettings`, `AnthropicSettings`, ...), каждое поле — `SecretStr | None` с alias на конкретную переменную окружения (`OPENAI_TEXT_KEY` и т.д.).
- `app/services/keys/enums.py` — `Provider` (12 провайдеров) и `KeyPurpose` (text/image/audio/video/music/search/premium/fast_video/fallback/dev).
- `app/services/keys/api_key_manager.py` — `ApiKeyManager.get_key(provider, purpose) -> str`. Единственная точка, откуда AI-сервисы получают ключ. Внутри — таблица `(provider, purpose) -> имя поля` плюс fallback на `*_DEV_KEY`, если основной ключ не задан (см. ниже про `APP_ENV`).
- `app/services/keys/key_healthcheck.py` — при старте логирует `[OK]`/`[MISSING]` по каждой активной модели из `model_configs`. Ничего не роняет: отсутствующий ключ — это просто `[MISSING]` в логе, конкретная модель ответит пользователю "модель временно недоступна", остальной сервис работает как обычно.
- `app/db/models/model_config.py` — колонка `key_purpose` (какой конкретно ключ провайдера нужен этой модели).
- AI-сервисы (`app/services/ai/*.py`) сами берут `model.provider` + `model.key_purpose` и зовут `ApiKeyManager` — они никогда не читают `.env`/`settings.*_api_key` напрямую.

## APP_ENV и dev-ключи

`APP_ENV` = `dev` | `staging` | `prod`.

- `dev`/`staging`: если основной ключ для нужного `purpose` не задан, `ApiKeyManager` пробует `*_DEV_KEY` этого провайдера (с warning в логе).
- `prod`: `*_DEV_KEY` никогда не используется автоматически. Если основной ключ не задан — `ApiKeyManager` бросает `DevKeyUsedInProductionError`/`ApiKeyNotConfiguredError`, а не тихо уходит на dev-ключ.

## Минимум для MVP (текстовый чат + картинки — то, что уже реализовано)

```text
OPENAI_TEXT_KEY
OPENAI_IMAGE_KEY
ANTHROPIC_PROD_KEY
ANTHROPIC_PREMIUM_KEY
GEMINI_TEXT_KEY
DEEPSEEK_PROD_KEY
```

Без остальных ключей приложение запускается нормально — просто соответствующие провайдеры/purpose недоступны.

## Заготовки на будущее (провайдеры без реализованного AI-сервиса)

`Perplexity`, `ElevenLabs`, `Runway`, `Stability`, `fal.ai`, `Replicate`, `Luma`, `OpenRouter` — для них заведены `Provider`/`*Settings`/переменные окружения, но **AI-сервисов под них ещё нет** (нет кода, который реально вызывает их API). Задать эти ключи уже можно — `ApiKeyManager.get_key()` для них отработает, — но пока это ни на что не влияет, пока не появится соответствующий `app/services/ai/<provider>_service.py` и запись в `app/services/ai/registry.py`.

Видео (когда появится провайдер):
```text
GEMINI_VIDEO_KEY
RUNWAY_FAST_VIDEO_KEY
RUNWAY_PREMIUM_VIDEO_KEY
LUMA_VIDEO_KEY
FAL_VIDEO_KEY
```

Голос (когда появится провайдер):
```text
OPENAI_AUDIO_KEY
ELEVENLABS_TTS_KEY
ELEVENLABS_VOICE_AGENT_KEY
GEMINI_AUDIO_KEY
```

## Как отключить дорогую функцию

Просто не задавайте её ключ (или очистите переменную окружения на Render/сервере). `ApiKeyManager` не найдёт ключ → конкретная модель начнёт отвечать безопасной ошибкой; остальные модели/функции продолжат работать. Также можно выключить саму модель в `model_configs.is_active` через админку — тогда она вообще не появится в списке моделей у пользователя.

## Как добавить нового провайдера

1. Добавить `<Provider>Settings` в `app/config.py` (по одному `SecretStr | None` полю на каждый нужный ключ) и подключить его как поле `Settings`.
2. Добавить значение в `Provider` (`app/services/keys/enums.py`).
3. Добавить его purpose-map в `_PURPOSE_ATTR` (`app/services/keys/api_key_manager.py`).
4. Написать `app/services/ai/<provider>_service.py` (класс `AIProvider`, берёт ключ только через `get_key_manager().get_key(...)`).
5. Зарегистрировать в `app/services/ai/registry.py` (`TEXT_PROVIDERS`/`IMAGE_PROVIDERS`).
6. Добавить модель(и) в `app/db/seed.py` с правильными `provider`/`category`/`key_purpose`; оставить `is_active=False`, пока сервис не проверен вживую.

## Почему нельзя хранить ключи в коде и коммитить `.env`

- Ключ в коде утекает в git-историю навсегда (даже после удаления файла — история остаётся), становится виден всем с доступом к репозиторию, и его нельзя быстро отозвать без поиска по всем коммитам.
- `.env` содержит боевые секреты конкретного окружения — если он в git, любой форк/клон репозитория получает эти секреты. `.gitignore` уже настроен: `.env` и `.env.*` игнорируются, `.env.example` (шаблон без реальных значений) — нет.
- Ключи никогда не логируются целиком. Если нужно показать статус в debug — использовать `mask_secret()` (`app/services/keys/masking.py`): `sk-...ab12`, а не полное значение.
