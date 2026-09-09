from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


class AmazonAccount(Base):
    __tablename__ = "amazon_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    orders: Mapped[list["Order"]] = relationship(back_populates="account")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("account_id", "amazon_order_id", name="uq_order_account_amazon_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("amazon_accounts.id"), index=True)
    amazon_order_id: Mapped[str] = mapped_column(String(32), index=True)
    order_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="ordered", index=True)
    order_total: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="GBP")
    delivery_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    delivered_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estimated_delivery_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    order_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    account: Mapped["AmazonAccount"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    events: Mapped[list["OrderEvent"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    tiktok_orders: Mapped[list["TikTokOrder"]] = relationship(back_populates="amazon_order")


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (UniqueConstraint("order_id", "asin", "product_name", name="uq_order_item"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_name: Mapped[str] = mapped_column(Text)
    asin: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    seller: Mapped[str | None] = mapped_column(Text, nullable=True)
    condition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    item_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    product_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    order: Mapped["Order"] = relationship(back_populates="items")


class OrderEvent(Base):
    __tablename__ = "order_events"
    __table_args__ = (
        UniqueConstraint("order_id", "gmail_message_id", name="uq_order_event_message"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    gmail_message_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_subject: Mapped[str | None] = mapped_column(Text, nullable=True)

    order: Mapped["Order"] = relationship(back_populates="events")


class TikTokShop(Base):
    __tablename__ = "tiktok_shops"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    shop_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    shop_cipher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region: Mapped[str | None] = mapped_column(String(16), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refresh_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_sync_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    orders: Mapped[list["TikTokOrder"]] = relationship(back_populates="shop")
    products: Mapped[list["TikTokProduct"]] = relationship(back_populates="shop")


class TikTokOrder(Base):
    __tablename__ = "tiktok_orders"
    __table_args__ = (UniqueConstraint("shop_id", "tiktok_order_id", name="uq_tiktok_shop_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("tiktok_shops.id"), index=True)
    tiktok_order_id: Mapped[str] = mapped_column(String(64), index=True)
    amazon_order_id_ref: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    amazon_order_db_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(64), index=True)
    create_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    update_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="GBP")
    customer_paid_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    estimated_earnings: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    settled_earnings: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    refund_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    cancellation_initiator: Mapped[str | None] = mapped_column(String(64), nullable=True)
    seller_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    shop: Mapped["TikTokShop"] = relationship(back_populates="orders")
    amazon_order: Mapped["Order | None"] = relationship(back_populates="tiktok_orders")


class TikTokProduct(Base):
    __tablename__ = "tiktok_products"
    __table_args__ = (UniqueConstraint("shop_id", "tiktok_product_id", name="uq_tiktok_shop_product"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("tiktok_shops.id"), index=True)
    tiktok_product_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(64), index=True, default="UNKNOWN")
    currency: Mapped[str] = mapped_column(String(3), default="GBP")
    tiktok_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    seller_sku: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sku_count: Mapped[int] = mapped_column(Integer, default=0)

    # Amazon source mapping is intentionally private to JSS Xray.  We do not
    # modify the live TikTok listing or overload the public product description.
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_asin: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    source_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    previous_source_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    source_currency: Mapped[str] = mapped_column(String(3), default="GBP")
    source_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_check_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_check_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    shop: Mapped["TikTokShop"] = relationship(back_populates="products")
    price_history: Mapped[list["ProductPriceHistory"]] = relationship(back_populates="product", cascade="all, delete-orphan")


class ProductPriceHistory(Base):
    __tablename__ = "product_price_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("tiktok_products.id", ondelete="CASCADE"), index=True)
    tiktok_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    source_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    source_currency: Mapped[str] = mapped_column(String(3), default="GBP")
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    product: Mapped["TikTokProduct"] = relationship(back_populates="price_history")
