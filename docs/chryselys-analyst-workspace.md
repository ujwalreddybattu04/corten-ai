# Analyst Workspace: yearly-to-monthly interpolation

The current workspace implements the Chryselys interpolation requirements supplied
by the project owner. A separate [Pharma intelligence tab](pharma-updates.md) now
provides dated public FDA and ClinicalTrials.gov records, as requested. The previous
dummy forecasting dashboard, project/scenario workflow and review-pack tools remain
removed. Switching tools preserves the current interpolation upload/result.

## Analyst flow

1. Upload a CSV and review its yearly inputs and column names.
2. Choose Average or Exit. Generating a result is an explicit action.
3. Inspect each series' graph, original inputs, monthly values and yearly checks.
4. Export monthly CSV, the complete JSON review, or PDF with inputs, graphs and
   monthly numbers. Exports are checked against the result that was reviewed.

No example is loaded automatically. The downloadable review example contains
exactly the supplied 13-year Slow/Moderate/Fast adoption inputs, including 98%
for all three columns in Year 10 and 100% in Years 11–13. Uploaded files are not
edited, filled, capped, rebased or replaced.

## Methods

Both modes minimize squared second differences across the complete monthly
sequence. Columns are solved independently, without carrying a previous column's
warm start into the next one.

- **Average:** each 12-month mean is an equality constraint. Each column's yearly
  minimum/maximum is a soft preference, weighted 0.1 against curvature. The first
  month has a positive lower bound: 1% of the largest positive yearly target, or
  a small bound relative to the series magnitude for entirely nonpositive
  inputs. Only an all-zero series uses the reference floor of 1e-6. Other monthly
  values can be negative or exceed the yearly extrema.
- **Exit:** every December is an equality constraint and the first month is
  non-negative. The first year is part of the same optimization. A single
  non-negative target produces a flat year; a negative single-year target is
  rejected because the flat fallback cannot satisfy the first-month constraint.

The supplied smoother was adapted to scale tiny inputs consistently, check every
nonzero target relative to its own magnitude, reject inaccurate solver statuses,
and use a bounded direct-solver fallback when the primary solver does not meet
feasibility requirements. No hard 0–100 output limits are applied. The internal
normalization is numerical scaling, not a business-value boundary.

## CSV support and validation

- A case-insensitive `year` column and 1–20 independent value columns.
- Calendar integers or relative integer years; `Year 1`/`Year1` labels also work.
- Consecutive years, sorted when necessary. Duplicate or missing years are errors.
- Numbers with optional `%`: `25%` and `25` mean the same numeric value, 25.
- UTF-8/BOM, UTF-16/BOM and Windows-1252, plus explicitly selectable GB18030.
  Auto detection handles UTF-8, BOM-marked UTF-16, then Windows-1252. Select an
  explicit legacy encoding if the preview's names do not match the source.
- Comma, semicolon and tab separators, Excel `sep=` declarations, and LF/CRLF/CR
  endings. Malformed rows, duplicate/empty/reserved/formula-like headers and
  invalid numbers are rejected with row/column details.
- Invalid/overflowing numbers, underflow, excessive decimal-to-float conversion
  loss and nonzero magnitude ratios above 1e12 are rejected.
- Limits: 10 MB files, 100 years, 20 columns and 12,000 monthly values per request.
  Body size is bounded at the frontend proxy and backend before multipart parsing.

Raw float64 results are independently checked using high-precision decimal
accumulation. Nonzero targets have a 1e-6 relative acceptance tolerance; zero
has a 1e-12 absolute tolerance. Only constraint roundoff may be corrected. Results
that cannot be verified are withheld. Display rounding is not used for validation.

## Outputs and privacy

CSV uses UTF-8 BOM and unrounded numeric values; JSON includes original yearly
inputs, monthly outputs, units, constraint errors, input digest and calculation
engine identifier. PDF embeds bundled Noto fonts and contains original targets,
one graph per series and all monthly rows. Its numbers display two decimal
places, using scientific notation for very large/small values.

PDF supports Latin, Greek, Cyrillic, Chinese and supported Japanese glyphs.
Unsupported glyphs or right-to-left scripts produce a clear PDF error rather than
missing characters; CSV and JSON remain available. See [font provenance and
licenses](../backend/assets/fonts/README.md).

Uploads are processed statelessly, with temporary upload files closed after read.
The interpolation tool does not persist files/projects, call AI/search providers or
modify company forecasts. Its requests/responses use `no-store`. One calculation/export per
backend worker is allowed at a time; capacity exhaustion returns 503 with
Retry-After. Exports recompute from the unchanged upload and reject a mismatched
calculation fingerprint with 409 so stale engine results cannot be exported as
if they were the reviewed result.

## API and verification

The interface review keeps Corten's Plus Jakarta Sans font and dark palette,
with higher-contrast captions, grouped input/mode controls and a responsive
results layout. Timeline, monthly-row and series summaries use the calculation's
actual data. All uploaded yearly rows can be reviewed before calculation.

Verified curves reveal over 850 ms, with a subtle area fill and brief transitions
between input, calculation and result states. Changing series reveals the new
curve. Animations do not change values or geometry; all workspace motion is
disabled when `prefers-reduced-motion` is enabled. Positive-only chart axes avoid
implying negative data while retaining overshoot; mixed-sign data retains both
sides of its range. The optimizer and numerical output are unchanged.

Monthly inspection supports mouse, touch and keyboard, including Left/Right,
Home/End and Escape. Review tabs use arrow navigation and one tab stop. Small
screens bring generated results into view. Uploads reject multiple-file drops
explicitly, errors preserve the current input and provide a retry/dismiss action,
and exports show pending/completion feedback.

POST `/api/v1/interpolation/preview`, `/calculate?mode=average|exit`, and
`/export?mode=average|exit&format=csv|json|pdf` accept a multipart `file` and an
optional `encoding`. Export accepts the reviewed `calculation_id`.

Install `backend/requirements-test.txt` to run the tests, then:

```sh
cd backend
python -m unittest tests.test_interpolation -v
```

The supplied adoption example was verified in both modes: 156 monthly rows,
three independent columns and 39 yearly checks each. Average errors were at most
1.67e-14 in the local verification; Exit December errors were zero. Smooth values
can exceed 100% by small amounts, as permitted by the requirements; inputs remain
98% in Year 10 and 100% in Years 11–13.

Local verification passed 93 backend tests, 39 frontend tests and 18 isolated
browser checks, including real downloads, Unicode Excel input, failure recovery,
canceled/out-of-order requests and responsive layouts from 320 to 1440 pixels.
The production frontend build passed. Both modes also completed a 100-year,
1,200-month absolute-value timeline with all yearly constraints verified.

The subsequent interface review passed 45 frontend tests and 30 local browser
checks, covering real uploads/downloads, animation progression and completion,
reduced motion, exact tooltip values, keyboard and touch input, cancellation,
error recovery, Unicode PDF text and layouts from 320 to 1440 pixels.
The original 29 interface checks also passed on the hosted deployment.

Hosted testing also observed an idle backend restart: the first upload failed,
and a direct request took approximately 43 seconds before succeeding. Upload
validation now retries HTTP 502/503/504 at most twice, after 2 and 4 seconds,
with unchanged file bytes and encoding. Replacing a file or leaving the page
cancels retry delays. Validation errors and calculation/export requests are not
automatically retried. Persistent unavailability gives a clear retry message.
These retries handle temporary failures; free hosting can still delay a request
while a stopped backend starts. Use always-on hosting for predictable team use;
see [Render's free-service limits](https://render.com/docs/free#spinning-down-on-idle).
