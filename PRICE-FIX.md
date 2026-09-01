# Purchase price parsing and historical backfill fix

This release fixes:
- clipped Purchase price / Delivery metadata in order rows;
- missing Amazon.co.uk purchase prices;
- dashboard spend remaining £0.00 when historical orders lacked totals;
- historical items not being updated after parser improvements.

Recognised formats include `Order Total`, `Grand Total`, `Total`, `Item Subtotal`, `Item Price`, and simple HTML variants.

Existing Gmail message IDs remain deduplicated. Re-syncing an account enriches its existing orders/items rather than duplicating events.
