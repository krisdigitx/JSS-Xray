# Product Price Monitor v10 — Polaris Zone Seller SKU source

This feature is additive. Existing TikTok order sync, finance/profit logic, Amazon order matching, Gmail cost parsing, fulfilment status and dashboard behaviour are unchanged.

## Source of truth

For Polaris Zone, the TikTok **Seller SKU** is the Amazon source URL.

Example:

```text
Seller SKU: https://amzn.eu/d/0cllMYzD
```

Supported source hosts:

- `https://amzn.eu/...`
- `https://www.amazon.co.uk/...`

JSS Xray does not manually write or override product source URLs. If Seller SKU is blank or invalid, update it in TikTok Seller Center and click **Sync products** (or wait for the scheduled product-monitor CronJob).

## Flow

TikTok Products API → Seller SKU → JSS Xray source mapping → resolve Amazon short URL → read current Amazon price → record history → compare with TikTok price.

The original Seller SKU remains the authoritative source URL. For `amzn.eu` links, JSS Xray follows the redirect and captures the Amazon ASIN when possible.

## Statuses

- `PENDING`: valid Seller SKU imported, awaiting source check
- `OK`: Amazon price found
- `SOURCE_MISSING`: no Seller SKU; add Amazon URL in TikTok
- `INVALID_SOURCE`: Seller SKU exists but is not an accepted Amazon URL
- `BLOCKED`: Amazon bot/CAPTCHA page
- `NOT_FOUND`: page loaded but price was not identified
- `ERROR`: HTTP/network/source error

The existing 6-hour Kubernetes CronJob remains unchanged.
