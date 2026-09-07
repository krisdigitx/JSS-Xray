import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .config import settings
from .db import SessionLocal
from .models import AmazonAccount, Order, TikTokOrder, TikTokShop
from .tiktok import TikTokClient, epoch_dt, money, parse_amazon_order_id, refresh_access_token

CANCELLED_STATUSES = {"CANCELLED", "CANCELED"}
REFUND_MARKERS = {"REFUNDED", "RETURNED", "RETURN_COMPLETED", "REFUND_COMPLETED"}


def _dt_from_expiry(value):
    try:
        if not value:
            return None
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def _note(order: dict) -> str | None:
    candidates = [
        order.get("seller_note"), order.get("note"), order.get("buyer_message"),
        order.get("message_to_seller"), order.get("remark"),
    ]
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _line_summary(order: dict):
    lines = order.get("line_items") or order.get("items") or []
    if not lines:
        return None, 1
    names = []
    qty = 0
    for line in lines:
        name = line.get("product_name") or line.get("sku_name") or line.get("display_name")
        if name and name not in names:
            names.append(name)
        try:
            qty += int(line.get("quantity") or 1)
        except (ValueError, TypeError):
            qty += 1
    return ", ".join(names[:3]) or None, max(qty, 1)


def _customer_paid(order: dict):
    payment = order.get("payment") or {}
    return money(payment.get("total_amount") or payment.get("original_total_product_price"))


def _first_money(tx: dict, *keys: str, prefer_nonzero: bool = False):
    """Return the first usable TikTok money value from a set of field names.

    Finance responses have changed field naming across endpoint versions and may
    include placeholder ``0.00`` values alongside a real estimate.  When
    ``prefer_nonzero`` is true, keep looking past zero values and only fall
    back to zero if no non-zero amount is present.
    """
    zero = None
    for key in keys:
        if key not in tx:
            continue
        value = money(tx.get(key))
        if value is None:
            continue
        if prefer_nonzero and value == 0:
            zero = value
            continue
        return value
    return zero


def _finance_amount(tx: dict | None):
    if not tx:
        return None, None, None

    # Unsettled Finance API values are estimates. TikTok has used both
    # est_* and estimated_* names across Finance API responses, so accept both
    # and prefer a meaningful non-zero estimate over a placeholder 0.00.
    estimated = _first_money(
        tx,
        "est_settlement_amount",
        "estimated_settlement_amount",
        "est_revenue_amount",
        "estimated_revenue_amount",
        prefer_nonzero=True,
    )

    # settlement_amount is a final/settled figure and must not be used as an
    # estimated value when TikTok supplies a separate estimate.
    settled = _first_money(tx, "settlement_amount", prefer_nonzero=True)

    refund = _first_money(
        tx,
        "refund_amount",
        "refund_subtotal_before_discount",
        "refund_sub_total",
        "refund_actual_amount",
        prefer_nonzero=True,
    )
    return estimated, settled, abs(refund) if refund is not None else None


def _find_amazon_order(db, shop_slug: str, amazon_order_id: str | None):
    if not amazon_order_id:
        return None
    stmt = (
        select(Order)
        .join(AmazonAccount)
        .where(Order.amazon_order_id == amazon_order_id)
        .options(selectinload(Order.items), selectinload(Order.account))
    )
    same_account = db.scalar(stmt.where(AmazonAccount.slug == shop_slug))
    return same_account or db.scalar(stmt)


def _ensure_shop(db) -> TikTokShop:
    shop = db.scalar(select(TikTokShop).where(TikTokShop.slug == settings.tiktok_shop_slug))
    if not shop:
        shop = TikTokShop(slug=settings.tiktok_shop_slug, name=settings.tiktok_shop_name)
        db.add(shop)
        db.flush()
    if settings.tiktok_access_token and not shop.access_token:
        shop.access_token = settings.tiktok_access_token
    if settings.tiktok_refresh_token and not shop.refresh_token:
        shop.refresh_token = settings.tiktok_refresh_token
    if settings.tiktok_shop_cipher:
        shop.shop_cipher = settings.tiktok_shop_cipher
    return shop


def _client_for_shop(db, shop: TikTokShop) -> TikTokClient:
    now = datetime.now(timezone.utc)
    access = shop.access_token or settings.tiktok_access_token
    refresh = shop.refresh_token or settings.tiktok_refresh_token

    if shop.access_token_expires_at and shop.access_token_expires_at <= now + timedelta(hours=6) and refresh:
        token = refresh_access_token(settings.tiktok_app_key, settings.tiktok_app_secret, refresh)
        access = token.get("access_token") or access
        shop.access_token = access
        shop.refresh_token = token.get("refresh_token") or refresh
        shop.access_token_expires_at = _dt_from_expiry(token.get("access_token_expire_in"))
        shop.refresh_token_expires_at = _dt_from_expiry(token.get("refresh_token_expire_in"))
        db.commit()

    if not settings.tiktok_app_key or not settings.tiktok_app_secret or not access:
        raise RuntimeError("TikTok credentials are incomplete: TIKTOK_APP_KEY, TIKTOK_APP_SECRET and access token are required")

    client = TikTokClient(settings.tiktok_app_key, settings.tiktok_app_secret, access, shop.shop_cipher)
    if not shop.shop_cipher:
        shops = client.authorized_shops()
        match = next((s for s in shops if (s.get("name") or s.get("shop_name")) == shop.name), None) or (shops[0] if len(shops) == 1 else None)
        if not match:
            raise RuntimeError(f"Could not determine authorized TikTok shop for {shop.name}")
        shop.shop_id = str(match.get("id") or match.get("shop_id") or "") or None
        shop.shop_cipher = match.get("cipher") or match.get("shop_cipher")
        shop.region = match.get("region") or match.get("region_code")
        db.commit()
        client.shop_cipher = shop.shop_cipher
    return client


def sync_tiktok_orders() -> dict:
    db = SessionLocal()
    shop = None
    try:
        shop = _ensure_shop(db)
        client = _client_for_shop(db, shop)
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=settings.tiktok_lookback_hours)
        orders = client.search_orders(update_time_ge=int(start.timestamp()), update_time_lt=int(now.timestamp()))

        finance = {}
        finance_error = None
        try:
            finance = client.unsettled_transactions(search_time_ge=int(start.timestamp()), search_time_lt=int(now.timestamp()))
        except Exception as exc:
            finance_error = str(exc)

        created = updated = matched = unmatched = 0
        for raw in orders:
            tiktok_id = str(raw.get("id") or raw.get("order_id") or "")
            if not tiktok_id:
                continue
            row = db.scalar(select(TikTokOrder).where(
                TikTokOrder.shop_id == shop.id,
                TikTokOrder.tiktok_order_id == tiktok_id,
            ))
            is_new = row is None
            if row is None:
                row = TikTokOrder(shop_id=shop.id, tiktok_order_id=tiktok_id, status=str(raw.get("status") or "UNKNOWN"))
                db.add(row)

            note = _note(raw)
            amazon_ref = parse_amazon_order_id(note)
            product_name, quantity = _line_summary(raw)
            amazon = _find_amazon_order(db, shop.slug, amazon_ref)

            tx = finance.get(tiktok_id)
            if not tx:
                try:
                    tx = client.settled_order_transaction(tiktok_id)
                except Exception:
                    tx = None
            estimated, settled, refund = _finance_amount(tx)

            status = str(raw.get("status") or row.status or "UNKNOWN")
            row.status = status
            row.amazon_order_id_ref = amazon_ref
            row.amazon_order_db_id = amazon.id if amazon else None
            row.create_time = epoch_dt(raw.get("create_time") or raw.get("created_time")) or row.create_time
            row.update_time = epoch_dt(raw.get("update_time") or raw.get("updated_time")) or now
            row.currency = ((raw.get("payment") or {}).get("currency") or (tx or {}).get("currency") or "GBP")[:3]
            row.customer_paid_amount = _customer_paid(raw)

            # Do not erase a previously captured non-zero estimate with a
            # placeholder 0.00 from a later Finance response. This commonly
            # happens as an order moves from unsettled to delivered/settled.
            # Keep the latest meaningful estimate for estimated-profit display.
            if estimated is not None and (estimated != 0 or row.estimated_earnings in (None, 0)):
                row.estimated_earnings = estimated
            if settled is not None and (settled != 0 or row.settled_earnings in (None, 0)):
                row.settled_earnings = settled
            if refund is not None:
                row.refund_amount = refund
            row.cancellation_initiator = raw.get("cancellation_initiator")
            row.seller_note = note
            row.product_name = product_name
            row.quantity = quantity
            row.raw_json = json.dumps(raw, separators=(",", ":"), ensure_ascii=False)

            if is_new:
                created += 1
            else:
                updated += 1
            if amazon:
                matched += 1
            else:
                unmatched += 1

        shop.last_sync_at = now
        shop.last_sync_status = "success"
        shop.last_sync_message = f"{len(orders)} orders; {matched} matched; {unmatched} unmatched" + (f"; finance warning: {finance_error}" if finance_error else "")
        db.commit()
        return {
            "shop": shop.slug,
            "orders": len(orders),
            "created": created,
            "updated": updated,
            "matched": matched,
            "unmatched": unmatched,
            "finance_warning": finance_error,
            "synced_at": now.isoformat(),
        }
    except Exception as exc:
        db.rollback()
        if shop:
            try:
                shop.last_sync_at = datetime.now(timezone.utc)
                shop.last_sync_status = "failed"
                shop.last_sync_message = str(exc)[:2000]
                db.commit()
            except Exception:
                db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    try:
        print(json.dumps(sync_tiktok_orders(), indent=2))
    except Exception as exc:
        print(f"TikTok sync failed: {exc}", file=sys.stderr)
        raise
