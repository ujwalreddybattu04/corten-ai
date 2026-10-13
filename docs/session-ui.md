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
