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
- Earlier documents stay in context for follow-up questions. Earlier images are included only when a follow-up refers to something visual, because images require the vision model.
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

Artifacts run in a sandboxed iframe with an opaque origin. They have no access to the app, cookies, storage or the network, and no popups or downloads. The React and diagram runtimes are self-hosted under `/artifact-runtime/` and are built from `src/artifact-runtime` during `npm run build`. Runtime errors show an **Ask Corten to fix** action. Mermaid labels that contain syntax characters are quoted automatically.

## Personalization and memory

Settings → Personalization offers:

- **Personal preferences**: free text applied to every answer.
- **Response style**: Normal, Concise, Explanatory, Formal or Custom.
- **Memory**: durable facts the user shares, such as their role or location. Memories are learned automatically, and only from messages that disclose something about the user. Secrets and sensitive categories are excluded by instruction.
  - Users can view, add, edit, delete or clear every memory, or turn memory off.
  - Private chats neither read nor write memory.
- **Your files**: attachments and created files, with download and delete.

## Citations

`[1]` and `【1】` markers in answers become clickable chips that open the cited source.

## Verification

- Unit tests: 244 backend tests and 114 frontend tests.
- Migration `0005_attachments_memory` is additive and was verified on PostgreSQL, including downgrade and re-upgrade. The release gate checks preferences, memory and private-chat isolation on the real schema.
- A real-browser end-to-end suite with real models passed **29/29**: modes, image and document answers, follow-up context, Extended thinking, an Excel file download, React and diagram artifacts rendering in the sandbox, citation links, memory learned and reused in a new chat, and no browser errors. The Spaces suite passed 30/30 on the same build.
