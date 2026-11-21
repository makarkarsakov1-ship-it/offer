import pytest

from bot.config import parse_amount, parse_currency
from bot.handlers import parse_chat_off_command, parse_off_command
from bot.nft_parser import parse_nft_link


def test_parse_stars_command():
    recipient, url, amount, currency = parse_off_command(
        ".off @buyer https://t.me/nft/PlushPepe-123 1400 star"
    )
    assert (recipient, url, amount, currency) == (
        "@buyer", "https://t.me/nft/PlushPepe-123", "1400", "star"
    )


def test_parse_ton_command_accepts_slash_alias():
    recipient, url, amount, currency = parse_off_command(
        "/off 123456789 https://t.me/nft/PlushPepe-123 10 ton"
    )
    assert recipient == "123456789"
    assert amount == "10"
    assert currency == "ton"


def test_parse_off_rejects_missing_parts():
    with pytest.raises(ValueError):
        parse_off_command(".off @buyer https://t.me/nft/PlushPepe-123 1400")


def test_parse_direct_business_chat_command():
    url, amount, currency = parse_chat_off_command(
        ".off https://t.me/nft/PlushPepe-123 1400 star"
    )
    assert (url, amount, currency) == (
        "https://t.me/nft/PlushPepe-123", "1400", "star"
    )


def test_parse_direct_business_chat_command_rejects_wrong_format():
    with pytest.raises(ValueError):
        parse_chat_off_command(".off @buyer https://t.me/nft/PlushPepe-123 1400 star")


def test_currency_aliases():
    assert parse_currency("STAR").code == "Stars"
    assert parse_currency("stars").code == "Stars"
    assert parse_currency("gram").code == "TON"
    assert parse_currency("TON").code == "TON"


def test_amount_validation():
    assert parse_amount("2,5") == "2.5"
    with pytest.raises(ValueError):
        parse_amount("0")
    with pytest.raises(ValueError):
        parse_amount("-1")


def test_nft_slug_parsing():
    parsed = parse_nft_link("https://t.me/nft/PlushPepe-123")
    assert parsed is not None
    assert parsed.gift_name == "PlushPepe"
    assert parsed.gift_number == "123"
    assert parse_nft_link("https://t.me/nft/A-1") is None



def test_parse_inline_offer_query():
    from bot.handlers import parse_inline_offer_query

    assert parse_inline_offer_query(
        "https://t.me/nft/PlushPepe-123 1400 star"
    ) == ("https://t.me/nft/PlushPepe-123", "1400", "star")
    assert parse_inline_offer_query(
        ".off https://t.me/nft/PlushPepe-123 10 gram"
    ) == ("https://t.me/nft/PlushPepe-123", "10", "gram")


def test_parse_inline_offer_query_rejects_fractional_stars():
    from bot.handlers import parse_inline_offer_query
    with pytest.raises(ValueError):
        parse_inline_offer_query("https://t.me/nft/PlushPepe-123 1.5 star")



def test_internal_stars_credit_and_withdrawal_refund(tmp_path):
    import asyncio
    from bot import database as db

    async def scenario():
        await db.init_db(str(tmp_path / "wallet.sqlite3"))
        offer_id = await db.create_inline_offer(
            owner_id=111, owner_username="seller",
            nft_url="https://t.me/nft/PlushPepe-123",
            gift_name="PlushPepe", gift_number="123",
            amount="150", currency="Stars",
        )
        assert await db.assign_inline_recipient(offer_id, 222)
        assert await db.transition(offer_id, "accepted")
        credited, balance = await db.credit_offer_to_balance(offer_id, 222)
        assert credited is True
        assert balance == 150
        credited_again, _ = await db.credit_offer_to_balance(offer_id, 222)
        assert credited_again is False

        withdrawal_id = await db.create_withdrawal(222, 50, "@wallet")
        assert withdrawal_id is not None
        assert await db.get_balance(222) == 100
        assert await db.decide_withdrawal(withdrawal_id, "rejected", "Invalid details")
        assert await db.get_balance(222) == 150

    asyncio.run(scenario())
