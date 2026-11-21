from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def offer_keyboard(offer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="Принять", callback_data=f"offer:accept:{offer_id}", icon_custom_emoji_id="5774022692642492953"),
            InlineKeyboardButton(text="Отклонить", callback_data=f"offer:reject:{offer_id}", icon_custom_emoji_id="5774077015388852135"),
        ]]
    )


def transfer_confirm_keyboard(offer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Передал(а)", callback_data=f"offer:transferred:{offer_id}", icon_custom_emoji_id="5895669571058142797")
    ]])


def main_menu_keyboard():
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Профиль", icon_custom_emoji_id="6035084557378654059"),
                KeyboardButton(text="Вывести", icon_custom_emoji_id="5904359114531675993"),
            ]
        ],
        resize_keyboard=True,
    )


def withdrawal_admin_keyboard(withdrawal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Принять", callback_data=f"withdraw:approve:{withdrawal_id}", icon_custom_emoji_id="5774022692642492953"),
        InlineKeyboardButton(text="Отклонить", callback_data=f"withdraw:reject:{withdrawal_id}", icon_custom_emoji_id="5774077015388852135"),
    ]])
