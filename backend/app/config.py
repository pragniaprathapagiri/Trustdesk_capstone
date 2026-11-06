from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./trustdesk.db"
    demo_token: str = "trustdesk-demo"
    llm_provider: str = "mock"
    gemini_api_key: str = ""
    data_dir: Path = Path(__file__).resolve().parents[2] / "data"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
