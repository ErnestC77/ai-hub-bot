"""markdown_to_plain: снятие разметки для бот-сообщений."""

import os

os.environ.setdefault("BOT_TOKEN", "123456:TEST-token")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test")

from app.services.text_format import markdown_to_plain


def test_headings_stripped():
    assert markdown_to_plain("### 1. Отвечать на вопросы") == "1. Отвечать на вопросы"
    assert markdown_to_plain("# Заголовок\nтекст") == "Заголовок\nтекст"


def test_bold_and_italic_unwrapped():
    assert markdown_to_plain("это **жирный** текст") == "это жирный текст"
    assert markdown_to_plain("это __жирный__ текст") == "это жирный текст"
    assert markdown_to_plain("это *курсив* текст") == "это курсив текст"


def test_heading_with_bold_from_screenshot():
    # Ровно случай со скриншота: «### 1. **Отвечать на вопросы**».
    assert markdown_to_plain("### 1. **Отвечать на вопросы**") == "1. Отвечать на вопросы"


def test_bullets_become_dots():
    assert markdown_to_plain("- один\n- два") == "• один\n• два"
    assert markdown_to_plain("* один\n* два") == "• один\n• два"


def test_inline_and_block_code():
    assert markdown_to_plain("вызови `print()`") == "вызови print()"
    assert markdown_to_plain("```python\nx = 1\n```") == "x = 1"


def test_links_keep_text_only():
    assert markdown_to_plain("см. [документацию](https://ex.com)") == "см. документацию"


def test_horizontal_rule_removed():
    assert markdown_to_plain("текст\n\n---\n\nещё") == "текст\n\nещё"


def test_no_markup_unchanged():
    plain = "Обычный текст без разметки."
    assert markdown_to_plain(plain) == plain


def test_empty_safe():
    assert markdown_to_plain("") == ""


def test_full_answer_no_asterisks_or_hashes():
    md = (
        "Вот что я умею:\n\n"
        "### 1. **Отвечать на вопросы**\n"
        "- Поиск информации\n"
        "- Объяснение концепций\n\n"
        "### 2. **Помощь с текстами**\n"
        "Пиши `код` и смотри [тут](https://x.com)."
    )
    out = markdown_to_plain(md)
    assert "#" not in out
    assert "*" not in out
    assert "`" not in out
    assert "](" not in out
    assert "• Поиск информации" in out
    assert "1. Отвечать на вопросы" in out
