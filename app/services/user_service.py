from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.enums import CreditTxType
from app.db.models import User
from app.services.credit_service import grant_credits
from app.services.settings_service import get_setting


async def _grant_welcome_bonus(session: AsyncSession, user_id: int) -> None:
    """Приветственные кредиты новичку. Тихий no-op при welcome_bonus_credits=0.

    Начисляем ТОЛЬКО на ветке реального создания строки, поэтому повторные
    входы (и проигравший гонку первого входа) бонус не получают -- второй
    подарок тому же telegram_id невозможен без второй строки в users.

    tx_type=welcome_bonus, а не purchase: иначе grant_credits поднял бы
    total_credits_purchased, и подарок открыл бы видео/ultra и снял free-cap
    (см. antifraud_service.check_tier_allowed).
    """
    amount = await get_setting(session, "welcome_bonus_credits", cast=int, default=0)
    if amount <= 0:
        return
    await grant_credits(
        session, user_id, amount,
        reason="welcome bonus", tx_type=CreditTxType.welcome_bonus,
    )
    await session.commit()


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
    language_code: str | None = None,
) -> User:
    user = (
        await session.execute(select(User).where(User.telegram_id == telegram_id))
    ).scalar_one_or_none()

    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            language_code=language_code,
            is_admin=telegram_id in settings.admin_id_list,
        )
        session.add(user)
        try:
            await session.commit()
            await _grant_welcome_bonus(session, user.id)
            return user
        except IntegrityError:
            # Гонка первого входа: webapp открылась и /start пришёл одновременно ->
            # оба вставляют по unique telegram_id, проигравший ловит здесь.
            # Перечитываем чужую строку и идём в общую ветку обновления полей.
            await session.rollback()
            user = (
                await session.execute(select(User).where(User.telegram_id == telegram_id))
            ).scalar_one()

    # Обновляем поля существующего (или созданного параллельно) юзера.
    user.username = username
    user.first_name = first_name
    if language_code:
        user.language_code = language_code
    # Ре-синхрон с ADMIN_IDS: снятие/добавление ID отражается на флаге (для
    # витрины). Авторизация всё равно сверяет env напрямую (current_admin).
    user.is_admin = telegram_id in settings.admin_id_list

    await session.commit()
    return user


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    return (
        await session.execute(select(User).where(User.telegram_id == telegram_id))
    ).scalar_one_or_none()


async def search_users(session: AsyncSession, query: str | None, limit: int = 20) -> list[User]:
    stmt = select(User).order_by(User.created_at.desc()).limit(limit)
    if query:
        conditions = [User.username.ilike(f"%{query}%")]
        if query.isdigit():
            conditions.append(User.telegram_id == int(query))
        stmt = stmt.where(or_(*conditions))
    return list((await session.execute(stmt)).scalars().all())


async def set_blocked(session: AsyncSession, user: User, blocked: bool) -> None:
    user.is_blocked = blocked
    await session.commit()
