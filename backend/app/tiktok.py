import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

AMAZON_ORDER_RE = re.compile(r"(?:Order\s*#?\s*)?(\d{3}-\d{7}-\d{7})", re.I)


def parse_amazon_order_id(text: str | None) -> str | None:
    if not text:
        return None
    match = AMAZON_ORDER_RE.search(text)
    return match.group(1) if match else None


def money(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        value = value.get("value") or value.get("amount")
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError, TypeError):
        return None


def epoch_dt(value: Any) -> datetime | None:
    try:
        if not value:
            return None
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def _canonical_body(body: dict | None) -> str:
    if not body:
        return ""
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False)


def sign_request(path: str, params: dict[str, Any], app_secret: str, body: dict | None = None) -> str:
    """Generate the TikTok Shop Open API HMAC-SHA256 signature."""
    filtered = {
        str(k): str(v)
        for k, v in params.items()
        if k not in {"sign", "access_token"} and v is not None
    }
    canonical = path + "".join(f"{k}{filtered[k]}" for k in sorted(filtered))
    if body:
        canonical += _canonical_body(body)
    payload = f"{app_secret}{canonical}{app_secret}".encode()
    return hmac.new(app_secret.encode(), payload, hashlib.sha256).hexdigest()


class TikTokAPIError(RuntimeError):
    pass


class TikTokClient:
    api_base = "https://open-api.tiktokglobalshop.com"
    auth_base = "https://auth.tiktok-shops.com/api/v2/token"

    def __init__(self, app_key: str, app_secret: str, access_token: str, shop_cipher: str | None = None):
        self.app_key = app_key
        self.app_secret = app_secret
        self.access_token = access_token
        self.shop_cipher = shop_cipher

    def _request(self, method: str, path: str, *, params: dict | None = None, body: dict | None = None) -> dict:
        query = {"app_key": self.app_key, "timestamp": int(time.time())}
        if self.shop_cipher:
            query["shop_cipher"] = self.shop_cipher
        if params:
            query.update({k: v for k, v in params.items() if v is not None})
        query["sign"] = sign_request(path, query, self.app_secret, body if method.upper() != "GET" else None)
        headers = {"x-tts-access-token": self.access_token, "content-type": "application/json"}
        with httpx.Client(timeout=30.0) as client:
            response = client.request(method, f"{self.api_base}{path}", params=query, json=body, headers=headers)
        if response.is_error:
            # Preserve TikTok's JSON error body in logs. This is especially
            # useful for Finance API validation failures (HTTP 400).
            try:
                detail = response.json()
            except Exception:
                detail = response.text[:1000]
            raise TikTokAPIError(
                f"TikTok HTTP {response.status_code} {method.upper()} {path}: {detail}"
            )
        payload = response.json()
        if payload.get("code") not in (0, "0", None):
            raise TikTokAPIError(f"TikTok API {payload.get('code')}: {payload.get('message')}")
        return payload.get("data") or {}

    def authorized_shops(self) -> list[dict]:
        original = self.shop_cipher
        self.shop_cipher = None
        try:
            return self._request("GET", "/authorization/202309/shops").get("shops", [])
        finally:
            self.shop_cipher = original

    def search_orders(self, *, update_time_ge: int, update_time_lt: int, page_size: int = 50) -> list[dict]:
        path = "/order/202309/orders/search"
        orders: list[dict] = []
        token = None
        while True:
            params = {"page_size": min(page_size, 100), "page_token": token}
            body = {
                "update_time_ge": update_time_ge,
                "update_time_lt": update_time_lt,
            }
            data = self._request("POST", path, params=params, body=body)
            orders.extend(data.get("orders") or [])
            token = data.get("next_page_token")
            if not token:
                break
        return orders

    def search_products(self, *, status: str = "ACTIVATE", page_size: int = 100) -> list[dict]:
        """Retrieve the shop product catalogue used by Product Price Monitor.

        TikTok Search Products v202502 requires seller.product.basic and the
        shop cipher. It returns SKU price data needed for comparison.
        """
        path = "/product/202502/products/search"
        products: list[dict] = []
        token = None
        while True:
            params = {"page_size": min(page_size, 100), "page_token": token}
            body = {"status": status, "locale": "en-GB"}
            data = self._request("POST", path, params=params, body=body)
            products.extend(data.get("products") or [])
            token = data.get("next_page_token")
            if not token:
                break
        return products

    def unsettled_transactions(self, *, search_time_ge: int, search_time_lt: int, page_size: int = 50) -> dict[str, dict]:
        path = "/finance/202507/orders/unsettled"
        by_order: dict[str, dict] = {}
        token = None
        while True:
            # TikTok Finance API v202507 requires sort_field. Omitting it
            # returns HTTP 400 even when the request is correctly signed.
            params = {
                "page_size": min(page_size, 100),
                "page_token": token,
                "search_time_ge": search_time_ge,
                "search_time_lt": search_time_lt,
                "sort_field": "order_create_time",
                "sort_order": "ASC",
            }
            data = self._request("GET", path, params=params)
            for tx in data.get("transactions") or data.get("orders") or []:
                order_id = str(tx.get("order_id") or tx.get("id") or "")
                if order_id:
                    by_order[order_id] = tx
            token = data.get("next_page_token")
            if not token:
                break
        return by_order

    def settled_order_transaction(self, order_id: str) -> dict | None:
        path = f"/finance/202501/orders/{order_id}/statement_transactions"
        try:
            data = self._request("GET", path)
        except TikTokAPIError:
            return None
        txs = data.get("statement_transactions") or data.get("transactions") or []
        return txs[0] if txs else (data if data else None)


def refresh_access_token(app_key: str, app_secret: str, refresh_token: str) -> dict:
    params = {
        "app_key": app_key,
        "app_secret": app_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.get(f"{TikTokClient.auth_base}/refresh", params=params)
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") not in (0, "0", None):
        raise TikTokAPIError(f"TikTok token refresh {payload.get('code')}: {payload.get('message')}")
    return payload.get("data") or {}


def exchange_auth_code(app_key: str, app_secret: str, auth_code: str) -> dict:
    params = {
        "app_key": app_key,
        "app_secret": app_secret,
        "auth_code": auth_code,
        "grant_type": "authorized_code",
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.get(f"{TikTokClient.auth_base}/get", params=params)
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") not in (0, "0", None):
        raise TikTokAPIError(f"TikTok token exchange {payload.get('code')}: {payload.get('message')}")
    return payload.get("data") or {}
