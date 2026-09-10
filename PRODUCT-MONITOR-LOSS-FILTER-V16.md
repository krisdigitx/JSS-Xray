# Product Monitor loss filter v16

Adds an explicit loss-risk flag when the current Amazon source price is greater than the TikTok selling price. This is a guaranteed pre-fee loss signal, not a full fee-adjusted profit calculation.

- Adds `loss_risk` and `loss_amount` to product payloads.
- Adds `loss_only=true` API filter.
- Adds global Loss in profit statistic.
- Adds red LOSS RISK badge/card highlighting.
- Adds All profit statuses / Loss in profit UI filter.
- Existing Seller SKU source, search and pagination behaviour remains unchanged.
