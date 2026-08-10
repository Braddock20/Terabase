from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    app_name: str = "FSE TeraBox Storage"
    app_password: str = ""
    session_secret: str = ""
    fse_master_key: str = ""
    database_url: str = "sqlite:///./data/fse.db"
    terabox_client_id: str = ""
    terabox_client_secret: str = ""
    terabox_private_secret: str = ""
    terabox_access_token: str = ""
    terabox_refresh_token: str = ""
    terabox_app_folder: str = "FSE-Storage"
    chunk_size: int = 8 * 1024 * 1024
    backup_interval_seconds: int = 600
    max_upload_bytes: int = 40 * 1024 * 1024 * 1024
    request_timeout: float = 120.0
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

settings = Settings()
Path("data").mkdir(exist_ok=True)
