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
    "👋 NFT Offer Bot подключён.\n\n"
    "КОМАНДА ПРЯМО В БИЗНЕС-ЧАТЕ\n"
    "Откройте личный чат с получателем в Telegram Business и отправьте от своего аккаунта:\n\n"
    ".off https://t.me/nft/Название-Номер 1400 star\n"
    "или\n"
    ".off https://t.me/nft/Название-Номер 10 gram\n\n"
    "Бот отправит отдельное предложение в этот же чат с кнопками «Принять» и «Отклонить». "
    "После нажатия кнопки он изменит текст предложения.\n\n"
    "Поддерживаются star/stars и gram/ton. Команда должна быть отправлена именно владельцем "
    "подключённого Business-аккаунта в личном чате. У бота должны быть права отвечать, "
    "а чат должен быть доступен подключённому боту.\n\n"
    "Команду можно также отправить боту в личку в старом формате: "
    ".off @username ссылка сумма star|gram. /contacts показывает сохранённых собеседников.\n\n"
    "Бот не проверяет существование или владение NFT, не принимает оплату и не передаёт подарок. "
    "Передача выполняется вручную."
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
