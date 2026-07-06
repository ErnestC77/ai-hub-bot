from datetime import datetime

from app.bot.instance import bot
from app.bot.keyboards import webapp_open_kb
from app.config import settings


async def _send(telegram_id: int, text: str) -> None:
    try:
        await bot.send_message(
            telegram_id, text, reply_markup=webapp_open_kb("Открыть AI Hub", settings.webapp_url)
        )
    except Exception:
        # Пользователь мог заблокировать бота -- не критично.
        pass


async def notify_payment_success(telegram_id: int, tariff_name: str, expires_at: datetime) -> None:
    await _send(
        telegram_id, f"✅ Подписка «{tariff_name}» активирована до {expires_at.strftime('%d.%m.%Y')}."
    )


async def notify_subscription_expiring(telegram_id: int, tariff_name: str, expires_at: datetime) -> None:
    await _send(
        telegram_id,
        f"⏳ Подписка «{tariff_name}» заканчивается {expires_at.strftime('%d.%m.%Y')}. "
        "Продлите её в приложении, чтобы не потерять доступ.",
    )


async def notify_subscription_expired(telegram_id: int, tariff_name: str) -> None:
    await _send(
        telegram_id,
        f"Подписка «{tariff_name}» закончилась. Оформите новую в приложении, чтобы продолжить пользоваться нейросетями.",
    )


async def notify_credits_purchase(telegram_id: int, credits: int) -> None:
    await _send(telegram_id, f"✅ Оплата прошла! Начислено {credits} кредитов.")
