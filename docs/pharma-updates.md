# Pharma updates in Analyst Workspace

The **Pharma updates** tab uses live public records, separately from the forecast's sample data. Nothing in this feed automatically changes a forecast. **Use as evidence** selects the title and source URL in the evidence form; an analyst must explain the supported assumption and submit it.

## Sources and coverage

| Source | Records | Coverage and dates | Configuration |
| --- | --- | --- | --- |
| [openFDA Drugs@FDA](https://open.fda.gov/apis/drug/drugsfda/) | Original and supplemental approval actions | US; all therapy areas. Dates refer to individual approved submissions, not the entire application's history. Source dataset updates on weekdays. | Anonymous access works; `OPENFDA_API_KEY` is optional for higher quotas. |
| [ClinicalTrials.gov API v2](https://clinicaltrials.gov/data-api/api) | Recently updated interventional drug and biologic study records | Global registry coverage; record update date. An update is not necessarily a new trial, clinical result, or regulatory milestone. | No key required. |
| [Guardian Open Platform](https://open-platform.theguardian.com/documentation/) | Pharma and biotechnology articles | Publication date; general industry reporting rather than a comprehensive specialist intelligence service. | Existing server-side `GUARDIAN_API_KEY`; provider must accept the key and its access entitlement. |

The local live check on 9 October 2026 returned FDA approval records and clinical trial updates. The configured Guardian key returned HTTP 401; the UI displays **Provider access denied**. A valid authorized news key is required to enable that source. No credentials appear in frontend responses.

## Filters and freshness

- Windows: 7, 30, or 90 UTC calendar days, including today. Therapy areas filter trials and news; FDA coverage remains all therapy areas and this is stated in the UI.
- Type and text search filter the loaded results locally. The search does not query the full upstream databases.
- Results are limited to 20 items per source. FDA examines up to 50 returned application records and filters each nested submission. This is a recent research feed, not an exhaustive archive or certified regulatory monitoring service.
- The browser checks when the tab opens, when filters change, and hourly while the tab is visible, including overdue checks when focus returns. Manual checks use the same server cache, which lasts up to one hour. Source and feed check timestamps remain visible.
- No scheduled ingestion, background processing when the workspace is closed, or email/push delivery has been added. Providers publish according to their own schedules, so a calendar day may contain no new records.
- Provider requests run concurrently with timeouts. Each source can fail independently. Previously successful results can be retained for at most 24 hours with a **Previous results · refresh failed** label. Otherwise the source shows unavailable, access denied, or key needed; fabricated entries are never substituted.

## Implementation and checks

`GET /api/v1/pharma/updates?topic=all&days=7` uses validated, bounded parameters. A memory cache avoids requiring Redis locally, and concurrent calls for the same filters share one fetch. Secrets stay on the backend. HTTPX request logging is suppressed because provider URLs can carry credentials.

The frontend's existing API proxy now preserves GET query parameters and avoids response caching. The tab uses the existing app font, fields, buttons, neutral colors, and responsive layout. Selecting an update does not mark it as reviewed or insert an unsupported assumption.

Backend unit tests: `python -m unittest tests.test_pharma_updates`. They cover nested submission dates, drug-only trials, safe news links, concurrent caching, partial failures, stale expiry, rejected and missing credentials, empty FDA responses, and query validation.

Validation completed locally: 9 pharma service tests, 8 existing search-routing tests, and 6 forecasting tests passed. Browser checks passed for all 6 workspace tabs at 10 widths (320–1920 px), real 7/30-day and oncology filters through the proxy, evidence selection and explicit submission, and simulated stale, empty, connection failure, and retry states. No browser runtime exceptions were observed. The project-wide TypeScript check still reports the 4 existing service errors involving `api.put` and unsupported Discover `params`; none are in the new workspace integration.
