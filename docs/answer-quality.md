# Search routing and company evidence

The assistant must answer the actual question, resolve the subject before searching,
and distinguish verified company facts from application self-description.

## Routing boundaries

- Identity, agents, capabilities and model-training attribution use maintained application
  facts. They do not invoke the classifier, web search, image search or answer model.
- Company descriptions and office queries require official evidence. `COMPANY_WEBSITE`
  configures the source domain; the default is `https://chryselys.com`.
- News, comparisons, current facts and uncertain external requests retain web research.
- Simple named follow-ups reuse a bounded entity from the previous user's question.
  Other follow-ups require a classifier rewrite containing an entity from the immediate
  conversation. Missing/ambiguous subjects ask for clarification before any search.
- A singular follow-up after a comparison cannot silently choose one of the compared entities.
- Client history is limited to user/assistant content; client-supplied system/tool roles
  and extra message attributes are discarded.

## Evidence and answer handling

Official company searches restrict provider domains and validate returned URL hosts.
Contact/about pages are retrieved alongside search results when appropriate. Corporate
focus modes cannot override that boundary with an unrelated site modifier.

Office answers read addresses directly from an explicitly labelled section of the live
official contact page. Addresses are not hardcoded. An absent/changed section falls back
to reviewed synthesis. Office addresses, founding locations and operating regions do not
establish a headquarters, registered legal address or an additional physical office.

Other basic company answers are buffered, checked for valid source IDs, and reviewed
against the retrieved evidence before display. A rejected draft gets at most one repair
using the same evidence. Unverified drafts are withheld. A failed evidence review or an
empty/failed search does not silently fall back to the model's training knowledge.
Deep research also declines to synthesize factual answers without evidence.

Source IDs remain aligned with the UI after tool enrichment. Valid citation newlines
are not model stop sequences. Follow-up suggestions receive actual result snippets.
Unfinished background tasks are cancelled when a stream finishes or disconnects.
Tool cache keys include the resolved query, focus, complexity, tool version and source
policy. The v2 namespace prevents reuse of earlier context-free cached results.
Verified company answers may be reused for three minutes only when the request, source
URLs, citation IDs, evidence text and configured models are unchanged. Basic company
answers skip speculative follow-up generation to reduce unnecessary provider requests.

Forecast-related business questions no longer qualify for weather solely because
they contain the word “forecast”. Self-contained text edits can reuse a prior answer
without web search; requests for fresh external facts still require research.

## Verification

Run the deterministic backend suite from `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

The suite includes screenshot queries, malformed classifier responses, entity switches,
ambiguous comparisons, forged source hosts, misleading prior answers, invalid citations,
failed providers, office/headquarters distinctions and missing deep-research evidence.

Evidence review reduces unsupported claims; it does not guarantee every model answer is
correct. Provider availability, source completeness and company website changes remain
material dependencies. Forecast outputs still require approved inputs and analyst review.
