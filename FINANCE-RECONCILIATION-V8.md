# Finance reconciliation v8

- Sends required `sort_field=order_create_time` and `sort_order=ASC` to TikTok `/finance/202507/orders/unsettled`.
- Treats non-cancelled `0.00` finance placeholders as unknown, so profit is not falsely calculated as `-Amazon cost`.
- Continues to fetch settled finance per order when it is absent from unsettled transactions.
- Adds `/api/version` so the running backend can be verified after GitOps deployment.
