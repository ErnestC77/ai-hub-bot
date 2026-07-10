from app.bot.instance import bot
from app.bot.keyboards import webapp_open_kb
from app.config import settings


async def _send(telegram_id: int, text: str) -> None:
    try:
        await bot.send_message(
            telegram_id, text, reply_markup=webapp_open_kb("Открыть AI Hub", settings.frontend_url)
        )
    except Exception:
        # Пользователь мог заблокировать бота -- не критично.
        pass


async def notify_credits_purchase(telegram_id: int, credits: int) -> None:
    await _send(telegram_id, f"✅ Оплата прошла! Начислено {credits} кредитов.")
