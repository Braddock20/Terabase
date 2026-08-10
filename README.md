# TeraBox Storage Engine — simple Render deployment

This is the simplified TeraBox-first build. There is **no PostgreSQL**, no `psycopg`, no separate FSE master-key variable, no application-password variable, and no database URL variable.

## 1. Render environment variables

Only these TeraBox values are required:

```text
TERABOX_CLIENT_ID=...
TERABOX_CLIENT_SECRET=...
TERABOX_PRIVATE_SECRET=...
```

If you already have OAuth tokens, you may additionally set:

```text
TERABOX_ACCESS_TOKEN=...
TERABOX_REFRESH_TOKEN=...
```

Otherwise open the dashboard and use **TeraBox → Authorize with QR**.

## 2. Render

Build command:

```text
pip install -r requirements.txt
```

Start command:

```text
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

The included `render.yaml` already contains this configuration.

## 3. First login

After deployment, open Render Shell and run:

```bash
python -m app.admin
```

Copy the printed admin key into the dashboard. This key is deterministically derived from the TeraBox application secret; no extra environment variable is required.

## 4. Persistent storage

For a serious production deployment, attach a Render persistent disk mounted at `/data`. This keeps the SQLite catalog and rotated OAuth refresh token across redeploys. Without a persistent disk, the service can lose its local token/catalog state when Render replaces the instance.

## 5. What it does

- TeraBox-first storage
- AES-256-GCM encryption before provider upload
- 8 MiB chunks
- SHA-256 integrity verification
- TeraBox precreate/upload/create flow
- byte-for-byte reconstruction
- file list/download/delete/verify
- encrypted catalog backup in TeraBox
- automatic token refresh
- quota/status dashboard
- no PostgreSQL dependency
- bounded chunk memory instead of buffering an entire upload

The engine intentionally uses only legitimate TeraBox application/OAuth interfaces. It does not bypass authentication, quotas, rate limits, anti-abuse systems, or undocumented private endpoints.


## Render Free — no Shell and no generated admin key

You do not need Render Shell or a generated admin key. On the login screen, use your `TERABOX_PRIVATE_SECRET` as the storage admin password. The server also accepts the derived key internally for compatibility. Do not expose your TeraBox credentials in screenshots or logs.
