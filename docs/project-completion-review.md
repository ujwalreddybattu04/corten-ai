# Project completion review

Reviewed 11 October 2026. Access policy: **public signup with personal accounts**, as requested. Company invitations, SSO and team roles are outside this rollout.

The application works as a hosted preview. The defects below are repaired, but the remaining persistence, account recovery and hosting work prevents describing it as ready for a company production rollout.

## Repairs completed

| Area | Result |
| --- | --- |
| Spaces | List, detail and templates use the same account-isolated browser storage. Questions started inside a Space save their thread association. Existing saved chats can be added to a chosen Space. |
| Feature accuracy | Spaces identify browser storage, notes and reference links accurately. Public/team sharing is not offered. Discover's unfinished article-to-Space action is explicitly unavailable. |
| Answer delivery | Chat/report readers handle Unicode, final unterminated SSE records, errors and premature EOF. Interrupted answers are not saved as successful conversations. |
| Report integrity | One sourced model draft replaces separate planning/outline/section calls. Missing evidence, invalid JSON, output limits, incomplete sentences, provider failures and unknown citations stop publication. Downloads appear only after the stream completes. |
| Report downloads | Random 128-bit identifiers, a 24-hour maximum download window, traversal rejection and no-store/nosniff headers. ReportLab headings and references escape markup. Files remain ephemeral. |
| Discover citations | The original article is inserted before showing sources. Citation numbers match the model's evidence order. Prior AI summaries remain conversation context rather than numbered sources. |
| Discover availability | Guardian/NewsAPI failures fall back to attributed BBC RSS headlines. Shared 20-story pools reduce duplicate provider calls while preserving page boundaries. Successful feeds remain cached for 15 minutes and can be served with a stale notice for at most six hours. Browser requests have bounded retries and cancellation; refresh failures preserve account-isolated saved stories. |
| Images | Hooks run consistently when an empty image list becomes populated, preventing a React runtime failure. |
| Authentication | PyJWT replaces python-jose/ecdsa. Algorithm allowlisting, issuer/audience checks, required typed session claims and refresh IDs are retained. Malformed/overflowing claims fail closed. Existing valid sessions retain their token format. |
| Dependencies | Next.js/ESLint config updated to 16.4.0; compatible vulnerable transitive dependencies updated; unused Jest removed. Production Docker images exclude development dependencies. |
| Readiness | `/health` checks liveness. `/ready` independently checks PostgreSQL and Redis, returning 503 on failure without exposing connection details. |
| CI | GitHub Actions runs the complete backend suite including asynchronous auth tests, frontend regressions, lint, production dependency audit and build. |

## Verification

- **152 backend tests and 195 subtests passed**, including authentication, ownership, outages, JWT validation, calculations, reports, citations and Discover recovery.
- **65 frontend tests passed**. Production Next.js build passed; ESLint has no errors, with maintenance warnings remaining.
- **11 isolated Discover browser checks** verify saved-feed recovery, partial topic outages, automatic retries, correct pagination retries, stale notices, cancelled tab requests and mobile layout. Real category APIs and all seven RSS fallback mappings were also checked, including non-overlapping RSS pages. Fault injection uses synthetic headlines; live fallback checks use publisher data.
- **17 isolated browser checks** cover Spaces, account separation, headings, interrupted chat, image lightbox, report errors/completion/retry and mobile layout. These use synthetic account/API responses.
- **18 Analyst Workspace browser checks** use real calculation/export endpoints: Average/Exit constraints, first-year behavior, the unchanged adoption example, UTF-16 CSV, Chinese/Greek/Cyrillic PDF labels, absolute values, single-year fallback, cancellation/replacement races, errors and 320–1440px layouts.
- **14 API checks** cover readiness, guest protection, input bounds, downloads, company identity and conversation recall.
- A real sourced report produced four sections and a five-page PDF, successfully downloaded and parsed. An earlier provider request was rejected; the application displayed an error without publishing an incomplete PDF. Provider output remains variable.
- Frontend production dependency audit: **zero findings**. Installed Python package OSV audit: **zero findings** at review time. These scans do not prove the whole application is vulnerability-free.

Hosted release results are recorded in [hosted verification](hosted-verification.md). Check CI and deployment status for the source commit being released.

## Remaining rollout work

| Priority | Work | Completion criteria |
| --- | --- | --- |
| Launch blocker | Durable hosting and recovery | Replace the expiring preview database, configure backups and prove a restore. Current Render database expiry: **10 November 2026, 02:50 UTC**. Choose persistent session/cache storage and hosting/model/search capacity for expected traffic. |
| Launch blocker | Personal cloud persistence | Connect browser history, Spaces, collections and analyst projects to server storage with ownership checks, migrations and conflict/retry handling. Verify cross-device access and isolation. Current Spaces/collections APIs return 501; PostgreSQL deployment alone does not implement them. |
| Launch blocker for public accounts | Email verification and recovery | Configure a transactional email API and approved sender/domain. Implement expiring single-use verification/reset tokens, rate limits and session revocation. Test delivery. Current public email/password signup/sign-in has no verification or password reset. |
| Operational | Monitoring and abuse controls | Add external readiness/error/latency alerts, shared limits for public AI/search/report endpoints, quota visibility and a tested incident procedure. Multiple keys can still share a provider organization quota. |
| Product | Durable report storage | Use an approved object store with owner-scoped access and retention. Current PDFs disappear on backend restart/redeploy/spin-down. |
| Product | Optional unfinished features | Article saving into Spaces, file retrieval/RAG, suggestions and extra provider adapters are unimplemented. The active Groq routing/research pipeline is separate from dormant service/provider stubs. |
| Maintenance | Development diagnostics | Resolve ESLint migration warnings. The latest ESLint-config chain has an [unpatched development-only braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm), excluded from the production image. Track the upstream fix rather than downgrading the patched framework. |

Paid hosting/provider capacity, email sender configuration and retention requirements are external rollout decisions. No paid plan was selected. [Render's free-service limitations](https://render.com/docs/free) cover idle starts, ephemeral files, absent free-database backups and database expiry. Free services also block standard SMTP ports; an HTTPS email API is suitable for that preview environment.

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
