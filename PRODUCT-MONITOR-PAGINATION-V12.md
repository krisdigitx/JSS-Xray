# v12 Orders dashboard fix + Product Price Monitor pagination

- Restores `loadShops()` and `loadDashboard()` on the Orders dashboard. These functions were accidentally omitted when Product Price Monitor was moved to its standalone page in v11.
- Product Price Monitor now uses server/API pagination parameters: `page` and `page_size`.
- Default Product Monitor page size is 25 products.
- Overall statistics remain calculated across the full filtered Polaris Zone catalogue, not only the visible page.
- Previous/Next controls show current page, total pages and total products.
- Existing TikTok order, finance, Gmail, fulfilment and product-source logic is otherwise unchanged.
