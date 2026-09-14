from decimal import Decimal
import re

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.main import _profit, _purchase_cost, _purchase_cost_expression
from app.models import AmazonAccount, Order, TikTokOrder, TikTokShop


@pytest.mark.parametrize('gmail_cost,note,expected', [
    (Decimal('0'), 'Order # 202-1928005-1517162\nPrice: £54.00', Decimal('54')),
    (None, 'Price: £54.00', Decimal('54')),
    (Decimal('50'), 'Price: £54.00', Decimal('50')),
    (None, 'No price available', None),
    (Decimal('0'), 'Total: £54.00', None),
    (None, 'Price: £0.00', Decimal('0')),
])
def test_purchase_cost_and_sql_agree(gmail_cost, note, expected):
    engine = create_engine('sqlite://')
    # Emulate PostgreSQL substring's capture semantics for this expression test.
    def substring(value, pattern):
        match = re.search(pattern, value or '')
        return match.group(1) if match else None
    with engine.connect() as conn:
        conn.connection.driver_connection.create_function('substring', 2, substring)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        account = AmazonAccount(slug='polaris-zone', name='Polaris Zone')
        shop = TikTokShop(slug='polaris-zone', name='Polaris Zone')
        amazon = Order(account=account, amazon_order_id='202-1928005-1517162', order_total=gmail_cost)
        row = TikTokOrder(shop=shop, amazon_order=amazon, tiktok_order_id='576949522224879753',
                         status='AWAITING_SHIPMENT', quantity=3, seller_note=note,
                         estimated_earnings=Decimal('58.78'))
        db.add(row)
        db.flush()
        assert _purchase_cost(row) == expected
        sql_cost = db.scalar(select(_purchase_cost_expression()).select_from(TikTokOrder).outerjoin(Order))
        assert sql_cost == expected
        assert _profit(row) == (float(Decimal('58.78') - expected) if expected is not None else None)


def test_unmatched_order_uses_note():
    row = TikTokOrder(status='AWAITING_SHIPMENT', seller_note='Price: £54.00',
                     estimated_earnings=Decimal('58.78'), quantity=3)
    assert _purchase_cost(row) == Decimal('54')
    assert _profit(row) == 4.78
    assert row.amazon_order is None
