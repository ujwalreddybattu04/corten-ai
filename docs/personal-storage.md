# Personal account storage

Signed-in history, Spaces, pins, answer feedback and Discover preferences synchronize to PostgreSQL. Guests keep browser data. Private-mode conversation content is not uploaded. Analyst CSVs and calculation results remain session work: keep exported CSV, JSON and PDF files.

The browser is a local cache. Settings and Spaces display whether work is saved, pending, offline or conflicted. Offline writes remain queued in account-scoped storage. Changing accounts aborts the previous worker and hides its views. Guest records are never silently imported into an account.

`GET /api/v1/personal/changes` returns account-owned changes with bounded pagination. `POST /api/v1/personal/records` accepts up to 16 distinct compare-and-set mutations. The backend derives ownership from the authenticated session; supplied owner fields are rejected. Per-account PostgreSQL advisory locks serialize revision allocation and quota checks across workers. Writes commit before acknowledging success. Identical retries are idempotent; deletions retain tombstones. A conflicting thread or Space edit is preserved as a separate copy rather than overwriting another device's work.

Storage is bounded to 256 KB per record, 500 active records and 10 MB per account. A maximum of 5,000 rows including deletion tombstones bounds incremental history. Storage failures retain local work and display a retry message. Export important material before clearing browser data when synchronization is unavailable.

Spaces are now shared server records with members, files and threads; see [Spaces](spaces.md). Migration `0004` copied each personal Space into them, and the browser no longer synchronizes Spaces as personal records. Collections also expose owner-scoped CRUD APIs. Updates and deletes require an expected revision, so a stale client cannot silently overwrite newer changes. Collections have no Library navigation; the legacy Library URL redirects to Spaces. Sharing offers a question link that generates a new answer for its recipient; it does not publish personal answers or Space content.

Migration `0002` adds storage tables and does not change existing users, sessions or conversations. The AWS release job verifies migration from `0001`, preservation of a synthetic existing user, concurrent revision allocation, conflicting edits, deletion protection and owner separation in a temporary PostgreSQL database before changing the application's database. The temporary database is deleted after verification. PostgreSQL backups include these tables.

This is personal synchronization, not team collaboration. Large shared datasets, analyst-project retention and organization roles require their own requirements and capacity plan.
