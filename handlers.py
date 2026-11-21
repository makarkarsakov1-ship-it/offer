import logging
import re
import sqlite3

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart
from aiogram.types import BusinessConnection, CallbackQuery, Message

from bot import database as db
from bot.business import (
    START_TEXT,
    edit_as_business,
    format_accepted,
    format_offer_text,
    format_rejected,
    mention,
    send_as_business,
)
from bot.config import Config, Currency, parse_amount, parse_currency
from bot.keyboards import offer_keyboard
from bot.nft_parser import parse_nft_link

log = logging.getLogger(__name__)
router = Router(name="main")

OFF_RE = re.compile(r"^\.off(\s|$)", re.IGNORECASE)

FORMAT_ERROR = (
    "❌ Неправильный формат команды.\n\n"
    "Примеры правильного формата:\n\n"
    ".off https://t.me/nft/... 1400 star\n\n"
    ".off https://t.me/nft/... 10 gram"
)


def parse_off_command(text: str) -> tuple[str, str, str]:
    """Split '.off <link> <amount> <currency>' into raw parts. Exactly four tokens required."""
    parts = text.split()
    if len(parts) != 4:
        raise ValueError(FORMAT_ERROR)
    _, url, amount_raw, currency_raw = parts
    return url, amount_raw, currency_raw


@router.message(CommandStart())
async def on_start(message: Message):
    await message.answer(START_TEXT)


@router.business_connection()
async def on_business_connection(connection: BusinessConnection):
    can_reply = bool(connection.rights and connection.rights.can_reply)
    await db.upsert_connection(
        connection.id, connection.user.id, connection.user.username,
        connection.is_enabled, can_reply,
    )
    log.info("business connection %s enabled=%s can_reply=%s",
             connection.id, connection.is_enabled, can_reply)


@router.business_message(F.text.regexp(OFF_RE))
async def on_off_command(message: Message, bot: Bot, config: Config):
    conn_id = message.business_connection_id
    conn = await db.get_connection(conn_id) if conn_id else None
    if conn is None or not conn["is_enabled"] or not conn["can_reply"]:
        log.warning("ignored .off: connection missing, disabled or no reply rights")
        return

    # Only the owner of the business account may issue offers.
    if message.from_user is None or message.from_user.id != conn["user_id"]:
        return
    # Offers only in private chats with another user, never with the owner.
    if message.chat.type != "private" or message.chat.id == conn["user_id"]:
        return

    async def reply(text: str) -> None:
        try:
            await send_as_business(bot, conn_id, message.chat.id, text)
        except TelegramAPIError:
            log.exception("failed to send business reply")

    try:
        url_raw, amount_raw, currency_raw = parse_off_command(message.text)
    except ValueError as exc:
        await reply(str(exc))
        return

    nft = parse_nft_link(url_raw)
    if nft is None:
        await reply("❌ Неверная ссылка на NFT.\n\nОжидается формат https://t.me/nft/Название-Номер.")
        return

    try:
        amount = parse_amount(amount_raw)
        currency: Currency = parse_currency(currency_raw)
    except ValueError as exc:
        await reply(str(exc))
        return

    # Recipient is the other party in the chat; they are the one who accepts.
    try:
        offer_id = await db.create_offer(
            business_connection_id=conn_id,
            owner_id=conn["user_id"],
            owner_username=conn["username"],
            recipient_id=message.chat.id,
            chat_id=message.chat.id,
            nft_url=nft.url,
            gift_name=nft.gift_name,
            gift_number=nft.gift_number,
            amount=amount,
            currency=currency.code,
        )
    except sqlite3.IntegrityError:
        await reply("⚠️ Такое предложение уже активно в этом диалоге.")
        return

    text = format_offer_text(
        nft.gift_name, nft.gift_number, nft.url,
        mention(conn["username"], conn["user_id"], "владелец"),
        amount, currency.display,
    )
    try:
        sent = await send_as_business(bot, conn_id, message.chat.id, text, offer_keyboard(offer_id))
    except TelegramAPIError:
        log.exception("failed to send offer %s", offer_id)
        await db.delete_offer(offer_id)
        await reply("Не удалось отправить предложение. Проверьте права бота в Telegram Business.")
        return

    await db.set_message_id(offer_id, sent.message_id)
    log.info("offer %s created", offer_id)


@router.callback_query(F.data.startswith("offer:"))
async def on_offer_button(callback: CallbackQuery, bot: Bot, config: Config):
    try:
        _, action, raw_id = callback.data.split(":")
        offer_id = int(raw_id)
    except ValueError:
        await callback.answer("Некорректная кнопка.", show_alert=True)
        return

    offer = await db.get_offer(offer_id)
    if offer is None:
        await callback.answer("Предложение не найдено.", show_alert=True)
        return
    if callback.from_user.id != offer["recipient_id"]:
        await callback.answer("Ответить может только получатель предложения.", show_alert=True)
        return
    if offer["status"] != "pending":
        await callback.answer("Предложение уже обработано.", show_alert=True)
        return

    if action == "accept":
        new_status = "accepted"
        text = format_accepted(config.transfer_fee_text)
    elif action == "reject":
        new_status = "rejected"
        text = format_rejected(
            mention(callback.from_user.username, callback.from_user.id, "получатель")
        )
    else:
        await callback.answer("Неизвестное действие.", show_alert=True)
        return

    # Atomic guard against double taps and concurrent presses.
    if not await db.transition(offer_id, new_status):
        await callback.answer("Предложение уже обработано.", show_alert=True)
        return

    if offer["message_id"] is not None:
        try:
            await edit_as_business(
                bot, offer["business_connection_id"], offer["chat_id"],
                offer["message_id"], text,
            )
        except TelegramAPIError:
            log.exception("failed to edit offer %s message", offer_id)

    await callback.answer("Готово.")
    log.info("offer %s -> %s", offer_id, new_status)
