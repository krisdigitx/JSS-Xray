import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from sqlalchemy import select
from .db import Base, SessionLocal, engine
from .gmail import list_message_ids, read_message
from .models import Order, OrderEvent, OrderItem
from .parser import parse_amazon_email

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

def _add_item_if_missing(db, order: Order, parsed) -> bool:
    if not parsed.product_name:
        return False
    existing = db.scalar(
        select(OrderItem).where(
            OrderItem.order_id == order.id,
            OrderItem.asin == parsed.asin,
            OrderItem.product_name == parsed.product_name,
        )
    )
    if existing:
        return False
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

def _refresh_order_status(db, order: Order) -> None:
    latest = db.scalar(
        select(OrderEvent)
        .where(OrderEvent.order_id == order.id)
        .order_by(OrderEvent.event_time.desc().nullslast(), OrderEvent.id.desc())
        .limit(1)
    )
    if latest:
        order.status = latest.event_type

def sync_orders(max_results=500):
    Base.metadata.create_all(bind=engine)
    processed = skipped = enriched = 0
    touched_order_ids = set()

    with SessionLocal() as db:
        for message_id in list_message_ids(max_results=max_results):
            existing_event = db.scalar(
                select(OrderEvent).where(OrderEvent.gmail_message_id == message_id)
            )

            # Existing events are still parsed so older data can be enriched with
            # product/item details after parser improvements.
            msg = read_message(message_id)
            headers = _headers(msg["payload"])
            subject = headers.get("subject", "")
            parsed = parse_amazon_email(subject, _body(msg["payload"]))
            if not parsed:
                skipped += 1
                continue

            order = db.scalar(select(Order).where(Order.amazon_order_id == parsed.order_id))
            if not order:
                order = Order(amazon_order_id=parsed.order_id)
                db.add(order)
                db.flush()

            touched_order_ids.add(order.id)

            if parsed.total is not None:
                order.order_total = parsed.total

            date_value = headers.get("date")
            event_time = parsedate_to_datetime(date_value) if date_value else datetime.now(timezone.utc)

            if parsed.event_type == "ordered":
                if order.order_date is None or event_time < order.order_date:
                    order.order_date = event_time

            if _add_item_if_missing(db, order, parsed):
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

        # Gmail usually returns newest first. Recompute status from the latest
        # persisted event instead of allowing an older message to overwrite it.
        for order_id in touched_order_ids:
            order = db.get(Order, order_id)
            if order:
                _refresh_order_status(db, order)
        db.commit()

    return {"processed": processed, "enriched": enriched, "skipped": skipped}

if __name__ == "__main__":
    print(sync_orders())
