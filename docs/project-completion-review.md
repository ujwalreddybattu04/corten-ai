# Project completion review

Reviewed 12 October 2026. Access policy: **public signup with personal accounts**, as requested. Company invitations, SSO and team roles are outside this rollout.

The application works as a hosted preview on AWS, its only active hosting provider. Render resources were deleted and the undeployed GCP project was marked for deletion at the user's request on 12 October 2026. Remaining persistence, account recovery and production capacity work prevents describing it as ready for a company production rollout.

## Repairs completed

| Area | Result |
| --- | --- |
| AWS deployment and recovery | Complete app deployed at https://d3a7ful0miola1.cloudfront.net in Sydney: private CloudFront origin, Next.js, FastAPI, PostgreSQL, Redis, encrypted retained storage and daily private S3 backups. Records copied with matching counts; backup restored in isolation. Real auth, chat, Discover, pharma, interpolation and PDF checks passed. Free plan retained; Render removed at the user's request. See [deployment, costs and capacity limits](aws-deployment.md). |
| Pharma intelligence | Added a dedicated Analyst Workspace tool using real FDA approval actions and ClinicalTrials.gov drug/biologic record updates. Therapy/date/type filters, searchable source metadata, record details and CSV export; existing interpolation results survive tool switching. Shared Redis source snapshots/refresh leases, bounded provider requests/cooldowns and labeled 24-hour stale retention. Optional Guardian access is currently rejected, explicitly displayed. See [coverage and limits](pharma-updates.md). |
| Google Cloud retirement | The dedicated, undeployed `corten-ai-ujwal-20261012` project was marked DELETE_REQUESTED on 12 October 2026. Billing was disabled. Prepared configuration is historical; no GCP deployment is pending. See [archived status](gcp-deployment.md). |
| Personal storage | Signed-in history, Spaces, pins, feedback and Discover preferences use account-owned PostgreSQL storage with local caching, offline queues, revisions, deletion tombstones and conflict copies. CRUD no longer returns 501. Analyst files/results remain session work; keep exports. See [storage behavior and limits](personal-storage.md). |
| Spaces | List, detail and templates use the active account's cache and cloud synchronization. Questions save their Space association; existing chats and original Discover article links can be added to a chosen Space. |
| Feature accuracy | Question sharing excludes private thread/Space identifiers and explains that recipients generate a new answer. Legacy empty Library/thread screens redirect to working views. Profile editing, latest-answer regeneration and account-local feedback work; inactive model/file buttons no longer imply unavailable choices. Team publishing and file retrieval are not offered. |
| Answer delivery | Readers handle Unicode, final SSE records, errors and premature EOF. Interrupted answers are not saved as successes. Rendering preserves complete Markdown, numeric values and URL lists; malformed percent-encoded links do not crash the reader. |
| Chat startup | Chat waits for the application status endpoint before submitting generation, with a two-minute connection budget and visible progress. Only status GETs are retried automatically. Failed generation has a manual Retry action that preserves the question and conversation and excludes interrupted drafts. |
| Report integrity | One sourced model draft replaces separate planning/outline/section calls. Missing evidence, invalid JSON, output limits, incomplete sentences, provider failures and unknown citations stop publication. Downloads appear only after the stream completes. |
| Report downloads | Random identifiers, a 24-hour window, traversal rejection and no-store/nosniff headers. Signed-in reports require their generating account; guests use expiring capability links. PDFs are published atomically after generation. Downloads recover expired cookie sessions. Encrypted host storage survives container restarts; report disk-loss recovery remains pending. |
| Code tools | JavaScript and Python run in opaque-origin workers, separated from account storage; Stop can terminate execution. Python readiness has a deadline and recovers initialization failures. Remote compilers come from Wandbox's current catalogue with bounded requests and readable errors. HTML previews remain sandboxed and can be downloaded. |
| Public AI budgets | Shared Redis counters protect generation requests across backend workers. Denials return 429 with Retry-After; an unavailable limit store returns 503 instead of bypassing protection. Nginx additionally limits requests per viewer IP. This does not substitute for provider capacity or a load-tested production hosting plan. |
| Discover citations | The original article is inserted before showing sources. Citation numbers match the model's evidence order. Prior AI summaries remain conversation context rather than numbered sources. |
| Discover availability | Guardian/NewsAPI failures fall back to attributed BBC RSS headlines. Shared 20-story pools reduce duplicate provider calls while preserving page boundaries. Successful feeds remain cached for 15 minutes and can be served with a stale notice for at most six hours. Browser requests have bounded retries and cancellation; refresh failures preserve account-isolated saved stories. |
| Images | Hooks run consistently when an empty image list becomes populated, preventing a React runtime failure. |
| Authentication | PyJWT replaces python-jose/ecdsa. Algorithm allowlisting, issuer/audience checks, required typed session claims and refresh IDs are retained. Malformed/overflowing claims fail closed. Existing valid sessions retain their token format. |
| Dependencies | Next.js/ESLint config updated to 16.4.0; compatible vulnerable transitive dependencies updated; unused Jest removed. Production Docker images exclude development dependencies. |
| Readiness | `/health` checks liveness. `/ready` independently checks PostgreSQL and Redis, returning 503 on failure without exposing connection details. |
| CI | GitHub Actions runs the complete backend suite including asynchronous auth tests, frontend regressions, lint, production dependency audit and build. |

The route/control and dormant-component inventory is recorded in [the full component audit](component-audit.md).

## Verification

- **174 backend tests and 197 subtests passed**, including authentication, ownership, outages, JWT validation, calculations, reports, citations, Discover recovery, pharma caching and migration release jobs.
- **100 frontend tests passed**, including Cloud Run service authentication and pharma feed validation/retries/exports. Production Next.js build passed; ESLint has no errors, with maintenance warnings remaining. A further 17 broad browser checks and nine repaired-control checks passed locally, including real JavaScript/Python execution and article-to-Space saving.
- **14 isolated pharma browser checks and seven live-source browser checks** passed, including live checks against the hosted preview. They cover filters, details, CSV export, pagination, partial outages/stale retention, retry, empty results, cancellation, actual CSV preservation across tools, reduced motion and five screen widths. FDA/ClinicalTrials.gov return real records; optional Guardian access is rejected and labeled. No client exceptions occurred. The 18 real interpolation/export checks were repeated successfully with the new tool tabs.
- **12 isolated Discover browser checks**, repeated against the hosted frontend, verify saved-feed recovery, partial/delayed topic outages, automatic retries, correct pagination retries, stale notices, cancelled tab requests and mobile layout. Nine live browser checks cover all seven tabs, reload and mobile layout. Real category APIs and all seven RSS fallback mappings were also checked, including non-overlapping RSS pages. Fault injection uses synthetic headlines; live fallback checks use publisher data.
- **Nine chat startup browser checks**, repeated against the hosted frontend, cover temporary 502 recovery before generation, single submission, manual Retry with unchanged context, failed/partial output persistence, persistent startup failure and mobile/reduced-motion states. The existing 17 browser regressions also pass with the startup check enabled. A real hosted identity conversation verified the startup GET followed by exactly one generation POST and completed without client errors.
- **17 isolated browser checks** cover Spaces, account separation, headings, interrupted chat, image lightbox, report errors/completion/retry and mobile layout. These use synthetic account/API responses.
- **18 Analyst Workspace browser checks** use real calculation/export endpoints: Average/Exit constraints, first-year behavior, the unchanged adoption example, UTF-16 CSV, Chinese/Greek/Cyrillic PDF labels, absolute values, single-year fallback, cancellation/replacement races, errors and 320–1440px layouts.
- **14 API checks** cover readiness, guest protection, input bounds, downloads, company identity and conversation recall.
- A real sourced report produced four sections and a five-page PDF, successfully downloaded and parsed. An earlier provider request was rejected; the application displayed an error without publishing an incomplete PDF. Provider output remains variable.
- Frontend production dependency audit: **zero findings**. Installed Python package OSV audit: **zero findings** at review time. These scans do not prove the whole application is vulnerability-free.

Hosted release results are recorded in [hosted verification](hosted-verification.md). Check CI and deployment status for the source commit being released.

## Remaining rollout work

| Priority | Work | Completion criteria |
| --- | --- | --- |
| Launch blocker at production scale | Hosting capacity and availability | AWS persistent storage and daily backups/verified restore are complete for the preview. Choose and load-test highly available hosting/database/cache and provider capacity. One host and finite credits cannot support a millions-of-users claim. The old Render database was retired. |
| External rollout dependency | Public account emails | The latest request adds forgot/reset-password pages, single-use tokens, account-wide session revocation, branded email and a private encrypted outbox worker. Gmail is verified in Sydney SES; delivery is restricted to that test recipient while production access is disabled. Signup email verification remains unimplemented. See [authentication](authentication.md). |
| Operational | Monitoring and abuse controls | Shared generation limits are implemented. Add external readiness/error/latency alerts, provider-organization quota visibility and a tested incident procedure. Multiple keys can still share a provider organization quota. |
| Product | Owner-scoped report storage | Owner checks and 24-hour retention gates are implemented. Add off-host report recovery or an approved object store; current PDFs survive container restarts on retained EBS. |
| Product | Optional additions | Analyst project retention, file retrieval/RAG, suggestions and extra provider adapters need separate requirements. The active Groq routing/research pipeline is separate from dormant provider/service stubs. Article reference saving is implemented. |
| Maintenance | Development diagnostics | Resolve ESLint migration warnings. The latest ESLint-config chain has an [unpatched development-only braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm), excluded from the production image. Track the upstream fix rather than downgrading the patched framework. |

Paid hosting/provider capacity, email sender configuration and retention requirements are external rollout decisions. No paid plan was selected. [Render's free-service limitations](https://render.com/docs/free) cover idle starts, ephemeral files, absent free-database backups and database expiry. Account email work is deferred at the user's request; the current AWS app does not depend on Render SMTP behavior.

## Reproduce verification

```bash
cd backend
python -m pip install -r requirements-test.txt
python -m pytest tests -q
```

```bash
cd frontend
npm ci
npm test
npm run lint
npm audit --omit=dev --audit-level=high
npm run build
```

Local account integration needs PostgreSQL and Redis. They are absent in the current local setup, so `/ready` correctly returns 503 while stateless features remain available.
