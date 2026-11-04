from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    model_base_url: str = "https://api.deepseek.com"
    model_name: str = "deepseek-chat"
    model_api_key: str = ""
    fixed_login_code: str = "123456"
    database_url: str = "sqlite:///./data/petpilot.db"
    model_timeout: float = 60.0


settings = Settings()
