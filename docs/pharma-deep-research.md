# Pharma Deep research

Open **Analyst Workspace → Pharma intelligence → Deep research**, or use the **Deep research** control beside the standard Pharma question box.

1. Enter a named medicine, company or study and the question to investigate.
2. Prepare the plan. Review the detected question type, subjects, condition, trial phase, source checklist and maximum rounds.
3. Select **Start research**. Source lookups, document reading, gap checks, writing and verification show actual activity. Leaving the page does not cancel the server-side job.
4. Open the report from **Research history**. Inspect coverage, exact passages, source dates and read methods, then download Word, PDF or the Excel evidence workbook.

The six checklists cover drug profiles, head-to-head comparisons, competitive landscapes, generic entry, safety and company pipelines. Source categories are independently editable. Registry filters use interventions or sponsors appropriately; direct comparisons search both interventions in the same study. MDS population terms are broadened to the registry's disease name rather than excluding pivotal studies.

## Evidence and verification

Read-only tools query ClinicalTrials.gov, FDA application records, submitted labels, Orange Book listings, drug recalls, scientific publications and restricted official domains for EMA, company announcements and SEC filings. A search result is an indexed excerpt until its source is actually opened. An abstract page remains labeled as an abstract, and document read limits remain explicit.

Document retrieval permits only HTTPS on approved public-source hosts. Redirect destinations and resolved IP addresses are checked. Downloads, parsing time, PDF pages and extracted text are bounded; PDFs are parsed in a separate process with resource limits. Scripts and navigation text are omitted from HTML. Source documents never provide executable instructions or new tools.

The evidence ledger preserves exact normalized passages or parsed API field values, references, source/date meanings, retrieval timestamps and document digests. Generated findings must cite ledger IDs. Each claim is checked against its own quotations for dates, numbers and identifiers; typed trial checks preserve actual/estimated qualifiers. A separate model reviews whether the quotes support the claim. A failed finding gets one repair attempt and another review. Remaining unsupported findings are withheld under **Not verified**, not presented as analyst conclusions. These checks reduce known failures; they are not a guarantee of scientific correctness.

Trial, primary-outcome, FDA-action, patent, recall and timeline tables are assembled directly from retrieved fields. Source samples, publication dates, approvals, tentative approvals, patent expiry and trial milestones retain their distinct meanings. The report does not establish prescribing advice or generic launch dates.

## Persistence, privacy and operating limits

Migration `0008` adds `pharma_deep_research` with an account foreign key and queue indexes. Every plan, report, cancellation and download is scoped to its authenticated owner. Plans require an explicit start. Starts are idempotent, one run per account can be active, and database leases limit execution to two jobs per deployment. A worker heartbeats its lease, checkpoints metered allowances and verified results, and recovers expired leases without resetting its allowance. A stopped run retains collected evidence. A failed run may resume once within its original time/usage window.

The initial limits are three rounds, 30 source lookups, 12 documents and 12 background model calls per report, with a 12-minute work budget. Planning can require one additional model call. The existing shared US$25 monthly Pharma model budget remains enforced by the host gateway. There is no new paid infrastructure or unbounded autonomous execution. Per-account daily report and queue limits are configurable. Exhaustion or unavailable sources result in explicit coverage gaps or a source-only partial report.

Reports are private account records. Private chat mode requires an explicit saved-research choice before a plan is created; other private chats remain private. Starting an existing saved plan is an explicit account-history action. Account deletion cascades to these records. Generated exports are served through authenticated routes with no-store headers; source strings are never executed as Excel formulas.

Enable only after applying the additive migration and verifying the background worker:

```text
PHARMA_INTELLIGENCE_ENABLED=true
PHARMA_DEEP_RESEARCH_ENABLED=true
```

Rollback can disable the feature and restore the prior application images without dropping the additive table or deleting saved reports.

## Validation

`tests/test_pharma_deep.py` covers approved plans and source boundaries, direct comparisons, exact quote/date/number checks, unsupported assertions, document redirects and size limits, partial-budget delivery, recovery, one bounded repair, genuine export formats and spreadsheet formula injection.

`tests/pharma_deep_postgres_check.py` runs only in a disposable `corten_deep_check_<12 hex digits>` database after migrations. It checks cross-account reads/downloads, idempotent starts, competing starts, execution leases, stale-worker rejection, recovery, cancellation, retry metering, authentication, private mode and request body bounds. It must never run against the application database.
