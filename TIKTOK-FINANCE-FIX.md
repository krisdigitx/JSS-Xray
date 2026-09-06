# TikTok Finance API fix

The TikTok Finance API v202507 `GET /finance/202507/orders/unsettled` requires the
`sort_field` query parameter. JSS Xray now sends:

- `sort_field=order_create_time`
- `sort_order=ASC`

This fixes the HTTP 400 seen after the Polaris Zone order sync. HTTP errors now also
include TikTok's JSON response body in the sync logs to make future API validation
errors diagnosable.
