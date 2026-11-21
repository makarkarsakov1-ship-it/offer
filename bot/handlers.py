import html
import logging
import re
import sqlite3
import secrets

from aiogram import Bot, F, Router
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart
from aiogram.types import (
    BusinessConnection, CallbackQuery, InlineQuery,
    InlineQueryResultArticle, InputTextMessageContent, Message, ForceReply,
    LabeledPrice, PreCheckoutQuery, InlineQueryResultsButton,
)
from aiogram.enums import ParseMode

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
from bot.keyboards import (offer_keyboard, transfer_confirm_keyboard, main_menu_keyboard, withdrawal_admin_keyboard)
from bot.nft_parser import parse_nft_link

log = logging.getLogger(__name__)
router = Router(name="main")

ACCESS_PRICE_STARS = 50
ACCESS_PAYMENT_PREFIX = "nft_offer_access"


async def send_access_invoice(bot: Bot, chat_id: int, user_id: int) -> None:
    payload = await db.get_or_create_access_intent(
        user_id, f"{ACCESS_PAYMENT_PREFIX}:{user_id}:{secrets.token_urlsafe(8)}"
    )
    await bot.send_invoice(
        chat_id=chat_id,
        title="NFT Offer — постоянный доступ",
        description="Разовая оплата 50 Telegram Stars. После оплаты доступ останется навсегда.",
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Постоянный доступ", amount=ACCESS_PRICE_STARS)],
    )


class AccessGateMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)

        config = data.get("config")
        if config and config.admin_id == user.id:
            return await handler(event, data)

        if await db.has_paid_access(user.id):
            return await handler(event, data)

        if not db.is_persistent():
            if isinstance(event, Message):
                if event.text and event.text.split(maxsplit=1)[0].split("@")[0] == "/start":
                    return await handler(event, data)
                if event.chat.type == "private":
                    await event.answer("Оплата временно недоступна: администратор ещё не подключил постоянную базу данных. Не отправляй Stars, попробуй позже.")
                return None
            if isinstance(event, InlineQuery):
                await event.answer([], cache_time=1, is_personal=True)
                return None
            if isinstance(event, CallbackQuery):
                await event.answer("Оплата временно недоступна. Попробуй позже.", show_alert=True)
                return None

        if isinstance(event, Message):
            if event.successful_payment:
                return await handler(event, data)
            if event.chat.type != "private":
                return await handler(event, data)
            if event.text and event.text.split(maxsplit=1)[0].split("@")[0] == "/start":
                return await handler(event, data)
            bot = data.get("bot") or event.bot
            await event.answer("Для использования бота нужен разовый вход за 50 Telegram Stars.")
            await send_access_invoice(bot, event.chat.id, user.id)
            return None

        if isinstance(event, InlineQuery):
            await event.answer(
                [],
                cache_time=1,
                is_personal=True,
                button=InlineQueryResultsButton(text="Оплатить вход — 50 ⭐", start_parameter="pay"),
            )
            return None

        if isinstance(event, CallbackQuery):
            await event.answer(
                "Доступ закрыт. Открой личный чат с ботом, отправь /start и оплати 50 ⭐. Затем нажми кнопку ещё раз.",
                show_alert=True,
            )
            return None

        return await handler(event, data)


_access_gate = AccessGateMiddleware()
router.message.outer_middleware(_access_gate)
router.inline_query.outer_middleware(_access_gate)
router.callback_query.outer_middleware(_access_gate)

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
            "Формат: NFT-ссылка сумма star|gram\n"
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
                    "Чтобы создать предложение, введи в строке ввода: \n"
                    "@имя_бота https://t.me/nft/PlushPepe-123 1400 star"
                )
            ),
        )
        await query.answer([result], cache_time=0, is_personal=True)


@router.pre_checkout_query()
async def on_access_pre_checkout(query: PreCheckoutQuery):
    payload = query.invoice_payload
    valid_payload = payload.startswith(f"{ACCESS_PAYMENT_PREFIX}:{query.from_user.id}:")
    if (
        not valid_payload
        or query.currency != "XTR"
        or query.total_amount != ACCESS_PRICE_STARS
        or await db.has_paid_access(query.from_user.id)
        or not await db.is_access_intent_pending(payload, query.from_user.id)
    ):
        await query.answer(
            ok=False,
            error_message="Счёт недействителен или доступ уже оплачен. Отправь /start для нового счёта.",
        )
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_access_successful_payment(message: Message):
    user = message.from_user
    payment = message.successful_payment
    if user is None or payment is None:
        return
    payload = payment.invoice_payload
    if (
        not payload.startswith(f"{ACCESS_PAYMENT_PREFIX}:{user.id}:")
        or payment.currency != "XTR"
        or payment.total_amount != ACCESS_PRICE_STARS
    ):
        log.error("invalid access payment payload/details from user %s", user.id)
        await message.answer("Платёж получен, но данные счёта не совпали. Напиши администратору.")
        return
    granted = await db.complete_access_payment(
        user.id, payload, payment.telegram_payment_charge_id
    )
    if granted:
        await message.answer(
            "Оплата подтверждена. Постоянный доступ к NFT Offer активирован.",
            reply_markup=main_menu_keyboard(),
        )
        await message.answer(START_TEXT, reply_markup=main_menu_keyboard())
    else:
        await message.answer(
            "Не удалось автоматически подтвердить доступ. Не оплачивай повторно — обратись к администратору."
        )


@router.message(CommandStart())
async def on_start(message: Message, bot: Bot, config: Config):
    user_id = message.from_user.id if message.from_user else 0
    if user_id != config.admin_id and not await db.has_paid_access(user_id):
        if not db.is_persistent():
            await message.answer("Оплата временно недоступна: администратор ещё не подключил постоянную базу данных. Не отправляй Stars, попробуй позже.")
            return
        await message.answer(
            "Для использования NFT Offer требуется разовая оплата 50 Telegram Stars. "
            "После подтверждения платёж даёт постоянный доступ."
        )
        await send_access_invoice(bot, message.chat.id, user_id)
        return
    await message.answer(START_TEXT, reply_markup=main_menu_keyboard())


@router.message(F.chat.type == "private", F.text == "Профиль")
async def on_profile(message: Message):
    if message.from_user is None:
        return
    balance = await db.get_balance(message.from_user.id)
    await message.answer(
        f'<tg-emoji emoji-id="6035084557378654059">👤</tg-emoji> <b>Профиль</b>\\n\\n'
        f"ID: <code>{message.from_user.id}</code>\\n"
        f'Баланс: <b>{balance} <tg-emoji emoji-id="6028338546736107668">⭐️</tg-emoji></b>',
        reply_markup=main_menu_keyboard(),
    )


@router.message(F.chat.type == "private", F.text == "Вывести")
async def on_withdraw_start(message: Message):
    if message.from_user is None:
        return
    balance = await db.get_balance(message.from_user.id)
    if balance <= 0:
        await message.answer('На балансе пока нет звёзд для вывода <tg-emoji emoji-id="6028338546736107668">⭐️</tg-emoji>.', reply_markup=main_menu_keyboard())
        return
    await db.set_user_state(message.from_user.id, "withdraw_amount")
    await message.answer(
        f'Укажи, сколько звёзд вывести. Доступно: <b>{balance} <tg-emoji emoji-id="6028338546736107668">⭐️</tg-emoji></b>\\n'
        "Отправь только целое число.",
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(F.data.startswith("withdraw:"))
async def on_withdraw_admin_action(callback: CallbackQuery, bot: Bot, config: Config):
    if config.admin_id is None or callback.from_user.id != config.admin_id:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return
    try:
        _, action, raw_id = callback.data.split(":")
        withdrawal_id = int(raw_id)
    except (ValueError, AttributeError):
        await callback.answer("Некорректная заявка.", show_alert=True)
        return
    withdrawal = await db.get_withdrawal(withdrawal_id)
    if withdrawal is None or withdrawal["status"] != "pending":
        await callback.answer("Заявка уже обработана или не найдена.", show_alert=True)
        return
    if action == "approve":
        if not await db.decide_withdrawal(withdrawal_id, "approved"):
            await callback.answer("Заявка уже обработана.", show_alert=True)
            return
        await bot.send_message(
            withdrawal["user_id"],
            f"✅ Заявка на вывод #{withdrawal_id} принята администратором.\\n"
            "Ожидай ручного выполнения выплаты.",
        )
        if callback.message:
            await callback.message.edit_text(
                callback.message.text + "\\n\\n✅ <b>Заявка принята.</b>",
                reply_markup=None,
            )
        await callback.answer("Заявка принята.")
    elif action == "reject":
        prompt = await bot.send_message(
            config.admin_id,
            f"Напиши причину отклонения заявки #{withdrawal_id} ответом на это сообщение:",
            reply_markup=ForceReply(selective=True),
        )
        await db.set_admin_rejection_state(config.admin_id, withdrawal_id, prompt.message_id)
        await callback.answer("Ожидаю причину отклонения.")
    else:
        await callback.answer("Неизвестное действие.", show_alert=True)



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


@router.message(F.chat.type == "private", F.text)
async def on_wallet_flow(message: Message, bot: Bot, config: Config):
    if message.from_user is None or not message.text:
        return
    user_id = message.from_user.id

    # Admin rejection reason must be a reply to the bot's ForceReply prompt.
    if config.admin_id == user_id and message.reply_to_message is not None:
        admin_state = await db.get_admin_rejection_state(user_id)
        if admin_state and message.reply_to_message.message_id == admin_state["prompt_message_id"]:
            reason = message.text.strip()
            if not reason:
                await message.answer("Причина не может быть пустой.")
                return
            withdrawal = await db.get_withdrawal(admin_state["withdrawal_id"])
            if withdrawal and await db.decide_withdrawal(withdrawal["id"], "rejected", reason):
                await bot.send_message(
                    withdrawal["user_id"],
                    f'<tg-emoji emoji-id="5774077015388852135">❌</tg-emoji> Заявка на вывод #{withdrawal["id"]} отклонена.\\n'
                    f"Причина от администратора: {html.escape(reason)}\\n\\n"
                    f'Сумма {withdrawal["amount"]} <tg-emoji emoji-id="6028338546736107668">⭐️</tg-emoji> возвращена на баланс.',
                )
                await message.answer(f"Заявка #{withdrawal['id']} отклонена, баланс возвращён.")
            else:
                await message.answer("Эта заявка уже обработана или не найдена.")
            await db.clear_admin_rejection_state(user_id)
            return

    state = await db.get_user_state(user_id)
    if not state:
        return

    if state["step"] == "withdraw_amount":
        raw = message.text.strip()
        if not raw.isdigit() or int(raw) <= 0:
            await message.answer("Введи целое положительное число, например 100.")
            return
        amount = int(raw)
        balance = await db.get_balance(user_id)
        if amount > balance:
            await message.answer(f"Недостаточно звёзд. Доступно: {balance} ⭐. Введи другую сумму.")
            return
        await db.set_user_state(user_id, "withdraw_details", str(amount))
        await message.answer(
            "Теперь отправь реквизиты для вывода и способ получения одним сообщением.\\n"
            "Например: @username или другие данные, по которым выполнить выплату."
        )
        return

    if state["step"] == "withdraw_details":
        details = message.text.strip()
        if len(details) < 3:
            await message.answer("Слишком короткие реквизиты. Отправь их ещё раз.")
            return
        amount = int(state["payload"])
        withdrawal_id = await db.create_withdrawal(user_id, amount, details)
        if withdrawal_id is None:
            await db.clear_user_state(user_id)
            await message.answer("Не удалось создать заявку: баланс изменился. Нажми «Вывести» ещё раз.")
            return
        await db.clear_user_state(user_id)
        username = f"@{message.from_user.username}" if message.from_user.username else "без username"
        admin_text = (
            f'<tg-emoji emoji-id="5904359114531675993">💰</tg-emoji> <b>Новая заявка на вывод #{withdrawal_id}</b>\\n\\n'
            f"Пользователь: {username}\\n"
            f"ID: <code>{user_id}</code>\\n"
            f'Сумма: <b>{amount} <tg-emoji emoji-id="6028338546736107668">⭐️</tg-emoji></b>\\n'
            f"Реквизиты: <code>{html.escape(details)}</code>"
        )
        if config.admin_id is not None:
            await bot.send_message(
                config.admin_id, admin_text,
                reply_markup=withdrawal_admin_keyboard(withdrawal_id),
            )
        await message.answer(
            f"✅ Заявка #{withdrawal_id} отправлена администратору.\\n"
            f'Сумма {amount} <tg-emoji emoji-id="6028338546736107668">⭐️</tg-emoji> зарезервирована до решения.',
            reply_markup=main_menu_keyboard(),
        )


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
async def on_business_message(message: Message, bot: Bot, config: Config):
    connection_id = message.business_connection_id
    sender = message.from_user
    if not connection_id or sender is None or message.chat.type != "private":
        return

    connection = await db.get_connection(connection_id)
    if connection is None or not connection["is_enabled"]:
        return

    # Owner's .off command is sent directly in the target Business chat.
    if sender.id == connection["user_id"]:
        if sender.id != config.admin_id and not await db.has_paid_access(sender.id):
            if not db.is_persistent():
                await send_as_business(
                    bot, connection_id, message.chat.id,
                    "Оплата временно недоступна: администратор ещё не подключил постоянную базу данных. Не отправляйте Stars."
                )
                return
            await send_as_business(
                bot, connection_id, message.chat.id,
                "Для создания предложений нужен постоянный доступ за 50 Telegram Stars. Открой личный чат с ботом, отправь /start и оплати вход."
            )
            return
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
    if action == "transferred":
        if offer["status"] != "accepted":
            await callback.answer("Сначала нужно принять предложение.", show_alert=True)
            return
        if offer["currency"] != "Stars":
            await callback.answer("Внутренний баланс пополняется только за предложения в Stars.", show_alert=True)
            return
        credited, balance = await db.credit_offer_to_balance(offer_id, callback.from_user.id)
        if not credited:
            await callback.answer("Баланс уже пополнен или предложение не подходит.", show_alert=True)
            return
        text = (
            f'<tg-emoji emoji-id="5774022692642492953">✅</tg-emoji> Ваш баланс пополнился на '
            f'{offer["amount"]} <tg-emoji emoji-id="6028338546736107668">⭐️</tg-emoji> в боте @gram_gem_bot.'
        )
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
            log.exception("failed to edit transferred offer %s", offer_id)
        await callback.answer("Баланс пополнен.")
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
                reply_markup=(
                    transfer_confirm_keyboard(offer_id)
                    if new_status == "accepted" and offer["currency"] == "Stars"
                    else None
                ),
                parse_mode=ParseMode.HTML,
            )
        elif offer["message_id"] is not None:
            await edit_as_business(
                bot, offer["business_connection_id"], offer["chat_id"],
                offer["message_id"], text,
                reply_markup=(
                    transfer_confirm_keyboard(offer_id)
                    if new_status == "accepted" and offer["currency"] == "Stars"
                    else None
                ),
            )
    except TelegramAPIError:
        log.exception("failed to edit offer %s message", offer_id)

    await callback.answer("Готово.")
    log.info("offer %s -> %s", offer_id, new_status)
