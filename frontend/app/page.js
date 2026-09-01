"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "";
const PAGE_SIZE = 25;

export default function Home() {
  const [q, setQ] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [accounts, setAccounts] = useState([]);
  const [account, setAccount] = useState("all");
  const [orders, setOrders] = useState([]);
  const [dashboard, setDashboard] = useState({ account_totals: [], monthly: [] });
  const [pagination, setPagination] = useState({
    page: 1, page_size: PAGE_SIZE, total: 0, total_pages: 0,
    has_previous: false, has_next: false,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadAccounts() {
    try {
      const r = await fetch(`${API}/api/accounts`);
      if (!r.ok) throw new Error(`Accounts API failed (${r.status})`);
      setAccounts(await r.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load accounts");
    }
  }

  async function loadDashboard(selectedAccount = account) {
    try {
      const r = await fetch(`${API}/api/dashboard?account=${encodeURIComponent(selectedAccount)}`);
      if (!r.ok) throw new Error(`Dashboard API failed (${r.status})`);
      setDashboard(await r.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load dashboard");
    }
  }

  async function load(search = activeSearch, page = 1, selectedAccount = account) {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(PAGE_SIZE),
        account: selectedAccount,
      });
      if (search) params.set("q", search);

      const r = await fetch(`${API}/api/orders?${params.toString()}`);
      if (!r.ok) throw new Error(`API request failed (${r.status})`);

      const data = await r.json();
      setOrders(Array.isArray(data.items) ? data.items : []);
      setPagination(data.pagination || {
        page, page_size: PAGE_SIZE, total: 0, total_pages: 0,
        has_previous: false, has_next: false,
      });
    } catch (e) {
      setOrders([]);
      setPagination({
        page: 1, page_size: PAGE_SIZE, total: 0, total_pages: 0,
        has_previous: false, has_next: false,
      });
      setError(e instanceof Error ? e.message : "Failed to load orders");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAccounts();
    load("", 1, "all");
    loadDashboard("all");
  }, []);

  function submitSearch(e) {
    e.preventDefault();
    const search = q.trim();
    setActiveSearch(search);
    load(search, 1, account);
  }

  function changeAccount(e) {
    const selected = e.target.value;
    setAccount(selected);
    load(activeSearch, 1, selected);
    loadDashboard(selected);
  }

  function goToPage(page) {
    if (page < 1 || page > pagination.total_pages || page === pagination.page) return;
    load(activeSearch, page, account);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return <main>
    <div className="hero">
      <div><h1>JSS XRay</h1><p>Search your Amazon.co.uk purchase history.</p></div>
      <div className="count">{pagination.total} orders</div>
    </div>

    <div className="toolbar">
      <label>
        <span>Amazon account</span>
        <select value={account} onChange={changeAccount}>
          <option value="all">All Accounts</option>
          {accounts.map(a => <option key={a.slug} value={a.slug}>{a.name}</option>)}
        </select>
      </label>
    </div>

    <section className="dashboard">
      <h2>Dashboard</h2>
      <div className="cards">
        {dashboard.account_totals.map(a => (
          <div className="card" key={a.slug}>
            <small>{a.name}</small>
            <strong>{a.total_orders}</strong>
            <span>Total orders</span>
            <em>£{Number(a.total_spend || 0).toFixed(2)} spend</em>
          </div>
        ))}
      </div>
      <div className="monthly">
        <h3>Monthly orders{account !== "all" ? ` · ${accounts.find(a => a.slug === account)?.name || account}` : ""}</h3>
        {dashboard.monthly.length === 0 ? <p>No monthly order data yet.</p> :
          dashboard.monthly.map(m => (
            <div className="month-row" key={m.month}>
              <span>{new Date(`${m.month}T00:00:00`).toLocaleDateString("en-GB", {month:"long", year:"numeric"})}</span>
              <strong>{m.total_orders} orders</strong>
              <span>£{Number(m.total_spend || 0).toFixed(2)}</span>
            </div>
          ))
        }
      </div>
    </section>

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
      {orders.map(o => <article key={`${o.account?.slug}-${o.amazon_order_id}`}>
        <div>
          <strong>{o.items?.[0]?.product_name || "Amazon order"}</strong>
          <small>
            {o.amazon_order_id} · {o.order_date ? new Date(o.order_date).toLocaleDateString("en-GB") : "Date unknown"}
          </small>
          {account === "all" && <small className="account-badge">{o.account?.name}</small>}
        </div>
        <span className="status">{o.status.replaceAll("_", " ")}</span>
        <div className="order-meta">
          <div className="price">
            <small>Purchase price</small>
            <strong>{o.items?.[0]?.item_price != null
              ? `£${Number(o.items[0].item_price).toFixed(2)}`
              : o.order_total != null ? `£${Number(o.order_total).toFixed(2)}` : "—"}</strong>
            {o.items?.[0]?.quantity > 1 && <small>Qty {o.items[0].quantity}</small>}
          </div>
          <div className="delivery-date">
            <small>{o.status === "delivered" ? "Delivered" : "Estimated delivery"}</small>
            <strong>{
              o.status === "delivered" && o.delivered_date
                ? new Date(o.delivered_date).toLocaleDateString("en-GB")
                : o.status !== "delivered" && o.estimated_delivery_date
                  ? new Date(o.estimated_delivery_date).toLocaleDateString("en-GB")
                  : "—"
            }</strong>
          </div>
        </div>
      </article>)}
    </div>

    {pagination.total_pages > 1 && (
      <nav className="pagination" aria-label="Order pages">
        <button type="button" onClick={() => goToPage(pagination.page - 1)}
          disabled={!pagination.has_previous || loading}>Previous</button>
        <span>
          Page <strong>{pagination.page}</strong> of <strong>{pagination.total_pages}</strong>
          <small>
            {pagination.total > 0
              ? ` · Showing ${(pagination.page - 1) * pagination.page_size + 1}-${Math.min(pagination.page * pagination.page_size, pagination.total)} of ${pagination.total}`
              : ""}
          </small>
        </span>
        <button type="button" onClick={() => goToPage(pagination.page + 1)}
          disabled={!pagination.has_next || loading}>Next</button>
      </nav>
    )}
  </main>;
}
