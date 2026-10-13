# Answer mode picker — 13 October 2026

The shared mode picker now uses aligned icon tiles, concise descriptions,
consistent row spacing and a visible selected row. Follow-up composers show the
current mode label; the compact thinking label is Thinking. Auto, Fast, Pro and
Extended thinking keep their existing backend values and selection persistence.

The popup renders outside composer overflow containers, flips and clamps to the
visible viewport, and updates while open on resize or scroll. Its height includes
the border and becomes scrollable on short screens. Selection and Escape return
focus to the trigger; Tab dismisses without trapping focus, and outside pointer
clicks retain focus on the clicked control. Arrow keys, Home and End navigate the
mode choices and Settings link. Reduced motion is supported. Response settings
now opens the Responses panel through a working Settings deep link.

Browser review uses isolated API fixtures and makes no provider calls. Ten
scenario groups cover both composers, selected-state persistence after reload,
the outgoing mode field, keyboard use, outside clicks, live resizing, five widths
and a 240-pixel viewport, Settings navigation and reduced motion. No browser
exceptions occurred. TypeScript and scoped lint passed.

The final release is `3535797b29b5c03d256f585af23b9f3e8d0ed8ac`; both
[CI jobs](https://github.com/ujwalreddybattu04/corten-ai/actions/runs/38356758755)
and all eleven isolated storage/account safeguards passed during AWS deployment.
The hosted production bundle then passed all ten picker scenario groups using a
temporary authenticated account. Search responses were fixtures to avoid model
quota use; account sessions, sync and Response settings loaded from the real API.
The follow-up picker was also checked at 320, 375 and 768 pixels. No browser
exceptions occurred. Production focus is placed during layout after positioning,
before the next keyboard event; it does not depend on an animation-frame delay.
