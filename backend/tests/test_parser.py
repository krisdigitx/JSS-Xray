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


def test_order_total_colon_format():
    body = """
    Order # 026-8642981-5011532
    Item Subtotal: £19.99
    Order Total: £19.99
    """
    p = parse_amazon_email("Ordered: ‘FineLuck 1080P WiFi Video Camera’", body)
    assert p is not None
    assert str(p.total) == "19.99"
    assert str(p.item_price) == "19.99"


def test_html_order_total_format():
    body = """
    <div>Order ID: 205-4101719-1813918</div>
    <div>Item Subtotal:&nbsp;£8.50</div>
    <div>Grand Total: £8.50</div>
    """
    p = parse_amazon_email("Ordered: Catsan Hygiene Plus Cat Litter", body)
    assert p is not None
    assert str(p.total) == "8.50"
    assert str(p.item_price) == "8.50"


def test_delivery_dates_are_returned():
    body = """
    Order # 203-1677420-3774750
    Estimated delivery: 3 September 2026
    """
    p = parse_amazon_email("Ordered: Example", body)
    assert p.estimated_delivery_text == "3 September 2026"


def test_amazon_superscript_price():
    body = """
    <div>Order # 202-0190583-1372366</div>
    <div>Kement Wireless Security Camera</div>
    <div>Quantity: 1</div>
    <div>£8<sup>49</sup></div>
    <div>Total</div><div>£8<sup>49</sup></div>
    """
    p = parse_amazon_email("Ordered: Kement Wireless Security Camera", body)
    assert p is not None
    assert str(p.total) == "8.49"
    assert str(p.item_price) == "8.49"


def test_amazon_split_plain_text_price():
    body = """
    Order # 206-2250955-3549969
    Quantity: 1
    £5
    39
    Total
    £5
    39
    """
    p = parse_amazon_email("Dispatched: Happy Birthday Banner", body)
    assert p is not None
    assert str(p.total) == "5.39"
    assert str(p.item_price) == "5.39"


def test_amazon_superscript_does_not_become_849():
    body = """
    Order # 202-1806212-6922711
    Quantity: 1
    £8<sup class="price-fraction">49</sup>
    Total £8<sup class="price-fraction">49</sup>
    """
    p = parse_amazon_email("Ordered: Kement Wireless Security Camera", body)
    assert p is not None
    assert str(p.total) == "8.49"
    assert str(p.item_price) == "8.49"
