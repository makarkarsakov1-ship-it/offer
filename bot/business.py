import html

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, Message


def mention(username: str | None, user_id: int, fallback: str) -> str:
    if username:
        return f"@{html.escape(username)}"
    return f'<a href="tg://user?id={user_id}">{html.escape(fallback)}</a>'


def format_offer_text(gift_name: str, gift_number: str, nft_url: str,
                      offeror_html: str, amount: str, currency_display: str) -> str:
    price_icon = '<tg-emoji emoji-id="6028338546736107668">⭐️</tg-emoji> Telegram Stars' if "Stars" in currency_display else html.escape(currency_display)
    return (
        f'<tg-emoji emoji-id="5773677501825945508">🎁</tg-emoji> <b>Подарок:</b> {html.escape(gift_name)} #{html.escape(gift_number)}\n\n'
        f"{html.escape(nft_url)}\n\n"
        f"Пользователь {offeror_html} предлагает вам {html.escape(amount)} "
        f"{price_icon} за этот подарок."
    )


def format_accepted(transfer_fee_text: str) -> str:
    return (
        '<tg-emoji emoji-id="5774022692642492953">✅</tg-emoji> <b>Предложение принято!</b>\n\n'
        "Для передачи подарка воспользуйтесь инструкцией Telegram:\n\n"
        "1. Откройте профиль и найдите соответствующий подарок.\n"
        "2. Откройте меню подарка.\n"
        "3. Выберите передачу подарка.\n"
        "4. Проверьте получателя и подтверждённую Telegram стоимость операции.\n"
        "5. Подтвердите передачу самостоятельно в Telegram.\n\n"
        f"⚠️ Перед передачей проверьте стоимость операции. {html.escape(transfer_fee_text)}"
    )


def format_rejected(recipient_html: str) -> str:
    return f'<tg-emoji emoji-id="5774077015388852135">❌</tg-emoji> <b>Предложение отклонено.</b>\n\nПользователь {recipient_html} отменил предложение.'


START_TEXT = (
    "👋 NFT Offer Bot готов.\n\n"
    "КАК ОТПРАВИТЬ ПРЕДЛОЖЕНИЕ\n"
    "1. В BotFather включи Inline Mode командой /setinline для этого бота.\n"
    "2. Открой личный чат с покупателем.\n"
    "3. Введи в поле сообщения: @имя_бота https://t.me/nft/PlushPepe-123 1400 star\n"
    "   или: @имя_бота https://t.me/nft/PlushPepe-123 10 gram\n"
    "4. Выбери карточку предложения в подсказках Telegram — она отправится от твоего аккаунта.\n"
    "5. Покупатель нажмёт «Принять» или «Отклонить», а бот обновит сообщение.\n\n"
    "Поддерживаются star/stars и gram/ton. Telegram Stars — только целым числом.\n\n"
    "ВАЖНО: сообщение отправляется от твоего личного аккаунта, не от Telegram Business. "
    "Бот не проверяет существование или владение NFT, не принимает оплату и не передаёт подарок. "
    "Передача выполняется вручную. В личном чате бота доступны «Профиль» и «Вывести»."
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
                           text: str,
                           reply_markup: InlineKeyboardMarkup | None = None) -> None:
    await bot.edit_message_text(
        text=text,
        chat_id=chat_id,
        message_id=message_id,
        business_connection_id=connection_id,
        reply_markup=reply_markup,
    )
