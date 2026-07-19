from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message
from sqlalchemy import select

from app.bot.keyboards import webapp_open_kb
from app.config import settings
from app.db.models import User
from app.db.session import get_session
from app.services.referral_service import record_referral
from app.services.user_service import get_or_create_user

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    async with get_session() as session:
        existing = (
            await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        ).scalar_one_or_none()
        is_new = existing is None

        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            language_code=message.from_user.language_code,
            # Рекламная метка из deep-link (t.me/bot?start=ads_X); ref_* сервис
            # нормализует в "referral". Применяется только при создании юзера.
            source=command.args,
        )

        if is_new and command.args and command.args.startswith("ref_"):
            try:
                referrer_telegram_id = int(command.args.removeprefix("ref_"))
                await record_referral(session, referrer_telegram_id, user)
            except ValueError:
                pass

    await message.answer(
        "Привет! Здесь доступ к нескольким нейросетям, тарифам и инструментам.\n"
        "Открывай приложение, чтобы начать 👇",
        reply_markup=webapp_open_kb("🤖 Открыть AI Hub", settings.frontend_url),
    )
