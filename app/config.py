from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "qr-studio"
    environment: str = "production"
    host: str = "0.0.0.0"
    port: int = 8000
    public_base_url: str = "http://localhost:8000"

    business_name: str = "QR Studio"
    admin_access_code: str = "admin-qr-2026"
    database_url: str = "sqlite:///./qr_studio.db"
    storage_dir: str = "./uploads"
    max_upload_size_mb: int = 15

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def sqlite_path(self) -> Path:
        prefix = "sqlite:///"
        if self.database_url.startswith(prefix):
            return Path(self.database_url[len(prefix):]).resolve()
        return Path("qr_studio.db").resolve()

    @property
    def storage_path(self) -> Path:
        return Path(self.storage_dir).resolve()


settings = Settings()
