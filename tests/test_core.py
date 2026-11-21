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
