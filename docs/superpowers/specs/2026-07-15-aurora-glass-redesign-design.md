# Design spec: Aurora Glass redesign (frontend-next)

Источник дизайна: Claude Design проект «AI-hub-bot фронт»
(`https://claude.ai/design/p/4906e2e0-6029-4ad9-8022-bcddd7f915da`).
Локальные копии: `docs/design/AI-Hub-Redesign.dc.html` (прототип, 961 строка),
`docs/design/HANDOFF.md` (README дизайнера), `docs/design/image-slot.js`.

Реализуем **только направление 1b «Aurora Glass»**. Направления 1a (Mono Brutalist)
и 1c (Warm Luminous) в прототипе — отклонённые альтернативы, не трогаем.

Где что в прототипе (номера строк `docs/design/AI-Hub-Redesign.dc.html`):

| Что | Строки |
|---|---|
| Тур 3a — интерактивный прототип (вся навигация, шторки, карусели) | 55–313 |
| Тур 2 — Aurora Glass раскатан на все экраны (2a–2i, статичные раскладки) | 314–687 |
| 1b Aurora Glass — эталон визуального направления | 738–786 |
| `<script data-dc-script>`, `class Component` — состояние прототипа | 836–959 |

---

## 1. Главные правила (читать до кода)

1. **Бэкенд — источник правды по данным. Дизайн — источник правды по визуалу.**
   Хэндофф писался без доступа к бэкенду, его «Suggested API Contract» — выдумка.
   Реальные типы: `frontend-next/src/api/client.ts`. При конфликте побеждает бэкенд,
   визуал адаптируем.
2. **Не переносить цены и формулы из прототипа.** В макете `vCost = round(duration × 4 × mult)`
   (mult 1 / 1.5 / 2.5) и «5 💎 за фото», «1 💎 за запрос» — это выдуманные дизайнером числа.
   Реальная стоимость приходит с бэка: `ModelOut.min_credits` / `recommended_credits`,
   а точная цена — из 409-гейта `ConfirmationRequiredError.estimatedCredits`.
   Из макета берём только то, **как цена выглядит**, а не чему равна.
3. **Вся текущая логика данных сохраняется как есть.** Это перекраска: `api.*`-вызовы,
   `useMe()`, поллинг `generationStatus`, обработка `ConfirmationRequiredError`,
   загрузка файлов — не переписывать. Меняем разметку и классы, не поведение.
4. **Роуты остаются роутами.** В макете чат/генерация — bottom sheets поверх экрана.
   У нас это `/chat`, `/generate-image`, `/generate-video`. Переезд на оверлеи сломал бы
   Telegram BackButton, deep-links и e2e. Поэтому: **оставляем роуты, одеваем страницы
   как шторки** — хват-полоска сверху, шапка (иконка + название модели + подпись + ✕),
   анимация появления `sheetUp`, радиус 22–26px сверху. Кнопка ✕ = `router.back()`.
5. **Не трогать чужие файлы.** Ниже таблица владения. Правит только свой список.
6. **Ничего не выдумывать в UI, чего нет в данных.** Если экран из макета показывает
   поле, которого нет в API — см. таблицу маппинга §4, там уже решено чем заменить.

---

## 2. Design tokens

Живут в `frontend-next/src/app/globals.css`, блок `@theme` (Tailwind v4).

**Стратегия: имена токенов сохраняем, значения меняем.** Компоненты уже ходят через
`bg-surface`, `text-foreground-muted`, `border-border-soft`, `shadow-glow`,
`var(--brand-gradient)` — если поменять значения, большая часть редизайна случится сама.

| Токен | Было (старый стиль) | Стало (Aurora Glass) |
|---|---|---|
| `--color-bg-deep` | `#050506` | `#0a0716` |
| `--color-bg-elevated` | `#0e0e12` | `#0d0d12` |
| `--color-surface` | `rgba(255,255,255,.06)` | `rgba(255,255,255,.06)` (без изменений) |
| `--color-surface-strong` | `rgba(255,255,255,.1)` | `rgba(255,255,255,.1)` (без изменений) |
| `--color-border-soft` | `rgba(255,255,255,.09)` | `rgba(255,255,255,.1)` |
| `--color-foreground` | `#f5f5f7` | `#eef0ff` |
| `--color-foreground-muted` | `#96979f` | `rgba(238,240,255,.6)` |
| `--color-brand-1` | `#ff5f6d` | `#8b5cff` |
| `--color-brand-2` | `#ff2d78` | `#35e0e6` |
| `--color-brand-3` | `#b721ff` | — (удалить, градиент двухцветный) |
| `--shadow-glow` | `0 8px 24px rgba(255,45,120,.35)` | `0 10px 24px rgba(139,92,255,.5)` |
| `--ease-out` | `cubic-bezier(.16,1,.3,1)` | без изменений |

Новые токены:

```
--color-foreground-dim: rgba(238,240,255,.45);   /* лейблы, «листай →» */
--color-accent-violet: #8b5cff;
--color-accent-cyan:   #35e0e6;
--shadow-glow-cyan: 0 10px 24px rgba(53,224,230,.45);  /* CTA видео-шторки */
--radius-screen: 38px;
--radius-sheet: 24px;   /* шторки/крупные карточки 22–26 */
--radius-lg: 20px;
--radius-md: 14px;
```

`:root`:
```
--brand-gradient: linear-gradient(135deg, #8b5cff, #35e0e6);
--app-bg:
  radial-gradient(120% 80% at 15% 0%, #1b1140 0%, #0a0716 55%),
  radial-gradient(90% 70% at 100% 30%, #0b2a3a 0%, rgba(10,7,22,0) 60%);
```
`body` получает `background: var(--app-bg); background-attachment: fixed;`
(подложка одна на всё приложение, не перерисовывается при скролле).

**Стекло (glass)** — повторяющийся паттерн, вынести в утилиту `.glass` в globals.css:
`background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1); backdrop-filter: blur(20px);`

**Бренд-градиенты моделей** (карточки на Home) — в `src/lib/modelStyles.ts` (новый файл,
владелец — агент Home), ключ = `ModelOut.code`:
```
ChatGPT:    linear-gradient(135deg,#10a37f,#0d7a5f)
Claude:     linear-gradient(135deg,#d97757,#b85c3f)
Gemini:     linear-gradient(135deg,#4285f4,#9b72f2)
Flux:       linear-gradient(135deg,#8b5cff,#5a34c9)
Midjourney: linear-gradient(135deg,#a86bff,#6b3fd6)
Kling:      linear-gradient(135deg,#35e0e6,#1b8fa0)
Runway:     linear-gradient(135deg,#22d3ee,#0e7f96)
```
Модели приходят из `api.models(category)` и настраиваются в админке, поэтому список
**не хардкодить**: сопоставление code → градиент делать по словарю с дефолтом
`var(--brand-gradient)` для незнакомого кода.

## 3. Типографика

**Шрифт: Onest** (веса 300/400/500/600/700) через `next/font/google` в `src/app/layout.tsx`,
переменной подключить в `@theme`. Заменяет и body-шрифт, и `.heading-font`
(был Space Grotesk, который к тому же нигде не подгружался — то есть не работал никогда).

> **Отступление от макета, сделано осознанно.** Хэндофф требует **Sora**, но у Sora
> **нет кириллицы**. Дизайнер этого не заметил, потому что в макете почти весь текст —
> латиница и цифры («AI Hub», «GPT-5», «128 💎»), а приложение русскоязычное: с Sora вся
> кириллица молча падала бы на системный шрифт, то есть интерфейс жил бы в двух разных
> шрифтах и выглядел по-разному на iOS и Android. **Onest** — геометрический гротеск с
> полной кириллицей и характером, близким к Sora. Это отступление от буквы макета ради
> его духа. Решение пользователя от 2026-07-15.

`.g-title` / `.heading-font`: `font-weight:600; letter-spacing:-.01em`.

Размеры (px): заголовок экрана 22 · крупная цифра 21–24 · название карточки 14.5 ·
body 12.5–13 · подпись 10.5–11.5 · лейбл-капс 10 (`uppercase; letter-spacing:.08–.1em`).

Радиусы: экран 38 · карточки/шторки 22–26 · карточки 16–20 · пилюли 999 · плитки 11–14.

Нажатие: `.press-scale` уже есть — поправить `scale(.97)` → `scale(.95)` по макету.

---

## 4. Маппинг «дизайн → реальные данные»

Здесь разрешены все расхождения. Отклоняться от этой таблицы нельзя.

| Экран | Что рисует макет | Чего нет в бэкенде | Что делаем |
|---|---|---|---|
| Home | пилюля «128 💎» | — | `me.credits_balance` |
| Home | карусель моделей (7 захардкоженных) | — | `api.models("text"/"image"/"video")`, градиент по code, тег = `display_name` + тип |
| Home | — (баннеров нет) | — | **`HeroCarousel` остаётся** (решение пользователя), перекрасить в Aurora Glass, поставить над секцией «Нейросети». Админка Banners продолжает работать |
| Home | «Сгенерировать фото · от 5 💎» | цены 5 нет | «от N 💎», где N = `min(min_credits)` по image-моделям; нет данных — пилюлю не рисуем |
| Account | «Текущий тариф / Premium» | планов нет вообще | Заменить на карточку кредитов: баланс + «куплено всего» / «потрачено всего» (`total_credits_purchased` / `total_credits_spent`) |
| Account | прогресс «Запросы сегодня 34/100» | дневных лимитов нет | Прогресс-бар оставить визуально, но считать **потрачено / куплено** (`total_credits_spent / total_credits_purchased`) — «Израсходовано» |
| Account | 3 пилюли (Быстрые 66/100, Премиум 12/20, Картинки 8/15) | нет | Убрать. Вместо них — пилюля с `default_model_code` («Модель по умолчанию») |
| Account | «Баланс 128 кредитов» + «+» | — | `me.credits_balance` + «+» открывает `CreditPurchaseSheet` (уже есть) |
| Account | Рефералы: Приглашено 7 / Заработано 140 | — | `api.referral()` → `ReferralOut` |
| Tariffs | подписки Free/Pro/Premium, 299₽/599₽/мес, «Активен», «ХИТ» | подписок нет, они намеренно удалены | **Экрана Tariffs не создаём.** Есть `CreditPurchaseSheet` с `CreditPackageOut` — перекрасить его в стиль макета (карточки планов: название пакета, кредиты, цена ₽/⭐, CTA). Пилюля «💳 Тарифы» на Home открывает эту шторку |
| Tariffs | футер «Отмена в один тап, деньги вернём» | возвратов по подписке нет | Заменить: «Оплата Telegram Stars или картой (ЮKassa)» — вторую фразу выбросить, она про подписки |
| Referral | ссылка `t.me/aihub?start=ref_8842`, 📋, «Поделиться» | — | `ReferralOut` (реальные link/invited/earned), логика копирования и share уже есть |
| Settings | «🌐 Язык ответов → Русский», «🔔 Уведомления» тумблер | **проверить** `api.*` — если эндпоинтов нет, полей нет | Рисовать только то, что реально сохраняется. Нет API — секцию «Предпочтения» не рисовать. Поддержка (`@aihub_support`, `NEXT_PUBLIC_SUPPORT_USERNAME`) и «О приложении» — оставить |
| Chat sheet | сегменты GPT-5 / Claude / Gemini | — | `api.models("text")` → `ModelPicker` (уже есть), сегмент-переключатель по макету |
| Chat sheet | «Чат · 1 💎 за запрос» | цены 1 нет | Цена из выбранной модели (`min_credits`), либо не показывать |
| Image sheet | Flux / Midjourney / DALL·E + 1K/2K/4K | **качества в API нет** | Модели — из `api.models("image")`. **Селектор качества не рисовать** — `api.generate()` его не принимает |
| Video sheet | Kling / Runway / Sora, слайдер 2–15 сек, 720p/1080p/4K, «Создать · N 💎» | качества нет; длительность **есть** (`durationSeconds`) | Модели — `api.models("video")`. Слайдер длительности — оставить (реальный параметр). **Селектор качества не рисовать.** Цена — не считать формулой из макета, показывать `recommended_credits` модели, точную цену даёт 409-гейт |
| Trends | 6 фото-трендов + 6 видео-трендов, захардкожены | — | Оставить как сейчас работает (`TrendCard`, `trendStyles.ts`), перекрасить: карточки 132×172, r18, скрим снизу, бейдж модели, `pointer-events:none` у оверлеев |
| Trends | image-slot (drag-n-drop) | — | Прототипная штука, **не переносить**. Обычные `<img>` / постеры |
| везде | Карусели: ручной drag-to-scroll + колесо→горизонталь | — | **Не переносить.** Это костыль под холст прототипа (сам хэндофф это подтверждает). Нативный `overflow-x:auto` + `scroll-snap` |

Экран «Админка» в макете отсутствует. Админку **не редизайним**: она построена на тех же
`ui/`-примитивах и перекрасится сама через токены. Задача — чтобы она не сломалась.

---

## 5. Владение файлами (параллельные агенты)

Пересечений нет. Каждый агент правит **только** свой список.

| Агент | Файлы |
|---|---|
| **Foundation** (первым, остальные ждут) | `src/app/globals.css`, `src/app/layout.tsx`, `src/components/shell.tsx`, `src/components/ui/*` (все 14) |
| Home | `src/app/page.tsx`, `src/components/HeroCarousel.tsx`, `src/components/ImageStack.tsx`, `src/lib/modelStyles.ts` (новый) |
| Trends | `src/app/trends/page.tsx`, `src/components/TrendCard.tsx`, `src/lib/trendStyles.ts` |
| Account | `src/app/account/page.tsx`, `src/components/account/CreditPurchaseSheet.tsx` |
| Referral+Settings | `src/app/referral/page.tsx`, `src/app/settings/page.tsx` |
| Chat | `src/app/chat/page.tsx`, `src/components/chat/ModelPicker.tsx` |
| Generate | `src/app/generate-image/page.tsx`, `src/app/generate-video/page.tsx`, `src/components/PhotoUploadBox.tsx` |
| e2e (последним) | `e2e/*.spec.ts` |

`src/api/client.ts`, `src/context/MeContext.tsx`, `src/lib/telegram.ts` — **не трогает никто**.
Нужно новое поле от бэка — не выдумывать, а сообщить в отчёте.

## 6. Порядок и приёмка

1. Foundation (последовательно) → `npx tsc --noEmit` зелёный.
2. 6 экранных агентов параллельно.
3. `npx tsc --noEmit` + `npm run lint` зелёные.
4. e2e-агент чинит сьют под новый копирайт (`npm run test:e2e`).

Копирайт берём из макета (русский): «Спросить нейросеть», «Сгенерировать фото»,
«Сгенерировать видео», «✨ Тренды», «Что сейчас вирусится — тапни и повтори» и т.д.
Это ломает текстовые селекторы e2e — ожидаемо, чинится на шаге 4. Где всё равно правим
разметку — ставить `data-testid`, чтобы впредь редизайн не валил тесты.

Вьюпорт макета 300×640; в проде — на всю высоту Mini App (`100vh`, `Telegram.WebApp.expand()`,
уже вызывается в `lib/telegram.ts`). Радиус экрана 38px — это рамка телефона в прототипе,
на реальный полноэкранный Mini App **не переносить**.
