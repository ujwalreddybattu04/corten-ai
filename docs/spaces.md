# Shared Spaces

A Space is a shared workspace for a topic or team. Questions asked in a Space are answered with the
Space's **instructions**, **files** and **trusted links**. Every member can read the Space's threads.
This follows the workflow of Perplexity's Spaces, which Perplexity now calls Projects.

## Workflow

1. **Create** a Space with **New Space**, or start from a template on the Spaces page or the Templates page. Templates include market access, competitive intelligence, regulatory watch and research. Set a name, an emoji icon, a description and optional instructions.
2. **Add context**:
   - **Instructions** (up to 8,000 characters): role, tone, format and focus applied to every answer. They cannot override grounding, citation or safety rules.
   - **Files**: PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx), HTML, Markdown, CSV, JSON and code or text files, up to 25 MB each. Text is extracted, indexed and cited as `Space file` sources ahead of web results.
   - **Links**: trusted sites. Each question runs one extra bounded search restricted to these domains, and those results are cited first.
   - **Sources**: "Search the web" can be switched off. Answers then use only the Space's files. When no file matches, the answer says so rather than guessing.

   On the Space page, instructions, files, links and sources sit in the right-hand column. The composer shows which sources answers will use.
3. **Ask** from the Space page. The composer offers the same answer modes and attachments as the main search. The thread is saved to the Space for all members and to the author's own history. The thread list shows the opening of each answer.
4. **Share** using either:
   - an invitation to a specific email address, which appears in the invitee's Spaces page after sign-in (valid 14 days, single use, bound to that email), or
   - an invitation link (valid 7 days, reusable, revocable).

   Owners change roles, transfer ownership, remove members and revoke invitations. Members can leave.

## Roles

| Role | Can do |
| --- | --- |
| Owner (exactly one) | Everything, including members, invitations, ownership transfer and deletion |
| Can edit | Ask questions, upload and remove files, edit instructions, links, details and answer sources |
| Can view | Read threads, files, links and instructions |

Non-members get `404`, so Space IDs never reveal that a Space exists. Only the owner sees member email addresses.
Only a thread's author can update it. A follow-up from anyone else starts that person's own copy. The author or the owner can remove a thread from the Space.

## Limits (configurable in `settings.py`)

| Limit | Default |
| --- | --- |
| Spaces owned per account | 100 |
| Members plus pending email invitations per Space | 50 |
| Files per Space / storage per Space / size per file | 100 / 500 MB / 25 MB |
| Links per Space | 100 |
| Saved thread size | 256 KB |

## Search behavior and known limits

- File retrieval uses PostgreSQL full-text search with the language-neutral `simple` configuration, plus prefix matching. Chinese, Japanese and Korean text is matched with bigrams. Matching is lexical, not semantic, so synonyms are not found. A pgvector embedding retriever can be added behind `space_service.retrieve` once an embedding provider is approved.
- Scanned or image-only PDFs have no extractable text and are rejected with an explanation. OCR is not included.
- Email invitations are **shown in the app**, not emailed. Outbound email still uses the SES sandbox (see [authentication](authentication.md)). Owners can copy the private invitation link from the share dialog.
- Membership changes appear for other members when they reload the page or return to its tab. There is no live push.

## Security

- Uploaded files are stored under server-generated UUID paths and are never rendered on the application origin. Downloads are forced attachments with `nosniff` and `Content-Security-Policy: sandbox`.
- Office files are read as ZIP/XML with a 200 MB decompression limit, and DTD/entity declarations are refused.
- Upload size is bounded at nginx, the Next.js proxy and the FastAPI middleware.
- Invitation tokens are 256-bit random values. Only their SHA-256 hashes are stored.
- Space instructions are labeled to the model as member-written preferences, not evidence.

## Operations

- Migration `0004_shared_spaces` adds the tables and copies every existing personal Space, and the threads saved in it, to its owner. It was verified on PostgreSQL, including invalid and deleted legacy records, downgrade and re-upgrade. The release gate (`verify-personal-storage.py`) now also checks shared-Space search.
- Files live on the retained host volume `/opt/corten/data/space-files`, mounted at `/app/space-files`. The daily backup mirrors them, encrypted, to `s3://<artifacts>/space-files/`.
  - **Before the first release with Spaces, apply the updated `deploy/aws/infrastructure.json`.** It grants the host role access to that prefix only.
- Spaces saved only in a browser under the earlier design are imported once when their owner opens Spaces. Spaces that had already reached cloud storage are never recreated from a stale device.
