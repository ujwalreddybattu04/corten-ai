# Conversation memory

Chat recall is a separate route from external research. Requests such as “what was my previous question?”, “what project did I mention earlier?”, and “summarize our conversation” use the current thread. Requests to search, verify, or add current external facts continue through the research pipeline.

## Recall and context

- Previous, first, numbered, relative and listed questions are read directly from user messages. This needs neither web search nor an LLM, including when the provider is unavailable.
- Notes beginning with “remember that” receive a direct acknowledgment for this conversation. Note titles also avoid an LLM call.
- Other conversation recall uses a dedicated prompt, with no external sources or search tools. Missing information must be acknowledged; the latest user correction takes precedence over earlier statements.
- The client sends up to 60 prior exchanges. The backend accepts only user/assistant messages, strips additional fields, bounds each message to 6,000 characters, and retains up to 120,000 characters total. Long messages preserve their beginning and end with an explicit shortening marker.
- Answer context has a 14,000-character budget. It selects recent messages and relevant earlier text, then restores chronological order. It does not create model-written summaries that could turn guesses into remembered facts. The query classifier uses a smaller context budget.
- Earlier assistant answers are conversation data, not verified evidence. Company research continues to use official evidence independently of previous assistant claims.

This is bounded conversation context, not unlimited recall. Messages outside the retained window or omitted by the context budget may be unavailable. First/numbered recall describes a position in the available history.

## Persistence and isolation

Completed non-private threads are saved in this browser's local storage. The URL receives the thread ID so refresh restores all displayed saved exchanges and continues their context without rerunning a search. Saved-thread navigation creates an independent hook session and cancels an outgoing request. A missing thread produces a useful error rather than an indefinite loading state.

Private mode keeps context in memory while the page is open and does not write new thread content to local storage. New threads start without another thread's messages.

This implementation does not provide account-backed cross-device persistence, team-wide memory, or automatic cross-chat recall. Those require authenticated server-side storage and access controls; browser history must not be presented as shared enterprise memory.

## Validation

Regression coverage checks exact recall without a provider, common phrasing, missing history, message-role sanitization, bounds, older relevant facts, supplied corrections, and mixed requests that must retain web research. Frontend tests check chronological history payloads, size bounds, and preservation of the latest correction and long-message tail.

The real browser audit uses synthetic project notes. Model-dependent checks are subject to the configured provider's quota; deterministic recall and note acknowledgments remain available when that quota is exhausted.

Local validation completed with 70 backend tests and 89 subtests, 18 frontend tests, and a successful Next.js production build. Browser checks covered exact/older question recall, saved refresh without a new search, reopening, new-thread isolation, missing saved threads, navigation between saved threads, and private mode. Real model responses correctly recalled Meridian/oncology with the supplied Japan correction and acknowledged an absent budget without searching.
