from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import User
from app.db.session import get_session_dependency
from app.services.telegram_auth import InvalidInitDataError, parse_and_validate_init_data
from app.services.user_service import get_or_create_user

get_db = get_session_dependency


async def current_user(
    x_telegram_init_data: str = Header(default="", alias="X-Telegram-Init-Data"),
    session: AsyncSession = Depends(get_db),
) -> User:
    try:
        data = parse_and_validate_init_data(x_telegram_init_data, settings.bot_token)
    except InvalidInitDataError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    tg_user = data.get("user") or {}
    tg_id = tg_user.get("id")
    if tg_id is None:
        raise HTTPException(status_code=401, detail="no user in initData")

    user = await get_or_create_user(
        session,
        telegram_id=tg_id,
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
        language_code=tg_user.get("language_code"),
    )
    if user.is_blocked:
        raise HTTPException(status_code=403, detail="user is blocked")
    return user


async def current_admin(user: User = Depends(current_user)) -> User:
    # ADMIN_IDS -- источник правды в рантайме, а не кэшированный флаг is_admin:
    # удаление ID из окружения сразу отзывает доступ (флаг в БД мог остаться
    # true с момента создания юзера). get_or_create_user его ре-синхронит для
    # витрины (кнопка «Админка»), но авторизация опирается на env напрямую.
    if user.telegram_id not in settings.admin_id_list:
        raise HTTPException(status_code=403, detail="not an admin")
    return user
