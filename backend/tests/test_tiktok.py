from app.tiktok import TikTokClient, money, parse_amazon_order_id, sign_request


def test_parse_amazon_order_id_from_note():
    assert parse_amazon_order_id("Order # 123-1234567-1234567\nTotal: 29.99") == "123-1234567-1234567"


def test_parse_amazon_order_id_missing():
    assert parse_amazon_order_id("customer requested blue") is None


def test_money_accepts_tiktok_money_objects():
    assert str(money({"value": "12.34", "currency": "GBP"})) == "12.34"


def test_signature_is_stable():
    params = {"timestamp": 123, "app_key": "abc", "shop_cipher": "cipher"}
    assert sign_request("/authorization/202309/shops", params, "secret") == sign_request("/authorization/202309/shops", dict(reversed(list(params.items()))), "secret")


def test_unsettled_transactions_includes_required_sort_field(monkeypatch):
    client = TikTokClient("app", "secret", "token", "cipher")
    captured = {}

    def fake_request(method, path, *, params=None, body=None):
        captured.update({"method": method, "path": path, "params": params, "body": body})
        return {"transactions": [], "next_page_token": None}

    monkeypatch.setattr(client, "_request", fake_request)
    client.unsettled_transactions(search_time_ge=100, search_time_lt=200)

    assert captured["path"] == "/finance/202507/orders/unsettled"
    assert captured["params"]["sort_field"] == "order_create_time"
    assert captured["params"]["sort_order"] == "ASC"
    assert captured["params"]["search_time_ge"] == 100
    assert captured["params"]["search_time_lt"] == 200


def test_finance_amount_prefers_nonzero_estimate():
    from app.tiktok_sync import _finance_amount

    estimated, settled, refund = _finance_amount({
        "est_settlement_amount": "0.00",
        "estimated_settlement_amount": "12.38",
        "settlement_amount": "0.00",
    })
    assert str(estimated) == "12.38"
    assert str(settled) == "0.00"
    assert refund is None


def test_finance_amount_does_not_use_settlement_as_estimate():
    from app.tiktok_sync import _finance_amount

    estimated, settled, _ = _finance_amount({"settlement_amount": "12.38"})
    assert estimated is None
    assert str(settled) == "12.38"
