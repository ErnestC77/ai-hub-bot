"""Markdown -> чистый текст для сообщений в бот.

Модели отвечают markdown'ом (###, **жирный**, списки). В Mini App его рендерит
react-markdown, а в бот-чат ответ уходит обычным текстом -- сырые ### и **
выглядят мусором. Telegram parse_mode тут ненадёжен: заголовков (###) он не
знает, а MarkdownV2/HTML на произвольном выводе модели легко ломается на
экранировании ("can't parse entities") и роняет всё сообщение. Поэтому просто
снимаем разметку в читаемый plain text -- он доставляется всегда.
"""

import re

_FENCE = re.compile(r"```[^\n]*\n?(.*?)```", re.DOTALL)  # ```lang\n...``` -> ...
_INLINE_CODE = re.compile(r"`([^`]+)`")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)  # ### Заголовок -> Заголовок
_BOLD = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__")
_ITALIC = re.compile(r"(?<![\*_])[*_]([^*_\n]+)[*_](?![\*_])")
_LINK = re.compile(r"\[([^\]]+)\]\((?:[^)]+)\)")  # [текст](url) -> текст
_BULLET = re.compile(r"^(\s*)[-*+]\s+", re.MULTILINE)  # - пункт -> • пункт
_BLOCKQUOTE = re.compile(r"^\s{0,3}>\s?", re.MULTILINE)
_HR = re.compile(r"^\s*([-*_])\1{2,}\s*$", re.MULTILINE)  # --- / *** -> убрать
_MULTI_BLANK = re.compile(r"\n{3,}")


def markdown_to_plain(text: str) -> str:
    """Снимает markdown-разметку, сохраняя читаемую структуру."""
    if not text:
        return text
    text = _FENCE.sub(lambda m: m.group(1).rstrip("\n"), text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _HEADING.sub("", text)
    text = _LINK.sub(r"\1", text)
    text = _BOLD.sub(lambda m: m.group(1) or m.group(2), text)
    text = _ITALIC.sub(r"\1", text)
    text = _HR.sub("", text)
    text = _BULLET.sub(r"\1• ", text)
    text = _BLOCKQUOTE.sub("", text)
    text = _MULTI_BLANK.sub("\n\n", text)
    return text.strip()
