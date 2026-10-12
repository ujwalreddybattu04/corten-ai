# Deploy Corten AI

For the requested Google Cloud migration, see [GCP deployment status and setup](gcp-deployment.md).
The GCP project is created; billing activation and infrastructure provisioning
are pending. The Render preview below remains the currently deployed application.

[Deploy the full preview on Render](https://render.com/deploy?repo=https://github.com/ujwalreddybattu04/corten-ai)

The root `render.yaml` defines four resources in Singapore: a Next.js frontend,
a FastAPI backend, PostgreSQL 17 with pgvector, and a Redis-compatible Key Value cache.
All four explicitly use the free plan. No hosting resources have been created merely
by adding this configuration to GitHub.

## Connect and deploy

1. Sign in to Render and connect this GitHub repository, or use the deployment link above.
2. Review the four resources and their free plans before creating the Blueprint.
3. Enter `GROQ_API_KEY` in the backend's secret configuration. Add your existing
   `TAVILY_API_KEY` and/or `SERPER_API_KEY` for search. `GUARDIAN_API_KEY` and
   `OPENFDA_API_KEY` are optional for the pharma feed. Leave unused optional secrets blank.
   Add other configured news, weather or LLM provider keys directly to the backend's
   environment if those integrations are needed. Never commit keys to this repository.
4. Render generates the JWT secret and database/cache connection strings. The backend
   normalizes PostgreSQL URLs for the async driver and runs Alembic before starting.
   Migration failure stops startup so a broken database is not presented as a successful deployment.
5. Set the frontend's `BACKEND_URL` to the backend's public HTTPS URL from its
   Render service page and redeploy the frontend. You can leave the initial
   Blueprint prompt blank until the backend's URL has been assigned.
   Wait for both services to become live. Open the **frontend** URL for the app.
   browser API calls use the frontend proxy, including authentication, streamed
   responses and PDF downloads. The backend URL stays in server environment variables.
6. If the frontend starts before the backend is ready, reload after the backend
   deployment finishes. Free service cold starts can also temporarily delay API calls.

Free backend services cannot receive private service traffic, so the web service
uses the backend's public HTTPS address. PostgreSQL and Redis accept only internal
connections (`ipAllowList: []`). A successful API `/health` response confirms the
process is running; verify login and a database operation to check persistence.
The backend `/ready` checks both database and cache and returns 503 when either is unavailable.

## Verify the hosted app

- Frontend `/`, `/analyst-workspace`, `/report` and `/auth/login` load without runtime errors.
- The backend `/health` responds with `status: healthy`.
- The frontend `/api/v1/pharma/updates?topic=oncology&days=7` returns the requested feed.
- “Who developed you?” returns the Chryselys identity without a web search.
- A factual current query produces a streamed answer with sources using the configured providers.
- Sign up and sign in, then verify an authenticated profile. Spaces currently use account-isolated browser storage; their server endpoints return 501.
- Generate a report and download its PDF through the frontend origin.
- Upload a yearly CSV in Analyst Workspace, calculate Average/Exit values and verify CSV/JSON/PDF exports against the yearly constraints.

## Preview limits and company deployment

This free Blueprint is for evaluation. Render's [free hosting documentation](https://render.com/docs/free)
specifies idle spin-down, 750 shared web-service hours per workspace per month, and
PostgreSQL expiration after 30 days. The free database has no backups. Free Redis
state is lost on restart. Upgrade and configure backups before storing company data.
Paid plans and any increased spending must be selected with an approved hosting budget.

Chat history and Spaces currently stay in account-isolated browser storage. The
Analyst Workspace processes uploaded yearly CSV data into monthly values and exports;
it has no shared server project store. PostgreSQL supports accounts and the existing
thread API, but deploying it does not implement personal cross-device synchronization.
See the [current completion review](project-completion-review.md) for launch requirements.

Reports are held on an ephemeral backend filesystem and can disappear on a service
restart. For durable reports, integrate object storage before production use.
Downloads expire after at most 24 hours and may become unavailable sooner after a restart.

## Local validation

```bash
cd frontend
npm ci
npm test
npm run lint
npm run build
```

```bash
cd backend
python -m pip install -r requirements-test.txt
python -m pytest tests -q
```

Docker build contexts and Git ignore local `.env` files, virtual environments,
node modules, build caches and logs. Only blank or placeholder environment examples
are published. The backend production setting rejects a weak default JWT secret.

Provider configuration follows the [Render Blueprint reference](https://render.com/docs/blueprint-spec).
