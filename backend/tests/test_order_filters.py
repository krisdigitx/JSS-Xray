import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import AmazonAccount, Order, TikTokOrder, TikTokShop


@pytest.fixture
def client():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        shop = TikTokShop(slug='polaris-zone', name='Polaris Zone')
        other = TikTokShop(slug='other', name='Other')
        amazon = Order(account=AmazonAccount(slug='polaris-zone', name='Polaris Zone'), amazon_order_id='123-1234567-1234567')
        for status in ['AWAITING_SHIPMENT', 'AWAITING_COLLECTION', 'TO_SHIP', 'READY_TO_SHIP', 'DELIVERED', 'COMPLETED', 'CANCELLED', 'CANCELED']:
            db.add(TikTokOrder(shop=shop, tiktok_order_id=status, status=status, product_name='Snack', amazon_order=amazon if status == 'DELIVERED' else None))
        db.add(TikTokOrder(shop=other, tiktok_order_id='other', status='COMPLETED', product_name='Snack'))
        db.commit()
        def override_db():
            yield db
        app.dependency_overrides[get_db] = override_db
        try:
            with TestClient(app) as test_client:
                yield test_client
        finally:
            app.dependency_overrides.pop(get_db, None)
    engine.dispose()


@pytest.mark.parametrize('status,expected', [
    ('all', 8), ('awaiting_shipment', 4), ('delivered', 1), ('completed', 1), ('cancelled', 2),
])
def test_status_filter_and_pagination(client, status, expected):
    response = client.get('/api/tiktok/orders', params={'shop': 'polaris-zone', 'status': status, 'page_size': 1})
    assert response.status_code == 200
    data = response.json()
    assert data['pagination']['total'] == expected
    assert data['pagination']['total_pages'] == expected
    assert len(data['items']) == 1
    if status in ('delivered', 'completed'):
        assert data['items'][0]['status'] == status.upper()


def test_attention_combines_with_status_and_search(client):
    params = {'shop': 'polaris-zone', 'status': 'delivered', 'attention_only': True}
    assert client.get('/api/tiktok/orders', params=params).json()['pagination']['total'] == 0
    params.update(status='completed', q='Snack')
    assert client.get('/api/tiktok/orders', params=params).json()['pagination']['total'] == 1
    params['q'] = 'missing'
    assert client.get('/api/tiktok/orders', params=params).json()['pagination']['total'] == 0


def test_invalid_status_is_rejected(client):
    assert client.get('/api/tiktok/orders?status=invalid').status_code == 422


@pytest.mark.parametrize('day,start,end', [
    ('2026-09-10', '2026-09-09T23:00:00+00:00', '2026-09-10T23:00:00+00:00'),
    ('2026-03-29', '2026-03-29T00:00:00+00:00', '2026-03-29T23:00:00+00:00'),
    ('2026-10-25', '2026-10-24T23:00:00+00:00', '2026-10-26T00:00:00+00:00'),
])
def test_inclusive_uk_date_range_and_combined_filters(client, day, start, end):
    from datetime import datetime, timedelta
    db = next(app.dependency_overrides[get_db]())
    shop = TikTokShop(slug='dates', name='Dates')
    start, end = datetime.fromisoformat(start), datetime.fromisoformat(end)
    for index, instant in enumerate([start - timedelta(microseconds=1), start, end - timedelta(microseconds=1), end, None]):
        db.add(TikTokOrder(shop=shop, tiktok_order_id=str(index), status='COMPLETED', product_name='Date snack', create_time=instant))
    db.commit()
    params = dict(shop='dates', date_from=day, date_to=day, status='completed', attention_only=True, q='Date snack', page_size=1)
    response = client.get('/api/tiktok/orders', params=params)
    assert response.status_code == 200
    data = response.json()
    assert data['pagination']['total'] == 2
    assert data['pagination']['total_pages'] == 2
    assert data['items'][0]['tiktok_order_id'] == '2'
    assert client.get('/api/tiktok/orders', params={**params, 'page': 2}).json()['items'][0]['tiktok_order_id'] == '1'
    del params['date_to']
    assert client.get('/api/tiktok/orders', params=params).json()['pagination']['total'] == 3
    params.pop('date_from')
    params['date_to'] = day
    assert client.get('/api/tiktok/orders', params=params).json()['pagination']['total'] == 3
    params.pop('date_to')
    assert client.get('/api/tiktok/orders', params=params).json()['pagination']['total'] == 5


@pytest.mark.parametrize('query', [
    'date_from=2026-09-11&date_to=2026-09-10',
    'date_from=not-a-date', 'date_to=2026-02-30', 'date_to=9999-12-31',
])
def test_invalid_dates(client, query):
    assert client.get('/api/tiktok/orders?' + query).status_code == 422
