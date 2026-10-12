# Full application component audit — 12 October 2026

This review covers the running application's pages, controls, account boundaries, calculation/export paths and deployment. It also inventories dormant components so their existence is not mistaken for a working feature. Tests establish the behaviors below at review time; they do not establish unlimited provider availability or production capacity.

The existing Plus Jakarta Sans font and dark design are preserved. Public signup with personal accounts remains the policy; the latest instruction requires sign-in for every app tool. Password recovery is implemented with an encrypted outbox and branded email. Public delivery still requires SES setup/approval. See [authentication](authentication.md).

## Page and control checklist

| Area | Reviewed behavior and repairs | Evidence |
| --- | --- | --- |
| Application shell | Sidebar links, desktop collapse/expand, mobile open/close, New Thread, account entry, Settings, history toggle and search shortcut. Mobile close now has an accessible name. | Browser controls and real auth checks. |
| Home / Search input | All eight focus modes, the six quick-action menus, empty input, report action and long international questions. Submitted prompts travel in owner-scoped temporary tab storage; saved chats open by ID. Full Chinese input survives navigation and reload. | New browser control audit and question-draft regressions. |
| Privacy | New private messages do not enter history; a draft's private flag survives a later toggle change. Spaces/preferences continue to sync independently. Blocked privacy storage fails closed. The notice describes provider processing accurately. | Browser private-chat check, draft/cloud regressions. |
| History dialog | Search, preview, select/open, rename, pin, deletion confirmation and cancellation. Escape cancels renaming without saving or closing the parent dialog. Deletion uses the latest stored list. Keyboard focus stays in the active dialog. | Browser control and storage checks. |
| Answer rendering | Markdown, numerical values, lists, bibliography headings, source links, code blocks and final paragraphs remain intact. Malformed percent encoding no longer crashes source links. | Nine repaired-control browser checks. |
| Chat lifecycle | Startup/readiness checks, exactly one generation submission, bounded recovery from 502, manual Retry, failed/partial streams and persistence only after success. Follow-up context and direct conversation recall are verified. | Nine startup browser cases, conversation tests and actual hosted SSE. |
| Chat actions | Follow-up, query editing, regeneration, helpful/unhelpful feedback, answer copying, research progress, related questions, source panel, Links and Images. Feedback is personal preference data. Images support empty-to-populated updates and the lightbox. | Component browser cases and frontend regressions. |
| Thread menu | Bookmark, add to Space, rename, delete, Markdown export, Word export and print/save PDF. Word is correctly labeled `.doc`, and embedded answer HTML is escaped. Confirmation dialogs support Escape/focus restoration. | Browser export payload and dialog checks. |
| Share | Shares the question; no private conversation ID, Space ID or saved answer is published. Overlong URLs are replaced by full question text with external link buttons disabled. Clipboard failures leave a manually selectable value. | Short/long share browser checks. |
| JavaScript runner | Opaque worker, actual output, Stop, timeout, bounded output, close and retry. Infinite JavaScript is stopped without freezing the page. | Actual browser runtime checks. |
| Python runner | Actual Pyodide cold initialization and calculation; bounded initialization errors and cancellation; worker recreation is deferred until the next run. Closing stops active work. | Actual browser Python check and worker lifecycle review. |
| Remote code runner | Current compiler discovery, unavailable-language errors, bounded input/output, timeout and explicit external-run action. The application no longer advertises missing Kotlin/TypeScript compilers. | Execute route regressions and current official compiler catalogue. |
| HTML preview | Opaque sandbox, validated console messages, preview controls and downloadable HTML. Application-origin executable blob tabs have been removed. | Real iframe and download-control check. |
| Discover feed | All seven tabs, interests, like/bookmark/dislike, article menus, source attribution, pagination, saved-feed recovery, stale notices, retry and cancellation. | Seven real API feeds and nine live browser cases; 12 isolated outage cases. |
| Discover widgets | Real four-index market data, five stock quotes and precise-coordinate weather returned successfully. Sidebar requests now cancel superseded loads, have a deadline and preserve loaded values with a retry notice after failure. Unsupported geolocation falls back safely. Weather errors no longer log credentials or location. | Real hosted sidebar API plus browser fault checks. |
| Article page | Article loading, original publisher link, attributed sources, complete medium summary, related articles, bookmark/share and follow-up. Save to Space stores the original publisher URL. Follow-up uses temporary prompt storage. | Actual summary stream plus article-to-Space browser check. |
| Signup / Login | Required-field and password validation, incorrect/duplicate credentials, safe redirects, HttpOnly/Secure cookies, remember-me, two tabs, refresh and logout recovery. Forged cached profiles do not authenticate. | 15 real hosted authentication browser checks and backend auth suite. |
| Settings | Server-verified profile, display-name edit, reload, sign out and cloud status/retry. Storage failures no longer turn a verified session into a misleading guest view. | Real auth flow and isolated profile editor browser check. |
| Spaces | Create/edit name/description/icon/color, search, templates, personal ownership, delete/cancel, thread association, references and notes. Create/edit/delete dialogs support keyboard focus and Escape. URLs are validated and bounded; duplicate references are avoided. | 17 broader browser cases and actual owner-scoped REST CRUD. |
| Space detail | Name/description editing, notes, links, chat list, new question and missing/foreign Space handling. Saved chat links use IDs. New-question failures remain visible with the input preserved. Notes are labeled as notes rather than automatic model instructions. | Browser Spaces workflow and account isolation. |
| Research reports | Topic entry, streamed outline/sections, complete/error/retry/cancel states, preview and authenticated PDF download. Missing terminal stream records cannot publish an incomplete report. | Report browser cases and actual generated PDF. |
| Monthly interpolation | Upload replacement/cancel, Average/Exit, unchanged adoption CSV, first month, exact unrounded yearly constraints, absolute values, single-year fallback, unreliable input rejection, animated graph, keyboard/table controls and CSV/JSON/PDF. | 18 real calculation/export browser checks and numerical tests. |
| Pharma intelligence | Therapy/date/search/source filters, source widgets, illustrated identifiers/publisher thumbnails, card/list view, highlights, sample charts, details, pagination, refresh/retry, stale/partial data and CSV. FDA and ClinicalTrials.gov provide actual dated records. | 14 isolated cases, seven live cases and five live design checks. |
| Error / legacy routes | Friendly page error with retry, unknown-page recovery, `/library` redirect to Spaces and old `/thread/[id]` redirect to Search. Internal exceptions are not shown by the active error page. | Build routes, redirect checks and source review. |

## Actual account and cross-device proof

Two temporary accounts and two independent browser profiles were used against AWS. No browser history was pre-seeded for the restoration check.

- A fresh profile restored a server-saved conversation and its complete answer.
- Two separately logged-in devices kept both competing edits, with the offline version saved as a conflict copy after reconnection.
- A stale write could not overwrite the newer version.
- Remote deletion removed the other device's cached conversation.
- Account switching hid the previous account's work; guests could not read personal records.
- Spaces and collections passed real create/read/edit/delete, stale-revision rejection, input rejection and account isolation.
- One actual generated report downloaded for its owner; another account and a guest received 404.
- No client exceptions occurred in those real account flows. Synthetic audit accounts are tracked by exact IDs for cleanup.

## Component source inventory

All **58 component source files** were inspected for how they connect to the current routes. Some page-specific controls are implemented inline and are covered in the checklist above.

The current mounted component groups are:

| Folder | Components used by the current application |
| --- | --- |
| `analyst` | `WorkspaceTools`, `YearlyMonthlyWorkspace`, `CurveChart`, `PharmaWorkspace` |
| `common` | `Favicon`, `PrivateToggle`, `PrivateNotice`, `StarField` |
| `layout` | `AppFrame`, `Sidebar`, `HistoryModal`, `CloudSyncStatus` |
| `search` | `HomeHero`, `SearchBar`, `QuickActions` |
| `spaces` | `SaveArticleModal` |
| `thread` | `AnswerStream`, `AnswerSkeleton`, `ImagesGrid`, `ResearchProgress`, `ThreadMenu`, `ShareModal`, `CodeRunnerModal`, `HtmlPreviewModal` |

The following **34 files are dormant reusable components or old scaffolding**, not active product controls. Their exported presence is not reported as an end-to-end pass:

- `common`: `Avatar`, `ErrorBoundary`, `LoadingSpinner`.
- `discover`: `CategoryFilter`, `TrendingCard`.
- `layout`: `Header`, `Footer`.
- `library`: `CollectionCard`, `ThreadCard`.
- `search`: `FocusMode`, `ImageGrid`, `RelatedQuestions`, `ResultCard`, `SearchSuggestions`.
- `spaces`: `FileUpload`, `MemberList`, `SpaceCard`, `SpaceHeader`.
- `thread`: `CitationBadge`, `CopyButton`, `FollowUpInput`, `MessageBubble`, `ModelSelector`, `RelatedQuestions`, `ShareButton`, `SourcesPanel`, `SourceCard`.
- `ui`: `Badge`, `Button`, `Dropdown`, `Input`, `Modal`, `Skeleton`, `Tooltip`.

Active hooks are `useSearch`, `useReport`, `usePyodideWorker` and `useModalFocus`, plus the verified authentication context. `useThread`/`useSpaces` scaffolding, the old streaming/focus/suggestion hooks and inactive provider/service adapters are not used to power the current pages. File retrieval/RAG, member collaboration, arbitrary model selection and autocomplete are not presented as completed features. The registered suggestion endpoint still returns an empty list; the active home menus use their own prompts.

## Verification and deployment gates

- Backend: **174 tests plus 197 subtests passed**.
- Frontend: **100 tests passed**, TypeScript and production build passed. Lint has no errors; migration/maintenance warnings remain.
- Added control audit: **20 browser checks**, including all eight focus modes, six quick menus, Chinese prompts, privacy, history, export contents, dialogs and mobile navigation.
- Five additional widget fault checks passed: missing Permissions API, superseded request cancellation, late-response rejection, retained values on refresh failure and retry recovery. The 17 broader browser cases, 12 Discover outage cases and nine chat startup cases passed again after the final navigation changes.
- Actual JavaScript/Python checks, hosted authentication, interpolation and pharma suites remain part of the release verification.
- Release verification now mounts and explicitly runs the isolated PostgreSQL check, then requires all six proof flags. A command that exits without executing that check cannot satisfy the gate. The six flags were independently verified against the current AWS image before this repair.
- Public source is scanned for credentials before publishing. API keys and audit/browser artifacts remain outside the public repository.

See [hosted verification](hosted-verification.md) for the published release and final AWS readback.

## Remaining external dependencies and scale work

| Dependency | Current state |
| --- | --- |
| Account emails | Password recovery and its encrypted email worker are implemented. Gmail is verified in SES; public delivery still requires sender setup/production approval. Signup email verification is not implemented. |
| Optional industry news | Guardian API access is currently rejected. This tile reports provider denial; FDA/trial records continue working. A working, appropriately licensed news credential/provider is required to populate it. [Guardian RSS guidance](https://www.theguardian.com/help/feeds) specifies personal, non-commercial use, so it was not substituted for the company workspace. |
| Large-scale operation | The present AWS Free-plan deployment is a single-host preview. Highly available infrastructure, load/capacity testing, operational alerts and adequate provider quotas remain production rollout work. |
| Retention | Personal history/Spaces are persisted in PostgreSQL with backup/restore proof. Analyst uploads are session-only; PDFs have 24-hour access gates and retained EBS storage, without off-host artifact recovery yet. |

These dependencies are distinct from a UI control failing. They remain visible rather than being hidden behind sample values or successful-looking empty responses.
