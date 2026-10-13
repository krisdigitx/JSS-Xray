import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import Settings, TIKTOK_SHOPS
from app.main import tiktok_oauth_callback
from app.models import TikTokShop


@pytest.fixture
def oauth(monkeypatch):
    engine = create_engine('sqlite://')
    TikTokShop.__table__.create(engine)
    configs = {
        slug: Settings(_env_file=None, tiktok_shop_slug=slug, tiktok_shop_name=name,
                       tiktok_app_key='legacy' if slug == 'polaris-zone' else 'isv',
                       tiktok_app_secret='test-secret', tiktok_oauth_state=slug)
        for slug, name in TIKTOK_SHOPS.items()
    }
    monkeypatch.setattr('app.main.settings_for_shop', configs.__getitem__)
    calls = []
    def exchange(key, secret, code):
        calls.append(key)
        return {'access_token': 'new-access', 'refresh_token': 'new-refresh', 'user_type': 0}
    monkeypatch.setattr('app.main.exchange_auth_code', exchange)
    shops = []
    monkeypatch.setattr('app.main.TikTokClient.authorized_shops', lambda self: shops)
    with Session(engine) as db:
        for slug, name in TIKTOK_SHOPS.items():
            db.add(TikTokShop(slug=slug, name=name, access_token='old-' + slug))
        db.commit()
        yield db, configs, calls, shops
    engine.dispose()


@pytest.mark.parametrize('slug', list(TIKTOK_SHOPS))
def test_callback_updates_only_validated_shop(oauth, slug):
    db, configs, calls, shops = oauth
    shops.append({'id': slug, 'name': TIKTOK_SHOPS[slug], 'cipher': 'cipher'})
    response = tiktok_oauth_callback(code='test-code', state=slug, db=db)
    assert response.status_code == 302
    assert calls == [configs[slug].tiktok_app_key]
    for shop in db.scalars(select(TikTokShop)):
        assert shop.access_token == ('new-access' if shop.slug == slug else 'old-' + shop.slug)


@pytest.mark.parametrize('state', [None, '', 'unknown'])
def test_invalid_state_never_exchanges_code(oauth, state):
    db, configs, calls, shops = oauth
    with pytest.raises(HTTPException) as exc:
        tiktok_oauth_callback(code='code', state=state, db=db)
    assert exc.value.status_code == 400
    assert calls == []


def test_duplicate_state_is_rejected(oauth):
    db, configs, calls, shops = oauth
    configs['jss-traders'].tiktok_oauth_state = 'tauri-royale'
    with pytest.raises(HTTPException):
        tiktok_oauth_callback(code='code', state='tauri-royale', db=db)
    assert calls == []


@pytest.mark.parametrize('existing_id', [None, 'original-shop-id'])
def test_wrong_shop_cannot_replace_tokens(oauth, existing_id):
    db, configs, calls, shops = oauth
    target = db.scalar(select(TikTokShop).where(TikTokShop.slug == 'tauri-royale'))
    target.shop_id = existing_id
    db.commit()
    shops.append({'id': 'wrong-shop', 'name': 'Polaris Zone', 'cipher': 'wrong-cipher'})
    with pytest.raises(HTTPException):
        tiktok_oauth_callback(code='code', state='tauri-royale', db=db)
    assert target.access_token == 'old-tauri-royale'
    assert target.shop_id == existing_id


def test_missing_credentials_never_exchanges_code(oauth):
    db, configs, calls, shops = oauth
    configs['tauri-royale'].tiktok_app_secret = ''
    with pytest.raises(HTTPException) as exc:
        tiktok_oauth_callback(code='code', state='tauri-royale', db=db)
    assert exc.value.status_code == 503
    assert calls == []


def test_stored_shop_id_allows_renamed_shop(oauth):
    db, configs, calls, shops = oauth
    target = db.scalar(select(TikTokShop).where(TikTokShop.slug == 'tauri-royale'))
    target.shop_id = 'stable-id'
    db.commit()
    shops.append({'id': 'stable-id', 'name': 'New seller name', 'cipher': 'cipher'})
    tiktok_oauth_callback(code='code', state='tauri-royale', db=db)
    assert target.access_token == 'new-access'
