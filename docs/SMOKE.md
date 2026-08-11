# Smoke-test contract

The deployment itself is the test runner.

1. Start Chromium.
2. Open TeraBox.
3. Detect existing authenticated session.
4. Otherwise submit email/password.
5. Wait for the authenticated page.
6. Create a tiny text file.
7. Upload it.
8. Return the result through `/health`.
9. Delete the local temporary file.

Possible outcomes:

- `ok:true` — login and upload succeeded.
- `AUTH_REQUIRED` — credentials/session did not authenticate.
- `LOGIN_INCOMPLETE` — TeraBox stopped at a security verification or changed the login flow.
- `TeraBox upload control not found` — UI changed.

Never interpret a browser UI success as proof of a durable storage API. This is a first integration smoke test.

