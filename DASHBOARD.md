# JSS XRay dashboard

Adds:
- Purchase price displayed against every order.
- Per-account cards for Tauri Royale, Polaris Zone and JSS Traders.
- Total order count per account.
- Total recorded purchase spend per account.
- Monthly order totals and monthly spend.
- Account selector also filters the monthly dashboard.

Purchase price is sourced from the Amazon transactional email parser. For older records where item_price is absent, the UI falls back to the recorded order_total. Existing Gmail messages are re-parsed by the sync process, so parser-supported historical prices can be enriched without duplicating events.
