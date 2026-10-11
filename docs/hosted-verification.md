# Hosted verification — 11 October 2026

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

