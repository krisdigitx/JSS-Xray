import html
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

ORDER_RE = re.compile(
    r"(?:Order\s*(?:#|ID|number)?\s*[:#]?\s*)"
    r"[\u202a\u202b\u202c\u200e\u200f\s]*([0-9]{3}-[0-9]{7}-[0-9]{7})",
    re.I,
)
ASIN_RE = re.compile(r"(?:/dp/|%2Fdp%2F)(B[0-9A-Z]{9})", re.I)
QTY_RE = re.compile(r"\b(?:Quantity|Qty)\s*[:x]?\s*(\d+)", re.I)
SELLER_RE = re.compile(r"\b(?:Sold by|Seller)\s*:?\s*([^\n|<]+)", re.I)
COND_RE = re.compile(r"\bCondition\s*:?\s*([^\n|<]+)", re.I)
PRODUCT_LINK_RE = re.compile(
    r"\[([^\]]+)\]\((https?://[^\s)]+(?:/dp/|%2Fdp%2F)(B[0-9A-Z]{9})[^\s)]*)\)",
    re.I,
)

TOTAL_PATTERNS = [
    re.compile(r"\bOrder\s+Total\s*:?\s*£\s*([0-9][0-9,]*(?:\.[0-9]{2})?)", re.I),
    re.compile(r"\bGrand\s+Total\s*:?\s*£\s*([0-9][0-9,]*(?:\.[0-9]{2})?)", re.I),
    re.compile(r"\bTotal\s*:?\s*£\s*([0-9][0-9,]*(?:\.[0-9]{2})?)", re.I),
    re.compile(r"£\s*([0-9][0-9,]*(?:\.[0-9]{2})?)\s*(?:Order\s+Total|Grand\s+Total)", re.I),
]
ITEM_PRICE_PATTERNS = [
    re.compile(r"\bItem\s+(?:Subtotal|Total|Price)\s*:?\s*£\s*([0-9][0-9,]*(?:\.[0-9]{2})?)", re.I),
    re.compile(r"\bPrice\s*:?\s*£\s*([0-9][0-9,]*(?:\.[0-9]{2})?)", re.I),
    re.compile(r"\b(?:Each|Unit\s+price)\s*:?\s*£\s*([0-9][0-9,]*(?:\.[0-9]{2})?)", re.I),
]
ANY_MONEY_RE = re.compile(r"£\s*([0-9][0-9,]*(?:\.[0-9]{2})?)")


@dataclass
class ParsedOrder:
    order_id: str
    event_type: str
    product_name: str | None = None
    asin: str | None = None
    seller: str | None = None
    condition: str | None = None
    quantity: int = 1
    item_price: Decimal | None = None
    total: Decimal | None = None
    product_url: str | None = None
    delivered_date_text: str | None = None
    estimated_delivery_text: str | None = None


def event_from_subject(subject: str) -> str:
    s = subject.lower()
    for needle, value in [
        ("out for delivery", "out_for_delivery"),
        ("dispatched", "dispatched"),
        ("shipped", "dispatched"),
        ("delivered", "delivered"),
        ("cancelled", "cancelled"),
        ("canceled", "cancelled"),
        ("refunded", "refunded"),
        ("refund", "refunded"),
        ("returned", "returned"),
        ("return", "returned"),
        ("ordered", "ordered"),
        ("order confirmation", "ordered"),
    ]:
        if needle in s:
            return value
    return "update"


def _normalise_text(value: str) -> str:
    """
    Convert Amazon plain-text/HTML email content into regex-friendly text.

    Amazon.co.uk commonly renders GBP prices with the pence in a smaller
    <sup> element, e.g. £8<sup>49</sup>. If HTML tags are simply stripped,
    that becomes £849. This normaliser converts those forms to £8.49 first.
    """
    value = html.unescape(value or "")

    # Common Amazon HTML: £8<sup>49</sup>, £8 <sup>49</sup>, or nested tags.
    value = re.sub(
        r"£\s*([0-9][0-9,]*)\s*<sup[^>]*>\s*([0-9]{2})\s*</sup>",
        lambda m: f"£{m.group(1)}.{m.group(2)}",
        value,
        flags=re.I,
    )

    # Some templates use spans for the fractional part.
    value = re.sub(
        r"£\s*([0-9][0-9,]*)\s*"
        r"<span[^>]*(?:a-price-fraction|price-fraction|fraction)[^>]*>\s*([0-9]{2})\s*</span>",
        lambda m: f"£{m.group(1)}.{m.group(2)}",
        value,
        flags=re.I,
    )

    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"(?i)</(?:p|div|tr|li|h[1-6]|td)>", "\n", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("\xa0", " ")

    # Handle MIME/plain-text conversions of Amazon's split price typography:
    #   £8 49
    #   £8\n49
    # But only when the fractional component is exactly two digits.
    value = re.sub(
        r"£\s*([0-9][0-9,]*)[ \t\r\n]+([0-9]{2})(?![0-9])",
        lambda m: f"£{m.group(1)}.{m.group(2)}",
        value,
    )

    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n\s+", "\n", value)
    return value


def _money(value: str | None):
    if not value:
        return None
    try:
        return Decimal(value.replace(",", ""))
    except InvalidOperation:
        return None


def _first_money(patterns, text: str):
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return _money(match.group(1))
    return None


def _product_from_subject(subject: str) -> str | None:
    if ":" not in subject:
        return None
    candidate = subject.split(":", 1)[1].strip()
    candidate = candidate.strip(" \t\r\n\"'‘’“”")
    if not candidate:
        return None
    if candidate.lower() in {"your order", "your amazon order", "order update"}:
        return None
    return candidate[:1000]


def _extract_delivery_dates(subject: str, body: str):
    text = f"{subject}\n{body}"
    months = (
        r"January|February|March|April|May|June|July|August|September|October|November|December"
        r"|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
    )
    date = rf"(?:\d{{1,2}}\s+(?:{months})\s+\d{{4}}|(?:{months})\s+\d{{1,2}},?\s+\d{{4}})"

    delivered = None
    estimated = None

    for pattern in [
        rf"\bDelivered\s+(?:on\s+)?(?:[A-Za-z]+,\s*)?({date})",
        rf"\bDelivery\s+date\s*:?\s*({date})",
    ]:
        match = re.search(pattern, text, re.I)
        if match:
            delivered = match.group(1)
            break

    for pattern in [
        rf"\b(?:Estimated\s+delivery|Estimated\s+arrival)\s*:?\s*(?:by|on)?\s*({date})",
        rf"\bArriving\s+(?:by|on)?\s*({date})",
        rf"\bDelivery\s+(?:by|on)\s+({date})",
    ]:
        match = re.search(pattern, text, re.I)
        if match:
            estimated = match.group(1)
            break

    return delivered, estimated


def _extract_prices(text: str, quantity: int):
    total = _first_money(TOTAL_PATTERNS, text)
    item_price = _first_money(ITEM_PRICE_PATTERNS, text)

    all_prices = [_money(x) for x in ANY_MONEY_RE.findall(text)]
    all_prices = [p for p in all_prices if p is not None and p >= 0]

    if item_price is None and total is not None and quantity == 1:
        item_price = total

    if total is not None and item_price is not None and item_price > total * 10:
        item_price = total if quantity == 1 else None

    if total is None and len(set(all_prices)) == 1:
        total = all_prices[0]
        if quantity == 1 and item_price is None:
            item_price = total

    if total is None and all_prices:
        total = all_prices[-1]

    return item_price, total


def parse_amazon_email(subject: str, body: str) -> ParsedOrder | None:
    text = _normalise_text(body)
    order = ORDER_RE.search(text)
    if not order:
        return None

    product_name = asin = product_url = None
    link = PRODUCT_LINK_RE.search(text)
    if link:
        product_name, product_url, asin = link.group(1).strip(), link.group(2), link.group(3).upper()
    else:
        asin_match = ASIN_RE.search(text)
        asin = asin_match.group(1).upper() if asin_match else None
        product_name = _product_from_subject(subject)

    seller = SELLER_RE.search(text)
    condition = COND_RE.search(text)
    qty_match = QTY_RE.search(text)
    quantity = int(qty_match.group(1)) if qty_match else 1

    item_price, total_value = _extract_prices(text, quantity)
    delivered_date_text, estimated_delivery_text = _extract_delivery_dates(subject, text)

    return ParsedOrder(
        order_id=order.group(1),
        event_type=event_from_subject(subject),
        product_name=product_name,
        asin=asin,
        seller=seller.group(1).strip() if seller else None,
        condition=condition.group(1).strip() if condition else None,
        quantity=quantity,
        item_price=item_price,
        total=total_value,
        product_url=product_url,
        delivered_date_text=delivered_date_text,
        estimated_delivery_text=estimated_delivery_text,
    )
