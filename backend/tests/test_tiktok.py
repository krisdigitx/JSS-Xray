from app.tiktok import money, parse_amazon_order_id, sign_request


def test_parse_amazon_order_id_from_note():
    assert parse_amazon_order_id("Order # 123-1234567-1234567\nTotal: 29.99") == "123-1234567-1234567"


def test_parse_amazon_order_id_missing():
    assert parse_amazon_order_id("customer requested blue") is None


def test_money_accepts_tiktok_money_objects():
    assert str(money({"value": "12.34", "currency": "GBP"})) == "12.34"


def test_signature_is_stable():
    params = {"timestamp": 123, "app_key": "abc", "shop_cipher": "cipher"}
    assert sign_request("/authorization/202309/shops", params, "secret") == sign_request("/authorization/202309/shops", dict(reversed(list(params.items()))), "secret")
