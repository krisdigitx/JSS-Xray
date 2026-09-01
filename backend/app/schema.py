from sqlalchemy import text
from .db import Base, engine

ACCOUNTS = [
    ("tauri-royale", "Tauri Royale"),
    ("polaris-zone", "Polaris Zone"),
    ("jss-traders", "JSS Traders"),
]


def ensure_schema() -> None:
    """Create new tables and perform the one-time additive migration for multi-account support."""
    Base.metadata.create_all(bind=engine)

    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as conn:
        # Seed account catalogue.
        for slug, name in ACCOUNTS:
            conn.execute(
                text("""
                    INSERT INTO amazon_accounts (slug, name, enabled, created_at)
                    VALUES (:slug, :name, true, NOW())
                    ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
                """),
                {"slug": slug, "name": name},
            )

        # Existing installations do not have account_id. Existing data belongs to Tauri Royale.
        conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS account_id INTEGER"))
        conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivered_date TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS estimated_delivery_date TIMESTAMPTZ"))
        conn.execute(text("""
            UPDATE orders
            SET account_id = (
                SELECT id FROM amazon_accounts WHERE slug = 'tauri-royale'
            )
            WHERE account_id IS NULL
        """))

        # Replace legacy global uniqueness with account-aware uniqueness.
        conn.execute(text("ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_amazon_order_id_key"))
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_order_account_amazon_id_idx
            ON orders (account_id, amazon_order_id)
        """))

        # Ensure FK + NOT NULL after backfill.
        conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'fk_orders_account_id'
                ) THEN
                    ALTER TABLE orders
                    ADD CONSTRAINT fk_orders_account_id
                    FOREIGN KEY (account_id) REFERENCES amazon_accounts(id);
                END IF;
            END $$;
        """))
        conn.execute(text("ALTER TABLE orders ALTER COLUMN account_id SET NOT NULL"))

        # Gmail message ids need not be globally unique across separate mailboxes.
        conn.execute(text("ALTER TABLE order_events DROP CONSTRAINT IF EXISTS order_events_gmail_message_id_key"))
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_order_event_message_idx
            ON order_events (order_id, gmail_message_id)
        """))
