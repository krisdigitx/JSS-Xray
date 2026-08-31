# JSS XRay pagination

The orders API now accepts:

- `page` — default `1`
- `page_size` — default `25`, maximum `100`
- `q` — search term
- `status` — optional status filter

Example:

    GET /api/orders?page=2&page_size=25

The frontend displays 25 orders per page with Previous/Next controls and keeps the active search while paging.
