"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [q, setQ] = useState("");
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(false);

  async function load(search = "") {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/orders?q=${encodeURIComponent(search)}`);
      setOrders(await r.json());
    } finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  return <main>
    <div className="hero">
      <div><h1>JSS XRay</h1><p>Search your Amazon.co.uk purchase history.</p></div>
      <div className="count">{orders.length} orders</div>
    </div>
    <form onSubmit={e => {e.preventDefault(); load(q);}} className="search">
      <input value={q} onChange={e => setQ(e.target.value)} placeholder="Product, order number, ASIN or seller…" />
      <button>Search</button>
    </form>
    {loading ? <p>Loading…</p> :
      <div className="table">
        {orders.map(o => <article key={o.amazon_order_id}>
          <div>
            <strong>{o.items?.[0]?.product_name || "Amazon order"}</strong>
            <small>{o.amazon_order_id} · {o.order_date ? new Date(o.order_date).toLocaleDateString("en-GB") : "Date unknown"}</small>
          </div>
          <span className="status">{o.status.replaceAll("_", " ")}</span>
          <strong>{o.order_total != null ? `£${o.order_total.toFixed(2)}` : "—"}</strong>
        </article>)}
      </div>}
  </main>;
}
