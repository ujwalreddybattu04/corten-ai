# Chat selection state

Questions such as “which mode i selected now?” read the response-mode selection
from the current authenticated search request. They return a short, deterministic
answer before routing, retrieval or generation. No web sources or suggested
follow-ups are generated for these answers.

The mode belongs to the current message, not an older answer or saved personal
memory. Auto remains Auto: it is a selector that can choose different models per
question, rather than an assertion that a particular provider model ran. Explicit
focus-mode questions report the separate focus selector. Unknown values are not
invented. Sign-in, Space membership and attachment ownership checks still run at
the API boundary before streaming.

The intent matcher accepts whole selection-state questions. Questions about
external applications, previous selections, model comparisons, translations and
mixed requests continue through normal routing. Title generation for this intent
is local as well.

Regression coverage includes all four response modes, five search focuses,
conflicting history and attached material, the authenticated streaming API, the
sign-in requirement and selection changes between turns. Provider and tool calls
are guarded with failing mocks for the local-answer path.

Verified on 13 October 2026: the isolated release passed all 321 backend tests
and both [GitHub verification jobs](https://github.com/ujwalreddybattu04/corten-ai/actions/runs/38359774145).
Runtime source is `a3aa4e630a2bbaf23b73a98f61e354d898855310`; only the
chat-selection changes were included, with concurrent Space-agent edits excluded.
The existing AWS release completed successfully with all eleven storage and
recovery checks passing.

Six live checks passed against CloudFront using real authenticated API requests
and a real browser, without mocked search responses: sign-in enforcement, all
four response selections, separate focus selection, local heading generation,
the original Pro question, and switching to Fast in the same conversation.
The browser displayed no source badges, unrelated follow-ups, web-search activity
or client exceptions for those selection answers.
