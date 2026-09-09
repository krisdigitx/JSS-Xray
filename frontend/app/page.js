"use client";
import { useEffect, useMemo, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "";
const PAGE_SIZE = 25;
const money = v => v == null ? "—" : `£${Number(v).toFixed(2)}`;
const date = v => v ? new Date(v).toLocaleString("en-GB", {dateStyle:"medium", timeStyle:"short"}) : "Never";
const day = v => v ? new Date(v).toLocaleDateString("en-GB") : "—";

export default function Home() {
  const [shops, setShops] = useState([]);
  const [shop, setShop] = useState("polaris-zone");
  const [orders, setOrders] = useState([]);
  const [dashboard, setDashboard] = useState({tiktok_totals:[], tiktok_monthly:[], sync_status:[]});
  const [q, setQ] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [attentionOnly, setAttentionOnly] = useState(false);
  const [pagination, setPagination] = useState({page:1,page_size:PAGE_SIZE,total:0,total_pages:0,has_previous:false,has_next:false});
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState("");

  // Product Price Monitor is additive and intentionally separate from the
  // existing TikTok order/profitability state above.
  const [productMonitor, setProductMonitor] = useState({total:0,mapped:0,unmapped:0,price_increased:0,source_errors:0,items:[]});
  const [productBusy, setProductBusy] = useState(false);
  const [productMessage, setProductMessage] = useState("");

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

  async function loadProductMonitor() {
    const r = await fetch(`${API}/api/product-monitor/products?shop=polaris-zone`, {cache:"no-store"});
    if (!r.ok) throw new Error(`Product Price Monitor API failed (${r.status})`);
    const data = await r.json();
    setProductMonitor(data);
  }

  async function syncProducts() {
    setProductBusy(true); setProductMessage("");
    try {
      const r = await fetch(`${API}/api/product-monitor/sync-products?shop=polaris-zone`, {method:"POST"});
      if (!r.ok) throw new Error(await r.text());
      const result = await r.json();
      await loadProductMonitor();
      setProductMessage(`Product catalogue synced: ${result.products || 0} active Polaris Zone products.`);
    } catch(e) { setProductMessage(`Product sync failed: ${e.message || e}`); }
    finally { setProductBusy(false); }
  }

  async function checkProductSource(product) {
    setProductBusy(true); setProductMessage("");
    try {
      const r = await fetch(`${API}/api/product-monitor/products/${product.id}/check`, {method:"POST"});
      if (!r.ok) throw new Error(await r.text());
      await loadProductMonitor();
      setProductMessage(`Amazon price checked for ${product.title}.`);
    } catch(e) { setProductMessage(`Price check failed: ${e.message || e}`); }
    finally { setProductBusy(false); }
  }

  async function checkAllProductSources() {
    setProductBusy(true); setProductMessage("");
    try {
      const r = await fetch(`${API}/api/product-monitor/check?shop=polaris-zone`, {method:"POST"});
      if (!r.ok) throw new Error(await r.text());
      const result = await r.json();
      await loadProductMonitor();
      setProductMessage(`Amazon scan complete: ${result.ok || 0}/${result.checked || 0} mapped products checked successfully.`);
    } catch(e) { setProductMessage(`Amazon scan failed: ${e.message || e}`); }
    finally { setProductBusy(false); }
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

  useEffect(() => { reloadAll("polaris-zone", false); loadProductMonitor().catch(()=>{}); }, []);

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
    customerPaid:a.customerPaid+Number(x.customer_paid||0), earnings:a.earnings+Number(x.earnings||0), cost:a.cost+Number(x.amazon_cost||0), profit:a.profit+Number(x.profit||0),
    refunds:a.refunds+Number(x.refunds||0), awaitingShipment:a.awaitingShipment+(x.awaiting_shipment||0),
    delivered:a.delivered+(x.delivered||0), cancelled:a.cancelled+(x.cancelled||0)
  }), {orders:0,matched:0,unmatched:0,customerPaid:0,earnings:0,cost:0,profit:0,refunds:0,awaitingShipment:0,delivered:0,cancelled:0}), [dashboard]);

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
      <div className="metric"><small>Customer paid</small><strong>{money(aggregate.customerPaid)}</strong><span>Total TikTok sales</span></div>
      <div className="metric"><small>Estimated earnings</small><strong>{money(aggregate.earnings)}</strong><span>After TikTok fees</span></div>
      <div className="metric"><small>Amazon cost</small><strong>{money(aggregate.cost)}</strong></div>
      <div className={`metric ${aggregate.profit<0?"negative":"positive"}`}><small>Estimated profit</small><strong>{money(aggregate.profit)}</strong><span>Earnings − Amazon cost</span></div>
      <div className="metric"><small>Refunds / cancelled</small><strong>{money(aggregate.refunds)}</strong><span>{aggregate.cancelled} cancelled orders</span></div>
    </section>

    <section className="fulfilment-status">
      <div className="section-head"><div><h2>Order status</h2><p>Current Polaris Zone TikTok fulfilment status.</p></div></div>
      <div className="status-grid">
        <div className="status-card awaiting"><small>Awaiting shipment</small><strong>{aggregate.awaitingShipment}</strong><span>Orders not shipped yet</span></div>
        <div className="status-card delivered"><small>Delivered</small><strong>{aggregate.delivered}</strong><span>Delivered / completed orders</span></div>
        <div className="status-card cancelled"><small>Cancelled</small><strong>{aggregate.cancelled}</strong><span>Cancelled orders</span></div>
        <div className="status-card"><small>Total orders</small><strong>{aggregate.orders}</strong><span>Polaris Zone orders</span></div>
      </div>
    </section>

    <section className="shop-totals">
      <div className="section-head"><div><h2>Shop totals</h2><p>Current totals for Polaris Zone.</p></div></div>
      <div className="shop-grid">{(dashboard.tiktok_totals||[]).map(s=><article key={s.slug}>
        <h3>{s.name}</h3><div><span>Orders</span><b>{s.orders}</b></div><div><span>Unmatched</span><b className={s.unmatched?"bad":""}>{s.unmatched}</b></div>
        <div><span>Awaiting shipment</span><b>{s.awaiting_shipment}</b></div><div><span>Delivered</span><b className="good">{s.delivered}</b></div>
        <div><span>Cancelled</span><b className={s.cancelled?"bad":""}>{s.cancelled}</b></div>
        <div><span>Customer paid</span><b>{money(s.customer_paid)}</b></div><div><span>Estimated earnings</span><b>{money(s.earnings)}</b></div><div><span>Amazon cost</span><b>{money(s.amazon_cost)}</b></div>
        <div><span>Profit</span><b className={Number(s.profit)<0?"bad":"good"}>{money(s.profit)}</b></div><div><span>Refunds</span><b>{money(s.refunds)}</b></div>
      </article>)}</div>
    </section>

    <section className="monthly">
      <h2>Monthly profitability</h2>
      {(dashboard.tiktok_monthly||[]).length===0 ? <p>No TikTok monthly data yet.</p> : <div className="monthly-table">
        <div className="monthly-row head"><span>Month</span><span>Shop</span><span>Orders</span><span>Awaiting</span><span>Delivered</span><span>Cancelled</span><span>Customer paid</span><span>Estimated earnings</span><span>Amazon cost</span><span>Profit</span><span>Refunds</span></div>
        {(dashboard.tiktok_monthly||[]).map((m,i)=><div className="monthly-row" key={`${m.shop_slug}-${m.month}-${i}`}>
          <span>{new Date(`${m.month}T00:00:00`).toLocaleDateString("en-GB",{month:"short",year:"numeric"})}</span><span>{m.shop_name}</span><span>{m.orders}</span><span>{m.awaiting_shipment}</span><span className="good">{m.delivered}</span><span className={m.cancelled?"bad":""}>{m.cancelled}</span><span>{money(m.customer_paid)}</span><span>{money(m.earnings)}</span><span>{money(m.amazon_cost)}</span><strong className={Number(m.profit)<0?"bad":"good"}>{money(m.profit)}</strong><span>{money(m.refunds)}</span>
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
          <div><small>Customer paid</small><strong>{money(o.customer_paid_amount)}</strong><em>TikTok sale</em></div>
          <div><small>Estimated earnings</small><strong>{money(o.display_earnings)}</strong><em>{o.earnings_source==="settled"?"Settled":"Estimated"}</em></div>
          <div><small>Amazon purchase cost</small><strong>{money(o.amazon_order?.purchase_cost)}</strong></div>
          <div><small>Estimated profit</small><strong className={Number(o.estimated_profit)<0?"bad":"good"}>{money(o.estimated_profit)}</strong></div>
          <div><small>Amazon match</small>{o.matched?<><strong>{o.amazon_order.amazon_order_id}</strong><em>{o.amazon_order.account.name}</em></>:<><strong className="bad">Needs attention</strong><em>{o.amazon_order_id_ref ? `Reference: ${o.amazon_order_id_ref}` : "No Amazon order ID found in note"}</em></>}</div>
          <div><small>Refund</small><strong>{money(o.refund_amount)}</strong></div>
          <div><small>Quantity</small><strong>{o.quantity || 1}</strong></div>
        </div>
        {o.seller_note && <div className="note"><small>TikTok note</small><span>{o.seller_note}</span></div>}
      </article>)}</div>
      {pagination.total_pages>1 && <nav className="pagination"><button onClick={()=>go(pagination.page-1)} disabled={!pagination.has_previous||loading}>Previous</button><span>Page <strong>{pagination.page}</strong> of <strong>{pagination.total_pages}</strong></span><button onClick={()=>go(pagination.page+1)} disabled={!pagination.has_next||loading}>Next</button></nav>}
    </section>

    <section className="product-monitor-section">
      <div className="section-head">
        <div><h2>Product price monitor</h2><p>Polaris Zone TikTok prices compared with the Amazon source URL stored in each product Seller SKU.</p></div>
        <div className="product-monitor-actions">
          <button className="attention" onClick={syncProducts} disabled={productBusy}>{productBusy?"Working…":"Sync products"}</button>
          <button className="sync-button" onClick={checkAllProductSources} disabled={productBusy || !productMonitor.mapped}>Check Amazon prices</button>
        </div>
      </div>
      <div className="product-monitor-summary">
        <div><small>Active products</small><strong>{productMonitor.total || 0}</strong></div>
        <div><small>Seller SKU sources</small><strong>{productMonitor.mapped || 0}</strong></div>
        <div><small>Seller SKU missing</small><strong>{productMonitor.unmapped || 0}</strong></div>
        <div><small>Amazon price increased</small><strong>{productMonitor.price_increased || 0}</strong></div>
        <div><small>Source check problems</small><strong>{productMonitor.source_errors || 0}</strong></div>
      </div>
      {productMessage && <div className="product-monitor-message">{productMessage}</div>}
      {(productMonitor.items || []).length === 0 ? <div className="empty">No product catalogue imported yet. Click <strong>Sync products</strong>.</div> :
      <div className="product-monitor-list">{(productMonitor.items || []).map(p=>{
        const sourceDelta = p.source_price_change;
        const spread = p.price_difference;
        return <article className="product-monitor-card" key={p.id}>
          <div className="product-monitor-title">
            <div><strong>{p.title}</strong><small>TikTok #{p.tiktok_product_id}</small></div>
            <span className={`source-status ${(p.source_check_status||"unmapped").toLowerCase()}`}>{p.source_check_status || "UNMAPPED"}</span>
          </div>
          <div className="product-monitor-grid">
            <div><small>TikTok price</small><strong>{money(p.tiktok_price)}</strong></div>
            <div><small>Amazon current price</small><strong>{money(p.source_price)}</strong></div>
            <div><small>TikTok − Amazon</small><strong className={spread!=null && spread<0?"bad":"good"}>{money(spread)}</strong></div>
            <div><small>Amazon price movement</small><strong className={sourceDelta>0?"bad":sourceDelta<0?"good":""}>{sourceDelta==null?"—":`${sourceDelta>0?"+":""}${money(sourceDelta)}`}</strong><em>{sourceDelta>0?"Price up":sourceDelta<0?"Price down":sourceDelta===0?"No change":"No previous scan"}</em></div>
            <div><small>Last Amazon check</small><strong>{p.source_checked_at?date(p.source_checked_at):"Never"}</strong></div>
          </div>
          <div className="source-mapping">
            <div className="seller-sku-source">
              <small>Seller SKU / Amazon source</small>
              {p.source_url ? <a href={p.source_url} target="_blank" rel="noreferrer">{p.seller_sku}</a> : <strong className="bad">Add Amazon URL to Seller SKU in TikTok</strong>}
            </div>
            <button className="sync-button" onClick={()=>checkProductSource(p)} disabled={productBusy || !p.source_url}>Check now</button>
          </div>
          {p.source_asin && <div className="product-source-meta"><span>ASIN: <strong>{p.source_asin}</strong></span>{p.previous_source_price!=null && <span>Previous Amazon price: <strong>{money(p.previous_source_price)}</strong></span>}</div>}
          {p.source_check_message && <div className="product-source-warning">{p.source_check_message}</div>}
        </article>
      })}</div>}
    </section>

  </main>;
}
