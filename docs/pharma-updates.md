# Pharma intelligence in Analyst Workspace

The **Pharma intelligence** tab at `/analyst-workspace` reads real public records.
Monthly interpolation remains the default; switching tools preserves the uploaded
CSV and calculation. The feed does not change forecasts or call an LLM.

## Sources

| Source | Records / date | Coverage | Configuration |
| --- | --- | --- | --- |
| [openFDA Drugs@FDA](https://open.fda.gov/apis/drug/drugsfda/) | Original/supplemental approved submissions; FDA action date, brands, sponsor, active ingredients | US, all therapies; weekday dataset updates | Anonymous access supported; optional server-only `OPENFDA_API_KEY` |
| [ClinicalTrials.gov API v2](https://clinicaltrials.gov/data-api/api) | Updated interventional drug/biologic studies; record update date, sponsor, phase, status, conditions, interventions | Global registry; an update is not necessarily a new trial, clinical result or approval | No key required |
| [Guardian Open Platform](https://open-platform.theguardian.com/documentation/) | Optional pharma/biotech reporting; publication date | General industry reporting | Authorized server-only `GUARDIAN_API_KEY`; missing/rejected access is labeled |

## Analyst controls and data meaning

- Six therapy filters: all, oncology, rare disease, immunology, neuroscience,
  cardiovascular/metabolic. Therapy filters apply to trials/news; FDA covers all
  therapies. This distinction appears in the screen and CSV.
- 7/30/90 UTC calendar-day windows including today. Up to 20 recent records per
  source, FDA examining up to 50 application records and filtering each nested
  approved submission. Counts describe loaded records, not market/trial totals.
- Search loaded records by drug, sponsor, condition, identifier or intervention;
  filter record type; paginate by ten; expand details; open original sources.
- CSV exports all matching loaded records with source check times/status, coverage,
  identifiers, dates and trial metadata. UTF-8 BOM supports Excel; source-controlled
  text with spreadsheet formula prefixes is neutralized.
- Existing Corten font, dark colors and Lucide icons, keyboard tool tabs,
  explicit labels/statuses, responsive layouts and reduced-motion support.
- The research desk adds source summary widgets, the latest dated FDA/study
  highlights, a stacked UTC date histogram and exclusive study-phase groups.
  All counts derive from the capped loaded records; they are not market totals
  or evidence of efficacy. Combined phases stay in one group.
- Card/list layouts retain filters and ordering. Highlight actions open the
  corresponding source-filtered record details. Full record titles remain readable;
  highlight previews offer the full title on hover and in the opened record.
- FDA/study thumbnails are labeled illustrated record previews using real
  application/study IDs. They do not pretend to be drug photographs. News uses
  optional publisher-provided HTTPS thumbnails from `i.guim.co.uk`, loaded lazily
  without a referrer; missing/failed images fall back to the labeled preview.
  Unsafe or malformed optional image values never suppress valid news records.

The recent feed is not an exhaustive regulatory archive. No generated events or
dummy metrics are substituted. Analysts should review the original evidence.

## Freshness and failures

Opening the pharma tool or changing therapy/window loads its records. While visible,
the browser checks overdue snapshots at a randomized minute interval and when the
page becomes visible/reconnects. Successful source snapshots are shared for one
hour. **Check updates** reads the shared snapshot, without bypassing the cache for
every user. GET retries obey Retry-After within a 90-second deadline; leaving the
tool or changing filters cancels obsolete browser requests.

Source checks have separate timestamps/statuses. Partial failures retain source
records at most 24 hours as **Previous results · refresh failed**, preserving the
original check time. Browser connection failures also label retained data stale.
Expired records are removed. Valid empty responses are distinct from outages;
complete failure with no usable data returns 503 / Retry-After and a visible retry.

## Capacity foundation

`GET /api/v1/pharma/updates?topic=all&days=7` validates bounded filters before
provider calls. It contains exclusively public records and a 60-second public
cache lifetime; the existing frontend proxy remains `no-store` for authenticated
requests. Keys/secrets never enter responses or the public repository.

Redis retains normalized source snapshots up to 24 hours, with one-hour freshness.
Token-owned 20-second refresh leases coalesce work across backend instances and
release with compare-and-delete. Warm peers receive labeled previous results;
cold peers wait for the owner without duplicating provider work. Browser cancellation
does not cancel shared refreshes. Redis failure degrades to bounded process caching.

Cache cardinality is fixed: three FDA windows shared across therapies, eighteen
trial combinations and eighteen news combinations. There are four upstream slots
per process, bounded wall time and a 2 MB decompressed response limit. Source error
cooldowns are shared across filters/workers: normally five minutes, rejected access
one hour; rate-limit responses honor Retry-After within that policy. Cache keys
include only a credential fingerprint.

This foundation is **not a million-user capacity certification**. Always-on compute,
database/cache capacity, CDN configuration, monitoring, abuse limits and load tests
remain necessary. At greater scale, use scheduled ingestion and a durable public
record store. This release does not provision scheduled/background ingestion,
email/push delivery or paid infrastructure. [Provider quotas still apply](https://open.fda.gov/apis/authentication/).

## Verification

Backend tests cover nested action dates, drug-only trials, unsafe links, partial/
complete failures, 24-hour expiry, rejected access, oversized/malformed payloads,
cooldowns, query validation, cancellation, 100 concurrent readers and shared-cache
reuse across workers. Frontend tests cover response consistency, loaded-record
search, Unicode/formula-safe CSV, retention, GET retries and cancellation.

Run `python -m pytest tests -q` in `backend`, then `npm test`, `npm run lint` and
`npm run build` in `frontend`. Browser/live checks are recorded in the completion
review when verified; historical checks of the removed dashboard do not validate
this screen.
