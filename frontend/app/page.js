"use client";
import { useEffect, useMemo, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "";
const PAGE_SIZE = 25;
const money = v => v == null ? "—" : `£${Number(v).toFixed(2)}`;
const date = v => v ? new Date(v).toLocaleString("en-GB", {dateStyle:"medium", timeStyle:"short"}) : "Never";
const day = v => v ? new Date(v).toLocaleDateString("en-GB") : "—";

export default function Home() {
  const [shops, setShops] = useState([]);
  const [shop, setShop] = useState("all");
  const [orders, setOrders] = useState([]);
  const [dashboard, setDashboard] = useState({tiktok_totals:[], tiktok_monthly:[], sync_status:[]});
  const [q, setQ] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [attentionOnly, setAttentionOnly] = useState(false);
  const [pagination, setPagination] = useState({page:1,page_size:PAGE_SIZE,total:0,total_pages:0,has_previous:false,has_next:false});
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState("");

  async function loadShops() {
    const r = await fetch(`${API}/api/tiktok/shops`, {cache:"no-store"});
    if (!r.ok) throw new Error(`TikTok shops API failed (${r.status})`);
    setShops(await r.json());
  }

  async function loadDashboard(selectedShop=shop) {
    const r = await fetch(`${API}/api/dashboard?shop=${encodeURIComponent(selectedShop)}`, {cache:"no-store"});
    if (!r.ok) throw new Error(`Dashboard API failed (${r.status})`);
    setDashboard(await r.json());
  }

  async function loadOrders(search=activeSearch, page=1, selectedShop=shop, attention=attentionOnly) {
    setLoading(true); setError("");
    try {
      const params = new URLSearchParams({page:String(page),page_size:String(PAGE_SIZE),shop:selectedShop,attention_only:String(attention)});
      if (search) params.set("q", search);
      const r = await fetch(`${API}/api/tiktok/orders?${params}`, {cache:"no-store"});
      if (!r.ok) throw new Error(`TikTok orders API failed (${r.status})`);
      const data = await r.json();
      setOrders(data.items || []); setPagination(data.pagination || {});
    } catch (e) { setError(e.message || "Failed to load TikTok orders"); setOrders([]); }
    finally { setLoading(false); }
  }

  async function reloadAll(selectedShop=shop, attention=attentionOnly) {
    try { await Promise.all([loadShops(), loadDashboard(selectedShop), loadOrders(activeSearch,1,selectedShop,attention)]); }
    catch(e) { setError(e.message || "Failed to load dashboard"); }
  }

  useEffect(() => { reloadAll("all", false); }, []);

  async function syncNow() {
    setSyncing(true); setError("");
    try {
      const r = await fetch(`${API}/api/tiktok/sync`, {method:"POST"});
      if (!r.ok) { const body = await r.text(); throw new Error(`TikTok sync failed (${r.status}): ${body}`); }
      await reloadAll(shop, attentionOnly);
    } catch(e) { setError(e.message || "TikTok sync failed"); }
    finally { setSyncing(false); }
  }

  const aggregate = useMemo(() => (dashboard.tiktok_totals || []).reduce((a,x)=>({
    orders:a.orders+(x.orders||0), matched:a.matched+(x.matched||0), unmatched:a.unmatched+(x.unmatched||0),
    earnings:a.earnings+Number(x.earnings||0), cost:a.cost+Number(x.amazon_cost||0), profit:a.profit+Number(x.profit||0),
    refunds:a.refunds+Number(x.refunds||0), cancelled:a.cancelled+(x.cancelled||0)
  }), {orders:0,matched:0,unmatched:0,earnings:0,cost:0,profit:0,refunds:0,cancelled:0}), [dashboard]);

  function submitSearch(e){e.preventDefault();const s=q.trim();setActiveSearch(s);loadOrders(s,1,shop,attentionOnly)}
  function changeShop(e){const s=e.target.value;setShop(s);loadDashboard(s);loadOrders(activeSearch,1,s,attentionOnly)}
  function toggleAttention(){const v=!attentionOnly;setAttentionOnly(v);loadOrders(activeSearch,1,shop,v)}
  function go(page){if(page<1||page>pagination.total_pages)return;loadOrders(activeSearch,page,shop,attentionOnly);window.scrollTo({top:0,behavior:"smooth"})}

  return <main>
    <header className="hero">
      <div><h1>JSS XRay</h1><p>TikTok Shop profitability and Amazon fulfilment reconciliation.</p></div>
      <button className="sync-button" onClick={syncNow} disabled={syncing}>{syncing?"Synchronising…":"Sync TikTok now"}</button>
    </header>

    <section className="sync-strip">
      {(dashboard.sync_status || []).length === 0 ? <span>No TikTok shop has synchronised yet.</span> : dashboard.sync_status.map(s=><div key={s.shop_slug}>
        <span className={`dot ${s.status || "unknown"}`}></span><strong>{s.shop_name}</strong>
        <span>{s.status || "not synced"}</span><small>{date(s.last_sync_at)}</small><small>{s.message}</small>
      </div>)}
    </section>

    <section className="summary-grid">
      <div className="metric"><small>TikTok orders</small><strong>{aggregate.orders}</strong><span>{aggregate.matched} matched</span></div>
      <div className={`metric ${aggregate.unmatched>0?"warn":""}`}><small>Needs attention</small><strong>{aggregate.unmatched}</strong><span>Unmatched Amazon orders</span></div>
      <div className="metric"><small>Estimated earnings</small><strong>{money(aggregate.earnings)}</strong><span>TikTok finance</span></div>
      <div className="metric"><small>Amazon cost</small><strong>{money(aggregate.cost)}</strong><span>From Gmail</span></div>
      <div className={`metric ${aggregate.profit<0?"negative":"positive"}`}><small>Estimated profit</small><strong>{money(aggregate.profit)}</strong><span>Earnings − Amazon cost</span></div>
      <div className="metric"><small>Refunds / cancelled</small><strong>{money(aggregate.refunds)}</strong><span>{aggregate.cancelled} cancelled orders</span></div>
    </section>

    <section className="shop-totals">
      <div className="section-head"><div><h2>Shop totals</h2><p>Current totals by TikTok Shop.</p></div>
        <select value={shop} onChange={changeShop}><option value="all">All shops</option>{shops.map(s=><option key={s.slug} value={s.slug}>{s.name}</option>)}</select>
      </div>
      <div className="shop-grid">{(dashboard.tiktok_totals||[]).map(s=><article key={s.slug}>
        <h3>{s.name}</h3><div><span>Orders</span><b>{s.orders}</b></div><div><span>Unmatched</span><b className={s.unmatched?"bad":""}>{s.unmatched}</b></div>
        <div><span>Earnings</span><b>{money(s.earnings)}</b></div><div><span>Amazon cost</span><b>{money(s.amazon_cost)}</b></div>
        <div><span>Profit</span><b className={Number(s.profit)<0?"bad":"good"}>{money(s.profit)}</b></div><div><span>Refunds</span><b>{money(s.refunds)}</b></div>
      </article>)}</div>
    </section>

    <section className="monthly">
      <h2>Monthly profitability</h2>
      {(dashboard.tiktok_monthly||[]).length===0 ? <p>No TikTok monthly data yet.</p> : <div className="monthly-table">
        <div className="monthly-row head"><span>Month</span><span>Shop</span><span>Orders</span><span>Earnings</span><span>Amazon cost</span><span>Profit</span><span>Refunds</span></div>
        {(dashboard.tiktok_monthly||[]).map((m,i)=><div className="monthly-row" key={`${m.shop_slug}-${m.month}-${i}`}>
          <span>{new Date(`${m.month}T00:00:00`).toLocaleDateString("en-GB",{month:"short",year:"numeric"})}</span><span>{m.shop_name}</span><span>{m.orders}</span><span>{money(m.earnings)}</span><span>{money(m.amazon_cost)}</span><strong className={Number(m.profit)<0?"bad":"good"}>{money(m.profit)}</strong><span>{money(m.refunds)}</span>
        </div>)}
      </div>}
    </section>

    <section className="orders-section">
      <div className="section-head"><div><h2>TikTok orders</h2><p>{pagination.total || 0} orders in this view.</p></div>
        <button className={attentionOnly?"attention active":"attention"} onClick={toggleAttention}>{attentionOnly?"Showing attention only":"Show unmatched only"}</button>
      </div>
      <form className="search" onSubmit={submitSearch}><input value={q} onChange={e=>setQ(e.target.value)} placeholder="TikTok order, Amazon order, product or note…"/><button disabled={loading}>{loading?"Loading…":"Search"}</button></form>
      {error && <div className="error"><strong>Error:</strong> {error}</div>}
      {!loading && !error && orders.length===0 && <div className="empty">No TikTok orders found.</div>}
      <div className="orders-list">{orders.map(o=><article className={!o.matched?"order attention-order":"order"} key={`${o.shop.slug}-${o.tiktok_order_id}`}>
        <div className="order-title"><div><strong>{o.product_name || "TikTok order"}</strong><small>{o.shop.name} · TikTok #{o.tiktok_order_id} · {day(o.create_time)}</small></div><span className={`badge ${o.status?.toLowerCase()}`}>{(o.status||"unknown").replaceAll("_"," ")}</span></div>
        <div className="order-grid">
          <div><small>TikTok earnings</small><strong>{money(o.display_earnings)}</strong>{o.settled_earnings!=null?<em>Settled</em>:<em>Estimated</em>}</div>
          <div><small>Amazon purchase cost</small><strong>{money(o.amazon_order?.purchase_cost)}</strong><em>Gmail source</em></div>
          <div><small>Estimated profit</small><strong className={Number(o.estimated_profit)<0?"bad":"good"}>{money(o.estimated_profit)}</strong></div>
          <div><small>Amazon match</small>{o.matched?<><strong>{o.amazon_order.amazon_order_id}</strong><em>{o.amazon_order.account.name}</em></>:<><strong className="bad">Needs attention</strong><em>{o.amazon_order_id_ref ? `Reference: ${o.amazon_order_id_ref}` : "No Amazon order ID found in note"}</em></>}</div>
          <div><small>Refund</small><strong>{money(o.refund_amount)}</strong></div>
          <div><small>Quantity</small><strong>{o.quantity || 1}</strong></div>
        </div>
        {o.seller_note && <div className="note"><small>TikTok note</small><span>{o.seller_note}</span></div>}
      </article>)}</div>
      {pagination.total_pages>1 && <nav className="pagination"><button onClick={()=>go(pagination.page-1)} disabled={!pagination.has_previous||loading}>Previous</button><span>Page <strong>{pagination.page}</strong> of <strong>{pagination.total_pages}</strong></span><button onClick={()=>go(pagination.page+1)} disabled={!pagination.has_next||loading}>Next</button></nav>}
    </section>
  </main>;
}
