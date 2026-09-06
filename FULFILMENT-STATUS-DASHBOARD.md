# Polaris Zone fulfilment status dashboard

This update adds fulfilment-status counts to the TikTok dashboard for Polaris Zone.

## Dashboard status groups

- Awaiting shipment: `AWAITING_SHIPMENT`, `AWAITING_COLLECTION`, `TO_SHIP`, `READY_TO_SHIP`
- Delivered: `DELIVERED`, `COMPLETED`
- Cancelled: `CANCELLED`, `CANCELED`

`COMPLETED` is counted with delivered because it represents a successfully fulfilled order after delivery. `AWAITING_COLLECTION` is counted with awaiting shipment because the parcel has not yet entered the carrier network.

## UI changes

- Removed `From Gmail` under the Amazon cost summary.
- Removed `Gmail source` from individual Amazon purchase-cost cards.
- Added Polaris Zone order-status cards for Awaiting shipment, Delivered, Cancelled and Total orders.
- Added fulfilment counts to Shop totals.
- Added Awaiting, Delivered and Cancelled columns to Monthly profitability.
- Dashboard starts filtered to `polaris-zone` for now.
