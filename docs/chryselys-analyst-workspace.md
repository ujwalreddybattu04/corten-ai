# Analyst Workspace for Chryselys

The previous analyst workflow was removed at the project owner's request. The
sidebar entry and `/analyst-workspace` route remain, with the page title and the
app's shared typography and dark styling.

The workspace currently has no dashboard, forecast models, projects, scenarios,
pharma feed, evidence review, import/export, or assistant actions. The page does
not load or create project data, run forecasts, or request pharma updates.

The next workflow will follow requirements supplied by Chryselys. No replacement
workflow has been assumed.

Previously saved browser records are not deleted by opening the empty workspace.
The standalone backend pharma API remains available independently; it has no
connection to the current workspace page.

The earlier [review](analyst-workspace-review.md) and
[test report](analyst-workspace-test-report.md) are historical records of the
removed implementation.

Validation of the reset: production build and TypeScript passed, along with 34
frontend regression tests and 36 backend routing/answer tests. Ten local browser
checks verified navigation, the title-only page, shared font and dark theme,
320–1440px layouts, reload, no pharma/research requests, and no runtime exceptions.
