from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def offer_keyboard(offer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Принять", callback_data=f"offer:accept:{offer_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"offer:reject:{offer_id}"),
        ]]
    )
