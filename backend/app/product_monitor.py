import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html import unescape
from urllib.parse import urlparse

import httpx
from sqlalchemy import select

from .db import SessionLocal
from .models import ProductPriceHistory, TikTokProduct, TikTokShop
from .tiktok_sync import _client_for_shop, _ensure_shop

ASIN_RE = re.compile(r"(?:/dp/|/gp/product/|/product/)([A-Z0-9]{10})(?:[/?#]|$)", re.I)
PRICE_PATTERNS = [
    re.compile(r'<span[^>]+class="[^"]*a-offscreen[^"]*"[^>]*>\s*£\s*([0-9,]+(?:\.[0-9]{1,2})?)\s*</span>', re.I),
    re.compile(r'"priceAmount"\s*:\s*"?([0-9]+(?:\.[0-9]{1,2})?)"?', re.I),
    re.compile(r'"price"\s*:\s*"?£?\s*([0-9,]+(?:\.[0-9]{1,2})?)"?', re.I),
    re.compile(r'£\s*([0-9,]+(?:\.[0-9]{1,2})?)'),
]


def _decimal(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _price_from_skus(product: dict):
    prices = []
    seller_skus = []
    for sku in product.get("skus") or []:
        seller_sku = sku.get("seller_sku")
        if seller_sku:
            seller_skus.append(str(seller_sku))
        price = sku.get("price") or {}
        # sale_price is the live retail price when present. Fall back to the
        # other fields used by older/product-region responses.
        amount = (
            price.get("sale_price")
            or price.get("tax_inclusive_price")
            or price.get("tax_exclusive_price")
            or price.get("amount")
        )
        value = _decimal(amount)
        if value is not None and value >= 0:
            prices.append(value)
    return (min(prices) if prices else None), (seller_skus[0] if seller_skus else None), len(product.get("skus") or [])


def sync_tiktok_products(shop_slug: str = "polaris-zone") -> dict:
    """Import live TikTok products without changing order/finance logic.

    For Polaris Zone, Seller SKU is the source of truth for the Amazon source
    URL. JSS Xray never writes the source back to TikTok; if Seller SKU is
    missing or invalid, the product is flagged so it can be corrected in
    TikTok Seller Center.
    """
    db = SessionLocal()
    try:
        shop = db.scalar(select(TikTokShop).where(TikTokShop.slug == shop_slug))
        if not shop:
            if shop_slug != "polaris-zone":
                raise RuntimeError(f"TikTok shop {shop_slug} has not been configured")
            shop = _ensure_shop(db)
        client = _client_for_shop(db, shop)
        raw_products = client.search_products(status="ACTIVATE")
        now = datetime.now(timezone.utc)
        created = updated = 0
        for raw in raw_products:
            product_id = str(raw.get("id") or raw.get("product_id") or "")
            if not product_id:
                continue
            row = db.scalar(select(TikTokProduct).where(
                TikTokProduct.shop_id == shop.id,
                TikTokProduct.tiktok_product_id == product_id,
            ))
            if row is None:
                row = TikTokProduct(shop_id=shop.id, tiktok_product_id=product_id, title=str(raw.get("title") or "TikTok product"))
                db.add(row)
                created += 1
            else:
                updated += 1
            price, seller_sku, sku_count = _price_from_skus(raw)
            row.title = str(raw.get("title") or row.title or "TikTok product")
            row.status = str(raw.get("status") or row.status or "UNKNOWN")
            row.tiktok_price = price
            row.seller_sku = seller_sku
            row.sku_count = sku_count

            # Polaris Zone convention: TikTok Seller SKU contains the Amazon
            # source URL (for example https://amzn.eu/d/0cllMYzD). Keep this as
            # the authoritative source mapping. Any previous JSS Xray manual
            # mapping is replaced/cleared on catalogue sync.
            seller_source = (seller_sku or "").strip()
            if seller_source and is_amazon_source_url(seller_source):
                if row.source_url != seller_source:
                    row.source_url = seller_source
                    row.source_asin = extract_asin(seller_source)
                    row.source_check_status = "PENDING"
                    row.source_check_message = None
            else:
                row.source_url = None
                row.source_asin = None
                row.source_price = None
                row.previous_source_price = None
                row.source_checked_at = None
                if seller_source:
                    row.source_check_status = "INVALID_SOURCE"
                    row.source_check_message = "Seller SKU must contain an Amazon.co.uk or amzn.eu product URL"
                else:
                    row.source_check_status = "SOURCE_MISSING"
                    row.source_check_message = "Add the Amazon source URL to Seller SKU in TikTok"

            if raw.get("skus"):
                first_price = (raw.get("skus")[0].get("price") or {})
                row.currency = str(first_price.get("currency") or row.currency or "GBP")[:3]
            row.product_synced_at = now
        db.commit()
        return {"shop": shop_slug, "products": len(raw_products), "created": created, "updated": updated, "synced_at": now.isoformat()}
    finally:
        db.close()


def extract_asin(url: str | None) -> str | None:
    if not url:
        return None
    match = ASIN_RE.search(url)
    return match.group(1).upper() if match else None


def is_amazon_source_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    return host == "amzn.eu" or host.endswith(".amzn.eu") or host == "amazon.co.uk" or host.endswith(".amazon.co.uk")


def _validate_amazon_url(url: str) -> None:
    if not is_amazon_source_url(url):
        raise ValueError("Seller SKU source must be an Amazon.co.uk or amzn.eu URL")


def fetch_amazon_price(url: str) -> tuple[Decimal | None, str, str, str | None]:
    """Best-effort Amazon UK price check.

    Amazon may return consent, CAPTCHA or bot-protection pages. Those are
    reported as BLOCKED rather than manufacturing a price from unrelated HTML.
    """
    _validate_amazon_url(url)
    headers = {
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0 Safari/537.36",
        "accept-language": "en-GB,en;q=0.9",
        "accept": "text/html,application/xhtml+xml",
    }
    with httpx.Client(timeout=25.0, follow_redirects=True, headers=headers) as client:
        response = client.get(url)
    resolved_url = str(response.url) if response.url else None
    if response.status_code >= 400:
        return None, "ERROR", f"Amazon returned HTTP {response.status_code}", resolved_url
    body = unescape(response.text)
    lower = body.lower()
    if "enter the characters you see below" in lower or "captcha" in lower or "robot check" in lower:
        return None, "BLOCKED", "Amazon returned a CAPTCHA/bot-protection page", resolved_url

    # Prefer structured product JSON-LD when it is available.
    for block in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', body, re.I | re.S):
        try:
            data = json.loads(block.strip())
        except Exception:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            offers = node.get("offers")
            offers = offers if isinstance(offers, list) else [offers] if offers else []
            for offer in offers:
                if isinstance(offer, dict):
                    price = _decimal(offer.get("price") or offer.get("lowPrice"))
                    currency = str(offer.get("priceCurrency") or "GBP")[:3]
                    if price is not None and price > 0:
                        return price, "OK", currency, resolved_url

    for pattern in PRICE_PATTERNS:
        for match in pattern.finditer(body):
            price = _decimal(match.group(1))
            # Guard against obvious non-product values accidentally captured
            # from unrelated page content.
            if price is not None and Decimal("0.01") <= price <= Decimal("100000"):
                return price, "OK", "GBP", resolved_url
    return None, "NOT_FOUND", "No product price could be identified on the Amazon page", resolved_url


def check_product_source(product: TikTokProduct, db) -> dict:
    now = datetime.now(timezone.utc)
    if not product.source_url:
        return {"product_id": product.tiktok_product_id, "status": "UNMAPPED"}
    try:
        price, status, detail, resolved_url = fetch_amazon_price(product.source_url)
    except Exception as exc:
        price, status, detail, resolved_url = None, "ERROR", str(exc), None

    # Short amzn.eu Seller SKU links resolve to the canonical Amazon page.
    # Keep Seller SKU as the authoritative source_url, but capture the ASIN
    # from the resolved URL when available.
    resolved_asin = extract_asin(resolved_url)
    if resolved_asin:
        product.source_asin = resolved_asin

    if price is not None:
        if product.source_price is not None and Decimal(product.source_price) != price:
            product.previous_source_price = product.source_price
        product.source_price = price
    product.source_checked_at = now
    product.source_check_status = status
    product.source_check_message = detail if status != "OK" else None
    history = ProductPriceHistory(
        product_id=product.id,
        tiktok_price=product.tiktok_price,
        source_price=price,
        source_currency=detail if status == "OK" else product.source_currency or "GBP",
        status=status,
        checked_at=now,
    )
    if status == "OK":
        product.source_currency = detail
    db.add(history)
    return {"product_id": product.tiktok_product_id, "status": status, "price": float(price) if price is not None else None, "message": None if status == "OK" else detail}


def check_mapped_products(shop_slug: str = "polaris-zone") -> dict:
    db = SessionLocal()
    try:
        rows = db.scalars(
            select(TikTokProduct)
            .join(TikTokShop)
            .where(TikTokShop.slug == shop_slug, TikTokProduct.source_url.is_not(None))
            .order_by(TikTokProduct.id)
        ).all()
        results = []
        for row in rows:
            results.append(check_product_source(row, db))
            db.commit()
        ok = sum(1 for r in results if r["status"] == "OK")
        return {"shop": shop_slug, "mapped": len(rows), "checked": len(results), "ok": ok, "problems": len(results)-ok, "results": results}
    finally:
        db.close()
