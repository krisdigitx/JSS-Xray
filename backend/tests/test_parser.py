from app.parser import parse_amazon_email

def test_order_confirmation():
    body = """
    Thanks for your order!
    Order # 203-1677420-3774750
    [Ofuca USB C Charger Cable,3Pack 1M USB to USB C Cable](https://www.amazon.co.uk/dp/B0BX6BPPNP)
    Sold by Tobanda store
    Condition: New
    Quantity: 1
    £699
    Total £6.99
    """
    p = parse_amazon_email("Ordered: ‘Ofuca USB C Charger...’", body)
    assert p is not None
    assert p.order_id == "203-1677420-3774750"
    assert p.asin == "B0BX6BPPNP"
    assert p.product_name.startswith("Ofuca")
    assert p.seller == "Tobanda store"
    assert str(p.total) == "6.99"
    assert str(p.item_price) == "6.99"
    assert p.event_type == "ordered"

def test_delivery_event():
    body = "Order # 203-1677420-3774750"
    p = parse_amazon_email("Delivered: ‘Example...’", body)
    assert p.event_type == "delivered"


def test_product_falls_back_to_subject():
    body = """
    Order # 203-1677420-3774750
    Total £6.99
    """
    parsed = parse_amazon_email("Ordered: ‘Ofuca USB C Charger Cable’", body)
    assert parsed is not None
    assert parsed.product_name == "Ofuca USB C Charger Cable"
    assert parsed.event_type == "ordered"
