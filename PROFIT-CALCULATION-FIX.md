# TikTok estimated profit and customer-paid totals

This revision corrects estimated profitability and adds gross TikTok sales totals.

## Profit rule

Estimated profit is now calculated as:

`TikTok estimated earnings - Amazon purchase cost`

TikTok `estimated_earnings` is preferred even when `settled_earnings` exists as `0.00`. Settled earnings are used only as a fallback if no estimate is available.

Example: TikTok order `576946475585739420` with estimated earnings £12.38 and Amazon purchase cost £9.34 displays estimated profit £3.04.

## Customer-paid totals

`customer_paid_amount` is now aggregated and shown as Customer paid / Total TikTok sales at dashboard, shop and monthly levels, and on each order card.
