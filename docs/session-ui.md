# Session transitions and sign-out confirmation

Successful password login uses a persistent cover above the account-keyed views:
the form exits in 180 ms, session hydration completes behind the cover, and the
mounted destination is revealed in 260 ms. The sanitized `next` destination is
preserved. Failed login never starts the transition. Reduced motion removes the
animations and their intentional delays. Session invalidation cancels the cover;
an eight-second deadline prevents a stalled navigation leaving the UI inert.

Sidebar and Settings sign-out actions open the same confirmation dialog. Opening
or cancelling the dialog sends no logout request. Confirming invokes the existing
logout flow, which immediately hides private views even if revocation fails.
The native modal uses the existing font and dark colors, defaults focus to Cancel,
traps Tab navigation, restores trigger focus, and supports Escape and backdrop
cancellation. It also works over the mobile navigation drawer.

Local browser checks cover eight login cases and seven confirmation cases,
including delayed session hydration, failed passwords, safe return paths, mobile,
reduced motion, interrupted sessions, cancellation and failed logout recovery.

Verified on 13 October 2026: all fifteen local browser cases passed, including
restoring page scrolling when a mobile drawer and confirmation close together.
The final runtime source is `fbe4cb24f1e00fe04058d8aff61794723acac558`, with both
[GitHub verification jobs passing](https://github.com/ujwalreddybattu04/corten-ai/actions/runs/38367507230).

AWS received only the seven frontend files for this feature. They were applied
to a copy of the existing live frontend and released without rebuilding or
restarting the backend, database or cache. The release verified unchanged
Space-agent source files and unchanged frontend files outside this feature.
Live source checks allowed only line-ending differences from the reviewed base;
the active source tree was retained. Frontend rollback uses the previous image.

Five real-account checks passed on CloudFront: failed login, successful animated
login, sidebar cancellation, Settings cancellation, and confirmed mobile logout
with cookies cleared and scrolling restored. No browser runtime exceptions were
reported. The disposable verification account was selected for exact-ID cleanup.
