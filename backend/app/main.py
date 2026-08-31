from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload
from .db import Base, engine, get_db
from .models import Order, OrderItem
from .sync import sync_orders

app = FastAPI(title="JSS XRay", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/api/orders")
def orders(
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    filters = []
    if status:
        filters.append(Order.status == status)

    search_filter = None
    if q:
        like = f"%{q}%"
        search_filter = or_(
            Order.amazon_order_id.ilike(like),
            OrderItem.product_name.ilike(like),
            OrderItem.asin.ilike(like),
            OrderItem.seller.ilike(like),
        )

    count_stmt = select(func.count(func.distinct(Order.id))).select_from(Order)
    if q:
        count_stmt = count_stmt.join(OrderItem, isouter=True).where(search_filter)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = db.scalar(count_stmt) or 0

    stmt = (
        select(Order)
        .options(selectinload(Order.items))
        .order_by(Order.order_date.desc().nullslast(), Order.id.desc())
    )
    if q:
        stmt = stmt.join(OrderItem, isouter=True).where(search_filter).distinct()
    if filters:
        stmt = stmt.where(*filters)

    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    result = db.scalars(stmt).unique().all()

    total_pages = (total + page_size - 1) // page_size if total else 0

    return {
        "items": [{
            "amazon_order_id": o.amazon_order_id,
            "order_date": o.order_date,
            "status": o.status,
            "order_total": float(o.order_total) if o.order_total is not None else None,
            "currency": o.currency,
            "items": [{
                "product_name": i.product_name,
                "asin": i.asin,
                "seller": i.seller,
                "quantity": i.quantity,
                "item_price": float(i.item_price) if i.item_price is not None else None,
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

@app.post("/api/sync")
def sync():
    return sync_orders()
