"""Надёжное восстановление ответа чата после закрытия приложения.

Chat синхронный: если юзер закрыл приложение в те секунды, пока ответ
генерировался, HTTP-запрос обрывается и ответ теряется, а кредиты уже списаны.
Детект разрыва (is_disconnected) -- best-effort с миллисекундной гонкой; здесь
гонки нет: ответ сохраняется на сервере В МОМЕНТ генерации, независимо от того,
дошёл ли HTTP до клиента, и приложение забирает его при повторном открытии.

Хранилище -- Redis со сроком жизни (не Postgres): ответы намеренно не оседают
в БД (privacy). Запись per-user, короткий TTL, читает только владелец, дедуп
на клиенте по id -> нормально полученный ответ не покажется дважды.
"""

import json
import logging

from app.redis_client import redis_client

logger = logging.getLogger(__name__)

RECENT_TTL_SECONDS = 60 * 60  # 1ч: дольше «пропущенный ответ» держать незачем
RECENT_MAX = 10  # последние N ответов на юзера (хвост обрезаем)


def _key(user_id: int) -> str:
    return f"chat_recent:{user_id}"


async def store_recent_answer(user_id: int, message_id: str, prompt: str, answer: str) -> None:
    """Кладёт ответ в недавние сразу после генерации. Не критичный путь --
    сбой Redis не должен ронять уже успешный ответ (клиент его и так получит,
    если соединение живо)."""
    try:
        key = _key(user_id)
        entry = json.dumps({"id": message_id, "prompt": prompt, "answer": answer}, ensure_ascii=False)
        await redis_client.lpush(key, entry)
        await redis_client.ltrim(key, 0, RECENT_MAX - 1)
        await redis_client.expire(key, RECENT_TTL_SECONDS)
    except Exception:  # noqa: BLE001
        logger.warning("failed to store recent chat answer for user_id=%s", user_id, exc_info=True)


async def get_recent_answers(user_id: int) -> list[dict]:
    """Недавние ответы юзера (для мержа при открытии чата). Пустой список при
    сбое Redis -- восстановление просто не сработает, ответ не задублируется."""
    try:
        raw = await redis_client.lrange(_key(user_id), 0, RECENT_MAX - 1)
    except Exception:  # noqa: BLE001
        logger.warning("failed to read recent chat answers for user_id=%s", user_id, exc_info=True)
        return []
    result = []
    for item in raw:
        try:
            result.append(json.loads(item))
        except (ValueError, TypeError):
            continue
    return result
