from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📩 Отправить задачу", callback_data="send_task")],
            [InlineKeyboardButton(text="📊 Проверить лимит", callback_data="check_limit")],
            [InlineKeyboardButton(text="💎 Оформить подписку", callback_data="subscribe")],
        ]
    )
