# Миграция фронтенда ai-hub-bot на Next.js + Tailwind v4

Дата: 2026-07-07
Статус: одобрено пользователем, готово к написанию implementation plan

## Контекст и мотивация

Текущий фронтенд (`frontend/`): Vite + React + TypeScript + `@telegram-apps/telegram-ui`,
собирается в статику и раздаётся тем же FastAPI-процессом. 8 пользовательских экранов
(Home, Chat, GenerateImage, MyAccount, Referral, Settings, Tariffs, Trends) + 6 админ-экранов
+ общие компоненты — 28 файлов.

Мотивация миграции: конкурентный бот (@GPT4Telegrambot, домен `app.gpt4telegram.com`) построен
на Next.js + Tailwind CSS v4 + полностью кастомной вёрстке (без готового Telegram UI kit), что
даёт более «фирменный», менее стоковый вид. Решено перенять этот стек, а не только отдельные
визуальные паттерны.

В этой же сессии обнаружен и исправлен независимый баг: `@telegram-apps/telegram-ui` резолвит
свои цвета как `var(--tgui--bg_color)` → `var(--tg-theme-*, тёмный фолбэк)`, из-за чего реальная
светлая тема Telegram-клиента перебивала `AppRoot appearance="dark"` для нативных компонентов
(Textarea, Modal). При переходе на полностью кастомные компоненты эта проблема отпадает сама
по себе, так как никто больше не читает `--tg-theme-*`.

## Архитектура и деплой

- Новая директория `frontend-next/` в репозитории `ai-hub-bot`, отдельный `package.json`,
  Next.js (App Router). Старая `frontend/` (Vite) остаётся нетронутой до полного переключения,
  затем удаляется одним коммитом.
- Next.js работает как **полноценный Node-сервер** (не static export) — выбор пользователя,
  ради доступности SSR/API routes/middleware на будущее.
  - **Важная оговорка**: авторизация в Mini App идёт через `window.Telegram.WebApp.initData`,
    доступный только в браузере — не через куки/JWT. Поэтому персонализированные данные
    (`MeContext`, баланс, тарифы) в любом случае остаются client-side (`"use client"`), SSR
    не даёт здесь персонализированного рендера с первого байта. Next-сервер даёт гибкость на
    будущее (API routes, middleware), но не «бесплатный» SSR для текущих данных пользователя.
- Топология деплоя: **два отдельных Render web service**:
  - `ai-hub-frontend` — Next.js, Node-рантайм.
  - `ai-hub-backend` — существующий FastAPI-сервис, бизнес-логика не меняется.
  - По аналогии с уже существующим разделением skycore-landing / skycore-frontend.
- FastAPI получает `CORS allow_origins=[FRONTEND_URL]` (сейчас фронт и бэк на одном origin,
  после миграции — на разных).
- `frontend-next/src/api/client.ts`: единственное содержательное изменение в API-слое —
  `fetch(path)` → `fetch(process.env.NEXT_PUBLIC_API_URL + path)`. Все типы (`ModelOut`,
  `MeOut`, `LimitsOut` и т.д.) переносятся без изменений.
- `WEBAPP_URL` бота переключается на новый `ai-hub-frontend` URL одним деплоем в конце миграции
  (Big Bang — см. ниже).

## Роутинг

Сейчас — `HashRouter` из `react-router-dom` (`#/generate-image`), необходимый только потому,
что раздача была чисто статической. С полноценным Next-сервером хэш-роутинг не нужен —
переход на обычные пути через App Router:

| Текущий экран | Новый путь |
|---|---|
| Home.tsx | `app/page.tsx` |
| Trends.tsx | `app/trends/page.tsx` |
| MyAccount.tsx | `app/account/page.tsx` |
| Chat.tsx | `app/chat/page.tsx` |
| GenerateImage.tsx | `app/generate-image/page.tsx` |
| Tariffs.tsx | `app/tariffs/page.tsx` |
| Referral.tsx | `app/referral/page.tsx` |
| Settings.tsx | `app/settings/page.tsx` |
| admin/* (6 файлов) | `app/admin/*/page.tsx` |

Разметка `Shell` (таббар снизу для `/`, `/trends`, `/account`; FAB на чат; полноэкранный режим
для `/chat` и `/generate-image` без таббара/FAB) переезжает в `app/layout.tsx` практически без
изменений в логике, меняется только источник текущего пути (`usePathname` вместо
`useLocation().pathname`).

## Стили и компоненты

- **Стили**: Tailwind CSS v4 (новый CSS-first конфиг через `@theme`, как у конкурента) вместо
  `global.css` с ручными custom properties. Текущая палитра переносится как токены:
  `--bg-deep`, `--bg-elevated`, `--surface`, `--border-soft`, `--foreground`,
  `--foreground-muted`, `--brand-1/2/3`, `--brand-gradient`, радиусы, тени. Визуальный бренд не
  меняется — меняется только механизм задания стилей.
- **UI-примитивы**: убираем `@telegram-apps/telegram-ui` полностью. Взамен — свои компоненты в
  `frontend-next/src/components/ui/`: `sheet.tsx`, `switch.tsx`, `dialog.tsx`, `input.tsx`,
  `textarea.tsx`, `button.tsx`, `list-row.tsx` — обёртки над `@radix-ui/react-dialog`,
  `@radix-ui/react-switch` и т.п., стилизованные Tailwind-классами под текущий
  тёмный/glass-дизайн. 0% чужого готового визуального кода — Radix даёт только безголовую
  доступность (focus trap, aria, жесты), вся стилизация своя.
- Побочный эффект: фикс `forceDarkTheme()` в `lib/telegram.ts` (сделанный в этой же сессии)
  становится не нужен — без `telegram-ui` никто не резолвит цвета через `--tg-theme-*`.

## Порядок реализации (одна ветка, один релиз — Big Bang)

Пользователь явно выбрал полный перенос одним релизом, без гибридного состояния в проде.
Внутри ветки `feature/nextjs-migration` порядок задач:

1. Скаффолд Next.js-проекта (App Router, TypeScript) + Tailwind v4 + перенос токенов дизайна.
2. UI-примитивы на Radix + Tailwind (список выше).
3. Общий слой без UI: `api/client.ts` (абсолютный URL бэкенда), `lib/telegram.ts`,
   `lib/imageCost.ts`, `lib/trendStyles.ts`, `context/MeContext.tsx` — переносятся почти без
   изменений в логике, только импорты/пути.
4. `app/layout.tsx` — таббар, FAB, полноэкранные роуты.
5. Экраны по возрастанию сложности: Home → Trends → MyAccount → Tariffs → Referral → Settings
   → Chat → GenerateImage (самый сложный: PhotoUploadBox, AspectRatioSheet, 3-кнопочный
   резолюшн-пикер) → 6 админ-экранов (наименее критичны к визуальной полировке, но требуют
   такой же замены Input/Switch/Select на свои Radix-компоненты).
6. `render.yaml`: новый сервис `ai-hub-frontend`; CORS на FastAPI.
7. Сквозная проверка через Playwright (см. «Тестирование»).
8. Деплой обоих сервисов, переключение `WEBAPP_URL` в `.env` бота, мониторинг.

## Обработка ошибок

- 401 / невалидный `initData` → отдельный экран «Не удалось войти» с сообщением и кнопкой
  «Перезапустить» (паттерн, подсмотренный у конкурента: тёмный фон, короткий текст, одна CTA),
  вместо дефолтного белого экрана Next.js.
- Сетевые/5xx-ошибки внутри экрана — как сейчас: инлайновое сообщение под конкретным действием
  (пример — блок ошибки в GenerateImage), паттерн переносится без изменений.
- `app/error.tsx` на уровне layout — глобальный error boundary на непойманные исключения
  рендера, стилизованный под тёмную тему проекта, а не дефолтный оверлей Next.js.

## Тестирование

- Типы: `tsc --noEmit` — как сейчас, без изменений в подходе.
- Линт: переход с `oxlint` на `eslint-config-next` (входит в Next из коробки) — покрывает
  специфичные для App Router правила (`use client`/`use server` границы, hooks), которых
  `oxlint` не проверяет.
- Ручная/E2E-проверка: Playwright с замоканным `window.Telegram.WebApp` и подписанным
  `initData` (HMAC через `BOT_TOKEN` из `.env`, `auth_date` регенерируется на каждый прогон) —
  тот же приём, что уже использовался в этой сессии для проверки экрана GenerateImage. Прогнать
  все 14 экранов, проверить тёмную тему по всему приложению и ключевые сценарии: генерация
  картинки, кнопка оплаты тарифа, загрузка списков в 6 админ-экранах.
- Бэкенд не меняется — новое здесь только проверка, что CORS реально работает между доменом
  фронта и бэкенда до переключения `WEBAPP_URL` в проде.

## Явно вне рамок этой миграции

- Любые новые фичи, подсмотренные у конкурента ранее в этой сессии (галерея Trends с фильтрами
  по категориям, разбивка кредитов на Image/Video/Music, видео/музыка-генерация) — это
  отдельная задача поверх уже существующей архитектуры `Trends.tsx`/кредитов, не часть переноса
  стека. Здесь переносится текущий функционал 1:1, только на новом стеке.
- Изменение схемы БД, платёжной логики, бота (aiogram-часть) — не затрагиваются.
