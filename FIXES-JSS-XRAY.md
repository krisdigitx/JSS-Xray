# JSS XRay fixes

- Frontend now uses a same-origin `/api/*` runtime proxy to the backend service.
- Frontend reports API errors instead of silently showing zero orders.
- Helm injects `BACKEND_INTERNAL_URL=http://jss-xray-backend:8000`.
- Parser falls back to the Amazon email subject for product names.
- Existing Gmail events are re-parsed so `order_items` can be backfilled without deleting event history.
- Order status is recomputed from the newest event to avoid regressions when Gmail returns messages newest-first.
- PostgreSQL password env var is defined before `DATABASE_URL` so Kubernetes env substitution is reliable.
