import html

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, Message


def mention(username: str | None, user_id: int, fallback: str) -> str:
    if username:
        return f"@{html.escape(username)}"
    return f'<a href="tg://user?id={user_id}">{html.escape(fallback)}</a>'


def format_offer_text(gift_name: str, gift_number: str, nft_url: str,
                      offeror_html: str, amount: str, currency_display: str) -> str:
    return (
        f"🎁 Подарок: {html.escape(gift_name)} #{html.escape(gift_number)}\n\n"
        f"{html.escape(nft_url)}\n\n"
        f"Пользователь {offeror_html} предлагает вам {html.escape(amount)} "
        f"{html.escape(currency_display)} за этот подарок."
    )


def format_accepted(transfer_fee_text: str) -> str:
    return (
        "✅ Предложение принято!\n\n"
        "Для передачи подарка воспользуйтесь инструкцией Telegram:\n\n"
        "1. Откройте профиль и найдите соответствующий подарок.\n"
        "2. Откройте меню подарка.\n"
        "3. Выберите передачу подарка.\n"
        "4. Проверьте получателя и подтверждённую Telegram стоимость операции.\n"
        "5. Подтвердите передачу самостоятельно в Telegram.\n\n"
        f"⚠️ Перед передачей проверьте стоимость операции. {html.escape(transfer_fee_text)}"
    )


def format_rejected(recipient_html: str) -> str:
    return f"❌ Предложение отклонено.\n\nПользователь {recipient_html} отменил предложение."


START_TEXT = (
    "👋 Добро пожаловать в NFT Offer Bot!\n\n"
    "Бот позволяет создавать предложения о покупке NFT-подарков прямо в Telegram Business.\n\n"
    "Как создать предложение?\n\n"
    "1. Подключите бота к Telegram Business.\n"
    "2. Откройте чат с человеком, которому хотите предложить покупку подарка.\n"
    "3. Отправьте в этом чате одну из команд:\n\n"
    "⭐ Предложение за Stars:\n"
    ".off ссылка_на_NFT сумма star\n\n"
    "💎 Предложение за TON:\n"
    ".off ссылка_на_NFT сумма gram\n\n"
    "Примеры:\n\n"
    ".off https://t.me/nft/... 1400 star\n\n"
    ".off https://t.me/nft/... 10 gram\n\n"
    "После отправки команды бот автоматически создаст сообщение с предложением "
    "и кнопками «Принять» и «Отклонить».\n\n"
    "Важно: команду .off нужно отправлять именно в бизнес-чате с получателем, "
    "а не в личном диалоге с ботом."
)


async def send_as_business(bot: Bot, connection_id: str, chat_id: int, text: str,
                           reply_markup: InlineKeyboardMarkup | None = None) -> Message:
    return await bot.send_message(
        chat_id=chat_id,
        text=text,
        business_connection_id=connection_id,
        reply_markup=reply_markup,
    )


async def edit_as_business(bot: Bot, connection_id: str, chat_id: int, message_id: int,
                           text: str) -> None:
    await bot.edit_message_text(
        text=text,
        chat_id=chat_id,
        message_id=message_id,
        business_connection_id=connection_id,
        reply_markup=None,
    )
