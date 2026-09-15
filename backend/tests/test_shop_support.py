import pytest
from fastapi.testclient import TestClient
from app.config import settings, settings_for_shop
from app.main import app


@pytest.mark.parametrize('slug,prefix', [('tauri-royale', 'TAURI_ROYALE'), ('jss-traders', 'JSS_TRADERS')])
def test_shop_credentials_are_isolated(monkeypatch, slug, prefix):
    monkeypatch.setattr(settings, 'tiktok_shop_slug', 'polaris-zone')
    monkeypatch.setattr(settings, 'tiktok_access_token', 'polaris-token')
    monkeypatch.setenv('TIKTOK_ACCESS_TOKEN', 'global-token')
    monkeypatch.setenv(f'{prefix}_TIKTOK_APP_KEY', 'shop-key')
    config = settings_for_shop(slug)
    assert config.tiktok_shop_slug == slug
    assert config.tiktok_app_key == 'shop-key'
    assert config.tiktok_access_token == ''
    monkeypatch.setenv(f'{prefix}_TIKTOK_ACCESS_TOKEN', 'shop-token')
    assert settings_for_shop(slug).tiktok_access_token == 'shop-token'


@pytest.mark.parametrize('slug', ['polaris-zone', 'tauri-royale', 'jss-traders'])
def test_manual_sync_uses_requested_shop(monkeypatch, slug):
    calls = []
    def fake_sync(shop):
        calls.append(shop)
        return {'shop': shop}
    monkeypatch.setattr('app.main.sync_tiktok_orders', fake_sync)
    with TestClient(app) as client:
        response = client.post('/api/tiktok/sync', params={'shop': slug})
    assert response.status_code == 200
    assert calls == [slug]
