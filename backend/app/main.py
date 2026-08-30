from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload
from .db import Base, engine, get_db
from .models import Order, OrderItem
from .sync import sync_orders

app = FastAPI(title="JSS XRay", version="1.0.0")
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
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = select(Order).options(selectinload(Order.items)).order_by(Order.order_date.desc().nullslast()).limit(limit)
    if status:
        stmt = stmt.where(Order.status == status)
    if q:
        like = f"%{q}%"
        stmt = stmt.join(OrderItem, isouter=True).where(or_(
            Order.amazon_order_id.ilike(like),
            OrderItem.product_name.ilike(like),
            OrderItem.asin.ilike(like),
            OrderItem.seller.ilike(like),
        )).distinct()
    result = db.scalars(stmt).all()
    return [{
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
    } for o in result]

@app.post("/api/sync")
def sync():
    return sync_orders()
