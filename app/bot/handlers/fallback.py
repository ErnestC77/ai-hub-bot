from aiogram import Router
from aiogram.types import Message

from app.bot.keyboards import webapp_open_kb
from app.config import settings
from app.redis_client import redis_client

router = Router(name="fallback")

THROTTLE_SECONDS = 30


@router.message()
async def handle_any_other_message(message: Message) -> None:
    key = f"fallback_throttle:{message.from_user.id}"
    if not await redis_client.set(key, "1", nx=True, ex=THROTTLE_SECONDS):
        return

    await message.answer(
        "Все функции бота — в приложении 👇",
        reply_markup=webapp_open_kb("🤖 Открыть AI Hub", settings.frontend_url),
    )
