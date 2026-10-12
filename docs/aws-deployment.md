# AWS deployment

Deployed and verified on **12 October 2026** in the **Moonshot Mode** project, Sydney (ap-southeast-2).

**Application: https://d3a7ful0miola1.cloudfront.net**

The complete application runs on AWS: Next.js frontend, Python backend, PostgreSQL, Redis and HTTPS gateway. **AWS is now the only active hosting provider.** On 12 October 2026, the user requested retirement of the other hosting: all four Corten Render resources were deleted and their absence verified; the undeployed dedicated GCP project was marked DELETE_REQUESTED. There were no Render Blueprints that could recreate the resources automatically. AWS remained healthy after retirement.

Database records were copied once before retirement, with verified backups retained on AWS. Browser-only history and Spaces belong to their original domain and do not automatically move to the new site.

## Architecture and capacity

CloudFront HTTPS → private VPC origin → Nginx → Next.js → FastAPI → PostgreSQL/Redis and hosted AI/research APIs.

One always-running t3.small Linux instance hosts the containers on an encrypted, retained 40 GB gp3 disk. Standard CPU credits avoid unlimited-credit surplus charges; 4 GB swap supports production builds on its 2 GB RAM. Docker restart policies restart services after reboot. Host-mounted state survives container redeployment.

This is a **Free-plan preview**, not an architecture validated for millions of users. One instance is a single point of failure; burstable CPU, provider quotas and finite credits limit capacity. Company production needs load testing, multiple application instances, highly available database/cache, stronger abuse controls and operational alerting. AWS removes Render's idle-service start behavior; it cannot guarantee the absence of every gateway/upstream failure.

## Network, credentials and caching

- CloudFront redirects HTTP to HTTPS, supplies HSTS/CSP/nosniff headers and uses an AWS-managed certificate. No custom domain was configured.
- The origin has **no public inbound access**. Port 80 accepts only the AWS-managed CloudFront VPC-origin security group. This private hop uses HTTP. SSH, database/cache and application container ports are not publicly exposed.
- Systems Manager provides administration. IMDSv2 is required; its hop limit prevents app containers from obtaining host credentials. The host role scopes storage and secret access to this deployment.
- Provider settings went directly from Render into Secrets Manager's corten-ai/runtime after explicit authorization. Database/cache/JWT credentials are distinct from Render. No local provider-key export was retained or committed.
- Runtime environment files use mode 0600 inside a private mode-0700 directory. Backend/frontend run as non-root users with read-only root filesystems, temporary writable mounts, dropped capabilities and no-new-privileges.
- APP_ORIGIN explicitly names the public HTTPS URL so secure cookies and same-origin mutation checks work behind the private HTTP gateway.
- Dynamic pages/APIs use disabled edge caching and forward session cookies/query strings. Only /_next/static/* uses immutable caching. Nginx does not buffer streamed responses.
- Nginx limits API traffic to 120 requests/minute per IP, with a 20-request burst. This supplements existing limits; it is not a complete public AI abuse-control system.
- Private encrypted CloudTrail and CloudFront access logs are enabled. Nginx omits query strings, cookies and bodies; edge logs exclude cookie fields. Edge URLs can still contain query strings, so access/retention must remain restricted.

## Migration and recovery evidence

The initial copy used pg_dump and transactional pg_restore, with Render TLS certificate/hostname verification. **All 12 public tables had matching row counts**, including the original account. Render remained intact. Exactly two newly created synthetic AWS authentication accounts were removed using exact IDs/emails; the imported account was preserved.

Migration temporarily allowed only the AWS host's /32 on Render and only Render's three resolved /32 addresses on AWS outbound port 5432. Both exceptions were removed; Render's allowlist returned to its original empty state. The migration secret was scheduled for deletion with seven-day recovery, and source connection files/dump were removed.

The daily backup timer runs at **07:30 IST**, with up to five minutes of jitter and a catch-up after downtime. Encrypted PostgreSQL dumps go to the private S3 deployment bucket. Local dumps are kept at least three days before daily cleanup; S3 lifecycle retention is 14 days. Verification downloaded the actual S3 object, compared its SHA-256 with the local dump, restored into a new temporary database and compared table counts. Only the temporary database was then removed. Production remained untouched.

Backups cover **PostgreSQL**. Redis AOF/session state and generated PDFs persist on the host disk but are not in the SQL backup. Disk loss would require signing in again and regenerating reports. PDFs retain the application's 24-hour download window and still lack owner-scoped object-store access.

## Verified user flows

- Public HTTPS pages and PostgreSQL/Redis readiness.
- **15 real authentication browser checks**: signup/login, Secure/HttpOnly cookies, refresh, coordinated two-tab refresh, logout, account isolation and interrupted logout recovery; no client exceptions.
- **18 real interpolation browser checks**: Average/Exit constraints, unchanged adoption CSV, first-year behavior, Unicode Excel/PDF labels, absolute values, CSV/JSON/PDF downloads, races/errors and 320–1440 px layouts.
- **Seven live pharma browser checks** using FDA and ClinicalTrials.gov records, filters, details, freshness, responsive layout and reduced motion.
- All **seven Discover API categories and browser tabs** displayed real articles without mobile overflow or client exceptions.
- Real identity, writing and research SSE responses completed. Research returned ten sources; identity did not search. Four exact-recall/long-note/untrusted-role cases completed without model/web calls.
- A real sourced report produced **four sections and a five-page PDF** in the durable report mount, downloaded successfully and rechecked after backend restart.
- Static assets hit CloudFront's cache; dynamic SSE responses did not. Redirects, security headers and secure sessions were checked at the public URL.

Provider output/availability can vary. These verify functionality, not sustained load. Remaining product work appears in [the completion review](project-completion-review.md).

## Operations and repeatable releases

Infrastructure is defined in [infrastructure.json](../deploy/aws/infrastructure.json) and [edge.json](../deploy/aws/edge.json), validated with cfn-lint, cfn-guard and AWS template validation. Stack names: corten-ai and corten-ai-edge. The CloudFront VPC origin was created separately from the instance ARN and supplied to the edge stack; it is not stack-owned.

Access the host using Systems Manager in Sydney; do not open SSH/database ports. Useful host commands:

    cd /opt/corten/current
    docker compose -f deploy/aws/compose.yaml ps
    curl --fail http://127.0.0.1/api/v1/search/status
    systemctl list-timers corten-backup.timer
    systemctl status corten-backup.service
    journalctl -u corten-backup.service --since yesterday
    python3 deploy/aws/verify-backup.py

Restore verification compares the backup with current data. Run during a quiet window: concurrent writes can legitimately change counts. Never overwrite production to make verification pass.

For releases, package only public source with readable directories; exclude secrets/generated files, normalize shell files to LF, upload to a private releases/ key and retain SHA-256. Invoke [release.sh](../deploy/aws/release.sh) on the host with bucket, key and digest. It validates the archive, serializes releases, prepares private settings, builds images, backs up PostgreSQL, runs advisory-lock migrations, then waits for healthy containers. It does not repeat the initial Render copy or downgrade schemas automatically. Keep prior sources and inspect migration compatibility before rollback.

Never print full Docker Compose configuration, runtime environments or secret responses. The script uses config --quiet.

## Free-plan costs and expiration

At deployment, AWS reported **FREE / ACTIVE**, **USD 100** credits, expiring **12 April 2027, 09:55 IST**. No Paid Plan/advanced features were activated. Recheck remaining credits in AWS Settings; this balance is time-specific.

The actual AWS Price List response was **USD 0.0264/hour**, calculated as **USD 19.27 per 730 hours** for this instance. EBS, secrets, storage, requests, logging and network use add costs. Credits cover eligible usage until exhausted/expired. AWS's retained disk/buckets remain active; Render and GCP hosting were retired at the user's request. Review usage and keep independent exports before credits expire.

References: [EC2 pricing](https://aws.amazon.com/ec2/pricing/on-demand/), [AWS Agent Toolkit setup](https://raw.githubusercontent.com/aws/agent-toolkit-for-aws/refs/heads/main/setup-instructions/setup.md), [connect an AI coding tool](https://docs.aws.amazon.com/accounts/latest/reference/connect-ai-coding-tool.html).
