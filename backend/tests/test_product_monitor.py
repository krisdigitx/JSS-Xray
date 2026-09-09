from decimal import Decimal

from app.product_monitor import _price_from_skus, extract_asin, is_amazon_source_url
from app.tiktok import TikTokClient


def test_extract_amazon_asin():
    assert extract_asin("https://www.amazon.co.uk/dp/B0ABC12345?th=1") == "B0ABC12345"
    assert extract_asin("https://www.amazon.co.uk/gp/product/B012345678/") == "B012345678"


def test_seller_sku_supports_amazon_uk_and_amzn_eu():
    assert is_amazon_source_url("https://amzn.eu/d/0cllMYzD") is True
    assert is_amazon_source_url("https://www.amazon.co.uk/dp/B012345678") is True
    assert is_amazon_source_url("https://example.com/item") is False
    assert is_amazon_source_url("") is False


def test_tiktok_price_uses_lowest_live_sku_price_and_first_seller_sku():
    product = {"skus": [
        {"seller_sku": "https://amzn.eu/d/0cllMYzD", "price": {"sale_price": "14.98", "currency": "GBP"}},
        {"seller_sku": "https://amzn.eu/d/another", "price": {"sale_price": "12.99", "currency": "GBP"}},
    ]}
    price, sku, count = _price_from_skus(product)
    assert price == Decimal("12.99")
    assert sku == "https://amzn.eu/d/0cllMYzD"
    assert count == 2


def test_search_products_calls_tiktok_product_api(monkeypatch):
    client = TikTokClient("key", "secret", "token", "cipher")
    calls = []
    def fake_request(method, path, *, params=None, body=None):
        calls.append((method, path, params, body))
        return {"products": [{"id":"1","title":"Example","status":"ACTIVATE","skus":[]}], "next_page_token": None}
    monkeypatch.setattr(client, "_request", fake_request)
    rows = client.search_products()
    assert len(rows) == 1
    assert calls[0][0:2] == ("POST", "/product/202502/products/search")
    assert calls[0][3]["status"] == "ACTIVATE"
