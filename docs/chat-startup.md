# Chat connection and startup

The screenshot's HTTP 502 means the frontend proxy could not obtain a successful upstream response. It does not by itself identify the underlying failure. The deployed services use Render's free compute plan: after 15 idle minutes the backend can spin down, and restarting takes about a minute. This matches the reported first-open pattern. Deployments, restarts and other connection failures can also cause 502s. See [Render's free-service documentation](https://render.com/docs/free#spinning-down-on-idle).

Before submitting a question, chat now reads `/api/v1/search/status`. This endpoint confirms the application is responding; it does not call an LLM/search provider or guarantee those providers' availability. The frontend retries transient status/network failures within a two-minute budget, honors Retry-After, and cancels on navigation or replacement. Each status attempt has a timeout; the frontend proxy also bounds its upstream status request to ten seconds. A hosting HTML loading page is treated as not ready.

Once ready, chat submits generation once. It does not automatically repeat a failed POST: a network interruption can occur after a provider has already started work, so replay could duplicate costs and results. Recoverable errors offer a manual Retry button. Retry retains the current question and successful conversation history, and clears the failed draft without adding it to that history. Failed or interrupted output is not saved as a successful conversation.

The UI distinguishes connecting from generating an answer, keeps the existing font/dark theme, and respects reduced-motion settings. Persistent connection failure still produces a clear error after the deadline.

This improves startup recovery but does not remove hosting idle delays or guarantee continuous availability. Always-on compute is needed to eliminate free-plan idle starts. No paid plans were selected or changed.

Run `node --test tests/search-connection.cjs` in frontend and `python -m pytest tests/test_search_status.py -q` in backend. The tests verify that startup retries never generate answers, interrupted or failed generation POSTs are not replayed automatically, context remains unchanged, Retry-After and cancellation are honored, and invalid/loading responses cannot trigger generation.
