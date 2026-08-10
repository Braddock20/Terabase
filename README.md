# FSE — TeraBox-first Storage Engine

A single production-oriented storage service designed for deployment on Render and backed primarily by the **official TeraBox Open Platform**. It exposes one private storage namespace while keeping application metadata, encryption, chunking, integrity and recovery logic independent from the provider.

## What is included

- FastAPI service and polished web dashboard
- TeraBox OAuth device-code authorization
- Automatic access-token refresh using TeraBox's documented refresh flow
- Dynamic API/upload-domain discovery through TeraBox tokeninfo
- TeraBox quota and account health reporting
- Encrypted provider credentials in the local catalog
- AES-256-GCM per logical chunk with unique nonces and associated data
- SHA-256 ciphertext integrity verification
- 8 MiB logical chunking (configurable)
- Each logical chunk stored as an opaque TeraBox object
- Upload precreate → shard upload → create flow using the official API
- Byte-for-byte reconstruction and verification on download
- Delete, list, search-ready local catalog and remote listing
- Encrypted catalog backup stored in TeraBox so an ephemeral Render filesystem can recover metadata
- Background catalog backup
- Application password + signed session cookie
- CORS, size limits, filename sanitization and no plaintext provider objects
- Render deployment manifest
- Tests

## Important TeraBox integration note

This implementation deliberately uses TeraBox's documented Open Platform interface. It does not scrape private endpoints, bypass authentication, defeat quotas, or use undocumented anti-abuse workarounds.

TeraBox currently documents OAuth, token-info/domain discovery, quota/user information, precreate, sharded upload, create, list, metadata/download links and file management. The service follows those documented flows.

## Generate secrets

Generate a master key with:

```bash
python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

Use the output for `FSE_MASTER_KEY`. Also create a long random `SESSION_SECRET` and a strong `APP_PASSWORD`.

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

## TeraBox setup

Create an application in the TeraBox Open Platform and obtain the required `client_id`, `client_secret` and `private_secret`. Put them in the Render environment. The dashboard can then start the official device-code authorization flow.

The TeraBox documentation states that access tokens expire after two days and refresh tokens after thirty days; refresh tokens are one-time-use and replaced on successful refresh. The engine persists the latest token pair in its encrypted catalog and refreshes before expiry.

## Render

Deploy this repository as a Python web service. Required secrets:

- `APP_PASSWORD`
- `SESSION_SECRET`
- `FSE_MASTER_KEY`
- `TERABOX_CLIENT_ID`
- `TERABOX_CLIENT_SECRET`
- `TERABOX_PRIVATE_SECRET`

Optional:

- `TERABOX_ACCESS_TOKEN`
- `TERABOX_REFRESH_TOKEN`
- `TERABOX_APP_FOLDER`
- `CHUNK_SIZE`
- `MAX_UPLOAD_BYTES`

The application periodically backs up its catalog to an encrypted TeraBox object. This is important because a normal Render filesystem is not a durable database. For a long-lived deployment, use a persistent Render disk or an external database for the catalog as an additional durability layer.

## Data model

The local catalog is authoritative for the logical namespace. Every file has a manifest-like record and ordered chunks. Each chunk contains only metadata plus a provider object path. Provider objects are encrypted ciphertext.

## Storage layout in TeraBox

```text
/From: Other Applications/<application-folder>-/
    <file-id>/
        00000000.bin
        00000001.bin
        ...
    _system/
        catalog.json.enc
```

Do not manually edit or delete these engine objects unless you intend to lose the corresponding logical file.
