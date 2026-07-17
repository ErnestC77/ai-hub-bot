"""Надёжное восстановление ответа чата (Redis recent + дедуп по id)."""

import os

os.environ.setdefault("BOT_TOKEN", "123456:TEST-token")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test")

import pytest

from app.services import chat_recovery_service as crs


class FakeRedis:
    """In-memory list-хранилище: lpush/ltrim/lrange/expire."""

    def __init__(self, broken=False):
        self.broken = broken
        self.store: dict[str, list[str]] = {}
        self.expires: dict[str, int] = {}

    async def lpush(self, key, value):
        if self.broken:
            raise RuntimeError("redis down")
        self.store.setdefault(key, []).insert(0, value)

    async def ltrim(self, key, start, end):
        if key in self.store:
            self.store[key] = self.store[key][start : end + 1]

    async def expire(self, key, ttl):
        self.expires[key] = ttl

    async def lrange(self, key, start, end):
        if self.broken:
            raise RuntimeError("redis down")
        return self.store.get(key, [])[start : end + 1]


async def test_store_then_get_roundtrips(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(crs, "redis_client", fake)

    await crs.store_recent_answer(1, "abc", "вопрос", "ответ")
    recent = await crs.get_recent_answers(1)

    assert recent == [{"id": "abc", "prompt": "вопрос", "answer": "ответ"}]
    assert crs._key(1) in fake.expires  # TTL проставлен


async def test_newest_first_and_trimmed(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(crs, "redis_client", fake)

    for i in range(crs.RECENT_MAX + 3):
        await crs.store_recent_answer(1, f"id{i}", f"q{i}", f"a{i}")
    recent = await crs.get_recent_answers(1)

    assert len(recent) == crs.RECENT_MAX  # хвост обрезан
    assert recent[0]["id"] == f"id{crs.RECENT_MAX + 2}"  # свежий сверху


async def test_per_user_isolation(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(crs, "redis_client", fake)

    await crs.store_recent_answer(1, "a", "q1", "a1")
    await crs.store_recent_answer(2, "b", "q2", "a2")

    assert [r["id"] for r in await crs.get_recent_answers(1)] == ["a"]
    assert [r["id"] for r in await crs.get_recent_answers(2)] == ["b"]


async def test_store_failure_is_swallowed(monkeypatch):
    """Сбой Redis не роняет ответ (клиент получит его по HTTP, если жив)."""
    monkeypatch.setattr(crs, "redis_client", FakeRedis(broken=True))
    await crs.store_recent_answer(1, "x", "q", "a")  # не должно бросить


async def test_get_failure_returns_empty(monkeypatch):
    monkeypatch.setattr(crs, "redis_client", FakeRedis(broken=True))
    assert await crs.get_recent_answers(1) == []
