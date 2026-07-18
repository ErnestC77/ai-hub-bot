# Деплой на собственный сервер (Selectel / Hetzner)

Прод-стек: **backend + worker + postgres + redis + frontend + Caddy** (авто-HTTPS).
Наружу открыт только Caddy (80/443); всё остальное — внутри compose-сети.
Единый домен: фронт и `/api` на одном origin (CORS не нужен).

## 0. Предпосылки
- Сервер Ubuntu 24.04, публичный IP, порты 80/443 открыты.
- Домен **или** `<IP-через-дефисы>.sslip.io` (Let's Encrypt его тоже подписывает).
- Ключи fal, `BOT_TOKEN`, (опц.) ключи ЮKassa.

## 1. Установка Docker
```bash
curl -fsSL https://get.docker.com | sh
```

## 2. Код и конфиг
```bash
git clone <repo> ai-hub-bot && cd ai-hub-bot
cp .env.prod.example .env
nano .env          # заполнить DOMAIN, BOT_TOKEN, ADMIN_IDS, FAL_*, POSTGRES_PASSWORD, DATABASE_URL
```
`DOMAIN` без своего домена: например `139-100-202-3.sslip.io` (IP через дефисы).

## 3. Запуск
```bash
docker compose -f docker-compose.prod.yml up -d --build
```
Миграции и сид накатываются автоматически (entrypoint backend'а). Caddy сам
получит HTTPS-сертификат при первом обращении к домену.

Проверка: `curl https://<DOMAIN>/health` → `{"status":"ok"}`.

## 4. Перенаправить бота на новый домен
У @BotFather (или скриптом) выставить Web App / Menu Button URL на `https://<DOMAIN>`.
Если используется fal-вебхук — он берётся из `BACKEND_PUBLIC_URL` автоматически.
ЮKassa-вебхук в кабинете: `https://<DOMAIN>/webhooks/yookassa`.

## 5. Перенос данных с Render (если мигрируем, не с нуля)
На машине с доступом к Render-БД:
```bash
pg_dump "<RENDER_DATABASE_URL>" --no-owner --no-privileges -Fc -f dump.pgc
# на новом сервере:
docker compose -f docker-compose.prod.yml cp dump.pgc postgres:/tmp/dump.pgc
docker compose -f docker-compose.prod.yml exec postgres \
  pg_restore --no-owner --clean --if-exists -U ai_bot -d ai_bot /tmp/dump.pgc
```
Загрузки `/uploads` с Render перенести в volume `uploads_data` (scp + docker cp),
если они нужны исторически.

## Обновление
```bash
git pull && docker compose -f docker-compose.prod.yml up -d --build
```

## Заметки
- **Telegram-блок у РФ-хостеров** обходится `extra_hosts: api.telegram.org:149.154.167.220`
  в compose (уже прописано для backend и worker). При смене IP Telegram — обновить.
- **Текст** идёт через fal LLM router (доступен из РФ), медиа — через fal queue.
- Порядок старта соблюдён: postgres/redis → backend (миграции) → worker → caddy.
