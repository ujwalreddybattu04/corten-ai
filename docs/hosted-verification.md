# Hosted verification — 12 October 2026

## Complete component audit release

Source `9f24b1b3ae6c19a2252c7d6ef78071b8e22f53ce` is deployed to **https://d3a7ful0miola1.cloudfront.net**. [Both final CI jobs passed](https://github.com/ujwalreddybattu04/corten-ai/actions/runs/38256796380). The route/control checklist and all 57 component files are inventoried in [component-audit.md](component-audit.md), including inactive scaffolding and external dependencies.

- Backend: 174 tests and 197 subtests passed. Frontend: 100 tests passed, with TypeScript, production build and zero lint errors. Maintenance warnings remain.
- Twenty expanded control cases and five widget fault cases passed on the AWS bundle. Nine additional cases passed with actual JavaScript/Python execution under the deployed CSP, sandboxed HTML preview, answer integrity, profile editing and article-to-Space saving. Two blocked-storage cases verified truthful sign-in status and successful sync reinitialization after storage access returned.
- Fifteen real authentication browser cases passed on the final release, including signup/login, session cookies, two-tab refresh, account isolation and interrupted logout recovery.
- Eighteen interpolation browser checks and seven live pharma checks passed on the final release, including actual exports, unrounded yearly constraints, Unicode PDFs and 320–1440px layouts. No client exceptions occurred.
- Ten real cloud-account checks proved fresh-device restoration, competing offline edits preserved as separate copies, stale-write rejection, deletion propagation, Spaces/collections CRUD, account isolation and owner-only generated PDF access. These checks used actual temporary accounts, API writes and separate browser profiles rather than seeded browser histories.
- All seven real Discover feeds returned 18 articles. The real sidebar returned four market indices, five stocks and weather for explicit coordinates. Actual identity and writing responses completed with no web search; current research completed with web search and ten sources. Four direct contextual-recall/long-note cases passed without model/search calls. A current article summary ended with a complete sentence and a terminal completion event.
- The final release command `c4101247-765d-4d2a-8ee5-b50c063f4b85` succeeded. Its output explicitly reported all six isolated PostgreSQL verification flags before migration. The database backup `20261012T134049Z` completed, services started successfully and public readiness returned 200.
- Release archive SHA-256: `8d641ee147a48448a723bdd5940b001ea9276ee2271644aeed4de749f890c262`. The archive contained 386 public source files; the credential scan found zero findings. Provider credentials and browser/audit artifacts remain excluded.

Account email work remains deferred at the user's request. The optional Guardian pharma-news source still denies access and is labeled; FDA/clinical-trial records work independently. The current single-host AWS Free-plan preview is not a completed large-scale production infrastructure rollout.

## Pharma workspace design release

Release `a1a5f3c` is live on AWS; [both CI jobs passed](https://github.com/ujwalreddybattu04/corten-ai/actions/runs/38220999298).

- Preserves Corten's Plus Jakarta Sans font and dark theme, adding source widgets, latest-record previews, loaded-date/phase charts and card/list controls. Charts use the capped source sample, with no fabricated trends or market totals.
- 17 targeted backend tests (two subtests), ten frontend feed/widget checks, TypeScript, scoped ESLint and production compilation passed. Both full CI jobs also passed.
- Existing 14 isolated pharma browser checks passed locally. Seven existing live checks and five new live design checks passed on AWS, covering real records, filters, details, highlights, layout switching, 320–1440px widths and reduced motion; no browser exceptions.
- Six additional isolated design checks passed locally and on the AWS bundle, including intentionally blocked publisher images recovering to labeled illustrations. Fixtures are browser-only; real API data was not changed.
- Optional news photos use publisher thumbnails when provided. FDA/trial visuals are labeled illustrated previews with real identifiers. The current news provider still lacks access; the UI states this explicitly and keeps available primary-source records usable.

## AWS full-stack deployment

Application: **https://d3a7ful0miola1.cloudfront.net**. Sydney Free-plan deployment includes Next.js, FastAPI, PostgreSQL, Redis, a private CloudFront origin and encrypted persistent storage. At the user's subsequent request, all four Render resources were deleted and the undeployed GCP project was marked DELETE_REQUESTED. AWS pages and readiness were verified again after retirement. The Render releases below are historical verification.

- 15 real authentication browser checks passed, including Secure/HttpOnly cookies, two-tab refresh, account isolation and interrupted logout recovery. Exactly two newly created synthetic AWS accounts were removed; the imported account was retained.
- 18 interpolation checks and seven live pharma browser checks passed. All seven Discover API categories and browser tabs rendered real articles; no mobile overflow or client exceptions occurred.
- Actual identity/writing/research SSE streams completed, with ten sources for current research and no search for identity. Four direct contextual-memory cases passed without model/web calls.
- A sourced report produced four sections and a five-page downloadable PDF. The download survived a backend container restart.
- All 12 source/target table counts matched. Daily encrypted PostgreSQL backups were configured; an actual S3 backup was downloaded, checksum-verified and restored in an isolated database, with matching counts and no production modification.
- Temporary migration access on Render/AWS and the host's source connection files/dump were removed. The migration secret is pending seven-day deletion. Provider keys went directly to Secrets Manager under explicit authorization, without a local export.
- HTTP redirects to HTTPS; security headers and static asset caching work. Dynamic streaming responses were not edge-cache hits. Both infrastructure templates passed local schema/security checks and AWS validation.

See [AWS operations, costs and capacity limitations](aws-deployment.md). These checks verify preview functionality, not high availability or millions-of-users capacity.

## Chat startup recovery release

Both services deployed `d510e33` and reached `live`. [Both CI jobs passed](https://github.com/ujwalreddybattu04/corten-ai/actions/runs/38157925617).

- All 153 backend tests (195 subtests), 73 frontend tests, production build and lint passed. Lint retains 53 maintenance warnings.
- Nine startup/retry browser checks passed locally and against the hosted frontend using isolated simulated gateway/startup errors. They verify waiting before generation, a single POST after readiness, manual Retry preserving context, failure/partial-output persistence, bounded waiting and mobile/reduced-motion behavior. No client exceptions occurred.
- The existing 17 local browser regressions passed with the startup check enabled.
- A live guest identity conversation checked application status first, submitted one generation POST, completed with the Chryselys identity, and displayed no error. This verifies real routing and streaming, not external provider availability under load.
- The hosting API confirmed both web services remain on the free compute plan. The public startup endpoint returned HTTP 200 with `status: ready`. No hosting plans or credentials were changed.
- The public-source scan found zero credential findings in 335 files.

Startup fault tests were simulated; they do not prove every historical 502 came from idle starts. Render's documented free-plan wake-up delay matches the reported first-open pattern. Deployments and other connection failures can also produce 502. Always-on hosting is still required to remove idle startup delays. See [chat startup behavior](chat-startup.md).

## Discover reliability release

Backend and frontend deployed `dcbca1d` and reached `live`. [Both CI jobs passed](https://github.com/ujwalreddybattu04/corten-ai/actions/runs/38156805923).

- All 152 backend tests (195 subtests), 65 frontend tests and the production build passed. ESLint reported zero errors and 53 existing maintenance warnings.
- Seven real hosted API requests returned HTTP 200 with stories: all six category feeds and a second page. Nine live browser checks covered For You, all six category tabs, refresh and mobile layout. No client exceptions occurred.
- Twelve fault-injection browser checks passed against both the local production build and hosted frontend. They cover saved stories after outage/reload, account/category cache boundaries, automatic 502 retry, refresh versus pagination retry, partial topic failure, delayed topics rendering progressively, stale notices, request cancellation and mobile layout. These failure checks use synthetic headlines and isolated guest browser profiles.
- All seven BBC RSS fallback mappings returned real headlines with API credentials disabled. Sports pagination had no overlapping stories. The hosted news check used the healthy NewsAPI provider; RSS fallback behavior was separately verified with live publisher feeds and offline failure tests.
- The public-source scan found zero credential findings in 331 files. No provider keys or hosting plans were changed.

The observed Guardian 401 remains a credential issue, but it no longer makes that source the only way to load the feed. Free hosting can still idle-start, and total upstream failure without any usable saved data still produces a clear error. Weather and financial widgets have separate providers. See [Discover recovery behavior](discover-reliability.md) for deadlines and freshness limits.

## Completion review release

The core completion repairs were deployed and checked on `61cfc0c`. Both Render
services reached `live`, and [both GitHub CI jobs passed](https://github.com/ujwalreddybattu04/corten-ai/actions/runs/38151055017).
Public signup with personal accounts remains the chosen rollout policy.

- 14 hosted API checks passed; `/ready` confirmed both PostgreSQL and Redis available.
- 10 real authentication checks passed: signup/login/profile, case-normalized duplicate email, wrong-password errors, token types, rotation/replay, logout, eight concurrent refresh requests, ownership, profile restrictions and account deactivation.
- Exactly two synthetic audit accounts were deleted; no other accounts were touched. Temporary single-IP database access was removed and the original rules were verified.
- 18 real hosted Analyst Workspace browser checks passed, including the unchanged adoption input, both modes, Unicode PDF output, CSV/JSON exports, errors/cancellation and mobile layouts.
- Discover returned articles for six categories and a second-page request: seven successful feed checks.
- A real report completed, downloaded and parsed as a four-page PDF with 15 research sources. Three model/chat checks passed for a generated Python answer, generated topic heading and previous-question recall without web search.
- Nine summary animation/error/reduced-motion checks passed against the upgraded local production build. The additional report retry action passed the local browser review.

See [the completion review](project-completion-review.md) for the current features,
test commands and unresolved launch work. Records below describe earlier iterations;
old forecast/scenario features were replaced by the CSV interpolation workspace.

## Earlier deployment verification (historical)

- Public repository: https://github.com/ujwalreddybattu04/corten-ai
- Frontend: https://corten-ai-web.onrender.com
- Analyst Workspace: https://corten-ai-web.onrender.com/analyst-workspace
- Backend: https://corten-ai-api.onrender.com
- PostgreSQL 17 with pgvector: available; initial Alembic migration completed.
- Redis-compatible cache: available; backend startup confirmed a successful connection.
- All four resources use free Render plans. Resources were created through the Render API;
  they are not linked to an automatically synchronized Blueprint. `render.yaml` also
  passed Render's official Blueprint validation for this configuration.
- Backend and frontend use their respective repository folders with automatic deploys enabled.
- Local secrets were excluded from the repository and Docker build contexts. Backend
  credentials were configured in Render after explicit authorization.

The first backend deployment reached the database before provisioning completed.
The final startup waits for a database connection before migration, then starts the API.
The backend subsequently deployed successfully.

## Completed checks

- Production Next.js build and TypeScript checking passed; TypeScript build errors are no longer ignored.
- 14 Node checks passed for forecasting and the API proxy, including authorization,
  query strings, error status, streaming, empty responses and binary PDF forwarding.
- 20 Python checks passed for search routing, pharma normalization/caching/failure
  behavior, production settings and password hashing.
- 34 checks passed in the hosted browser with no client exceptions: home/workspace/report/login
  routes, shared font family, dark theme, all six workspace tabs at 1440/768/390/320 pixels,
  patient forecast recovery after reload, saved review versions and 12 monthly output rows.
  Browser requests used the deployed origin rather than localhost or the previous cloud backend.
- The public backend health check returned healthy.
- A protected authentication request returned 401 through the frontend proxy.
- A nonexistent-user login reached the database and returned the expected 401.
  Successful registration/login was not exercised with a permanent test account.
- Invalid pharma query parameters returned 422.
- The filtered oncology feed returned 40 dated FDA and clinical-trial records, with
  the requested topic and seven-day window preserved through the proxy.
- “Who developed you?” streamed the Chryselys identity with no tools or web sources.
- A current FDA query streamed an answer with ten web sources.
- Forecast-assumption writing was subsequently corrected to use a direct answer.
  Business forecasts no longer qualify for the weather tool solely because they
  contain the word “forecast”; see [answer-quality.md](answer-quality.md).
- The report page loaded successfully. Full report generation and a live generated-PDF
  download were not exercised; PDF forwarding was covered by the proxy regression test.

## Current limits

- Guardian news returned an authentication error for the configured key. Discover
  now falls back to the configured NewsAPI source. The workspace's Guardian pharma
  source still reports its authentication error; FDA and ClinicalTrials.gov work independently.
- Serper image requests returned 403. Tavily web search still returned cited results.
- Groq briefly retried some requests; the tested streamed answers completed successfully.
- Forecasts and review versions remain local to each browser. Hosting PostgreSQL does
  not provide shared forecast storage or team approval history.
- Reports use temporary backend storage.
- Render reported database expiration on **10 November 2026**. Its free plans can
  spin down and share a monthly web-service hours allowance. Upgrade the database
  and configure backups before using this setup for ongoing company work.

See [deployment instructions](deployment.md) and [Render free-plan limits](https://render.com/docs/free).

## Discover follow-up verification — 11 October 2026

The empty Discover page was caused by calling only Guardian and returning its
authentication failure as a successful empty feed. The deployed fix tries NewsAPI
when Guardian fails, distinguishes source failure from an empty category, and
shows a Retry action. Personalized requests respect the API's minimum page size,
and Redis cache entries include the requested size. Delayed responses from a
previous tab cannot replace the active feed.

- Ten deterministic backend checks passed for fallback, missing keys, cache sizes,
  pagination, topic mapping, truthful HTTP statuses and safe error logging.
- Two personalization checks passed, including strong positive and negative preferences.
- The production frontend build passed compilation, TypeScript and static generation.
- Twelve local browser checks passed with no client exceptions, including all seven
  tabs, mobile layout, Retry recovery, failed pagination preserving existing stories,
  and a deliberately delayed previous-tab response.
- Both Render services deployed commit `7d51d98` successfully.
- The hosted API returned 17–18 articles in each of the six news categories and six
  articles for the tested next page. All responses used the NewsAPI fallback.
- The hosted browser displayed 50 articles in For You and 17–18 in each other tab,
  with no client exceptions or horizontal overflow in the tested mobile viewport.

## Context and company answers (2026-10-11)

The backend is live at commit `72ea81d`. The existing frontend design and deployment
remain unchanged. See [answer-quality.md](answer-quality.md) for the routing and evidence rules.

- All 59 deterministic backend tests passed, including 52 additional subtests.
- Thirteen hosted functional query cases passed: identity, company description,
  company location follow-up, agents, capabilities, training attribution, missing and
  ambiguous subjects, another company's follow-up, misleading prior answers,
  headquarters uncertainty, generic forecast explanation and current FDA research.
- Seven hosted browser checks passed with no client exceptions. The real input form
  sent conversation history, displayed verified office locations, and answered the
  agent question without web-search progress. The tested mobile layout remained dark
  and fit the viewport after its sidebar transition completed.
- Company sources came from the configured official domain. Office addresses were read
  from the retrieved contact page; they were not inferred as headquarters.
- The generic forecast explanation used no tools, invented figures or project conditions.
- The current FDA request retained web search and used 2026 in its generated plan.
- The public-source scan found no credential values in 278 source files.

The first rapid hosted sequence hit the configured Groq account's 8,000-token-per-minute
limit. Verified company-answer caching and removal of unnecessary company suggestion
calls reduced repeated usage. Functional checks were then paced within that quota;
this is not a concurrent load test. Company-wide usage still needs appropriate provider
capacity. The security and shared-workspace gaps from the separate project review
were not addressed by this answer-quality change.

## Conversation recall and saved context (2026-10-11)

Both services deployed the conversation-memory change at `aa0ef0d`. See
[conversation-memory.md](conversation-memory.md) for the retention limits and persistence model.

- All 70 backend tests and 89 subtests passed, along with 18 frontend tests and the
  production frontend build.
- Hosted real-model recall returned the older Meridian/oncology note with the
  user's latest Japan correction. An absent budget was acknowledged. Neither
  request selected tools or returned web sources.
- The hosted browser answered previous/first/numbered question requests without
  web search. Refresh restored ten saved exchanges without issuing another search;
  reopening the saved thread preserved context. A follow-up after reopening used
  the retained earlier messages.
- New-thread context, navigation between saved threads, missing-thread errors and
  private mode passed in the hosted browser, with no client exceptions. Private
  synthetic notes were absent from local storage.
- Fast offline responses render even when the entire stream completes in one React
  batch. Native URL updates participate in Next.js navigation state.
- The public-source scan found no credential values in 283 source files.

During initial testing, the configured Groq model hit its 200,000-token daily
allowance. Question retrieval, note acknowledgment and conversation titles no
longer require an LLM. Other generated responses still depend on provider
availability and quota. This is functional verification, not a concurrency test.
Memory remains bounded and specific to a conversation in this browser; authenticated
cross-device and shared-team memory are separate work.

## Conversation headings (2026-10-11)

Both services deployed `1413645`. See [thread-titles.md](thread-titles.md) for the
generation, migration, privacy and fallback behavior.

- All 77 backend tests (104 subtests), 27 frontend tests and the final production
  build passed. The public-source scan found no credential values in 288 files.
- The live title provider generated `Python Code Writing` from `write a python code`.
  The sidebar displayed it; refresh retained it without another search or title request.
- Controlled browser responses verified late updates, legacy prompt migration,
  updates in an open history dialog, identical prompts in different threads,
  manual rename protection, greeting-to-topic headings and provider-failure backoff.
- Private mode sent no title request and left stored history unchanged.
- A real hosted conversation note was answered and saved with `Meridian Project Notes`.
  The test browser reported no client exceptions.
- The greeting follow-up test also exposed and verified a fix for the research
  indicator's conditional React hook, which could previously crash a new follow-up.

Browser race checks use synthetic conversation content and controlled stream/title
responses, alongside the live provider title and live conversation-note checks.
This is functional validation, not concurrent load testing or shared-team persistence.
# Authentication verification — 11 October 2026

Email signup/login and server-verified cookie sessions were tested on the hosted
app. Critical fixes include rejecting refresh tokens as access credentials,
atomic refresh rotation with replay detection, immediate logout revocation,
private-thread ownership, disabled-account checks, browser account data separation,
and recoverable interrupted logout. Render's public HTTPS origin is used for CSRF
checks and Secure cookies.

All 89 backend tests (plus 104 subtests), 44 frontend tests, ten live API checks,
seven local browser checks, and fifteen hosted browser checks passed. Production
builds and TypeScript checks passed. Local PostgreSQL and Redis are currently
unavailable; local email authentication requires those services.

Email verification/recovery, SSO/MFA, company membership rules, and centralized
team storage remain prerequisites for using real company data. See
[authentication.md](authentication.md) for the session design and complete findings.

## Pharma integration and GCP preparation — 12 October 2026

Code release `4b315cf36d059c889ee4f5b71edfc210168aa355` is live on both current
Render services. [Both GitHub CI jobs passed](https://github.com/ujwalreddybattu04/corten-ai/actions/runs/38193722756).

- Seven hosted live-browser checks passed for the pharma tab, actual FDA/trial
  records, record details, therapy/date/source filters, dark/font consistency,
  five viewport widths and reduced motion. No client exceptions occurred.
- Fourteen isolated browser checks passed locally and against the hosted frontend, including CSV export,
  pagination, source outages/stale retention, retry, empty results, cancellation
  and preserving an actual interpolation CSV across tool switches.
- The eighteen existing real interpolation/calculation/CSV/JSON/PDF checks also
  passed locally with the tool switcher. Source upload values were unchanged.
- Complete backend suite: 163 tests and 197 subtests. Frontend: 83 tests.
  Production build passed; ESLint has zero errors and 53 existing warnings.
  The public-source scan found zero credential findings in 348 files.
- A dedicated GCP project was created and deployment support prepared. Project
  billing activation and persistent infrastructure are pending; no GCP app URL
  has been created. See [the GCP deployment record](gcp-deployment.md).

The optional Guardian pharma source currently rejects access and is labeled in
the screen. FDA and ClinicalTrials.gov remain available independently. Hosting
plans and production capacity were not upgraded by this release.

