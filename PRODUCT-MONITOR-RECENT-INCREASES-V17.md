# Product Monitor Recent Amazon Price Increases – v17

Adds history-based Amazon price increase filtering to Product Price Monitor.

- Uses existing `product_price_history`; no DB migration required.
- New 7-day stat counts products that experienced an Amazon price increase in the last 7 days, even if a later scan was unchanged or lower.
- New movement filter: latest increase, last 24 hours, last 7 days, last 30 days, latest decrease.
- Recent-increase filters show the latest increase event on each product: old price, new price, increase amount and timestamp.
- Search, Seller SKU source filter, loss filter and pagination continue to combine with the movement filter.
