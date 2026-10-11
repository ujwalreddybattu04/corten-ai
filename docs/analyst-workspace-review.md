# Analyst Workspace: enterprise UX review

> Historical review of the removed implementation. The workspace now contains
> only its sidebar entry and page shell. See [current scope](chryselys-analyst-workspace.md).

Reviewed on 9 October 2026 against the existing Corten interface and the local implementation. This is a product and usability review; it does not certify the platform for enterprise production use.

## Findings and changes

| Priority | Finding | Effect on an analyst | Change implemented |
|---|---|---|---|
| High | The screen exposed setup fields before an obvious workflow. Navigation appeared below the chart. | Analysts had to scroll to find editing and review tools. | Added an Overview landing view and moved all five workflow tabs above the content. Setup details expand on demand. |
| High | Review snapshots did not visibly indicate changes to their inputs. | A saved version could appear current after assumptions changed. | Added current/outdated snapshot indicators and a review preparation task that updates when inputs change. |
| High | Saved version totals used the active project's currency. | A historical snapshot could receive an incorrect currency label. | Display each snapshot using its own saved reporting currency. |
| High | Patient defaults could be mistaken for substantiated assumptions after a real CSV import. | Analysts might carry illustrative parameters into a patient model without review. | Explicitly label patient assumptions as requiring review, independent of the historical data flag. |
| Medium | The workspace used purple tints and smaller type than the rest of the app. | The feature looked like a separate application. | Use the shared Plus Jakarta Sans font, neutral color tokens, existing Spaces form controls and primary action, and Discover-style secondary buttons. |
| Medium | Decorative icon tiles and repeated titles competed with the content. | The screen felt busy without improving understanding. | Removed decorative icon tiles and repeated headings. Retained consistent icons for actions such as importing, exporting, and searching. |
| Medium | Patient inputs appeared as one undifferentiated form. | It was difficult to understand the relationship between input groups. | Grouped inputs into Population and access, Treatment and brand uptake, and Commercial assumptions. |
| Medium | There was no direct way to find forecasts or resume the selected one. | Analysts lost their place when working across projects. | Added forecast search, a compact selector on smaller screens, and selected-project persistence across reloads. |
| Medium | The desktop chart was reduced to fit mobile screens. | Chart labels became too small to read. | Adapt the SVG plotting dimensions and tick density to the actual container width. |
| Medium | Tab navigation lacked arrow-key behavior. | Keyboard users had to traverse every tab separately. | Added arrow, Home, and End key navigation, tab focus management, and panel labels. |
| Medium | Review dates could be ambiguous and snapshot numbers could repeat after the retention limit. | Review handoff was harder to interpret. | Use named months in dates and continue the review sequence after older snapshots are removed. |
| Medium | Re-entering an out-of-range number at an existing limit could leave the displayed value different from the calculation. | The input could show 999% while the model used the capped 100%. | Reset the displayed draft to the bounded value on commit; verified with repeated edits at the limit. |

## Final information hierarchy

1. Workspace header: product identity, actual local save state, and New forecast.
2. Forecast navigation: search and selected project on desktop; a compact selector on smaller screens.
3. Forecast heading: project context, draft/snapshot state, and import/save/export actions.
4. Workflow: Overview, Model inputs, Scenarios, Evidence & review, and Monthly outputs.
5. Overview: forecast measures, a responsive chart, planning assumptions, and actionable review tasks.
6. Details: focused forms and outputs for the selected task.
7. Assistance: explain supplied forecast results or research external drivers.

The review preparation checklist records whether a baseline exists, ownership is filled in, evidence is attached, and a snapshot captures the current inputs. Completing it does **not** constitute validation or approval. Synthetic historical data remains labeled. Patient inputs remain subject to domain review.

## Verification

The browser walkthrough exercised all five tabs at ten viewport widths, from 320 to 1920 pixels, with no page-level horizontal overflow. It checked input editing, patient input groups, evidence entry, ownership preparation, snapshot freshness, saved snapshot currency, forecast search, keyboard tabs, CSV import, selected-project persistence, and review-pack export/import. No uncaught client exceptions were observed in that walkthrough.

Additional checks covered repeated out-of-range edits, simulated storage failure and recovery, chart keyboard interaction, sidebar collapse, and the sticky mobile header. At 320 and 390 pixels the chart clears the header and all vertical-axis labels fit inside the drawing area.

The font was previously compared with the home page using the browser's actual rendered font information. The primary action and form controls were compared with Spaces, and secondary buttons with Discover. The shared design styles remain in use after reorganizing the layout.

Full-project TypeScript checking still reports four existing API-client issues in collection, discovery, space, and user services. It reports no Analyst Workspace errors. These existing issues must be addressed before treating a production build as verified.

## Remaining enterprise requirements

The current installation stores forecast projects in the browser and shares them through review packs. Before company-wide deployment, the team needs shared authenticated storage, agreed author/reviewer/approver roles, enforceable access controls, conflict handling, a server-side audit history, recovery and retention policies, and validation of the forecasting definitions with representative company data. ForecastIQ integration and licensed data connections require an agreed interface and access.

The workspace does not present local snapshots as authenticated approvals or claim a ForecastIQ connection. Project archiving, portfolio roll-ups, and comparing selected historical review versions are sensible next product steps once the shared project lifecycle is defined.
