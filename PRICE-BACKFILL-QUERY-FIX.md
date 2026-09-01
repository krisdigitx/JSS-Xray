# PostgreSQL DISTINCT/ORDER BY backfill query fix

The historical price-backfill query previously joined `order_items`, used
`SELECT DISTINCT`, and ordered by expressions that were not in the SELECT list.
PostgreSQL rejects that shape with:

    for SELECT DISTINCT, ORDER BY expressions must appear in select list

The query now uses `EXISTS` / `NOT EXISTS` checks against `order_items`.
This avoids duplicate `OrderEvent` rows, removes the need for `DISTINCT`, and
preserves the required priority ordering:

1. Ordered messages first
2. Newest event time
3. Newest event ID
4. Backfill limit
