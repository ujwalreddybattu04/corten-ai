# Monthly interpolation design — 13 October 2026

The monthly tool now follows the same Plus Jakarta Sans typography, dark palette,
rounded panels and restrained controls used by the pharma workspace. Calculation
code, solver constraints and uploaded values are unchanged.

The setup panel separates source data from Average/Exit rules. Advanced CSV format
and encoding help stays available without overwhelming the initial view. A format
guide illustrates yearly input becoming twelve months; it contains no numeric
example or simulated results. The input preview shows actual year/column counts
and labels the expected monthly rows before calculation. Analysts can calculate
directly after reviewing that preview.

Four result widgets show the returned timeline, monthly rows, independent series
and successful yearly checks. The chart has a selected-series heading, mode badge,
clearer controls and an understated accent. Review tables distinguish monthly
values, original targets and validation. Check labels use each returned passed
flag. Scientific notation and unrounded exports remain intact. Single-year
timelines show the year once.

Local verification: 20 real calculation/export browser cases plus six interaction
and layout cases passed. They cover the unchanged 13-year adoption example, all
39 raw yearly constraints, Average/Exit, the global first year, single-year Exit,
absolute values above 100, Unicode/Excel encodings, actual CSV/JSON/PDF downloads,
cancelled/replaced requests and service errors. Five responsive widths fit without
invalid graph coordinates. Keyboard chart inspection, radio/tab navigation,
reduced motion and results retained across workspace tabs passed. No client
exceptions occurred. Six pharma design regressions passed after the stylesheet
addition. The complete frontend suite passed 115 tests; TypeScript and scoped lint
passed with no errors.

The sidebar repair was independently verified on the AWS bundle in 18 layout
cases, followed by 15 real authentication cases, including interrupted logout and
recovery. See [sidebar layout](sidebar-layout.md).

Published source: `24be2e284a343b1785f739538de723d3d0ee975d`.
Both jobs passed in [GitHub CI](https://github.com/ujwalreddybattu04/corten-ai/actions/runs/38345094500).
The exact committed archive was scanned (432 files, zero credential findings),
uploaded privately and deployed to the existing AWS host. On
[the hosted workspace](https://d3a7ful0miola1.cloudfront.net/analyst-workspace),
all 20 real calculation/export checks and all six interaction/layout checks
passed using temporary authenticated accounts. These also verified the single-year
timeline label. Seven real-source pharma compatibility checks passed, with no
browser exceptions. The reviewed adoption CSV was unchanged. No LLM or web search
requests were used for the monthly calculation review.
