import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from sqlalchemy import select
from .config import settings
from .db import SessionLocal
from .gmail import list_message_ids, read_message
from .models import AmazonAccount, Order, OrderEvent, OrderItem
from .parser import parse_amazon_email
from .schema import ensure_schema


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _body(payload: dict) -> str:
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return _decode(payload["body"]["data"])
    for part in payload.get("parts", []):
        text = _body(part)
        if text:
            return text
    if payload.get("body", {}).get("data"):
        return _decode(payload["body"]["data"])
    return ""


def _headers(payload: dict) -> dict:
    return {h["name"].lower(): h["value"] for h in payload.get("headers", [])}



def _parse_date_text(value: str | None):
    if not value:
        return None
    for fmt in ("%d %B %Y", "%B %d, %Y", "%B %d %Y", "%d %b %Y", "%b %d, %Y", "%b %d %Y"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _upsert_item(db, order: Order, parsed) -> bool:
    """Create or enrich an existing item from a re-parsed historical email."""
    if not parsed.product_name:
        return False

    existing = db.scalar(
        select(OrderItem).where(
            OrderItem.order_id == order.id,
            OrderItem.asin == parsed.asin,
            OrderItem.product_name == parsed.product_name,
        )
    )

    if not existing:
        db.add(OrderItem(
            order_id=order.id,
            product_name=parsed.product_name,
            asin=parsed.asin,
            seller=parsed.seller,
            condition=parsed.condition,
            quantity=parsed.quantity,
            item_price=parsed.item_price,
            product_url=parsed.product_url,
        ))
        return True

    changed = False
    for attr, value in [
        ("item_price", parsed.item_price),
        ("seller", parsed.seller),
        ("condition", parsed.condition),
        ("product_url", parsed.product_url),
    ]:
        if value is not None and getattr(existing, attr) != value:
            setattr(existing, attr, value)
            changed = True

    if parsed.quantity and existing.quantity != parsed.quantity:
        existing.quantity = parsed.quantity
        changed = True

    return changed


def _refresh_order_status(db, order: Order) -> None:
    latest = db.scalar(
        select(OrderEvent)
        .where(OrderEvent.order_id == order.id)
        .order_by(OrderEvent.event_time.desc().nullslast(), OrderEvent.id.desc())
        .limit(1)
    )
    if latest:
        order.status = latest.event_type


def _get_account(db) -> AmazonAccount:
    account = db.scalar(select(AmazonAccount).where(AmazonAccount.slug == settings.account_slug))
    if not account:
        account = AmazonAccount(slug=settings.account_slug, name=settings.account_name, enabled=True)
        db.add(account)
        db.flush()
    return account


def sync_orders(max_results=500):
    ensure_schema()
    processed = skipped = enriched = 0
    touched_order_ids = set()

    with SessionLocal() as db:
        account = _get_account(db)

        for message_id in list_message_ids(max_results=max_results):
            msg = read_message(message_id)
            headers = _headers(msg["payload"])
            subject = headers.get("subject", "")
            parsed = parse_amazon_email(subject, _body(msg["payload"]))
            if not parsed:
                skipped += 1
                continue

            order = db.scalar(
                select(Order).where(
                    Order.account_id == account.id,
                    Order.amazon_order_id == parsed.order_id,
                )
            )
            if not order:
                order = Order(
                    account_id=account.id,
                    amazon_order_id=parsed.order_id,
                )
                db.add(order)
                db.flush()

            touched_order_ids.add(order.id)

            existing_event = db.scalar(
                select(OrderEvent).where(
                    OrderEvent.order_id == order.id,
                    OrderEvent.gmail_message_id == message_id,
                )
            )

            if parsed.total is not None:
                order.order_total = parsed.total

            date_value = headers.get("date")
            event_time = parsedate_to_datetime(date_value) if date_value else datetime.now(timezone.utc)

            parsed_delivered = _parse_date_text(getattr(parsed, "delivered_date_text", None))
            parsed_estimated = _parse_date_text(getattr(parsed, "estimated_delivery_text", None))

            if parsed_estimated:
                order.estimated_delivery_date = parsed_estimated

            if parsed.event_type == "delivered":
                order.delivered_date = parsed_delivered or event_time
                order.estimated_delivery_date = None

            if parsed.event_type == "ordered":
                if order.order_date is None or event_time < order.order_date:
                    order.order_date = event_time

            if _upsert_item(db, order, parsed):
                enriched += 1

            if existing_event:
                db.commit()
                skipped += 1
                continue

            db.add(OrderEvent(
                order_id=order.id,
                gmail_message_id=message_id,
                event_type=parsed.event_type,
                event_time=event_time,
                email_subject=subject,
            ))
            db.commit()
            processed += 1

        for order_id in touched_order_ids:
            order = db.get(Order, order_id)
            if order:
                _refresh_order_status(db, order)
        db.commit()

    return {
        "account": settings.account_slug,
        "processed": processed,
        "enriched": enriched,
        "skipped": skipped,
    }


if __name__ == "__main__":
    print(sync_orders())
