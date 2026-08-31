import re
from dataclasses import dataclass, field
from decimal import Decimal

ORDER_RE = re.compile(r"Order\s*#\s*[\u202a\u202b\u202c\u200e\u200f\s]*([0-9]{3}-[0-9]{7}-[0-9]{7})", re.I)
ASIN_RE = re.compile(r"/dp/(B[0-9A-Z]{9})", re.I)
TOTAL_RE = re.compile(r"\bTotal\s*£\s*([0-9]+(?:[.,][0-9]{2})?)", re.I)
QTY_RE = re.compile(r"\bQuantity:\s*(\d+)", re.I)
SELLER_RE = re.compile(r"\bSold by\s+([^\n]+)", re.I)
COND_RE = re.compile(r"\bCondition:\s*([^\n]+)", re.I)
PRICE_RE = re.compile(r"(?<!Total )£\s*([0-9]+(?:[.,][0-9]{2})?)")
PRODUCT_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+(?:/dp/|%2Fdp%2F)(B[0-9A-Z]{9})[^\s)]*)\)", re.I)

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

def event_from_subject(subject: str) -> str:
    s = subject.lower()
    for needle, value in [
        ("out for delivery", "out_for_delivery"),
        ("dispatched", "dispatched"),
        ("delivered", "delivered"),
        ("cancelled", "cancelled"),
        ("canceled", "cancelled"),
        ("refunded", "refunded"),
        ("refund", "refunded"),
        ("returned", "returned"),
        ("return", "returned"),
        ("ordered", "ordered"),
    ]:
        if needle in s:
            return value
    return "update"

def _money(value: str | None):
    if not value:
        return None
    return Decimal(value.replace(",", "."))


def _product_from_subject(subject: str) -> str | None:
    """Best-effort product title from Amazon transactional subjects.

    Examples:
      Ordered: ‘USB C Charger Cable’
      Dispatched: "Coffee Grinder"
      Delivered: Dog food
    """
    if ":" not in subject:
        return None
    candidate = subject.split(":", 1)[1].strip()
    candidate = candidate.strip(" \t\r\n\"'‘’“”")
    if not candidate:
        return None
    # Avoid treating generic status text as a product name.
    if candidate.lower() in {"your order", "your amazon order", "order update"}:
        return None
    return candidate[:1000]

def parse_amazon_email(subject: str, body: str) -> ParsedOrder | None:
    order = ORDER_RE.search(body)
    if not order:
        return None

    product_name = asin = product_url = None
    link = PRODUCT_LINK_RE.search(body)
    if link:
        product_name, product_url, asin = link.group(1).strip(), link.group(2), link.group(3).upper()
    else:
        am = ASIN_RE.search(body)
        asin = am.group(1).upper() if am else None
        product_name = _product_from_subject(subject)

    seller = SELLER_RE.search(body)
    condition = COND_RE.search(body)
    qty = QTY_RE.search(body)
    total = TOTAL_RE.search(body)

    # Amazon's rendered text can occasionally collapse £6.99 to £699.
    # Prefer Total as authoritative for single-item order confirmations.
    prices = PRICE_RE.findall(body)
    item_price = _money(prices[-1]) if prices else None
    total_value = _money(total.group(1)) if total else None
    if total_value is not None and (item_price is None or item_price > total_value * 10):
        item_price = total_value

    return ParsedOrder(
        order_id=order.group(1),
        event_type=event_from_subject(subject),
        product_name=product_name,
        asin=asin,
        seller=seller.group(1).strip() if seller else None,
        condition=condition.group(1).strip() if condition else None,
        quantity=int(qty.group(1)) if qty else 1,
        item_price=item_price,
        total=total_value,
        product_url=product_url,
    )
