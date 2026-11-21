from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def offer_keyboard(offer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Принять", callback_data=f"offer:accept:{offer_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"offer:reject:{offer_id}"),
        ]]
    )


def transfer_confirm_keyboard(offer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📦 Передал(а)", callback_data=f"offer:transferred:{offer_id}")
    ]])


def main_menu_keyboard():
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Профиль"), KeyboardButton(text="Вывести")]
        ],
        resize_keyboard=True,
    )


def withdrawal_admin_keyboard(withdrawal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Принять", callback_data=f"withdraw:approve:{withdrawal_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"withdraw:reject:{withdrawal_id}"),
    ]])
