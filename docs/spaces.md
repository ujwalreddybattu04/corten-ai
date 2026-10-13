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
   - Every answer knows the Space it was asked in: its name, purpose, file names, priority sites, web-search setting and instructions. All of it is labelled to the model as member-written context, never as evidence.
   - A question with nothing of its own to look up, such as "What's this about?" or "What is this Space for?", gets an overview of the Space when it opens a thread: what the Space is for, what it holds and three questions to ask next. Its files are summarized when it has any. In a follow-up, the same question explains the previous answer. Neither case searches the web for the phrase.
   - "What's new?" or "Any updates this week?" opening a thread searches news on the Space's topic.
   - An empty Space suggests first questions. Spaces created from a template suggest that template's own questions, served by the API with the Space (`agent.starters`).
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

## Space agents

Each Space with web search on is answered by an **agent**: a LangChain agent (`langchain.agents.create_agent`) that
plans the answer, calls tools one at a time, and writes a cited answer. The template decides the agent's tools; a
Space created without a template gets the general set. Code: `backend/src/services/agents/`.

| Template | Tools |
| --- | --- |
| None (custom Space) | Web search, Page reader, Space files, Calculator, Charts, Stock prices, Exchange rates, Economic data |
| Market Access & Pricing | Web search, Page reader, Space files, FDA approvals, Exchange rates, Calculator, Charts |
| Competitive Intelligence | Web search, Page reader, ClinicalTrials.gov, FDA approvals, Stock prices, Space files, Charts |
| Regulatory Watch | FDA approvals, Web search, Page reader, ClinicalTrials.gov, Space files |
| Research Assistant | PubMed, arXiv, Web search, Page reader, Space files |
| Data Analyst | Stock prices, Exchange rates, Economic data, Charts, Calculator, Web search, Space files |
| Patent Researcher | Web search, Page reader, PubMed, Space files |
| Study Guide · Tutor · Code Helper · Writing Coach | Space files, Web search, plus Calculator and Page reader where useful |
| Trip Planner | Weather, Exchange rates, Web search, Page reader, Calculator |

**Data sources.** All are free public APIs that need no key: Yahoo Finance daily closes (Stooq as a fallback for US
tickers), European Central Bank reference rates (Frankfurter), the IMF World Economic Outlook (with IMF projections,
marked as such) and the World Bank, ClinicalTrials.gov v2, PubMed E-utilities, arXiv and openFDA Drugs@FDA. Web search
and page reading use the configured Tavily key. Every call has a timeout, one retry for transient failures and a Redis
cache.

**How an answer is built.**
- The user sees each step live (for example "Fetching AAPL prices (6m)" → "251 trading days · last 340.97 USD"), sent
  as `agent_step` events and kept with the saved thread.
- Data tools return compact text with computed figures, so the model never estimates them: period change, high and
  low, where the latest value sits, averages and country rankings, and started versus planned trials. Charts are
  drawn server-side from the fetched series as a React/Recharts artifact. The model passes dataset ids and never
  retypes numbers or writes chart code. Series on different scales or in different currencies are rebased to 100.
- Sources are numbered across the whole answer, and the same URL keeps its number. Model citations written as
  `【1†source】` are rewritten to `[1]`.
- The prompt states today's date, the Space's details (template, tools, files, instructions) and working rules: use
  only tool figures; name no causes unless a source states them; no forecasts, trading signals or personal advice; be
  exact with counts and dates.

**Limits.** At most 6 model calls and 6 tool calls per answer, 35 s per tool, 150 s per answer and 3 charts. When the
budget is spent, the last call runs with tool calls switched off and must answer. Series fetched but not charted are
charted first. Repeated identical calls are answered from memory. If a model is out of quota before it starts writing,
the other model (each has its own per-minute provider quota) takes over. A short cooldown is waited out once. A
stream that breaks after it started writing is never retried or mixed.

**When the standard pipeline answers instead.** Files-only Spaces (web search off: their agent has no tools), questions
about the Space itself ("What's this about?"), greetings and questions about Corten, conversation recall, image
questions, and requests for a downloadable file. Setting `SPACE_AGENTS_ENABLED=false` sends every Space question to
the standard pipeline without a redeploy of the frontend.

**Known limits.** Prices are end-of-day closes, not live quotes. Yahoo Finance may refuse cloud addresses; the Stooq
fallback covers US tickers only. openFDA is updated weekly and can lag recent approvals, so answers never present it
as complete. Each Groq model allows 8,000 tokens per minute on the current plan. Several long agent answers in the
same minute can hit that limit; the user then sees the provider's retry time.

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
- Migration `0006_space_templates` adds `spaces.template` and recognizes existing template Spaces by their unchanged template instructions or the template's name. It is additive; downgrade drops the column. Templates are served by `GET /api/v1/spaces/templates`, and creating a Space with `{"template": "<id>"}` fills in its name, description, icon and instructions.
