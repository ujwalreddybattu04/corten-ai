# Google Cloud deployment

**Retired on 12 October 2026 at the user's request.** Project `corten-ai-ujwal-20261012` is verified in `DELETE_REQUESTED` state. It had billing disabled and no deployed Corten application. AWS is the only active hosting provider; use [AWS deployment instructions](aws-deployment.md). The configuration below is historical preparation, not pending deployment work.

On 12 October 2026, the account owner requested hosting on Google Cloud and a
dedicated project. Project `corten-ai-ujwal-20261012` was created successfully.
Google sign-in was completed. Deployment was blocked by project billing activation and has now been cancelled.
No paid infrastructure or live GCP application exists yet.

Google's API cannot reopen billing accounts (`open` is output-only). The billing
owner must [reopen an account in the console](https://docs.cloud.google.com/billing/docs/how-to/close-or-reopen-billing-account)
and link it to this project. An account with payment/verification problems may
require Google support. Enabling billing is distinct from a successful deployment.

## Concrete deployment configuration

| Component | Proposed configuration |
| --- | --- |
| Region | Singapore, `asia-southeast1`, same region for compute/database/cache |
| Frontend | Cloud Run, public, 1 vCPU / 1 GiB, minimum 1 warm instance, maximum 20, concurrency 40 |
| Backend | Cloud Run, IAM private, 1 vCPU / 1 GiB, minimum 1 warm instance, maximum 10, concurrency 16 |
| Database | Cloud SQL PostgreSQL 17; private access/Cloud SQL socket, automated backups and point-in-time recovery; choose capacity/HA within an approved budget |
| Cache/session store | Managed Redis on the private VPC; configure AUTH, persistence/HA and transport security within the approved capacity plan |
| Provider/database credentials | Secret Manager versions, backend identity access scoped per secret; never baked into container images |
| Images | Artifact Registry repository `corten`; Cloud Build produces both images, tagged by reviewed Git commit |
| Migrations | One Cloud Run release job before app deployment, PostgreSQL advisory lock, bounded runtime; app replicas skip startup migrations |

Warm instances reduce scale-from-zero latency; additional autoscaled instances can
still start cold. External API quotas and failures still apply. These starting
limits do not certify million-user throughput. Confirm capacity with load tests,
monitoring and database/cache connection budgets before increasing traffic.
Minimum instances, Cloud SQL, Redis, builds/storage and network usage can incur
charges. Use [Google's pricing calculator](https://cloud.google.com/products/calculator)
for the approved region/capacity; a monthly budget alert is not a hard spending cap.

## Prepared files and deployment sequence

- `deploy/gcp/cloudbuild.yaml` builds the existing Docker images. `.gcloudignore`
  excludes local credentials, `.env`, tooling, dependencies and private test scripts.
- `deploy/gcp/backend.env.yaml` contains non-secret runtime settings. SQL pools
  allow 3 persistent connections + 2 overflow per process (up to 50 connections
  for the initial ten-instance backend ceiling, excluding migration/admin usage).
- `deploy/gcp/Deploy-Gcp.ps1` defaults to read-only preflight. It checks billing,
  Artifact Registry, SQL/network, service identities and secret-version metadata.
  `-Deploy` additionally builds, runs migrations, deploys the private backend,
  grants only the frontend identity invoker access and deploys the frontend.
- The frontend proxy uses a Google metadata ID token in `X-Serverless-Authorization`,
  separately from the app's user JWT. Metadata tokens are server-only, cached by
  audience and refreshed before expiry. Other hosting is unchanged without
  `BACKEND_IDENTITY_AUDIENCE`.
- After deployment, set `APP_ORIGIN` to the actual frontend/custom-domain HTTPS
  origin; the script sets the Cloud Run URL. This is needed for secure cookies and
  request-origin validation behind the Cloud Run proxy.
- Service startup checks `/ready` (database + Redis); backend liveness checks
  `/health`. Frontend honors Cloud Run's injected `PORT` and binds all interfaces.

Before running `-Deploy`, provision the reviewed VPC/subnet, Artifact Registry,
service identities, Cloud SQL and Redis with an approved budget. Required secrets:
`corten-database-url`, `corten-redis-url`, `corten-jwt-secret`, `corten-groq-key`,
`corten-tavily-key`. Optional provider secrets follow the names in the script.
Optional absent sources remain unavailable instead of receiving placeholder keys.
Secret versions are resolved once and pinned for the migration/app release.

Example (after infrastructure and secret access are ready):

```powershell
./deploy/gcp/Deploy-Gcp.ps1 -ProjectId corten-ai-ujwal-20261012 -ImageTag COMMIT_SHA
./deploy/gcp/Deploy-Gcp.ps1 -ProjectId corten-ai-ujwal-20261012 -ImageTag COMMIT_SHA -Deploy
```

An existing database must be migrated with a protected export/import and verified
row counts. Preserve the intended account/JWT policy; changing the JWT secret or
session store invalidates existing sessions. Verify auth, chat streaming, Discover,
pharma, interpolation and downloads at the new origin before changing traffic.
Render should be retired only after verification and an approved data cutover.

## Historical deployment prerequisites (cancelled)

1. Billing owner reopens/creates a usable account and enables project billing.
2. Confirm baseline infrastructure capacity/budget; provision persistent services
   and scoped identities/secrets. No service-account key downloads are needed.
3. Execute reviewed build/migration/deployment, migrate existing account data and
   test the hosted endpoints. Record URLs and release/verification results here.

The portable Google Cloud CLI is installed outside the Git repository in the local
workspace; authentication lives in excluded local tooling state.
