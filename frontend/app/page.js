"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "";
const PAGE_SIZE = 25;

export default function Home() {
  const [q, setQ] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [orders, setOrders] = useState([]);
  const [pagination, setPagination] = useState({
    page: 1,
    page_size: PAGE_SIZE,
    total: 0,
    total_pages: 0,
    has_previous: false,
    has_next: false,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function load(search = activeSearch, page = 1) {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(PAGE_SIZE),
      });
      if (search) params.set("q", search);

      const r = await fetch(`${API}/api/orders?${params.toString()}`);
      if (!r.ok) throw new Error(`API request failed (${r.status})`);

      const data = await r.json();
      setOrders(Array.isArray(data.items) ? data.items : []);
      setPagination(data.pagination || {
        page,
        page_size: PAGE_SIZE,
        total: 0,
        total_pages: 0,
        has_previous: false,
        has_next: false,
      });
    } catch (e) {
      setOrders([]);
      setPagination({
        page: 1,
        page_size: PAGE_SIZE,
        total: 0,
        total_pages: 0,
        has_previous: false,
        has_next: false,
      });
      setError(e instanceof Error ? e.message : "Failed to load orders");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load("", 1); }, []);

  function submitSearch(e) {
    e.preventDefault();
    const search = q.trim();
    setActiveSearch(search);
    load(search, 1);
  }

  function goToPage(page) {
    if (page < 1 || page > pagination.total_pages || page === pagination.page) return;
    load(activeSearch, page);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return <main>
    <div className="hero">
      <div><h1>JSS XRay</h1><p>Search your Amazon.co.uk purchase history.</p></div>
      <div className="count">{pagination.total} orders</div>
    </div>

    <form onSubmit={submitSearch} className="search">
      <input
        value={q}
        onChange={e => setQ(e.target.value)}
        placeholder="Product, order number, ASIN or seller…"
      />
      <button disabled={loading}>{loading ? "Loading…" : "Search"}</button>
    </form>

    {error && <p><strong>API error:</strong> {error}</p>}
    {!loading && orders.length === 0 && !error && <p className="empty">No orders found.</p>}

    <div className="table">
      {orders.map(o => <article key={o.amazon_order_id}>
        <div>
          <strong>{o.items?.[0]?.product_name || "Amazon order"}</strong>
          <small>
            {o.amazon_order_id} · {o.order_date ? new Date(o.order_date).toLocaleDateString("en-GB") : "Date unknown"}
          </small>
        </div>
        <span className="status">{o.status.replaceAll("_", " ")}</span>
        <strong>{o.order_total != null ? `£${o.order_total.toFixed(2)}` : "—"}</strong>
      </article>)}
    </div>

    {pagination.total_pages > 1 && (
      <nav className="pagination" aria-label="Order pages">
        <button
          type="button"
          onClick={() => goToPage(pagination.page - 1)}
          disabled={!pagination.has_previous || loading}
        >
          Previous
        </button>

        <span>
          Page <strong>{pagination.page}</strong> of <strong>{pagination.total_pages}</strong>
          <small>
            {pagination.total > 0
              ? ` · Showing ${(pagination.page - 1) * pagination.page_size + 1}-${Math.min(pagination.page * pagination.page_size, pagination.total)} of ${pagination.total}`
              : ""}
          </small>
        </span>

        <button
          type="button"
          onClick={() => goToPage(pagination.page + 1)}
          disabled={!pagination.has_next || loading}
        >
          Next
        </button>
      </nav>
    )}
  </main>;
}
