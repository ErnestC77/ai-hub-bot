import logging

from app.bot.instance import bot
from app.bot.keyboards import webapp_open_kb
from app.config import settings

logger = logging.getLogger(__name__)


async def _send(telegram_id: int, text: str) -> None:
    try:
        await bot.send_message(
            telegram_id, text, reply_markup=webapp_open_kb("Открыть AI Hub", settings.frontend_url)
        )
    except Exception:
        # Юзер мог заблокировать бота (частый случай) ИЛИ кнопка невалидна из-за
        # пустого frontend_url (баг конфига) -- логируем warning, чтобы второе не
        # пряталось за первым (аудит I6).
        logger.warning("failed to send notification to %s", telegram_id, exc_info=True)


async def notify_credits_purchase(telegram_id: int, credits: int) -> None:
    await _send(telegram_id, f"✅ Оплата прошла! Начислено {credits} кредитов.")
