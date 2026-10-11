# Analyst Workspace for Chryselys

Research date: 9 October 2026. This design uses public company material, not access to Chryselys' internal systems, data contracts, or ForecastIQ implementation.

## What Chryselys does

Chryselys describes itself as a pharma data, analytics, and AI company. Its work spans commercial, medical, and clinical functions, with data platforms and analytical products intended to support business decisions. This makes pharmaceutical commercial planning the appropriate domain for this workspace, rather than stock-market forecasting. [Company overview](https://chryselys.com/about-us/)

Its forecasting services cover patient-based and historical forecasts, planning across product and geography, scenario analysis, and reviews involving commercial, finance, launch, and supply functions. [Forecasting services](https://chryselys.com/forecasting/)

ForecastIQ already addresses pharmaceutical forecasts, scenarios, dashboards, configuration, and governance. It describes time-based and patient-based models, multi-country/SKU configurations, backtesting, simulations, access controls, and version/approval trails. Corten should therefore be positioned as an analyst workbench that can prepare inputs, explain results, research assumptions, and package reviews; it should not claim to replace or integrate with that platform without an agreed interface. [ForecastIQ](https://chryselys.com/datafusioniq/forecastiq/)

## The forecasting problem to design around

The rare-hematology case study describes a move away from a simple market-size estimate toward patient-flow modelling. It distinguishes existing populations and incident patients, considers treatment and retention, reconciles evidence, and examines monthly launch dynamics and uncertainty. This supports an assumption-driven workspace where an analyst can explain how patient activity connects to commercial outcomes. [Rare-hematology forecasting case study](https://chryselys.com/rare-hematology-patient-based-forecasting/)

Market access matters to forecasts: Chryselys describes payer restrictions, coverage, treatment uptake, rebates, and gross-to-net leakage. Commercial forecasts should expose access and net-price assumptions instead of hiding them in a single revenue multiplier. [Market Access Intelligence](https://chryselys.com/datafusioniq/market-access-intelligence/)

Data readiness is equally important. Chryselys describes anomaly detection and human review of master and transactional data. Forecast import should flag invalid periods, duplicated observations, missing months, and impossible values instead of silently filling or overwriting them. [Data Anomaly Detection](https://chryselys.com/data-anomaly-detection/)

Competitive and regulatory intelligence can inform assumptions, but a news article should not automatically change a forecast. An analyst needs to connect a market event to a parameter, record the evidence, and review the resulting impact. [Competitive Intelligence](https://chryselys.com/competitive-intelligence/)

## Proposed analyst workflow

1. Create a planning project with brand, therapy area, country, lifecycle, currency, and analyst ownership.
2. Choose a historical-volume baseline or a patient-flow planning model.
3. Validate aggregate inputs before generating outputs.
4. Compare baseline, upside, and downside scenarios; record their business rationale.
5. Evaluate monthly patients/volume, gross sales, gross-to-net deductions, and net sales.
6. Connect material assumptions and events to evidence, dates, and review notes.
7. Save a version at each review milestone and export the assumptions and results together.
8. Use Corten to explain computed results; use web research separately when checking external market facts.

## First local release

### Planning scope

Projects carry commercial planning context. Fictional demonstration brands and synthetic aggregate data are clearly labelled. Users can create a blank project instead of starting from demonstration inputs.

### Historical forecasts

Import monthly CSV data with `date,value` columns, where value is aggregate volume. Compare a recent three-month average, linear trend, and seasonal-naive baseline when sufficient history exists. Select a baseline using the lowest mean absolute error on a chronological holdout, with RMSE and WAPE visible. The holdout remains separate from fitting; after comparison, the selected model is refitted on the complete history.

Do not describe these baselines as ARIMA, machine learning, clinical models, or validated ForecastIQ algorithms. Historical volume and forecast net sales are separate measures. Revenue requires an explicit per-unit price and gross-to-net deduction.

### Patient-flow baseline

Use an existing diagnosed population, annual incidence, diagnosis rate, treatment eligibility, monthly treatment initiation, brand capture among initiators, monthly discontinuation, launch ramp, units per active patient, unit price, and gross-to-net deduction.

The untreated eligible pool receives newly diagnosed eligible patients each month. Treatment starts remove patients from that pool. A proportion of starts enters the brand, adjusted by launch ramp; existing brand patients are retained according to monthly discontinuation. Active brand patients generate units, then gross and net sales.

This is a transparent, simplified aggregate planning model. It does not reconstruct individual journeys or distinguish treatment lines, switching origins, mortality, cure, diagnosis lag, inventory, or competitors' individual cohorts. Its outputs are business scenarios, not estimates of clinical outcomes. Those extensions require domain-reviewed definitions and data.

### Scenarios and market events

Compare explicit upside and downside changes to volume/capture and unit price. Permit a dated future event with a relative impact and rationale. Patient-mode events affect brand capture; historical-mode events affect forecast volume. Display which lever changes in each mode. These scenario curves are assumed business outcomes, not calibrated prediction intervals or Monte Carlo percentiles.

### Evidence and review versions

Keep a dated evidence register, rationale, analyst notes, and review snapshots that retain inputs and computed results. Export a review pack as JSON and monthly outputs as CSV. Local snapshots help compare decisions, but are not authenticated approvals or a tamper-proof audit log.

### AI assistance

An explicit “Explain forecast” action sends a compact summary of calculated values and declared assumptions to the existing assistant. It should not browse the web to explain supplied results. A separate market-research action uses web search and citations; external findings require analyst review before changing model inputs.

## Enterprise work that requires internal requirements

| Priority | Capability | Needed agreement |
|---|---|---|
| Next | Shared projects and persistence | Database, tenant model, user identity, retention |
| Next | Role-based review and approval | Author/reviewer/approver roles, separation of duties |
| Next | ForecastIQ interoperability | Supported APIs or file exchange, IDs, version semantics |
| Next | Commercial data ingestion | Approved IQVIA/claims/CRM feeds, licensing, aggregation rules |
| Next | Brand/country/channel roll-ups | Hierarchy, currency conversion policy, reconciliation |
| Later | Patient journey expansion | Treatment lines, switching, mortality, discontinuation definitions |
| Later | Advanced statistics | ARIMA/ETS model selection, rolling validation, interval calibration |
| Later | Monte Carlo uncertainty | Reviewed parameter distributions, dependencies, seeds |
| Later | Payer/G2N detail | Contracts, rebate eligibility, channel mix, timing, deductions |
| Later | Sensitivity and price-volume bridges | Business-approved decomposition and interactions |

Production gates should include access controls, shared storage, monitoring, domain-reviewed calculations, and forecast validation on representative data. Existing company products' public security claims do not establish those properties for this new Corten feature.

## Important implementation boundary

The current Corten installation has no running PostgreSQL/Redis services and its existing Spaces UI stores data in the browser. The initial Analyst Workspace likewise saves projects on the current device and supports file-based review handoff. It does not claim live collaboration, SSO, authenticated approval, connected licensed datasets, or ForecastIQ integration. Those require a separate infrastructure and integration phase.
