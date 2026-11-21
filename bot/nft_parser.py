import re
from dataclasses import dataclass

# t.me/nft/<Name>-<Number>. Name and number come from the link slug only.
# Telegram Bot API has no method that looks up a gift by its link, so nothing
# here is verified against Telegram.
NFT_RE = re.compile(
    r"^(?:https?://)?(?:www\\.)?(?:t\\.me|telegram\\.me)/nft/([A-Za-z][A-Za-z0-9]{2,63})-(\\d{1,12})/?(?:[?#].*)?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NftLink:
    url: str
    gift_name: str
    gift_number: str


def parse_nft_link(raw: str) -> NftLink | None:
    match = NFT_RE.match(raw.strip())
    if not match:
        return None
    name, number = match.group(1), match.group(2)
    return NftLink(url=f"https://t.me/nft/{name}-{number}", gift_name=name, gift_number=number)
