# Discover feed recovery

The intermittent empty page had two observed triggers: the hosted Guardian key returned HTTP 401, and hosted backend requests returned HTTP 502 during an idle restart. Previously the browser cleared its articles after a failed refresh. Discover news does not require an LLM call.

## Feed behavior

The backend tries Guardian, NewsAPI and then BBC's public RSS feeds. The fallback carries the publisher name, original article URL and publication time. It contains headlines and descriptions, not invented articles. RSS content has a size limit, rejects DTD/entity declarations and excludes invalid links. Each provider request has a deadline. Invalid credentials and throttling enter a cooldown; a changed credential has a separate cooldown identity.

All page sizes share canonical 20-story pools. Requested pages slice those pools, including across boundaries, so smaller requests do not skip stories. Concurrent requests in the same backend process share a refresh. Redis stores successful pools for up to six hours; a bounded process cache also supports temporary Redis failures. Results are fresh for 15 minutes. Older successful stories are returned with `status: "stale"` and their original `fetched_at`, up to the six-hour limit. Outages never advance that timestamp. When no usable stories exist, provider failures return HTTP 503 and `Retry-After: 30`; a successful empty result remains distinct from failure.

The browser saves first-page results per category and verified account, with the same maximum age. It displays saved stories while reconnecting and preserves them after refresh failure. Each read-only news request retries transient failures within a 90-second budget, honors Retry-After, and aborts on tab changes or unmount. For You displays successful topics as they arrive, then identifies unavailable topics. A failed pagination retry requests the failed page; a refresh retry requests page one.

## Limits

This recovers temporary failures; it does not guarantee provider uptime or eliminate free hosting cold starts. A first-time visitor has no saved feed, and a complete upstream outage can still produce a clear error with Retry. Guardian's rejected credential still needs a valid replacement if that provider is to be used. The fallback avoids making it the sole dependency. Weather and financial widgets use separate services and can be unavailable independently.

The process refresh lock is per instance, not a distributed lock. Before scaling to multiple instances or a commercial rollout, choose appropriately licensed provider capacity, always-on hosting, and shared monitoring. Account feed snapshots are browser-local; this does not add cross-device personal persistence.

## Verification

Run `python -m pytest tests/test_discover_feed.py -q` in backend and `node --test tests/discover-feed.cjs` in frontend. Fault tests cover unauthorized/missing credentials, fallback, cache outages/corruption, stale expiration, canonical pagination, shared refresh cancellation, browser account isolation, retry deadlines and malformed responses. See [hosted verification](hosted-verification.md) for deployed checks.
