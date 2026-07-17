"""Инварианты каталога трендов.

Тренды -- захардкоженный список, который правится руками, поэтому опечатка
здесь тихо ломает витрину: дубль слага уводит get_tool на чужой пресет,
а неизвестная категория роняет карточку в текстовую секцию вместо фото/видео.
"""

from pathlib import Path

from app.services.tools_service import TOOLS, get_tool, list_tools

# Фронт роутит по этому полю: image -> /generate-image, video -> /generate-video,
# остальное -> /chat (см. frontend-next/src/app/trends/page.tsx).
VALID_CATEGORIES = {"fast", "medium", "image", "video"}

PREVIEW_DIR = Path(__file__).resolve().parents[2] / "frontend-next" / "public" / "trends"


def test_slugs_are_unique():
    slugs = [t.slug for t in TOOLS]
    assert len(slugs) == len(set(slugs))


def test_every_tool_has_known_category():
    assert {t.recommended_category for t in TOOLS} <= VALID_CATEGORIES


def test_every_tool_has_title_and_prompt_prefix():
    for t in TOOLS:
        assert t.title.strip(), t.slug
        assert t.description.strip(), t.slug
        # Префикс склеивается с текстом пользователя встык, поэтому обязан
        # заканчиваться разделителем -- иначе получится "...на тему: тема" слитно.
        assert t.prompt_prefix.endswith(" "), t.slug


def test_every_tool_has_preview_clip():
    """У каждого тренда есть превью /trends/<slug>.mp4.

    Карточка без файла не падает (TrendCard прячет видео по onError), но
    выглядит пустым градиентом -- то есть тренд молча теряет витрину.
    """
    missing = [t.slug for t in TOOLS if not (PREVIEW_DIR / f"{t.slug}.mp4").is_file()]
    assert not missing, f"нет превью-клипов: {missing}"


def test_get_tool_finds_by_slug_and_returns_none_for_unknown():
    assert get_tool(TOOLS[0].slug) is TOOLS[0]
    assert get_tool("no-such-trend") is None


def test_list_tools_returns_full_catalogue():
    assert list_tools() == TOOLS
