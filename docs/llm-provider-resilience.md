# Hosted AI providers and quota recovery

All AI requests pass through `backend/src/services/llm_runtime.py`, including
routing, chat answers, article summaries, research, report generation, titles
and follow-up suggestions. The existing `groq_llm_service` name is retained for
compatibility with these consumers.

## Groq credential pool

Keep the primary credential in `GROQ_API_KEY`. Set `GROQ_FALLBACK_API_KEYS` to a
JSON array of additional credentials in the private backend environment. Never
put real credentials in source files, documentation or `.env.example`.

Requests try the primary key, then each distinct fallback key. A 429 pauses that
credential/model combination until the provider's `Retry-After` expires. Other
requests, including titles and routing, skip paused combinations. After the
cooldown, the credential becomes eligible again. Missing or invalid reset
headers use a 60-second cooldown. Duplicate keys are removed.

With three keys, at most three initial provider attempts occur. If the last
eligible credential reports a wait of two seconds or less, one additional
attempt is allowed after waiting. SDK retries are disabled, so they cannot
multiply these attempts. Cancellation stops the wait and request immediately.

401/403 credentials are skipped until the application restarts with corrected
configuration. Request validation failures (400/422) are not retried across
credentials. Temporary connection/server failures can use the next configured
credential. Streaming failures never restart or splice another answer into an
answer that has begun.

When every available credential is cooling down, chat SSE returns
`code: llm_rate_limited` and `retry_after_seconds`, with a readable wait message.
Subsequent requests do not call those credentials again during the cooldown.
Raw provider error bodies and credentials are excluded from these messages.

These cooldowns are shared across tasks **within one backend process**. A
deployment with multiple workers/replicas needs a shared Redis cooldown store
before relying on this behavior across the deployment. The provider continues
to enforce its own limits regardless of application state or restarts.

**Rotation does not create unlimited capacity.** Groq applies rate limits at the
organization level; credentials in the same organization can all exhaust the
same quota. Check each organization in the
[Groq limits console](https://console.groq.com/settings/limits).
See [Groq's rate-limit documentation](https://console.groq.com/docs/rate-limits).

## Reduce avoidable usage

`LLM_MAX_OUTPUT_TOKENS` defaults to 2,048 and caps every provider request,
including deep research that previously requested 8,192 output tokens. This
budget includes reasoning tokens where the provider counts them. It can be
raised when the account quota supports the larger request; long answers may
otherwise be cut off at the configured output limit.

Groq GPT-OSS requests use low reasoning effort by default. Follow-up requests
are explicitly capped at 512 tokens. Standard research reuses the router's
intent for progress text rather than making an extra planning request just for
that text. Suggestions run after the answer, with a four-second timeout, so they
do not take priority over answering the question. Title and suggestion failures
retain their existing local fallback/empty-suggestion behavior.

There is no automatic change to the configured answer or router model.

## Optional independent hosted fallback

Gemini can be explicitly selected with these private environment settings:

```dotenv
GOOGLE_AI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
LLM_PROVIDER=groq
LLM_FALLBACK_PROVIDER=gemini
```

To use Gemini as the primary provider, set `LLM_PROVIDER=gemini` instead.
Merely storing a Google key does not enable it or send it conversation data.
The Gemini adapter replaces Groq model names with `GEMINI_MODEL`, preserves
conversation/source messages and supports streaming and JSON responses through
the [official compatibility endpoint](https://ai.google.dev/gemini-api/docs/openai).
Gemini 2.5 Flash uses a zero optional thinking budget so small title/JSON outputs
do not get consumed by internal thinking.

A key must be issued by the account owner through
[Google AI Studio](https://aistudio.google.com/api-keys). Its
[free tier also has quotas](https://ai.google.dev/gemini-api/docs/rate-limits).
Review [the provider's pricing and data-use terms](https://ai.google.dev/gemini-api/docs/pricing)
before choosing a free tier for confidential company data. This application
does not create accounts, add billing, upgrade provider plans or claim unlimited
free API usage.

## Verification

Run `python -m unittest discover -s tests -p test_llm_runtime.py` from `backend`.
The tests use mock HTTP transports: they do not consume provider quota. Coverage
includes three-key failover, shared quota exhaustion, bounded retries,
cancellation, revoked credentials, output caps, explicit provider selection,
cross-provider context preservation and interrupted streaming.
