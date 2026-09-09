"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

const API = process.env.NEXT_PUBLIC_API_URL || "";
const money = v => v == null ? "—" : `£${Number(v).toFixed(2)}`;
const date = v => v ? new Date(v).toLocaleString("en-GB", {dateStyle:"medium", timeStyle:"short"}) : "Never";

export default function ProductMonitorPage() {
  const [productMonitor, setProductMonitor] = useState({total:0,mapped:0,unmapped:0,price_increased:0,source_errors:0,items:[]});
  const [productBusy, setProductBusy] = useState(false);
  const [productMessage, setProductMessage] = useState("");
  const [error, setError] = useState("");

  async function loadProductMonitor() {
    setError("");
    const r = await fetch(`${API}/api/product-monitor/products?shop=polaris-zone`, {cache:"no-store"});
    if (!r.ok) throw new Error(`Product Price Monitor API failed (${r.status})`);
    setProductMonitor(await r.json());
  }
  async function syncProducts() {
    setProductBusy(true); setProductMessage(""); setError("");
    try {
      const r = await fetch(`${API}/api/product-monitor/sync-products?shop=polaris-zone`, {method:"POST"});
      if (!r.ok) throw new Error(await r.text());
      const result = await r.json(); await loadProductMonitor();
      setProductMessage(`Product catalogue synced: ${result.products || 0} active Polaris Zone products.`);
    } catch(e) { setError(`Product sync failed: ${e.message || e}`); } finally { setProductBusy(false); }
  }
  async function checkProductSource(product) {
    setProductBusy(true); setProductMessage(""); setError("");
    try {
      const r = await fetch(`${API}/api/product-monitor/products/${product.id}/check`, {method:"POST"});
      if (!r.ok) throw new Error(await r.text());
      await loadProductMonitor(); setProductMessage(`Amazon price checked for ${product.title}.`);
    } catch(e) { setError(`Price check failed: ${e.message || e}`); } finally { setProductBusy(false); }
  }
  async function checkAllProductSources() {
    setProductBusy(true); setProductMessage(""); setError("");
    try {
      const r = await fetch(`${API}/api/product-monitor/check?shop=polaris-zone`, {method:"POST"});
      if (!r.ok) throw new Error(await r.text());
      const result = await r.json(); await loadProductMonitor();
      setProductMessage(`Amazon scan complete: ${result.ok || 0}/${result.checked || 0} mapped products checked successfully.`);
    } catch(e) { setError(`Amazon scan failed: ${e.message || e}`); } finally { setProductBusy(false); }
  }
  useEffect(() => { loadProductMonitor().catch(e=>setError(e.message || "Failed to load product monitor")); }, []);

  const stats = useMemo(() => {
    const items=productMonitor.items || [];
    const priceDown=items.filter(p=>Number(p.source_price_change)<0).length;
    const unchanged=items.filter(p=>p.source_price_change != null && Number(p.source_price_change)===0).length;
    const checked=items.filter(p=>p.source_checked_at).length;
    return {priceDown, unchanged, checked};
  }, [productMonitor]);

  return <main>
    <nav className="app-nav"><Link href="/">Orders dashboard</Link><Link className="active" href="/product-monitor">Product price monitor</Link></nav>
    <header className="hero product-page-hero">
      <div><h1>Product Price Monitor</h1><p>Polaris Zone catalogue compared with Amazon sources stored in TikTok Seller SKU.</p></div>
      <div className="product-monitor-actions"><button className="attention" onClick={syncProducts} disabled={productBusy}>{productBusy?"Working…":"Sync products"}</button><button className="sync-button" onClick={checkAllProductSources} disabled={productBusy || !productMonitor.mapped}>Check Amazon prices</button></div>
    </header>

    <section className="product-stats-grid">
      <div className="metric"><small>Active products</small><strong>{productMonitor.total || 0}</strong><span>Polaris Zone catalogue</span></div>
      <div className="metric positive"><small>Amazon sources mapped</small><strong>{productMonitor.mapped || 0}</strong><span>Seller SKU contains Amazon URL</span></div>
      <div className={`metric ${productMonitor.unmapped?"warn":""}`}><small>Source missing</small><strong>{productMonitor.unmapped || 0}</strong><span>Add source to TikTok Seller SKU</span></div>
      <div className={`metric ${productMonitor.price_increased?"negative":""}`}><small>Amazon price increased</small><strong>{productMonitor.price_increased || 0}</strong><span>Since previous check</span></div>
      <div className="metric positive"><small>Amazon price decreased</small><strong>{stats.priceDown}</strong><span>Since previous check</span></div>
      <div className={`metric ${productMonitor.source_errors?"negative":""}`}><small>Check problems</small><strong>{productMonitor.source_errors || 0}</strong><span>Blocked / unavailable / errors</span></div>
      <div className="metric"><small>Prices checked</small><strong>{stats.checked}</strong><span>Products with scan history</span></div>
    </section>

    {productMessage && <div className="product-monitor-message">{productMessage}</div>}
    {error && <div className="error"><strong>Error:</strong> {error}</div>}

    <section className="product-monitor-section standalone">
      <div className="section-head"><div><h2>Polaris Zone products</h2><p>{productMonitor.total || 0} active products. Seller SKU is the primary Amazon source.</p></div></div>
      {(productMonitor.items || []).length === 0 ? <div className="empty">No product catalogue imported yet. Click <strong>Sync products</strong>.</div> :
      <div className="product-monitor-list">{(productMonitor.items || []).map(p=>{
        const sourceDelta=p.source_price_change; const spread=p.price_difference;
        return <article className="product-monitor-card" key={p.id}>
          <div className="product-monitor-title"><div><strong>{p.title}</strong><small>TikTok #{p.tiktok_product_id}</small></div><span className={`source-status ${(p.source_check_status||"unmapped").toLowerCase()}`}>{p.source_check_status || "UNMAPPED"}</span></div>
          <div className="product-monitor-grid">
            <div><small>TikTok price</small><strong>{money(p.tiktok_price)}</strong></div>
            <div><small>Amazon current price</small><strong>{money(p.source_price)}</strong></div>
            <div><small>TikTok − Amazon</small><strong className={spread!=null && spread<0?"bad":"good"}>{money(spread)}</strong></div>
            <div><small>Amazon price movement</small><strong className={sourceDelta>0?"bad":sourceDelta<0?"good":""}>{sourceDelta==null?"—":`${sourceDelta>0?"+":""}${money(sourceDelta)}`}</strong><em>{sourceDelta>0?"Price up":sourceDelta<0?"Price down":sourceDelta===0?"No change":"No previous scan"}</em></div>
            <div><small>Last Amazon check</small><strong>{p.source_checked_at?date(p.source_checked_at):"Never"}</strong></div>
          </div>
          <div className="source-mapping"><div className="seller-sku-source"><small>Seller SKU / Amazon source</small>{p.source_url?<a href={p.source_url} target="_blank" rel="noreferrer">{p.seller_sku}</a>:<strong className="bad">Add Amazon URL to Seller SKU in TikTok</strong>}</div><button className="sync-button" onClick={()=>checkProductSource(p)} disabled={productBusy || !p.source_url}>Check now</button></div>
          {p.source_asin && <div className="product-source-meta"><span>ASIN: <strong>{p.source_asin}</strong></span>{p.previous_source_price!=null&&<span>Previous Amazon price: <strong>{money(p.previous_source_price)}</strong></span>}</div>}
          {p.source_check_message && <div className="product-source-warning">{p.source_check_message}</div>}
        </article>
      })}</div>}
    </section>
  </main>;
}
