import logging

from app.bot.instance import bot
from app.bot.keyboards import webapp_open_kb
from app.config import settings
from app.db.enums import ModelCategory

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


async def send_media_result(
    telegram_id: int, category: ModelCategory, result_url: str, prompt_preview: str
) -> None:
    """Доставляет готовый результат генерации в личный чат с ботом.

    Это ГЛАВНАЯ защита от потери: результат приходит в чат независимо от того,
    открыто ли ещё Mini App -- юзер мог закрыть его во время генерации. Ссылка
    fal-CDN отдаётся Telegram'у строкой, он сам её скачивает.

    Медиа-отправка может упасть (CDN недоступен, слишком большой файл, юзер
    заблокировал бота). На этот случай -- фолбэк текстом с прямой ссылкой:
    результат не должен потеряться из-за формата доставки.
    """
    is_video = category == ModelCategory.video
    caption = (
        f"✅ Готово! {'🎬 Ваше видео' if is_video else '🖼 Ваше фото'} по запросу:\n{prompt_preview}"
    )
    kb = webapp_open_kb("Открыть AI Hub", settings.frontend_url)
    try:
        if is_video:
            await bot.send_video(telegram_id, result_url, caption=caption, reply_markup=kb)
        else:
            await bot.send_photo(telegram_id, result_url, caption=caption, reply_markup=kb)
    except Exception:
        logger.warning("media send failed for %s, falling back to link", telegram_id, exc_info=True)
        try:
            await bot.send_message(telegram_id, f"{caption}\n{result_url}", reply_markup=kb)
        except Exception:
            logger.warning("media result delivery fully failed for %s", telegram_id, exc_info=True)
