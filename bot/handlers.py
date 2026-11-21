import logging
import re
import sqlite3

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart
from aiogram.types import (\n    BusinessConnection, CallbackQuery, InlineQuery,\n    InlineQueryResultArticle, InputTextMessageContent, Message,\n)\nfrom aiogram.enums import ParseMode

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
CHAT_FORMAT_ERROR = (
    "❌ Формат команды:\n"
    ".off https://t.me/nft/Название-Номер сумма star|gram\n\n"
    "Примеры:\n"
    ".off https://t.me/nft/PlushPepe-1 1400 star\n"
    ".off https://t.me/nft/PlushPepe-1 10 gram"
)
PRIVATE_FORMAT_ERROR = (
    "❌ Формат команды в личке бота:\n"
    ".off @username ссылка сумма star|gram"
)


def parse_off_command(text: str) -> tuple[str, str, str, str]:
    parts = text.split()
    if len(parts) != 5 or not OFF_RE.match(parts[0]):
        raise ValueError(PRIVATE_FORMAT_ERROR)
    _, recipient, url, amount_raw, currency_raw = parts
    if not recipient.startswith("@") and not recipient.isdigit():
        raise ValueError("❌ Получатель должен быть указан как @username или числовой Telegram ID.")
    return recipient, url, amount_raw, currency_raw


def parse_inline_offer_query(text: str) -> tuple[str, str, str]:
    parts = text.strip().split()
    if parts and parts[0].lower() in {".off", "/off"}:
        parts = parts[1:]
    if len(parts) != 3:
        raise ValueError(
            "Формат: NFT-ссылка сумма star|gram\\n"
            "Пример: https://t.me/nft/PlushPepe-123 1400 star"
        )
    url_raw, amount_raw, currency_raw = parts
    nft = parse_nft_link(url_raw)
    if nft is None:
        raise ValueError("Неверная NFT-ссылка. Нужен формат https://t.me/nft/Название-Номер.")
    amount = parse_amount(amount_raw)
    currency = parse_currency(currency_raw)
    if currency.code == "Stars" and "." in amount:
        raise ValueError("Telegram Stars указываются целым числом.")
    return nft.url, amount, currency_raw


def parse_chat_off_command(text: str) -> tuple[str, str, str]:
    parts = text.split()
    if len(parts) != 4 or not OFF_RE.match(parts[0]):
        raise ValueError(CHAT_FORMAT_ERROR)
    return parts[1], parts[2], parts[3]


async def create_and_send_offer(
    *, bot: Bot, connection_id: str, owner_id: int, owner_username: str | None,
    chat_id: int, recipient_id: int, url_raw: str, amount_raw: str,
    currency_raw: str, error_chat_id: int | None = None,
) -> bool:
    nft = parse_nft_link(url_raw)
    if nft is None:
        error = "❌ Неверная ссылка на NFT. Ожидается https://t.me/nft/Название-Номер."
        if error_chat_id is not None:
            await send_as_business(bot, connection_id, error_chat_id, error)
        return False

    try:
        amount = parse_amount(amount_raw)
        currency: Currency = parse_currency(currency_raw)
        if currency.code == "Stars" and "." in amount:
            raise ValueError("❌ Telegram Stars указываются целым числом, например 1400.")
    except ValueError as exc:
        if error_chat_id is not None:
            await send_as_business(bot, connection_id, error_chat_id, str(exc))
        return False

    try:
        offer_id = await db.create_offer(
            business_connection_id=connection_id,
            owner_id=owner_id,
            owner_username=owner_username,
            recipient_id=recipient_id,
            chat_id=chat_id,
            nft_url=nft.url,
            gift_name=nft.gift_name,
            gift_number=nft.gift_number,
            amount=amount,
            currency=currency.code,
        )
    except sqlite3.IntegrityError:
        if error_chat_id is not None:
            await send_as_business(bot, connection_id, error_chat_id,
                                   "⚠️ В этом диалоге уже есть активное предложение для этой NFT.")
        return False

    offer_text = format_offer_text(
        nft.gift_name, nft.gift_number, nft.url,
        mention(owner_username, owner_id, "владелец"),
        amount, currency.display,
    )
    try:
        sent = await send_as_business(
            bot, connection_id, chat_id, offer_text, offer_keyboard(offer_id)
        )
    except TelegramAPIError:
        log.exception("failed to send offer %s", offer_id)
        await db.delete_offer(offer_id)
        if error_chat_id is not None:
            await send_as_business(
                bot, connection_id, error_chat_id,
                "❌ Telegram не разрешил отправить предложение. Проверь права Business-бота "
                "и 24-часовое окно ответа. Подробности — в логах Render."
            )
        return False

    await db.set_message_id(offer_id, sent.message_id)
    log.info("offer %s sent to chat %s", offer_id, chat_id)
    return True


@router.inline_query()
async def on_inline_query(query: InlineQuery, bot: Bot, config: Config):
    if config.admin_id is not None and query.from_user.id != config.admin_id:
        await query.answer([], cache_time=1, is_personal=True)
        return

    try:
        url_raw, amount, currency_code = parse_inline_offer_query(query.query)
        nft = parse_nft_link(url_raw)
        currency = parse_currency(currency_code)
        offer_id = await db.create_inline_offer(
            owner_id=query.from_user.id,
            owner_username=query.from_user.username,
            nft_url=nft.url,
            gift_name=nft.gift_name,
            gift_number=nft.gift_number,
            amount=amount,
            currency=currency.code,
        )
        offer_text = format_offer_text(
            nft.gift_name, nft.gift_number, nft.url,
            mention(query.from_user.username, query.from_user.id, "владелец"),
            amount, currency.display,
        )
        result = InlineQueryResultArticle(
            id=str(offer_id),
            title=f"Предложение: {nft.gift_name} #{nft.gift_number}",
            description=f"{amount} {currency.display} · нажми, чтобы отправить",
            input_message_content=InputTextMessageContent(
                message_text=offer_text,
                parse_mode=ParseMode.HTML,
            ),
            reply_markup=offer_keyboard(offer_id),
        )
        await query.answer([result], cache_time=0, is_personal=True)
    except ValueError as exc:
        result = InlineQueryResultArticle(
            id="inline-help",
            title="Неверный формат предложения",
            description=str(exc),
            input_message_content=InputTextMessageContent(
                message_text=(
                    "Чтобы создать предложение, введи в строке ввода: \\n"
                    "@имя_бота https://t.me/nft/PlushPepe-123 1400 star"
                )
            ),
        )
        await query.answer([result], cache_time=0, is_personal=True)


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
            "❌ Получатель не найден среди недавних бизнес-диалогов. "
            "Проверь /contacts и убедись, что человек недавно писал Business-аккаунту."
        )
        return

    ok = await create_and_send_offer(
        bot=bot,
        connection_id=contact["connection_id"],
        owner_id=message.from_user.id,
        owner_username=message.from_user.username,
        chat_id=contact["chat_id"],
        recipient_id=contact["user_id"],
        url_raw=url_raw,
        amount_raw=amount_raw,
        currency_raw=currency_raw,
    )
    if ok:
        await message.answer("✅ Предложение отправлено в бизнес-чат.")


@router.message(F.chat.type == "private", F.text == "/contacts")
async def on_contacts(message: Message):
    if message.from_user is None:
        return
    contacts = await db.list_recent_contacts(message.from_user.id)
    if not contacts:
        await message.answer("Пока нет сохранённых собеседников. Сначала человек должен написать вашему Business.")
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
async def on_business_message(message: Message, bot: Bot):
    connection_id = message.business_connection_id
    sender = message.from_user
    if not connection_id or sender is None or message.chat.type != "private":
        return

    connection = await db.get_connection(connection_id)
    if connection is None or not connection["is_enabled"]:
        return

    # Owner's .off command is sent directly in the target Business chat.
    if sender.id == connection["user_id"]:
        if not message.text or not OFF_RE.match(message.text.strip()):
            return
        try:
            url_raw, amount_raw, currency_raw = parse_chat_off_command(message.text.strip())
        except ValueError as exc:
            await send_as_business(bot, connection_id, message.chat.id, str(exc))
            return

        await create_and_send_offer(
            bot=bot,
            connection_id=connection_id,
            owner_id=sender.id,
            owner_username=sender.username,
            chat_id=message.chat.id,
            recipient_id=message.chat.id,
            url_raw=url_raw,
            amount_raw=amount_raw,
            currency_raw=currency_raw,
            error_chat_id=message.chat.id,
        )
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
    inline_mode = offer["business_connection_id"] == "inline"
    if inline_mode:
        if not callback.inline_message_id:
            await callback.answer("Не удалось определить inline-сообщение.", show_alert=True)
            return
        if callback.from_user.id == offer["owner_id"]:
            await callback.answer("Владелец не может принять собственное предложение.", show_alert=True)
            return
        if offer["recipient_id"] == 0:
            await db.assign_inline_recipient(offer_id, callback.from_user.id)
            offer = await db.get_offer(offer_id)
        if offer["recipient_id"] != callback.from_user.id:
            await callback.answer("Ответить может только получатель предложения.", show_alert=True)
            return
    elif callback.from_user.id != offer["recipient_id"]:
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

    try:
        if inline_mode:
            await bot.edit_message_text(
                inline_message_id=callback.inline_message_id,
                text=text,
                reply_markup=None,
                parse_mode=ParseMode.HTML,
            )
        elif offer["message_id"] is not None:
            await edit_as_business(
                bot, offer["business_connection_id"], offer["chat_id"],
                offer["message_id"], text,
            )
    except TelegramAPIError:
        log.exception("failed to edit offer %s message", offer_id)

    await callback.answer("Готово.")
    log.info("offer %s -> %s", offer_id, new_status)
