# Analyst Workspace test report

**Follow-up, 11 October 2026:** the app now supports dark mode only at the user's request. Light-theme styles and switching code have been removed. Light-theme checks below describe the earlier version reviewed before that change.

Tested on **11 October 2026** using the running local application and an isolated Chromium browser profile. Test fixtures, simulated failures, and project resets affected the test profile only. The normal browser's saved forecasts and backend credentials were not changed.

## Result

The workspace's tested forecasting, import/export, evidence, snapshots, device storage, live feed, and responsive workflows pass after the fixes below. This is a local functional assessment. The full application still has production build and TypeScript issues outside the workspace, and its industry-news credentials are rejected by the provider.

## Issues fixed during this review

| Finding | Fix and verification |
| --- | --- |
| CSV import accepted values above the range allowed when restoring projects, so an accepted project could disappear on reload. | Use the same monthly-volume ceiling for CSV and saved-project validation. Regression tests verify the supported maximum survives serialization and larger values are rejected without changing the project. |
| Entering `1.4` for an event month could display `1.4` while calculating month `1`. | Normalize whole-month input before updating both its draft and stored value; expose an integer input step. Repeated edits show and calculate the same month. |
| A valid imported horizon such as 18 months did not exist in the preset selector and appeared blank. | Include the imported horizon among the available choices. The selected horizon and project survive reload. |
| A market event could be outside a shortened horizon without any explanation, while its input maximum excluded the saved value. | Keep the event's original timing, allow the supported 1–60 month range, and explicitly state when it does not affect the current horizon. Shortening a forecast does not move the event. |
| Truncated JSON or individual invalid saved projects could be replaced by a sample or a partial restoration, overwriting original data. | Preserve the original stored JSON and suspend autosaving over it. Valid restored projects remain usable in memory, new work can be exported, and original data can be downloaded for recovery. The recovery action is also visible on mobile. Manual repair of the preserved JSON may be needed before normal autosaving resumes. |
| Small secondary labels failed contrast checks in both themes; shared Spaces controls used white input text in light mode. | Adjust workspace-specific secondary text and light-theme status colors, and give light-theme input text a readable foreground. Keep the app's font, neutral palette, control geometry, and layout. |

## Verification

| Check | Outcome |
| --- | --- |
| Forecasting regression tests | **10 passed**: exact linear trend, chronological holdout, seasonal repetition, zero-demand WAPE, CSV structure and bounds, patient cohort conservation, capture saturation, zero population, full discontinuation, net-sales maths, event timing, and review validation. |
| Backend pharma and existing search-routing tests | **17 passed**: nested approval dates, drug-only trials, unsafe URLs, cache coalescing, partial failures, stale expiry, missing/rejected credentials, empty results, and query validation; existing routing checks also pass. |
| Deep browser workflow | **48 passed**, with no uncaught runtime errors. Independent reference calculations checked forecast volume, patient starts and persistence, and net sales. |
| Responsive browser checks | **60 passed** across all six tabs at 320, 360, 390, 600, 768, 820, 1024, 1280, 1440, and 1920 px, with no page-level horizontal overflow. |
| Automated accessibility scans | All six tabs scanned in both light and dark themes: **12 scans, no reported violations after fixes**. Chart contrast and pharma ARIA scans retain manual-review items; this is not a screen-reader or accessibility certification. |
| Live pharma integration | FDA approvals and ClinicalTrials.gov study updates loaded successfully. Therapy/date filters were verified against the rendered feed and the frontend proxy; source-type filtering, local search, pagination, evidence selection, stale results, empty responses, failed requests, and recovery were checked. |
| Production compilation | Webpack compilation succeeded, but the full build failed while prerendering the existing `/report` page. Type validation is skipped by the current build configuration, so compilation does not replace a type check. |
| Full TypeScript check | **Five errors** after generating production route types: the four existing service errors, plus the existing thread page's synchronous `params` type being incompatible with Next.js's promised route params. No errors were reported in the workspace changes. |

The deep walkthrough additionally covered invalid imports leaving the active project unchanged, synthetic-data labels, disabled actions before a baseline exists, evidence title/rationale requirements, unsafe evidence links, explicit evidence submission, snapshot immutability, the latest-20 snapshot retention policy with increasing review numbers, separate review-pack imports, selected-project persistence, evidence-draft isolation, quota failure and recovery, exports during storage failure, keyboard tabs, keyboard chart tooltips, sidebar collapse, mobile chart sizing, corrupted and partially invalid stored data, and the 20-project limit.

## Remaining findings

1. **Industry news:** the configured `GUARDIAN_API_KEY` receives HTTP 401. A valid provider-authorized key is needed. FDA and ClinicalTrials.gov remain usable independently.
2. **Production build:** `/report` uses `useSearchParams()` without the required Suspense boundary and fails static prerendering. This existing page was not changed as part of the workspace review.
3. **TypeScript:** `collectionService`, `spaceService`, and `userService` call a missing `api.put`; `discoverService` supplies unsupported `params` to `api.get`. Production-generated route types also expose the existing `/thread/[id]` page's synchronous `params` signature, which does not match Next.js's promised params.
4. **Build configuration:** Next.js 16 warns that the existing `eslint` configuration key is unsupported. The configuration also explicitly skips TypeScript validation during builds.
5. **Enterprise scope:** projects and review versions are still browser-local. These checks do not validate shared collaboration, authenticated approvals, company data entitlements, or specialist forecasting assumptions. Those require the shared storage and domain validation described in the existing enterprise review.

## Reproducing the checks

From `frontend`: `node --test tests/forecasting.cjs` and `node node_modules/typescript/bin/tsc --noEmit`.

From `backend`: `python -m unittest tests.test_pharma_updates tests.test_routing_policy`.

From the outer workspace, the browser checks are `.local-run/deep-workspace.py`, `.local-run/check-pharma.py`, and `.local-run/workspace-accessibility.py`. They require the local app on port 3000 and an isolated Chrome profile with remote debugging on port 9223. Run the browser scripts sequentially because they change the test page and its test data. The scripts use the backend environment's Python and `websockets`; accessibility checks use the frontend's installed `axe-core`.

Artifacts are in `.local-run/deep-workspace-results.json`, `.local-run/workspace-accessibility-results.json`, `.local-run/deep-workspace-dark.png`, `.local-run/deep-workspace-light.png`, and `.local-run/deep-workspace-mobile-chart.png`. Actual CSV and review-pack downloads are retained in the timestamped `deep-downloads-*` directories.
