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

def sync_orders(max_results=500):
    Base.metadata.create_all(bind=engine)
    processed = skipped = 0
    with SessionLocal() as db:
        for message_id in list_message_ids(max_results=max_results):
            if db.scalar(select(OrderEvent).where(OrderEvent.gmail_message_id == message_id)):
                skipped += 1
                continue
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

            order.status = parsed.event_type
            if parsed.total is not None:
                order.order_total = parsed.total

            date_value = headers.get("date")
            event_time = parsedate_to_datetime(date_value) if date_value else datetime.now(timezone.utc)
            if parsed.event_type == "ordered" and order.order_date is None:
                order.order_date = event_time

            if parsed.product_name:
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

            db.add(OrderEvent(
                order_id=order.id,
                gmail_message_id=message_id,
                event_type=parsed.event_type,
                event_time=event_time,
                email_subject=subject,
            ))
            db.commit()
            processed += 1
    return {"processed": processed, "skipped": skipped}

if __name__ == "__main__":
    print(sync_orders())
