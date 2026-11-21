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
    "Бот помогает отправлять предложения о покупке NFT через подключённый Telegram Business.\n\n"
    "НАСТРОЙКА\n"
    "1. Подключите бота в Настройки → Telegram Business → Чат-боты.\n"
    "2. Включите доступ к нужным чатам и право отвечать.\n"
    "3. Попросите покупателя сначала написать вашему бизнес-аккаунту. "
    "Бот запомнит собеседника автоматически.\n\n"
    "СОЗДАНИЕ ПРЕДЛОЖЕНИЯ\n"
    "Откройте личный чат с этим ботом и отправьте:\n\n"
    ".off @username https://t.me/nft/Название-Номер 1400 star\n"
    "или\n"
    ".off @username https://t.me/nft/Название-Номер 10 gram\n\n"
    "Вместо @username можно указать Telegram ID собеседника. "
    "Команда поддерживает star/stars для Telegram Stars и gram/ton для TON.\n\n"
    "Команда /contacts показывает сохранённых собеседников.\n\n"
    "ВАЖНО\n"
    "Предложение можно отправить только собеседнику, который уже писал бизнес-аккаунту, "
    "и пока Telegram разрешает отвечать в этом диалоге (обычно в пределах 24 часов "
    "после последнего входящего сообщения). Бот не проверяет существование NFT, "
    "не принимает оплату и не передаёт подарок."
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
