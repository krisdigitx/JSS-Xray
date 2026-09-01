from sqlalchemy import inspect, text
from .db import Base, engine

ACCOUNTS = [
    ("tauri-royale", "Tauri Royale"),
    ("polaris-zone", "Polaris Zone"),
    ("jss-traders", "JSS Traders"),
]

MIGRATION_VERSION = 1
ADVISORY_LOCK_ID = 746737971  # Stable application-specific PostgreSQL advisory lock.


def _column_names(conn, table_name: str) -> set[str]:
    return {c["name"] for c in inspect(conn).get_columns(table_name)}


def _constraint_names(conn, table_name: str) -> set[str]:
    inspector = inspect(conn)
    names = {
        c.get("name")
        for c in inspector.get_unique_constraints(table_name)
        if c.get("name")
    }
    names.update(
        c.get("name")
        for c in inspector.get_foreign_keys(table_name)
        if c.get("name")
    )
    return names


def run_migrations() -> None:
    """
    Run schema changes once from the dedicated Kubernetes migration Job.

    Normal API pods and Gmail CronJobs MUST NOT call this function.
    """
    if engine.dialect.name != "postgresql":
        Base.metadata.create_all(bind=engine)
        return

    with engine.connect() as conn:
        # Serialize migration Jobs even if ArgoCD retries or two syncs overlap.
        conn.execute(text("SELECT pg_advisory_lock(:lock_id)"), {"lock_id": ADVISORY_LOCK_ID})
        try:
            # Migrations may legitimately need longer than normal API statements,
            # but should fail instead of hanging forever behind a lock.
            conn.execute(text("SET statement_timeout = '120s'"))
            conn.execute(text("SET lock_timeout = '10s'"))
            conn.execute(text("SET idle_in_transaction_session_timeout = '60s'"))

            # Creates only tables that do not exist. Existing tables are not altered here.
            Base.metadata.create_all(bind=conn)

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))
            conn.commit()

            already_applied = conn.scalar(
                text("SELECT 1 FROM schema_migrations WHERE version = :version"),
                {"version": MIGRATION_VERSION},
            )
            if already_applied:
                print(f"Migration {MIGRATION_VERSION} already applied; nothing to do.", flush=True)
                return

            # Seed account catalogue before backfilling existing orders.
            for slug, name in ACCOUNTS:
                conn.execute(
                    text("""
                        INSERT INTO amazon_accounts (slug, name, enabled, created_at)
                        VALUES (:slug, :name, true, NOW())
                        ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
                    """),
                    {"slug": slug, "name": name},
                )

            columns = _column_names(conn, "orders")

            # Only execute DDL when the column is genuinely missing. This avoids
            # taking ACCESS EXCLUSIVE locks on every application deployment.
            if "account_id" not in columns:
                conn.execute(text("ALTER TABLE orders ADD COLUMN account_id INTEGER"))

            if "delivered_date" not in columns:
                conn.execute(text("ALTER TABLE orders ADD COLUMN delivered_date TIMESTAMPTZ"))

            if "estimated_delivery_date" not in columns:
                conn.execute(text("ALTER TABLE orders ADD COLUMN estimated_delivery_date TIMESTAMPTZ"))

            conn.execute(text("""
                UPDATE orders
                SET account_id = (
                    SELECT id FROM amazon_accounts WHERE slug = 'tauri-royale'
                )
                WHERE account_id IS NULL
            """))

            constraints = _constraint_names(conn, "orders")

            if "orders_amazon_order_id_key" in constraints:
                conn.execute(text(
                    "ALTER TABLE orders DROP CONSTRAINT orders_amazon_order_id_key"
                ))

            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_order_account_amazon_id_idx
                ON orders (account_id, amazon_order_id)
            """))

            constraints = _constraint_names(conn, "orders")
            if "fk_orders_account_id" not in constraints:
                conn.execute(text("""
                    ALTER TABLE orders
                    ADD CONSTRAINT fk_orders_account_id
                    FOREIGN KEY (account_id) REFERENCES amazon_accounts(id)
                """))

            # Only change nullability if needed.
            nullable = {
                c["name"]: c["nullable"]
                for c in inspect(conn).get_columns("orders")
            }
            if nullable.get("account_id", True):
                conn.execute(text(
                    "ALTER TABLE orders ALTER COLUMN account_id SET NOT NULL"
                ))

            event_constraints = _constraint_names(conn, "order_events")
            if "order_events_gmail_message_id_key" in event_constraints:
                conn.execute(text(
                    "ALTER TABLE order_events DROP CONSTRAINT order_events_gmail_message_id_key"
                ))

            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_order_event_message_idx
                ON order_events (order_id, gmail_message_id)
            """))

            conn.execute(
                text("INSERT INTO schema_migrations(version) VALUES (:version)"),
                {"version": MIGRATION_VERSION},
            )
            conn.commit()
            print(f"Migration {MIGRATION_VERSION} applied successfully.", flush=True)
        except Exception:
            conn.rollback()
            raise
        finally:
            # Session-level advisory lock must be explicitly released.
            try:
                conn.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": ADVISORY_LOCK_ID},
                )
                conn.commit()
            except Exception:
                pass
