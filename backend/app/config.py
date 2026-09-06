from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./amazon_orders.db"
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""

    account_slug: str = "tauri-royale"
    account_name: str = "Tauri Royale"
    gmail_max_new_messages: int = 50
    gmail_backfill_messages: int = 50
    gmail_lookback_hours: int = 24

    tiktok_app_key: str = ""
    tiktok_app_secret: str = ""
    tiktok_access_token: str = ""
    tiktok_refresh_token: str = ""
    tiktok_shop_cipher: str = ""
    tiktok_shop_slug: str = "polaris-zone"
    tiktok_shop_name: str = "Polaris Zone"
    tiktok_lookback_hours: int = 48
    tiktok_oauth_state: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
