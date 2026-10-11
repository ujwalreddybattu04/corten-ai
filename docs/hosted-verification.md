# Hosted verification — 11 October 2026

## Deployment

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
- A request to explain forecast assumptions streamed an answer. It invoked web search
  and an unnecessary weather tool because the existing router treats “forecast” as
  an external-information/weather signal. This behavior remains a routing limitation.
- The report page loaded successfully. Full report generation and a live generated-PDF
  download were not exercised; PDF forwarding was covered by the proxy regression test.

## Current limits

- Guardian news returned an authentication error for the configured key. FDA and
  ClinicalTrials.gov continue working independently.
- Serper image requests returned 403. Tavily web search still returned cited results.
- Groq briefly retried some requests; the tested streamed answers completed successfully.
- Forecasts and review versions remain local to each browser. Hosting PostgreSQL does
  not provide shared forecast storage or team approval history.
- Reports use temporary backend storage.
- Render reported database expiration on **10 November 2026**. Its free plans can
  spin down and share a monthly web-service hours allowance. Upgrade the database
  and configure backups before using this setup for ongoing company work.

See [deployment instructions](deployment.md) and [Render free-plan limits](https://render.com/docs/free).
