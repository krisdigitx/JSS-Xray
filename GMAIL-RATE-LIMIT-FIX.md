# Gmail API rate-limit fix

This release changes Gmail syncing to reduce HTTP 429 responses.

## What changed

- Gmail list operations are capped at 50 recent messages per run.
- Existing Gmail message IDs already stored in PostgreSQL are reused for historical
  price enrichment. Up to 50 missing-price messages are fetched directly per run,
  so the app no longer lists 500 historical messages every 30 minutes.
- Recent sync is incremental. It searches from the latest stored Gmail event with a
  24-hour overlap, relying on database deduplication for safety.
- Gmail HTTP 429/5xx responses automatically retry with exponential backoff and
  respect Retry-After when Google supplies it.
- The Gmail API service object is reused within the process rather than rebuilt for
  every message.
- The three account CronJobs are staggered:
  - Tauri Royale: minute 0 and 30
  - Polaris Zone: minute 10 and 40
  - JSS Traders: minute 20 and 50

## Historical price backfill

The backfill does not require a broad Gmail list query. JSS XRay selects Gmail
message IDs from `order_events` for orders/items that still have NULL prices and
re-reads up to 50 of those messages per CronJob run.

This means missing purchase prices should fill progressively while keeping Gmail
API traffic bounded.
