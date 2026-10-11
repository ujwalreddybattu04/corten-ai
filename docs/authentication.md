# Authentication review

Email signup and login use PostgreSQL accounts, bcrypt-SHA256 password hashing,
and Redis-backed sessions. Existing bcrypt hashes remain readable. New passwords
are limited to 8–1024 characters and are never silently truncated to bcrypt's
72-byte limit. Login errors do not distinguish unknown or disabled accounts.

## Browser sessions

The Next.js API proxy keeps both JWTs in HttpOnly, SameSite=Lax cookies, with
Secure on HTTPS. Browser API calls use the frontend origin. JWTs are removed from
login/register/refresh JSON responses and are never saved in localStorage.
Cookie-authenticated writes require the frontend Origin. The proxy never forwards
browser cookies to the backend.
On Render, the public origin comes from `RENDER_EXTERNAL_URL`, rather than the
internal HTTP request URL. Set `APP_ORIGIN` to the full HTTPS origin when using a
custom domain or another reverse proxy. This setting controls CSRF validation and
the Secure cookie flag; never derive trust from arbitrary forwarded-host headers.

Session restoration calls the proxy's `/api/v1/auth/session`, which verifies
existing cookies through `/api/v1/auth/me` and returns null immediately for guests;
a cached profile cannot authenticate a user. A 401 triggers one refresh and one
retry. Concurrent requests share a
refresh promise, and browsers supporting Web Locks coordinate rotation across
tabs. Logout and account changes synchronize across tabs.
An interrupted logout hides private views, persists a pending-logout marker, and
retries on reconnect or explicitly; it cannot silently restore the old session.
If the proxy cannot confirm backend revocation, it clears the access cookie and
retains only the HttpOnly refresh credential needed for a real revocation retry.
Remember me creates persistent cookies; otherwise cookies last for the browser
session. Sessions have
an absolute seven-day maximum; refreshing cannot extend that maximum.

Access and refresh JWTs have distinct types, issuer, audience, expiry, issue time,
validated UUID subjects, and a session ID. Refresh has a one-use JTI. Redis Lua
atomically rotates the JTI, verifies its owner, and preserves session expiry.
Reusing an old refresh token revokes that session's active token family, following
[RFC 9700 replay detection](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14.2).
Clients must serialize refresh across tabs; concurrent direct API refreshes cause
the session to require a new login.
Logout deletes the entire session, so existing access tokens stop working too.
Every protected request checks both the session and the active database account.
Security-store outages fail with 503, rather than granting access. Auth attempts
have atomic Redis limits and 429 responses with Retry-After.

## Authorization and browser data

Private threads are available only to their owner. Public threads remain readable
without signing in. Invalid credentials are rejected instead of being treated as
anonymous. Malformed thread IDs return 422. Profile endpoints require authentication
and return actual account data; updating a profile can change only its display name.
Spaces and collections API placeholders now require authentication and return 501
until server storage is implemented.

The app remains available in guest mode. Browser histories, pins, analyst projects,
Spaces, and Discover personalization use separate namespaces for each verified
account. An account change remounts the app to discard stale component state and
abort pending conversation work. Delayed title responses cannot write across an
account change. Guest data stays separate.

This is browser storage, not centralized team storage or encryption. Anyone with
access to the browser profile or its developer tools can inspect local records.
Do not use this preview for confidential company data until server persistence,
tenant membership, retention, and access policies are implemented.

## Remaining deployment prerequisites

- Configure transactional email before adding email verification and password
  recovery. Unavailable social-login buttons and broken recovery/policy links
  have been removed; these capabilities are not presented as working.
- Decide company membership/invitation rules; signup currently remains public.
  SSO and MFA are not implemented.
- Provide approved Terms and Privacy policy content before general release.
- Use durable production PostgreSQL/Redis plans, backups, monitoring, and an
  appropriate production authentication traffic policy. Redis session checks must
  remain authoritative across every backend instance.
- Locally, run PostgreSQL and Redis before testing email authentication. A running
  Python process alone does not provide those services.

Existing browser JWT sessions must sign in again after this migration. Signup and
login now create the new typed, server-revocable cookie session.

## Verification

Regression tests cover complete email auth, token-type confusion, concurrent
refresh, logout revocation, disabled/deleted accounts, malformed/expired tokens,
duplicate email casing, long-password collisions, storage outages, rate limiting,
private-thread ownership, CSRF, cookie flags, session persistence, refresh retries,
safe redirects, browser data separation, and truthful unsupported endpoints.

Verified on 11 October 2026:

- 89 backend tests and 104 subtests passed, including 12 authentication tests.
- 44 frontend tests passed; TypeScript and production builds passed.
- Seven local browser checks passed, including truthful errors with local
  PostgreSQL and Redis unavailable.
- Ten hosted API checks passed against real PostgreSQL and Redis. These included
  eight concurrent refresh requests, another account attempting private-thread
  reads/writes, public-share revocation, and account deactivation.
- Fifteen hosted browser checks passed: actual signup/login, wrong passwords,
  automatic expiry recovery, coordinated refresh from two tabs, cross-tab logout,
  remember me, local redirects, separate account histories, signing out of a
  stored conversation without resubmitting its query, interrupted logout
  across reload with successful retry, mobile layout, and no runtime exceptions.

Synthetic audit records were used for database checks. Temporary database access
was limited to the audit client's IP and the original rules were restored and
verified. The application backend runs commit `00467d1`; frontend authentication
and outage recovery run commit `7cd1030`.
