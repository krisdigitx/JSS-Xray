# Delivery date support

JSS XRay now stores and displays:

- `delivered_date` for delivered orders.
- `estimated_delivery_date` for orders that are not yet delivered.

The Gmail parser looks for delivery-date text in Amazon transactional messages.
When an order reaches `delivered`, the explicit delivered date is used if present; otherwise the delivered email timestamp is used.
Once delivered, the estimated date is cleared.

Existing Gmail messages can be re-parsed by the normal sync process, so historical orders can be enriched without creating duplicate events.

The UI shows the date alongside Purchase price for every order.
