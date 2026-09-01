# JSS XRay purchase-price backfill MIME fix

## Root causes

1. Gmail Amazon messages are commonly `multipart/alternative`.
2. The previous `_body()` returned the first `text/plain` MIME part and stopped.
3. Amazon's reliable price representation can exist only in `text/html`, such as
   `£8<sup>49</sup>`.
4. Historical backfill previously preferred newest events, so its limited Gmail
   reads could be spent on Delivered/Dispatched emails that do not contain the
   original purchase price.

## Changes

- Read and combine both `text/plain` and `text/html` Gmail MIME parts.
- Preserve HTML long enough for the existing parser to normalize Amazon
  superscript/span fractional prices correctly.
- Prioritize `ordered` events when backfilling rows missing price.
- Add `price_enriched` to sync output for easy verification.

Existing orders with NULL `order_total` or `item_price` remain eligible for
automatic backfill, so no database reset is required.
