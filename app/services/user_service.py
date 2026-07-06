from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import User


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
    else:
        user.username = username
        user.first_name = first_name
        if language_code:
            user.language_code = language_code

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
