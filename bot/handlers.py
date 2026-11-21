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

OFF_RE = re.compile(r"^(?:\.off|/off)(?:\s|$)", re.IGNORECASE)

FORMAT_ERROR = (
    "❌ Неправильный формат команды.\n\n"
    "Используйте:\n"
    ".off @username ссылка сумма star|gram\n\n"
    "Примеры:\n"
    ".off @example https://t.me/nft/PlushPepe-1 1400 star\n"
    ".off @example https://t.me/nft/PlushPepe-1 10 gram"
)


def parse_off_command(text: str) -> tuple[str, str, str, str]:
    parts = text.split()
    if len(parts) != 5 or not OFF_RE.match(parts[0]):
        raise ValueError(FORMAT_ERROR)
    _, recipient, url, amount_raw, currency_raw = parts
    if not recipient.startswith("@") and not recipient.isdigit():
        raise ValueError("❌ Получатель должен быть указан как @username или числовой Telegram ID.")
    return recipient, url, amount_raw, currency_raw


@router.message(CommandStart())
async def on_start(message: Message):
    await message.answer(START_TEXT)


@router.message(F.chat.type == "private", F.text.regexp(OFF_RE))
async def on_private_off_command(message: Message, bot: Bot, config: Config):
    if message.from_user is None:
        return
    try:
        recipient_identifier, url_raw, amount_raw, currency_raw = parse_off_command(message.text)
    except ValueError as exc:
        await message.answer(str(exc))
        return

    contact = await db.find_contact_for_owner(message.from_user.id, recipient_identifier)
    if contact is None:
        await message.answer(
            "❌ Не удалось найти получателя среди недавних бизнес-диалогов.\n\n"
            "Убедитесь, что этот человек уже написал вашему Telegram Business, "
            "что бот подключён и имеет право отвечать, и что с последнего сообщения "
            "прошло меньше 24 часов. Используйте /contacts, чтобы посмотреть найденных собеседников."
        )
        return

    nft = parse_nft_link(url_raw)
    if nft is None:
        await message.answer("❌ Неверная ссылка на NFT. Ожидается формат https://t.me/nft/Название-Номер.")
        return

    try:
        amount = parse_amount(amount_raw)
        currency: Currency = parse_currency(currency_raw)
        if currency.code == "Stars" and "." in amount:
            raise ValueError("❌ Telegram Stars указываются целым числом, например 1400.")
    except ValueError as exc:
        await message.answer(str(exc))
        return

    try:
        offer_id = await db.create_offer(
            business_connection_id=contact["connection_id"],
            owner_id=message.from_user.id,
            owner_username=message.from_user.username,
            recipient_id=contact["user_id"],
            chat_id=contact["chat_id"],
            nft_url=nft.url,
            gift_name=nft.gift_name,
            gift_number=nft.gift_number,
            amount=amount,
            currency=currency.code,
        )
    except sqlite3.IntegrityError:
        await message.answer("⚠️ Такое предложение уже активно в этом диалоге.")
        return

    offer_text = format_offer_text(
        nft.gift_name, nft.gift_number, nft.url,
        mention(message.from_user.username, message.from_user.id, "владелец"),
        amount, currency.display,
    )
    try:
        sent = await send_as_business(
            bot, contact["connection_id"], contact["chat_id"],
            offer_text, offer_keyboard(offer_id),
        )
    except TelegramAPIError as exc:
        log.exception("failed to send offer %s", offer_id)
        await db.delete_offer(offer_id)
        await message.answer(
            "❌ Telegram не разрешил отправить предложение. Возможно, истекло 24-часовое "
            "окно ответа или изменились права Business-бота. Подробности есть в логах Render."
        )
        return

    await db.set_message_id(offer_id, sent.message_id)
    await message.answer("✅ Предложение отправлено.")
    log.info("offer %s created for recipient %s", offer_id, contact["user_id"])


@router.message(F.chat.type == "private", F.text == "/contacts")
async def on_contacts(message: Message):
    if message.from_user is None:
        return
    contacts = await db.list_recent_contacts(message.from_user.id)
    if not contacts:
        await message.answer(
            "Пока нет сохранённых собеседников. Сначала человек должен написать "
            "вашему подключённому Telegram Business."
        )
        return

    lines = ["👥 Последние собеседники бизнес-аккаунта:"]
    seen = set()
    for contact in contacts:
        key = (contact["user_id"], contact["username"])
        if key in seen:
            continue
        seen.add(key)
        label = f"@{contact['username']}" if contact["username"] else str(contact["user_id"])
        lines.append(f"• {label} — ID: {contact['user_id']}")
    lines.append("\nДля предложения используйте @username или ID из списка.")
    await message.answer("\n".join(lines))


@router.business_connection()
async def on_business_connection(connection: BusinessConnection):
    can_reply = bool(connection.rights and connection.rights.can_reply)
    await db.upsert_connection(
        connection.id, connection.user.id, connection.user.username,
        connection.is_enabled, can_reply,
    )
    log.info("business connection %s enabled=%s can_reply=%s",
             connection.id, connection.is_enabled, can_reply)


@router.business_message(F.chat.type == "private", F.from_user)
async def on_business_incoming_message(message: Message):
    connection_id = message.business_connection_id
    sender = message.from_user
    if not connection_id or sender is None or message.chat.type != "private":
        return

    connection = await db.get_connection(connection_id)
    if connection is None or not connection["is_enabled"]:
        return
    if sender.id == connection["user_id"]:
        return

    await db.record_business_contact(
        connection_id=connection_id,
        user_id=sender.id,
        username=sender.username,
        chat_id=message.chat.id,
    )
    log.info("saved business contact %s in connection %s", sender.id, connection_id)


@router.callback_query(F.data.startswith("offer:"))
async def on_offer_button(callback: CallbackQuery, bot: Bot, config: Config):
    try:
        _, action, raw_id = callback.data.split(":")
        offer_id = int(raw_id)
    except (ValueError, AttributeError):
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
