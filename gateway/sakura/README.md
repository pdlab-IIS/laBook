# Sakura Slack OAuth gateway

The active gateway automatically starts Slack sign-in and uses a fixed 30-day
server-side session. Command entry is not part of the user flow. See the
[current migration plan](../../docs/sakura-auth-proxy-plan.md).

`config.example.json` is a template only. Real settings stay in ignored
`deploy/local/` and an owner-readable private directory outside www. Only thin
index.php/callback.php wrappers go in the document root. App code, vendor,
configuration and SQLite state stay private.

The verified Slack OIDC implementation is reused from `gateway/slack-demo/src`.
Use the existing client credentials and registered callback. Signing Secret, bot
tokens and Slash Commands are not needed. The configured team is mandatory.

`state/auth.sqlite` stores authentication users and hashed opaque session IDs.
User identity is unique by `(slack_team_id, slack_user_id)`. It is independent of
the RPi library Users table. Sessions expire 30 days after issuance, without
sliding renewal or membership rechecks. A new login rotates the session and CSRF;
logout revokes the stored session as well as clearing the Cookie. Each request
checks the current team, generation and revoked subjects. Change
`session_generation` to invalidate all sessions, or set `revoked_subjects` to
reject particular subjects.

The PHP pre-login session uses `LABOOK_GATE_PREAUTH` (one hour), OAuth state uses
`LABOOK_GATE_TX` (five minutes), and the authenticated Cookie is
`LABOOK_GATE_SESSION` (30 days). A trial site's own expiry still takes precedence.
No access/ID tokens, raw session IDs or authorization codes are stored in this DB.

Tests:

- `scripts/check_sakura_gateway.py`: isolated PHP policy, boundary, preauth and DB session tests.
- `scripts/deploy_gateway_trial.py`: first deployment and unauthenticated HTTP/OAuth transaction tests. Use without `--deploy` to recheck an existing trial.
- `node tests/test_runtime.cjs`: application request/CSRF integration.

Production cutover is complete and user-verified. Logout is inside the root
page hamburger menu; other pages hide that menu. The logged-out page does not
automatically restart sign-in. Old deployed demos and trials have been removed.
Reusable source and tests remain. See the operations document for rollback and
known hosting limits; never reuse deleted trial deployment settings.

Every asset request still passes the session and access checks. Successful GET
responses for fixed static-file and cover paths can then be served from the
private `state/asset-cache` directory, reducing new upstream connections. API
responses, HTML, mutations, query-bearing URLs and errors are not cached.
Static files expire after 60 seconds and covers after 300 seconds; each object
is limited to 2 MiB and the cache to 64 MiB. After replacing a static file,
allow 60 seconds for existing entries to expire or remove its private cache
entry. Browser responses remain no-store. Cover images load lazily.

`state/gateway-errors.log` records bounded, private failure diagnostics (about
1 MiB): status, safe reason, cURL error number, elapsed time and byte counts.
It excludes URLs, credentials, cookies and user identities. A 502 with cURL 35
and upstream status 0 indicates a TLS connection failure before an HTTP
response; this alone does not establish an ngrok quota violation. Transport
errors no longer instruct users to authenticate again. Never commit these logs
or deployed network configuration.

When `LABOOK_LOCAL_URL` is configured privately, the remote book-list page
probes that local origin's `healthz` endpoint in the background. A
successful network response marks local access as confirmed. The Access mode
button is available whenever a valid local destination is configured, even when
the probe fails. Clicking it asks for confirmation before navigating with the
gateway prefix removed and the query/fragment retained. Opening the menu
retries an unconfirmed connection. The probe sends no credentials
or referrer and allows no redirects; its opaque response confirms reachability,
not application readiness. Failure or a ten-second timeout leaves access unconfirmed.
Local-network permission and mixed-content restrictions depend on the browser;
this feature does not bypass them. Keep the actual local URL outside Git.

Remote lists offer 10 or 25 items per page; local lists also offer 50 and 100.
Remote pagination and page-size changes are disabled while loading and until
three seconds after the list request starts, with spinners replacing the arrows.
The UI and document titles identify this release as `[beta-mode]`.
