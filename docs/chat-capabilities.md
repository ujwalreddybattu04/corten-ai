# Chat capabilities

Corten's chat now covers the core capabilities of leading AI assistants, all served by the configured Groq account.

## Answer modes

Use the mode menu in the search bar and the follow-up box.

| Mode | Model | Use |
| --- | --- | --- |
| Auto (default) | Chosen per question | Fast for simple questions; Pro for complex research, long documents, artifacts and files |
| Fast | `openai/gpt-oss-20b` | Everyday questions |
| Pro | `openai/gpt-oss-120b` | Analysis, writing, long documents |
| Extended thinking | `openai/gpt-oss-120b`, high reasoning | Hard problems; the reasoning is shown in a collapsible "Thought process" panel |
| Vision (automatic) | `qwen/qwen3.8-27b` | Questions with images; the only configured model that accepts images |

Models are configured with `DEFAULT_MODEL`, `HEAVY_MODEL` and `VISION_MODEL`. Large models may write up to `LLM_HEAVY_MAX_OUTPUT_TOKENS` (default 16,384).

## Attachments

You can attach up to 10 files per message by using the paperclip, pasting, or dragging them in.

- **Images** (PNG, JPEG, WebP, GIF, BMP) are decoded and re-encoded as JPEG. This removes metadata such as GPS location and limits the image to 2,048 px. Decompression bombs are rejected.
- **Documents** (PDF, Word, PowerPoint, Excel, HTML, text, code) are converted to text and cited as `Attachment` sources. Long documents contribute their most relevant passages.
- A question sent with files, such as "What's this?" or "Summarize it", is answered from those files only. The web is searched only when the question asks for outside information, for example "latest", "compare with…" or "online".
- Earlier documents stay available for follow-up questions. They are read when the question refers to them (for example "the brief" or "summarize it") or shares key terms with them. Unrelated follow-ups, such as a diagram request, are answered normally, not from the document. Earlier images are included only when a follow-up refers to something visual, because images require the vision model.
- Files are private to their owner and deleted after `ATTACHMENT_RETENTION_DAYS` (90). Quotas: 1,000 files and 2 GB per account, 25 MB per file.
- Files are stored on the retained volume under `space-files/attachments/` and are covered by the daily S3 mirror.

## Created files

Explicit requests, such as "create an Excel spreadsheet…" or "make a PowerPoint…", produce real **Word, PDF, Excel, CSV and PowerPoint** files.

- The Pro model writes a validated JSON content spec. The server renders the file.
- Facts keep their `[n]` citations, and a Sources section is added automatically.
- Spreadsheet formulas are kept only when they compute within the workbook. External links, web functions and references to other workbooks are stored as text.
- CSV cells are protected against formula injection.

## Artifacts

Requests to build something visual or interactive produce an artifact, which opens in a side panel with Preview and Code tabs, versions, copy, download and full screen. Supported types:

- React apps (React, Recharts and Lucide icons)
- HTML pages
- Mermaid diagrams
- SVG graphics
- Long Markdown documents
- Code

Artifacts run in a sandboxed iframe with an opaque origin. They have no access to the app, cookies, storage or the network, and no popups or downloads. The React and diagram runtimes are self-hosted under `/artifact-runtime/` and are built from `src/artifact-runtime` during `npm run build`. Runtime errors show an **Ask Corten to fix** action. Mermaid labels that contain syntax characters are quoted automatically, and a diagram written as a plain `mermaid` code block is still drawn as a diagram.

## Personalization and memory

Settings → Personalization offers:

- **Personal preferences**: free text applied to every answer.
- **Response style**: Normal, Concise, Explanatory, Formal or Custom.
- **Memory**: durable facts the user shares, such as their role or location. Memories are learned automatically, and only from messages that disclose something about the user. Secrets and sensitive categories are excluded by instruction.
  - Questions about the user, such as "Which city am I based in?", are answered from memory and never sent to web search.
  - Users can view, add, edit, delete or clear every memory, or turn memory off.
  - Private chats neither read nor write memory.
- **Your files**: attachments and created files, with download and delete.

## Citations

`[1]`, `【1】` and `【1†source】` markers in answers become clickable chips that open the cited source.

## Answer style

Search, deep research and Space agents share one answer style (`ANSWER_STYLE` in `backend/src/config/prompts.py`). It
is based on OpenAI's Model Spec (be clear and direct, format to aid scanning, no filler) and answer-engine practice.

- The first line answers the question in one or two plain sentences, with only the key figure in bold. Answers
  never open with a heading or a table.
- The shape follows the question: paragraphs for facts, a short opening plus bullets for "how/why", numbered steps
  for processes, a table for comparisons, and `##` sections only for long answers. Requested emails and letters
  are written out directly, with nothing before or after.
- Figures carry units, currencies ("USD 1.2 billion") and periods. Dates are unambiguous ("12 October 2026").
  There are no "Takeaway:" labels, closing questions or source lists; the app shows sources and follow-up questions.
- Each request ends with a short format reminder, because models follow format rules there more reliably than deep in
  a long system prompt.
- Dates such as "this Friday", "tomorrow" or "next month" are worked out in code (`resolve_relative_dates`) and
  given to the model, along with today's weekday and the next seven days. Models cannot be trusted with calendar
  arithmetic.
- If the answer model is out of its per-minute quota before writing, the other text model answers. Deep research
  never shows a blank answer: it retries once, then shows an error.

## Space agents

Questions asked in a Space with web search on are answered by that Space's agent, which calls live data tools,
draws charts and shows each step as it runs. See [Space agents](spaces.md#space-agents).

## Verification

- Unit tests: 252 backend tests and 115 frontend tests.
- Migration `0005_attachments_memory` is additive and was verified on PostgreSQL, including downgrade and re-upgrade. The release gate checks preferences, memory and private-chat isolation on the real schema.
- A real-browser end-to-end suite with real models passed **29/29**: modes, image and document answers, follow-up context, Extended thinking, an Excel file download, React and diagram artifacts rendering in the sandbox, citation links, memory learned and reused in a new chat, and no browser errors. The Spaces suite passed 30/30 on the same build.
