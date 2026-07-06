from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo


def webapp_open_kb(text: str, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))]]
    )
