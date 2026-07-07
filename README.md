# ai-hub-bot

Telegram Mini App с доступом к нескольким AI-моделям (OpenAI, Claude, Gemini, DeepSeek, генерация картинок) по подписке. Оплата — Telegram Stars и ЮKassa.

Стек: Python 3.12, aiogram3, FastAPI, PostgreSQL16, Redis7, SQLAlchemy(async), Alembic, Next.js+TypeScript+Tailwind CSS v4 (`frontend-next/`).

## Архитектура

- Всё пользовательское взаимодействие (чат, тарифы, баланс, инструменты, реферальная программа, админка) — Telegram Mini App (Next.js, полностью client-rendered), развёрнутый как отдельный Render-сервис `ai-hub-frontend`, ходит в backend по HTTPS.
- Классический aiogram-бот в чате нужен только для `/start`, обработки Stars-платежей (`PreCheckoutQuery`/`successful_payment` — это Bot API updates, Mini App их не получает) и уведомлений.
- Backend (`ai-hub-backend`) и frontend (`ai-hub-frontend`) — два независимых Render-сервиса из двух разных Docker-образов (backend: `python:3.12-slim`, без Node; frontend: свой `frontend-next/Dockerfile`). Backend разрешает CORS только для `FRONTEND_URL` — публичного адреса `ai-hub-frontend`.

## Обязательные переменные окружения

Скопируйте `.env.example` в `.env` и заполните как минимум:

- `BOT_TOKEN` — токен бота от @BotFather.
- `BOT_USERNAME` — username бота без `@` (нужен для реферальных ссылок и страницы `/payment/return`).
- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY` — ключи AI-провайдеров (без реального ключа конкретный провайдер будет отвечать безопасной ошибкой, не роняя остальные).
- `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY` — для оплаты картой/СБП.
- `ADMIN_IDS` — Telegram ID администраторов через запятую (получают доступ к `/admin` в Mini App).

Для фронтенда — `frontend-next/.env.local` (см. `frontend-next/.env.local.example`): `NEXT_PUBLIC_API_URL` — адрес backend, `NEXT_PUBLIC_SUPPORT_USERNAME` — username поддержки для экрана «Настройки».

## Локальная разработка

```
cp .env.example .env          # заполнить BOT_TOKEN и ключи выше
cp frontend-next/.env.local.example frontend-next/.env.local
docker compose up --build     # postgres + redis + backend (polling) + worker
cd frontend-next && npm install && npm run dev   # UI на localhost:3000, ходит в :8000 через NEXT_PUBLIC_API_URL
```

В обычном браузере (`npm run dev`) `window.Telegram` не определён — все хелперы в `frontend-next/src/lib/telegram.ts` деградируют без ошибок, но `X-Telegram-Init-Data` будет пустым и API вернёт 401 (см. `/login-failed`). Для полноценной проверки нужен реальный Telegram — см. ниже.

## Тест внутри настоящего Telegram

Telegram Mini App (initData, `openInvoice`, `openLink`) работает только внутри настоящего Telegram-клиента, и WebApp URL обязан быть HTTPS. Для локального теста:

```
docker compose up --build          # backend на :8000
cd frontend-next && npm run dev    # frontend на :3000
cloudflared tunnel --url http://localhost:3000
# или: ngrok http 3000
```

Впишите полученный `https://...` адрес в `WEBAPP_URL` в `.env` и перезапустите backend — при старте (`lifespan`) бот переустановит Menu Button на новый адрес. Откройте бота в Telegram и нажмите кнопку меню.

Stars не имеют полноценного тестового режима — используйте минимальную цену тестового тарифа и `refund_star_payment` (кнопка «Возврат» в админке) после проверки. Для ЮKassa используйте тестовый магазин (`shop_id`/`secret_key` из тестового кабинета) и тестовую карту `5555 5555 5555 4444`.

## Продакшен

Две независимые службы (см. `render.yaml`): `ai-hub-backend` (FastAPI, этот репозиторий, `Dockerfile` в корне) и `ai-hub-frontend` (Next.js Mini App, `frontend-next/Dockerfile`). Между ними нет общего образа и общего процесса — только HTTPS-запросы браузера к backend.

- `BOT_MODE=webhook`, `WEBHOOK_SECRET` — случайная строка; webhook принимается на `POST /webhook/{WEBHOOK_SECRET}`.
- `WEBAPP_URL` — публичный HTTPS-домен **фронтенда** (`ai-hub-frontend`): именно на него бот ставит Menu Button в Telegram.
- `FRONTEND_URL` (на backend) — тот же публичный домен фронтенда, используется только для CORS (`allow_origins`) в `app/main.py`.
- `NEXT_PUBLIC_API_URL` (на frontend, при сборке) — публичный HTTPS-домен backend, на который фронтенд шлёт `/api/*`-запросы.
- `PAYMENT_RETURN_URL`, `YOOKASSA_WEBHOOK_URL` — публичные HTTPS-адреса backend (webhook ЮKassa регистрируется в личном кабинете ЮKassa на `YOOKASSA_WEBHOOK_URL`).
- Деплой backend/worker — `docker compose up -d --build` на VDS (см. `docker-compose.yml`: `backend`, `worker`, `postgres:16`, `redis:7`) за Nginx с HTTPS, либо два отдельных Render-сервиса из `render.yaml`; frontend деплоится отдельно как `ai-hub-frontend` из `frontend-next/Dockerfile`.
- `worker` стартует только после того, как `backend` пройдёт healthcheck (миграции применяются в `entrypoint.sh` при старте каждого контейнера — так исключается гонка одновременного создания таблиц на чистой БД).

## Структура

```
app/
├── main.py              # FastAPI + lifespan (бот polling/webhook)
├── worker.py             # APScheduler: экспирация подписок, поллинг ЮKassa, уведомления
├── config.py
├── db/                   # SQLAlchemy-модели, Alembic, seed тарифов/моделей
├── bot/                  # aiogram: /start, Stars-платежи, fallback
├── api/routes/           # /api/* для Mini App (me, chat, tools, tariffs, payments, referral, admin)
├── services/             # AI Router, Payment Gateway, лимиты, статистика
└── webhooks/yookassa.py
frontend-next/            # Next.js + TypeScript + Tailwind CSS v4 Mini App (отдельный Render-сервис)
```
