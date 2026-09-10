from datetime import datetime, timezone
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from .config import settings
from .db import get_db
from .models import AmazonAccount, Order, OrderItem, ProductPriceHistory, TikTokOrder, TikTokProduct, TikTokShop
from .sync import sync_orders
from .tiktok import TikTokClient, exchange_auth_code
from .tiktok_sync import sync_tiktok_orders
from .product_monitor import check_mapped_products, check_product_source, extract_asin, sync_tiktok_products

app = FastAPI(title="JSS XRay", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# TikTok fulfilment status groups used by the operational dashboard.
# AWAITING_COLLECTION is included in awaiting shipment because the parcel has
# not yet entered the carrier network. COMPLETED is counted as delivered since
# it represents a successfully fulfilled order after delivery.
AWAITING_SHIPMENT_STATUSES = {
    "AWAITING_SHIPMENT", "AWAITING_COLLECTION", "TO_SHIP", "READY_TO_SHIP"
}
DELIVERED_STATUSES = {"DELIVERED", "COMPLETED"}
CANCELLED_STATUSES = {"CANCELLED", "CANCELED"}


def _f(value):
    return float(value) if value is not None else None


def _amazon_cost(order: Order | None):
    if not order:
        return None
    return _f(order.order_total)


def _effective_earnings_value(row: TikTokOrder):
    """Return the best TikTok payout figure for profitability.

    TikTok can expose temporary 0.00 finance placeholders while an order moves
    between unsettled and settled datasets. For a live/delivered order, a zero
    is treated as not reconciled yet rather than as a real payout; otherwise
    the dashboard incorrectly reports -Amazon-cost as profit. Cancelled orders
    are the exception where a genuine zero payout is valid.
    """
    estimated = row.estimated_earnings
    settled = row.settled_earnings
    if estimated not in (None, 0):
        return estimated, "estimated"
    if settled not in (None, 0):
        return settled, "settled"
    if (row.status or "").upper() in CANCELLED_STATUSES:
        if settled is not None:
            return settled, "settled"
        if estimated is not None:
            return estimated, "estimated"
    return None, None


def _earnings(row: TikTokOrder):
    value, _ = _effective_earnings_value(row)
    return _f(value)


def _profit(row: TikTokOrder):
    # Estimated profit = effective TikTok earnings - actual Amazon purchase cost.
    earnings, _ = _effective_earnings_value(row)
    cost = row.amazon_order.order_total if row.amazon_order else None
    if earnings is None or cost is None:
        return None
    return float(Decimal(earnings) - Decimal(cost))


def _tiktok_order_payload(row: TikTokOrder):
    amazon = row.amazon_order
    return {
        "tiktok_order_id": row.tiktok_order_id,
        "shop": {"slug": row.shop.slug, "name": row.shop.name},
        "status": row.status,
        "create_time": row.create_time,
        "update_time": row.update_time,
        "product_name": row.product_name,
        "quantity": row.quantity,
        "currency": row.currency,
        "customer_paid_amount": _f(row.customer_paid_amount),
        "estimated_earnings": _f(row.estimated_earnings),
        "settled_earnings": _f(row.settled_earnings),
        "display_earnings": _earnings(row),
        "earnings_source": _effective_earnings_value(row)[1],
        "refund_amount": _f(row.refund_amount),
        "cancellation_initiator": row.cancellation_initiator,
        "seller_note": row.seller_note,
        "amazon_order_id_ref": row.amazon_order_id_ref,
        "matched": amazon is not None,
        "amazon_order": None if not amazon else {
            "amazon_order_id": amazon.amazon_order_id,
            "status": amazon.status,
            "order_date": amazon.order_date,
            "purchase_cost": _amazon_cost(amazon),
            "currency": amazon.currency,
            "account": {"slug": amazon.account.slug, "name": amazon.account.name},
        },
        "estimated_profit": _profit(row),
    }


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/accounts")
def accounts(db: Session = Depends(get_db)):
    result = db.scalars(
        select(AmazonAccount)
        .where(AmazonAccount.enabled.is_(True))
        .order_by(AmazonAccount.name)
    ).all()
    return [{"id": a.id, "slug": a.slug, "name": a.name} for a in result]


@app.get("/api/tiktok/shops")
def tiktok_shops(db: Session = Depends(get_db)):
    shops = db.scalars(select(TikTokShop).where(TikTokShop.enabled.is_(True)).order_by(TikTokShop.name)).all()
    return [{
        "slug": s.slug,
        "name": s.name,
        "region": s.region,
        "authorized": bool(s.shop_cipher and (s.access_token or settings.tiktok_access_token)),
        "last_sync_at": s.last_sync_at,
        "last_sync_status": s.last_sync_status,
        "last_sync_message": s.last_sync_message,
    } for s in shops]


@app.get("/api/dashboard")
def dashboard(
    account: str | None = Query(default=None, description="Amazon account slug; omit or use 'all' for all accounts"),
    shop: str | None = Query(default=None, description="TikTok shop slug; omit or use 'all' for all shops"),
    db: Session = Depends(get_db),
):
    account_filter = []
    if account and account != "all":
        account_filter.append(AmazonAccount.slug == account)

    totals_stmt = (
        select(
            AmazonAccount.slug,
            AmazonAccount.name,
            func.count(Order.id).label("total_orders"),
            func.coalesce(func.sum(Order.order_total), 0).label("total_spend"),
        )
        .select_from(AmazonAccount)
        .outerjoin(Order, Order.account_id == AmazonAccount.id)
        .where(AmazonAccount.enabled.is_(True))
        .group_by(AmazonAccount.id, AmazonAccount.slug, AmazonAccount.name)
        .order_by(AmazonAccount.name)
    )
    account_totals = [{
        "slug": row.slug,
        "name": row.name,
        "total_orders": int(row.total_orders or 0),
        "total_spend": float(row.total_spend or 0),
    } for row in db.execute(totals_stmt)]

    month_expr = func.date_trunc("month", Order.order_date)
    monthly_stmt = (
        select(
            month_expr.label("month"),
            func.count(Order.id).label("total_orders"),
            func.coalesce(func.sum(Order.order_total), 0).label("total_spend"),
        )
        .select_from(Order)
        .join(AmazonAccount)
        .where(Order.order_date.is_not(None))
    )
    if account_filter:
        monthly_stmt = monthly_stmt.where(*account_filter)
    monthly_stmt = monthly_stmt.group_by(month_expr).order_by(month_expr.desc()).limit(24)
    monthly = [{
        "month": row.month.date().isoformat() if row.month else None,
        "total_orders": int(row.total_orders or 0),
        "total_spend": float(row.total_spend or 0),
    } for row in db.execute(monthly_stmt)]

    tt_filters = []
    if shop and shop != "all":
        tt_filters.append(TikTokShop.slug == shop)

    # Estimated profitability must prefer TikTok's estimated earnings.  Settled
    # earnings are only a fallback when no estimate exists.
    # A zero estimate can be a TikTok placeholder after settlement; prefer a
    # non-zero estimate, then settled earnings, then fall back to the literal
    # zero estimate when both are zero/missing.
    earning_expr = case(
        (TikTokOrder.status.in_(CANCELLED_STATUSES), func.coalesce(
            func.nullif(TikTokOrder.estimated_earnings, 0),
            func.nullif(TikTokOrder.settled_earnings, 0),
            TikTokOrder.estimated_earnings,
            TikTokOrder.settled_earnings,
            0,
        )),
        else_=func.coalesce(
            func.nullif(TikTokOrder.estimated_earnings, 0),
            func.nullif(TikTokOrder.settled_earnings, 0),
        ),
    )
    customer_paid_expr = func.coalesce(TikTokOrder.customer_paid_amount, 0)
    cost_expr = func.coalesce(Order.order_total, 0)
    tt_totals_stmt = (
        select(
            TikTokShop.slug,
            TikTokShop.name,
            func.count(TikTokOrder.id).label("orders"),
            func.sum(case((TikTokOrder.amazon_order_db_id.is_not(None), 1), else_=0)).label("matched"),
            func.sum(case((and_(TikTokOrder.id.is_not(None), TikTokOrder.amazon_order_db_id.is_(None)), 1), else_=0)).label("unmatched"),
            func.coalesce(func.sum(customer_paid_expr), 0).label("customer_paid"),
            func.coalesce(func.sum(earning_expr), 0).label("earnings"),
            func.coalesce(func.sum(cost_expr), 0).label("amazon_cost"),
            func.coalesce(func.sum(case((TikTokOrder.amazon_order_db_id.is_not(None), earning_expr - cost_expr), else_=0)), 0).label("profit"),
            func.coalesce(func.sum(TikTokOrder.refund_amount), 0).label("refunds"),
            func.sum(case((TikTokOrder.status.in_(AWAITING_SHIPMENT_STATUSES), 1), else_=0)).label("awaiting_shipment"),
            func.sum(case((TikTokOrder.status.in_(DELIVERED_STATUSES), 1), else_=0)).label("delivered"),
            func.sum(case((TikTokOrder.status.in_(CANCELLED_STATUSES), 1), else_=0)).label("cancelled"),
        )
        .select_from(TikTokShop)
        .outerjoin(TikTokOrder, TikTokOrder.shop_id == TikTokShop.id)
        .outerjoin(Order, Order.id == TikTokOrder.amazon_order_db_id)
        .where(TikTokShop.enabled.is_(True))
        .group_by(TikTokShop.id, TikTokShop.slug, TikTokShop.name)
        .order_by(TikTokShop.name)
    )
    if tt_filters:
        tt_totals_stmt = tt_totals_stmt.where(*tt_filters)
    tiktok_totals = [{
        "slug": r.slug,
        "name": r.name,
        "orders": int(r.orders or 0),
        "matched": int(r.matched or 0),
        "unmatched": int(r.unmatched or 0),
        "customer_paid": float(r.customer_paid or 0),
        "earnings": float(r.earnings or 0),
        "amazon_cost": float(r.amazon_cost or 0),
        "profit": float(r.profit or 0),
        "refunds": float(r.refunds or 0),
        "awaiting_shipment": int(r.awaiting_shipment or 0),
        "delivered": int(r.delivered or 0),
        "cancelled": int(r.cancelled or 0),
    } for r in db.execute(tt_totals_stmt)]

    tt_month = func.date_trunc("month", TikTokOrder.create_time)
    tt_monthly_stmt = (
        select(
            TikTokShop.slug,
            TikTokShop.name,
            tt_month.label("month"),
            func.count(TikTokOrder.id).label("orders"),
            func.coalesce(func.sum(customer_paid_expr), 0).label("customer_paid"),
            func.coalesce(func.sum(earning_expr), 0).label("earnings"),
            func.coalesce(func.sum(cost_expr), 0).label("amazon_cost"),
            func.coalesce(func.sum(case((TikTokOrder.amazon_order_db_id.is_not(None), earning_expr - cost_expr), else_=0)), 0).label("profit"),
            func.coalesce(func.sum(TikTokOrder.refund_amount), 0).label("refunds"),
            func.sum(case((TikTokOrder.status.in_(AWAITING_SHIPMENT_STATUSES), 1), else_=0)).label("awaiting_shipment"),
            func.sum(case((TikTokOrder.status.in_(DELIVERED_STATUSES), 1), else_=0)).label("delivered"),
            func.sum(case((TikTokOrder.status.in_(CANCELLED_STATUSES), 1), else_=0)).label("cancelled"),
        )
        .select_from(TikTokOrder)
        .join(TikTokShop)
        .outerjoin(Order, Order.id == TikTokOrder.amazon_order_db_id)
        .where(TikTokOrder.create_time.is_not(None))
    )
    if tt_filters:
        tt_monthly_stmt = tt_monthly_stmt.where(*tt_filters)
    tt_monthly_stmt = tt_monthly_stmt.group_by(TikTokShop.slug, TikTokShop.name, tt_month).order_by(tt_month.desc()).limit(72)
    tiktok_monthly = [{
        "shop_slug": r.slug,
        "shop_name": r.name,
        "month": r.month.date().isoformat() if r.month else None,
        "orders": int(r.orders or 0),
        "customer_paid": float(r.customer_paid or 0),
        "earnings": float(r.earnings or 0),
        "amazon_cost": float(r.amazon_cost or 0),
        "profit": float(r.profit or 0),
        "refunds": float(r.refunds or 0),
        "awaiting_shipment": int(r.awaiting_shipment or 0),
        "delivered": int(r.delivered or 0),
        "cancelled": int(r.cancelled or 0),
    } for r in db.execute(tt_monthly_stmt)]

    sync_status = [{
        "shop_slug": s.slug,
        "shop_name": s.name,
        "last_sync_at": s.last_sync_at,
        "status": s.last_sync_status,
        "message": s.last_sync_message,
    } for s in db.scalars(select(TikTokShop).order_by(TikTokShop.name)).all()]

    return {
        "account_totals": account_totals,
        "monthly": monthly,
        "tiktok_totals": tiktok_totals,
        "tiktok_monthly": tiktok_monthly,
        "sync_status": sync_status,
        "selected_account": account or "all",
        "selected_shop": shop or "all",
    }


@app.get("/api/orders")
def orders(
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    account: str | None = Query(default=None, description="Amazon account slug; omit or use 'all' for all accounts"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    filters = []
    if status:
        filters.append(Order.status == status)
    if account and account != "all":
        filters.append(AmazonAccount.slug == account)

    search_filter = None
    if q:
        like = f"%{q}%"
        search_filter = or_(
            Order.amazon_order_id.ilike(like),
            OrderItem.product_name.ilike(like),
            OrderItem.asin.ilike(like),
            OrderItem.seller.ilike(like),
        )

    count_stmt = select(func.count(func.distinct(Order.id))).select_from(Order).join(AmazonAccount)
    if q:
        count_stmt = count_stmt.join(OrderItem, isouter=True).where(search_filter)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = db.scalar(count_stmt) or 0

    stmt = (
        select(Order)
        .join(AmazonAccount)
        .options(selectinload(Order.items), selectinload(Order.account))
        .order_by(Order.order_date.desc().nullslast(), Order.id.desc())
    )
    if q:
        stmt = stmt.join(OrderItem, isouter=True).where(search_filter).distinct()
    if filters:
        stmt = stmt.where(*filters)

    offset = (page - 1) * page_size
    result = db.scalars(stmt.offset(offset).limit(page_size)).unique().all()
    total_pages = (total + page_size - 1) // page_size if total else 0

    return {
        "items": [{
            "amazon_order_id": o.amazon_order_id,
            "order_date": o.order_date,
            "status": o.status,
            "order_total": _f(o.order_total),
            "currency": o.currency,
            "delivered_date": o.delivered_date,
            "estimated_delivery_date": o.estimated_delivery_date,
            "account": {"slug": o.account.slug, "name": o.account.name},
            "items": [{
                "product_name": i.product_name,
                "asin": i.asin,
                "seller": i.seller,
                "quantity": i.quantity,
                "item_price": _f(i.item_price),
            } for i in o.items],
        } for o in result],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_previous": page > 1,
            "has_next": page < total_pages,
        },
    }


@app.get("/api/tiktok/orders")
def tiktok_orders(
    q: str | None = Query(default=None),
    shop: str | None = Query(default=None),
    attention_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    filters = []
    if shop and shop != "all":
        filters.append(TikTokShop.slug == shop)
    if attention_only:
        filters.append(TikTokOrder.amazon_order_db_id.is_(None))
    if q:
        like = f"%{q}%"
        filters.append(or_(
            TikTokOrder.tiktok_order_id.ilike(like),
            TikTokOrder.amazon_order_id_ref.ilike(like),
            TikTokOrder.product_name.ilike(like),
            TikTokOrder.seller_note.ilike(like),
        ))

    count_stmt = select(func.count(TikTokOrder.id)).select_from(TikTokOrder).join(TikTokShop)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = db.scalar(count_stmt) or 0

    stmt = (
        select(TikTokOrder)
        .join(TikTokShop)
        .options(
            selectinload(TikTokOrder.shop),
            selectinload(TikTokOrder.amazon_order).selectinload(Order.account),
        )
        .order_by(TikTokOrder.create_time.desc().nullslast(), TikTokOrder.id.desc())
    )
    if filters:
        stmt = stmt.where(*filters)
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).unique().all()
    total_pages = (total + page_size - 1) // page_size if total else 0
    return {
        "items": [_tiktok_order_payload(row) for row in rows],
        "pagination": {
            "page": page, "page_size": page_size, "total": total, "total_pages": total_pages,
            "has_previous": page > 1, "has_next": page < total_pages,
        },
    }


@app.get("/api/tiktok/oauth/callback")
def tiktok_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if not code:
        raise HTTPException(status_code=400, detail="TikTok callback did not contain an authorization code")
    if settings.tiktok_oauth_state and state != settings.tiktok_oauth_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    if not settings.tiktok_app_key or not settings.tiktok_app_secret:
        raise HTTPException(status_code=500, detail="TikTok app credentials are not configured")

    token = exchange_auth_code(settings.tiktok_app_key, settings.tiktok_app_secret, code)
    if token.get("user_type") not in (0, "0", None):
        raise HTTPException(status_code=400, detail="Authorization is not a seller token")

    access = token.get("access_token")
    client = TikTokClient(settings.tiktok_app_key, settings.tiktok_app_secret, access)
    authorized = client.authorized_shops()
    match = next((s for s in authorized if (s.get("name") or s.get("shop_name")) == settings.tiktok_shop_name), None)
    if not match and len(authorized) == 1:
        match = authorized[0]
    if not match:
        raise HTTPException(status_code=400, detail=f"Could not identify {settings.tiktok_shop_name} in authorized shops")

    shop = db.scalar(select(TikTokShop).where(TikTokShop.slug == settings.tiktok_shop_slug))
    if not shop:
        shop = TikTokShop(slug=settings.tiktok_shop_slug, name=settings.tiktok_shop_name)
        db.add(shop)
    shop.shop_id = str(match.get("id") or match.get("shop_id") or "") or None
    shop.shop_cipher = match.get("cipher") or match.get("shop_cipher")
    shop.region = match.get("region") or match.get("region_code")
    shop.access_token = access
    shop.refresh_token = token.get("refresh_token")
    try:
        shop.access_token_expires_at = datetime.fromtimestamp(int(token.get("access_token_expire_in")), tz=timezone.utc) if token.get("access_token_expire_in") else None
        shop.refresh_token_expires_at = datetime.fromtimestamp(int(token.get("refresh_token_expire_in")), tz=timezone.utc) if token.get("refresh_token_expire_in") else None
    except (ValueError, TypeError, OSError):
        pass
    shop.last_sync_status = "authorized"
    shop.last_sync_message = "TikTok seller authorization completed; waiting for first sync"
    db.commit()
    return RedirectResponse(url="/?tiktok=connected", status_code=302)


@app.post("/api/sync")
def sync():
    return sync_orders()


@app.post("/api/tiktok/sync")
def tiktok_sync():
    return sync_tiktok_orders()


class ProductSourceUpdate(BaseModel):
    source_url: str | None = None


def _product_monitor_payload(row: TikTokProduct):
    tiktok_price = _f(row.tiktok_price)
    source_price = _f(row.source_price)
    previous = _f(row.previous_source_price)
    difference = (tiktok_price - source_price) if tiktok_price is not None and source_price is not None else None
    source_change = (source_price - previous) if source_price is not None and previous is not None else None
    return {
        "id": row.id,
        "tiktok_product_id": row.tiktok_product_id,
        "title": row.title,
        "status": row.status,
        "currency": row.currency,
        "tiktok_price": tiktok_price,
        "seller_sku": row.seller_sku,
        "sku_count": row.sku_count,
        "source_url": row.source_url,
        "source_asin": row.source_asin,
        "source_price": source_price,
        "previous_source_price": previous,
        "source_price_change": source_change,
        "price_difference": difference,
        "loss_risk": difference is not None and difference < 0,
        "loss_amount": abs(difference) if difference is not None and difference < 0 else None,
        "source_checked_at": row.source_checked_at,
        "source_check_status": row.source_check_status or ("UNMAPPED" if not row.source_url else "PENDING"),
        "source_check_message": row.source_check_message,
        "product_synced_at": row.product_synced_at,
        "shop": {"slug": row.shop.slug, "name": row.shop.name},
    }


@app.get("/api/product-monitor/products")
def product_monitor_products(
    shop: str = Query(default="polaris-zone"),
    q: str | None = Query(default=None),
    mapped: bool | None = Query(default=None),
    loss_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    # Statistics always describe the full Polaris Zone catalogue. Search/source
    # filters affect only the product list and its pagination.
    shop_filter = [TikTokShop.slug == shop]
    list_filters = list(shop_filter)
    if mapped is True:
        list_filters.append(TikTokProduct.source_url.is_not(None))
    elif mapped is False:
        list_filters.append(TikTokProduct.source_url.is_(None))
    if q:
        like = f"%{q.strip()}%"
        list_filters.append(or_(
            TikTokProduct.title.ilike(like),
            TikTokProduct.tiktok_product_id.ilike(like),
            TikTokProduct.seller_sku.ilike(like),
            TikTokProduct.source_asin.ilike(like),
        ))

    stats_rows = db.scalars(
        select(TikTokProduct)
        .join(TikTokShop)
        .options(selectinload(TikTokProduct.shop))
        .where(*shop_filter)
        .order_by(TikTokProduct.title)
    ).all()
    stats_payload = [_product_monitor_payload(row) for row in stats_rows]

    rows = db.scalars(
        select(TikTokProduct)
        .join(TikTokShop)
        .options(selectinload(TikTokProduct.shop))
        .where(*list_filters)
        .order_by(TikTokProduct.title)
    ).all()
    filtered_payload = [_product_monitor_payload(row) for row in rows]
    if loss_only:
        filtered_payload = [p for p in filtered_payload if p["loss_risk"]]
    filtered_total = len(filtered_payload)
    total_pages = (filtered_total + page_size - 1) // page_size if filtered_total else 0
    safe_page = min(page, total_pages) if total_pages else 1
    offset = (safe_page - 1) * page_size
    payload = filtered_payload[offset:offset + page_size]

    return {
        "shop": shop,
        "total": len(stats_payload),
        "filtered_total": filtered_total,
        "mapped": sum(1 for p in stats_payload if p["source_url"]),
        "unmapped": sum(1 for p in stats_payload if not p["source_url"]),
        "price_increased": sum(1 for p in stats_payload if p["source_price_change"] is not None and p["source_price_change"] > 0),
        "price_decreased": sum(1 for p in stats_payload if p["source_price_change"] is not None and p["source_price_change"] < 0),
        "prices_checked": sum(1 for p in stats_payload if p["source_checked_at"]),
        "source_errors": sum(1 for p in stats_payload if p["source_check_status"] in {"ERROR", "BLOCKED", "NOT_FOUND"}),
        "loss_risk": sum(1 for p in stats_payload if p["loss_risk"]),
        "filters": {"q": q or "", "mapped": mapped, "loss_only": loss_only},
        "pagination": {
            "page": safe_page,
            "page_size": page_size,
            "total": filtered_total,
            "total_pages": total_pages,
            "has_previous": safe_page > 1,
            "has_next": safe_page < total_pages,
        },
        "items": payload,
    }


@app.post("/api/product-monitor/sync-products")
def product_monitor_sync_products(shop: str = Query(default="polaris-zone")):
    if shop != "polaris-zone":
        raise HTTPException(status_code=400, detail="Product Price Monitor is enabled for Polaris Zone only")
    return sync_tiktok_products(shop)


@app.put("/api/product-monitor/products/{product_id}/source")
def product_monitor_update_source(product_id: int, update: ProductSourceUpdate, db: Session = Depends(get_db)):
    # Seller SKU in TikTok is the source of truth for Polaris Zone. Keep this
    # endpoint for backwards compatibility, but do not allow JSS Xray to create
    # a competing source mapping.
    raise HTTPException(
        status_code=409,
        detail="Amazon source is managed from the TikTok Seller SKU. Add or update the Amazon URL in Polaris Zone, then sync products.",
    )


@app.post("/api/product-monitor/products/{product_id}/check")
def product_monitor_check_one(product_id: int, db: Session = Depends(get_db)):
    row = db.scalar(select(TikTokProduct).where(TikTokProduct.id == product_id).options(selectinload(TikTokProduct.shop)))
    if not row:
        raise HTTPException(status_code=404, detail="TikTok product not found")
    if not row.source_url:
        raise HTTPException(status_code=400, detail="Seller SKU does not contain an Amazon source URL. Add it in TikTok, then sync products.")
    result = check_product_source(row, db)
    db.commit()
    return {"result": result, "product": _product_monitor_payload(row)}


@app.post("/api/product-monitor/check")
def product_monitor_check_all(shop: str = Query(default="polaris-zone")):
    if shop != "polaris-zone":
        raise HTTPException(status_code=400, detail="Product Price Monitor is enabled for Polaris Zone only")
    return check_mapped_products(shop)


@app.get("/api/version")
def api_version():
    return {"version": "v16-product-monitor-loss-filter", "finance_sort_field": "order_create_time", "product_price_monitor": "polaris-zone", "product_source": "seller_sku"}
