"""Доставка результата генерации в бот (send_media_result)."""

import os

os.environ.setdefault("BOT_TOKEN", "123456:TEST-token")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test")

import pytest

from app.db.enums import ModelCategory
from app.services import notification_service as ns


class FakeBot:
    def __init__(self, fail_media=False):
        self.fail_media = fail_media
        self.photos = []
        self.videos = []
        self.messages = []

    async def send_photo(self, chat_id, photo, caption=None, reply_markup=None):
        if self.fail_media:
            raise RuntimeError("cdn down")
        self.photos.append((chat_id, photo, caption))

    async def send_video(self, chat_id, video, caption=None, reply_markup=None):
        if self.fail_media:
            raise RuntimeError("cdn down")
        self.videos.append((chat_id, video, caption))

    async def send_message(self, chat_id, text, reply_markup=None):
        self.messages.append((chat_id, text))


async def test_photo_result_sent_as_photo(monkeypatch):
    bot = FakeBot()
    monkeypatch.setattr(ns, "bot", bot)

    await ns.send_media_result(42, ModelCategory.image, "https://cdn/out.png", "a bear")

    assert len(bot.photos) == 1
    chat_id, url, caption = bot.photos[0]
    assert chat_id == 42
    assert url == "https://cdn/out.png"
    assert "a bear" in caption
    assert bot.messages == []  # фолбэк не понадобился


async def test_video_result_sent_as_video(monkeypatch):
    bot = FakeBot()
    monkeypatch.setattr(ns, "bot", bot)

    await ns.send_media_result(7, ModelCategory.video, "https://cdn/out.mp4", "a cat")

    assert len(bot.videos) == 1 and bot.videos[0][0] == 7
    assert bot.photos == []


async def test_media_failure_falls_back_to_link(monkeypatch):
    """CDN недоступен / файл велик -> результат всё равно доставлен текстом
    с прямой ссылкой (иначе потеря из-за формата доставки)."""
    bot = FakeBot(fail_media=True)
    monkeypatch.setattr(ns, "bot", bot)

    await ns.send_media_result(42, ModelCategory.image, "https://cdn/out.png", "a bear")

    assert bot.photos == []
    assert len(bot.messages) == 1
    chat_id, text = bot.messages[0]
    assert chat_id == 42
    assert "https://cdn/out.png" in text


async def test_total_failure_is_swallowed(monkeypatch):
    """Юзер заблокировал бота: и медиа, и текст падают -> тихо, без исключения
    наружу (доставка не должна ронять уже успешную генерацию)."""
    bot = FakeBot(fail_media=True)

    async def _boom(*a, **k):
        raise RuntimeError("bot blocked")

    bot.send_message = _boom
    monkeypatch.setattr(ns, "bot", bot)

    # не должно бросить
    await ns.send_media_result(42, ModelCategory.image, "https://cdn/out.png", "x")
