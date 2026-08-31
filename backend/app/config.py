from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./amazon_orders.db"
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""

    account_slug: str = "tauri-royale"
    account_name: str = "Tauri Royale"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
