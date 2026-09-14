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
