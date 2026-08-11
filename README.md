# TeraBox Playwright — Render Free V1

This version is designed specifically for **Render Free**, where you do not have shell access.

## What changed

The previous version required `npm run login` locally and then copying browser state. That is inconvenient on Render Free.

This version performs the bootstrap automatically:

```text
Render starts
   ↓
Playwright starts Chromium
   ↓
opens TeraBox
   ↓
uses TERABOX_EMAIL + TERABOX_PASSWORD
   ↓
normal TeraBox login
   ↓
session is retained in the running browser profile
   ↓
startup smoke test
   ↓
creates a tiny test file
   ↓
uploads it to TeraBox
   ↓
/health reports smoke result
```

No Render shell is required.

## Render environment variables

Set:

```text
API_KEY=<long random secret>
TERABOX_EMAIL=<your TeraBox email>
TERABOX_PASSWORD=<your TeraBox password>
```

Keep:

```text
AUTO_LOGIN=1
STARTUP_SMOKE=1
HEADLESS=1
```

Do not commit credentials.

## Endpoints

### Public

```http
GET /
GET /health
```

### Protected

```http
GET /smoke
GET /session
POST /upload
```

Authentication:

```text
x-api-key: YOUR_API_KEY
```

or:

```text
Authorization: Bearer YOUR_API_KEY
```

Upload:

```bash
curl -X POST   -H "x-api-key: YOUR_API_KEY"   -F "file=@photo.jpg"   -F "folder=/"   https://YOUR-SERVICE.onrender.com/upload
```

## Startup smoke test

The application automatically creates:

```text
.terabox-smoke-<timestamp>.txt
```

and uploads it when authentication succeeds.

The file is deleted locally afterward.

Check:

```text
GET /health
```

A successful deployment should show:

```json
{
  "ok": true,
  "smoke": {
    "ok": true,
    "publicPage": true,
    "authenticated": true,
    "upload": {
      "uploaded": true
    }
  }
}
```

## Important limitation

TeraBox currently offers several login methods and can require security verification. Its official login pages show email/password as well as other methods, and TeraBox documents login protection for new internet environments. If the account requires CAPTCHA, MFA, QR login, or another interactive verification, automatic headless login can stop at that step.

This project does **not** bypass those protections.

If your account requires interactive verification, the startup smoke test will report the failure in `/health` and Render logs.

## Why no Render disk?

Render Free does not provide the persistent-disk workflow needed for reliable browser-profile persistence. Therefore this V1 treats the browser session as disposable. On a restart/redeploy, it simply performs the login again using the environment credentials.

That makes this version suitable for the exact first experiment: **can Playwright log into your TeraBox account from Render Free and upload a file?**

## Testing

Local:

```bash
npm install
npm test
npm run lint
```

The repository also uses the Playwright Docker image so the Chromium runtime is already included.

A real TeraBox smoke test is executed by the deployed service itself because it requires your credentials and the live TeraBox environment.

## Security

- Use a strong API key.
- Store TeraBox credentials only in Render environment variables.
- Never put them in GitHub.
- Never expose `/session` or `/smoke` without API authentication.
- Do not share the Render service URL if you have disabled API authentication.
- This automation is intended for your own TeraBox account.

## Next step after V1

Once the smoke test succeeds, we should stop relying on browser clicks for every operation.

TeraBox has an official Open Platform with authorization and upload APIs. Their documentation describes access tokens, pre-create upload, chunk upload, and file operations. That is a much better foundation for a serious storage engine if we can obtain an application/client ID and secret. See the official documentation linked below.

https://www.terabox.com/integrations/docs?lang=en

