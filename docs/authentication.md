# Authentication and password recovery

Public signup creates personal accounts. Sign-in is required for chat, Discover,
reports, code execution, Spaces and both Analyst Workspace tools. Only auth pages
and readiness endpoints remain public. Browser session verification happens before
tools mount. App APIs independently require a valid session; auth pages do not mount
the sidebar. Requested local return paths survive sign-in.

## Session security

Passwords use bcrypt-SHA256, with legacy bcrypt readable and no silent truncation.
Passwords accept 8–1024 characters. Login errors do not reveal account existence.
The proxy keeps JWTs in HttpOnly, SameSite=Lax cookies, Secure on HTTPS. APP_ORIGIN
controls CSRF and cookie checks. Tokens never appear in browser login JSON or
localStorage. Authenticated responses use no-store; source caching remains internal.

Redis tracks session IDs and one-use refresh JTIs, with atomic rotation, replay
revocation and rate limits. Browser tabs coordinate refresh; logout revokes the
whole session. Sessions have an absolute seven-day maximum. Protected requests also
check the active PostgreSQL user and password version (pv). Legacy valid JWTs
represent version zero. Database/security-store outages fail closed.

Private threads and PDFs require their owner; public threads still require sign-in.
Personal histories, Spaces and preferences sync through owner-scoped PostgreSQL
records with revisions. Account changes cancel work and isolate browser caches.
Existing guest data stays separate and does not authenticate anyone.

## Recovery

The sign-in page links to /auth/forgot-password. Eligible requests atomically create
a random token and encrypted mail outbox entry. The reset table stores only a SHA-256
digest. Purpose-separated queue encryption derives from the existing JWT secret.
Known and unknown eligible addresses get the same neutral reply. Sending restrictions
produce an explicit error rather than a false delivery confirmation.

The responsive branded HTML email has a plain-text alternative, reset button,
expiry and security notice. HTTPS links carry a URL fragment token outside server
paths/queries. Reset UI checks matching passwords, handles expired links, clears
sensitive fields and removes the token after success.

Links expire after 30 minutes and work once. A new request supersedes older links.
Account-before-token PostgreSQL locks ensure one concurrent reset succeeds.
Success increments the user password version, invalidating all previous access
and refresh sessions across devices. Reset does not auto-login. Additive migration
0003 preserves accounts and initializes their password version to zero.

## AWS sending and current restriction

ujwalreddybattu@gmail.com is individually verified in Sydney SES. The existing host
role allows only ses:SendEmail for that identity, pinned with ses:FromAddress.
Application containers get no AWS credentials or access to the host role.

The private host worker leases encrypted rows, submits via SES v2, acknowledges
provider acceptance and clears payloads. Retries/backoff are bounded; stale leases
recover. Expired, superseded or used links are cancelled. Daily maintenance prunes
rows after seven days past expiry. Logs omit recipients, bodies and tokens.
Delivery is at least once: a lost acknowledgement may resend the same link.
Changing the JWT secret invalidates encrypted queued payloads as well as JWTs.

SES production access is disabled. Sandbox permits (1) individually verified
recipients, (2) SES mailbox simulator addresses, or (3) mailboxes at a verified domain.
Runtime permits only the verified Gmail test recipient. Public delivery awaits
sender authentication and SES production approval. SES MessageId means acceptance,
not delivery or SPF/DKIM/DMARC alignment. No Gmail SMTP connection is assumed.

Keep RECOVERY_EMAIL_ENABLED, EMAIL_FROM, EMAIL_PUBLIC_BASE_URL,
EMAIL_ALLOWED_RECIPIENTS (JSON list), and PASSWORD_RESET_EXPIRE_MINUTES in
corten-ai/runtime, excluded from Git. Remove the test restriction only after public
sending approval and bounce/complaint/quotas monitoring are ready.

## Verification and rollout

193 backend tests plus 197 subtests and 104 frontend tests pass. Release verification
also proves additive migrations, concurrent reset, version revocation and worker
leases against isolated real PostgreSQL. See [hosted verification](hosted-verification.md).

Email verification, SSO and MFA remain unimplemented. Authenticated public email,
approved Terms/Privacy, monitoring and load-tested high availability remain rollout
work. One preview host cannot support millions-of-users availability.
