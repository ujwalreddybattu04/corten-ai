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
exceptions occurred. TypeScript and scoped lint passed. Hosted verification is
recorded after deployment.
