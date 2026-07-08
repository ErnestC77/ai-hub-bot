# Кредитная система v2 — Фаза 4: пакеты кредитов + оплата

## Контекст

Фазы 1–3 (все смёрждены) построили движок кредитов, OpenRouter (текст) и
fal.ai (изображения/видео). Эта фаза чинит и переписывает единственную ещё
не переписанную часть флоу — покупку кредитов: `activate_paid_payment`,
`PaymentGateway`/`YooKassaPaymentService`/`TelegramStarsPaymentService`,
`app/webhooks/yookassa.py`, `app/bot/handlers/payments.py`,
`app/api/routes/payments.py` — всё это уже сломано (импортирует удалённые в
фазе 1 `Tariff`/`Subscription`/`UsageLimit` и удалённый в фазе 1
dataclass-модуль `app.services.credit_packages`).

Полное ТЗ: `C:\Users\mccaq\Desktop\promt.md`. Backend-only, без изменений
`frontend-next` (то же решение, что и в фазах 2–3).

## Решения, принятые до этого документа

- **Полная замена** платёжного флоу под тарифы/подписки: единственный
  сценарий покупки теперь — пакет кредитов (`credit_package_code`).
  `PaymentGateway.create_payment(tariff)` убирается из интерфейса;
  `Subscription`/`UsageLimit`/`Tariff` нигде больше не создаются.
- **Telegram Stars остаётся** наряду с YooKassa — уже рабочая (до поломки)
  интеграция (инвойсы, `pre_checkout_query`, `successful_payment`, возврат
  через `bot.refund_star_payment`). Новой таблице `credit_packages` (фаза 1)
  добавляется `price_stars`.
- **`Payment.tariff_id` удаляется** — мёртвая колонка с фазы 1 (FK уже снят
  той миграцией), `Payment` теперь всегда только про
  `credit_package_code`.
- **Добавляется `CryptoPaymentGateway`-заглушка**: реализует интерфейс
  `PaymentGateway` (новый `PaymentProvider.crypto`), но без интеграции с
  реальным процессором — `create_credit_payment` создаёт `Payment(status=
  created)` с инструкцией оплаты в `payment_url`, `check_payment_status`
  просто читает текущий статус из БД (внешнего API нет),
  `refund_payment` — `NotImplementedError` с явным комментарием.
  Подтверждение оплаты — ручное (админ вызывает `grant_credits` напрямую или
  через будущую admin-команду фазы 5), не автоматический webhook.
- **`worker.py` чинится в этой же фазе**: удаляются `expire_subscriptions`/
  `warn_expiring_subscriptions` (тарифные job'ы, концепция ушла),
  `poll_pending_yookassa_payments` переписывается под новый
  `ActivationResult` (без `.subscription`), и подключается уже готовая
  `refund_stale_reserved_requests` из фазы 3 (там был оставлен TODO-
  комментарий именно на этот случай).

## Модель данных

### Миграция: `credit_packages.price_stars` + удаление `payments.tariff_id`

```python
price_stars: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
```

Сиды пяти пакетов получают `price_stars` по курсу `≈ price_rub / 2`
(округление до целого) — тот же PLACEHOLDER-подход, что и у
`provider_model_id`/цен OpenRouter/fal.ai в фазах 1–2: приблизительное
значение, редактируемое админом в фазе 5, не точный биржевой курс:

| code | price_rub | price_stars |
|---|---|---|
| start | 149 | 75 |
| basic | 599 | 300 |
| plus | 1290 | 645 |
| pro | 2990 | 1495 |
| business | 5990 | 2995 |

Одна миграция (revision поверх текущего head `d5e6f7a8b9c0`): `ADD COLUMN
credit_packages.price_stars`, `DROP COLUMN payments.tariff_id` (FK-constraint
на эту колонку уже снят миграцией фазы 1 — `payments.tariff_id` там осталась
как обычный `Integer` без FK, так что здесь достаточно прямого
`DROP COLUMN`, без предварительного `DROP CONSTRAINT`).

### `app/db/enums.py`

`PaymentProvider` получает новое значение `crypto` (наряду с существующими
`telegram_stars`, `yookassa`, `manual`, `promo`).

## Удаляемые/переписываемые файлы

- `app/services/payments/activation.py` — переписывается: убирается весь
  `Subscription`/`UsageLimit`/`Tariff`-путь, остаётся только начисление
  кредитов через `grant_credits` (фаза 1, сигнатура `grant_credits(session,
  user_id, amount, *, reason, tx_type=CreditTxType.purchase)` — параметра
  `payment_id` там больше нет, связь платёж→начисление — через
  `metadata_json={"payment_id": payment.id}` в транзакции, по дизайну
  фазы 1). Идемпотентный паттерн (`SELECT ... FOR UPDATE` + проверка
  `status == succeeded`) сохраняется без изменений — он не завязан на
  Tariff.
- `app/services/payments/gateway.py` — `PaymentGateway.create_payment`
  убирается из интерфейса; `create_credit_payment` меняет тип `package`
  с `app.services.credit_packages.CreditPackage` (dataclass, удалён) на
  `app.db.models.CreditPackage` (DB-модель фазы 1).
- `app/services/payments/yookassa_service.py`,
  `app/services/payments/stars_service.py` — убирается метод
  `create_payment` (тариф), `create_credit_payment` переписывается под
  новую `CreditPackage` (`title` вместо `name`, `price_stars` уже есть).
- `app/services/payments/crypto_service.py` (новый) — `CryptoPaymentGateway`.
- `app/webhooks/yookassa.py` — убирается ветка
  `if result and result.subscription`, остаётся только
  `result.credits_granted`.
- `app/bot/handlers/payments.py` — убирается сообщение про подписку.
- `app/api/routes/payments.py` — убираются `/payments/stars/create`,
  `/payments/yookassa/create` (создание подписки) и весь
  `_get_tariff_or_404`; `/credits/packages` теперь читает активные
  `CreditPackage` из БД (`is_active=True`), а не статический список;
  добавляется `POST /api/payments/credits/crypto/create`.
- `app/services/notification_service.py` — убираются
  `notify_payment_success`/`notify_subscription_expiring`/
  `notify_subscription_expired` (тарифные, недостижимый код после
  переписывания вызывающих мест); `notify_credits_purchase` остаётся как
  есть.
- `app/worker.py` — убираются `expire_subscriptions`,
  `warn_expiring_subscriptions` и их job'ы в `create_scheduler()`;
  `poll_pending_yookassa_payments` обновляется под новый
  `ActivationResult` (только `credits_granted`); добавляется новый job
  `reconcile_stale_media_reserves` (обёртка над
  `media_generation_service.refund_stale_reserved_requests`),
  запускаемый раз в 5–10 минут.

## API-поверхность (без изменений в форме, под новые модели)

- `GET /api/credits/packages` — `CreditPackageOut(code, title, credits,
  price_rub, price_stars)` из БД.
- `POST /api/payments/credits/{yookassa,stars,crypto}/create` —
  `{package_code}` → `{payment_id, invoice_link?, confirmation_url?}`.
- `GET /api/payments/{id}/status`, `GET /api/payments/history` — без
  изменений в контракте.

## Явно вне рамок фазы 4

Реальная интеграция с крипто-процессором (только заглушка-интерфейс),
админ-команды управления пакетами/платежами (фаза 5), `frontend-next`.

## Тесты

- `tests/services/payments/test_activation.py` (новый) — идемпотентная
  активация (`SELECT ... FOR UPDATE`, повторный webhook не начисляет
  дважды), `grant_credits` вызывается с правильными `amount`/`reason`,
  `metadata_json` содержит `payment_id`.
- `tests/services/payments/test_gateway.py` — `YooKassaPaymentService`/
  `TelegramStarsPaymentService`/`CryptoPaymentGateway` под новой
  `CreditPackage`, замоканные внешние SDK (`yookassa`, `aiogram bot`), как
  уже принято в этом проекте.
- `tests/api/test_payments_routes.py` (новый, взамен фактически
  нерабочего текущего покрытия) — `/api/credits/packages`,
  `/api/payments/credits/*/create`, `/api/payments/{id}/status`,
  `/api/payments/history`.
- `tests/db/test_credit_schema_v2.py` — round-trip тест на
  `credit_packages.price_stars`.
- `tests/test_worker.py` (новый — тестов на `worker.py` в проекте пока нет) —
  `poll_pending_yookassa_payments` без Tariff-веток,
  `reconcile_stale_media_reserves` вызывает `refund_stale_reserved_requests`.
