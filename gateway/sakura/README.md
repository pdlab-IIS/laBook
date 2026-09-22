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
