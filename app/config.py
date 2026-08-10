import os
from pathlib import Path

class Settings:
    app_name = "TeraBox Storage Engine"
    terabox_client_id = os.getenv("TERABOX_CLIENT_ID", "").strip()
    terabox_client_secret = os.getenv("TERABOX_CLIENT_SECRET", "").strip()
    terabox_private_secret = os.getenv("TERABOX_PRIVATE_SECRET", "").strip()
    terabox_access_token = os.getenv("TERABOX_ACCESS_TOKEN", "").strip()
    terabox_refresh_token = os.getenv("TERABOX_REFRESH_TOKEN", "").strip()
    terabox_app_folder = "FSE-Storage"
    chunk_size = 8 * 1024 * 1024
    max_upload_bytes = 40 * 1024 * 1024 * 1024
    request_timeout = 180.0
    backup_interval_seconds = 600
    database_path = os.getenv("FSE_DB", "/data/fse.db" if os.path.isdir("/data") else "data/fse.db")

settings = Settings()
Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)

def require_credentials():
    missing=[]
    for k,v in [("TERABOX_CLIENT_ID",settings.terabox_client_id),("TERABOX_CLIENT_SECRET",settings.terabox_client_secret),("TERABOX_PRIVATE_SECRET",settings.terabox_private_secret)]:
        if not v: missing.append(k)
    if missing: raise RuntimeError("Missing TeraBox credentials: " + ", ".join(missing))
