# FSE — TeraBox-first Multi-Account Storage Engine

A Render-friendly storage manager built around the FSE architecture: logical files are encrypted, chunked, integrity-checked, and mapped to one or more independent TeraBox accounts. The core treats each TeraBox account as a provider instance, so accounts can be enabled, disabled, inspected, and removed without changing storage logic.

## Deploy on Render Free

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Environment variables for official TeraBox Open Platform authorization:

```text
TERABOX_CLIENT_ID=
TERABOX_CLIENT_SECRET=
TERABOX_PRIVATE_SECRET=
```

Optional direct token bootstrap:

```text
TERABOX_ACCESS_TOKEN=
TERABOX_REFRESH_TOKEN=
```

No Render Shell is required.

## Multi-account model

The dashboard has **TeraBox Accounts**. Each account has its own provider instance and isolated FSE namespace folder. Uploads can be automatically placed or pinned to an account. Download/delete operations use the account recorded in each chunk's manifest.

The engine does not bypass TeraBox authentication, quotas, anti-abuse controls, or undocumented private APIs. It expects legitimate authorization tokens or TeraBox's documented OAuth/device flow.

## Persistence

Set `FSE_DB=/data/fse.db` and attach a Render persistent disk if you need the local catalog to survive restarts. The encrypted catalog is also backed up to every enabled TeraBox account.
