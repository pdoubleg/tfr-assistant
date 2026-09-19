# Hover supplement research

Standalone extraction and research for supplied homeowners claim evidence. No database,
frontend, API server, document OCR, image processing, or Hover API is involved.
All examples below run from the repository's `backend` directory.

## Setup and offline walkthrough

```powershell
uv sync --group notebook --group explainability
uv run --group explainability python -m ad_hoc.hover_supplements demo data/hover_research/demo --claims 400 --bootstrap 40
uv run --group notebook --group explainability jupyter lab ad_hoc/hover_supplements/walkthrough.ipynb
```

The demo and notebook use explicit Pydantic AI test models with fictional outputs. They
never call an API. The notebook exercises sampling, async extraction, evidence QA,
analysis, statistical adjustment, prediction, and artifact generation. It uses 40 bootstrap
replicates for a quick walkthrough; research functions default to 500. Fewer than 30
successful bootstrap fits, or success below 80%, suppresses confidence intervals.

## Claim bundles and independent extraction

Inputs are a JSON array or JSONL of `ClaimBundle` records. IDs are stable strings; money
is in dollars. One record represents one claim and its aggregate supplement history.

```python
from datetime import date
from ad_hoc.hover_supplements import ClaimBundle, Evidence, extract_claim
from app.core.config import get_settings

claim = ClaimBundle(
    claim_id="example", hover=True, peril="hail", sub_peril="roof",
    initial_estimate_cutoff=date(2024, 6, 10),
    initial_estimate_amount=10000, supplement_approved_amount=1200,
    supplement_requested_amount=1500, supplement_denied_amount=300,
    supplement_activity="yes",
    initial_evidence=[Evidence(
        id="initial", source="Initial estimate", kind="estimate",
        date=date(2024, 6, 10), text="Caller-supplied initial estimate text ...",
    )],
    later_evidence=[Evidence(
        id="revision", source="Supplement notes", kind="note",
        date=date(2024, 7, 1), text="Caller-supplied supplement evidence ...",
    )],
)
# In a notebook, using your existing backend LLM credentials/configuration:
result = await extract_claim(claim, get_settings().audit_llm_config())
```

`extract_baseline` and `extract_supplement` are independently callable. The baseline
pass receives only initial evidence; the supplement pass receives both partitions.
No pass receives the `hover` metadata field, approved outcomes, sampling weights, or
the complete bundle in its dependencies. Evidence text may naturally identify a vendor;
caller-supplied text is not automatically redacted. Field-level references must identify
accessible evidence and known schema paths. Nonmissing factual findings require references.
References establish provenance, not automated proof that a source supports the finding.

The caller must partition evidence by availability at the initial-estimate cutoff.
An initial source dated after the cutoff is rejected. Undated initial evidence is allowed
only because the caller explicitly put it in that partition. Later evidence must not
contain unrelated claims. Photo descriptions support only what the descriptions say;
the agent does not inspect original photographs.

`supplement_activity="no"` is an explicit caller assertion and skips the second pass.
`unknown` does not skip it. A denied request with zero approved dollars still runs.
Missing approved dollars remain unknown; they never become zero or an inferred approval.
Structured amounts remain authoritative and extracted amounts are retained separately for
QA. Denied dollars are never inferred as requested minus approved. Ratios use authoritative
amounts and are missing for unknown amounts or zero initial estimates.

```powershell
uv run python -m ad_hoc.hover_supplements extract claims.jsonl data/hover_research/extractions.jsonl --checkpoints data/hover_research/checkpoints --concurrency 4
```

By default, live extraction reuses `get_settings().audit_llm_config()` and the existing
model builder. `--model-config model.json` accepts an `LLMModelConfig` override (model
name, API mode, reasoning, timeout, etc.), never credentials. Checkpoints hash the input,
model configuration, schema, and prompts. Only complete successful records are reusable.
Failed claims are retained with pass-level errors and retried on a subsequent run.
Change the schema/prompt versions whenever extraction behavior changes. JSON serialization
preserves cost, usage, latency, evidence, and discrepancies. A nonzero extraction exit code
means at least one pass failed; successful claims are still written.

## Feature tables and sampling

The source is the final Pydantic code in the
[shared planning conversation](https://chatgpt.com/share/6aac6fae-a418-83ea-bb97-b22e29431a0d).
All 124 leaf fields, descriptions, nested groups, and enums are retained. The standalone
supplement `to_pandas()` prefix is normalized to `supplement_mechanism__`, matching the
combined model. Calculation and conversion live outside the LLM schema.

`feature_dictionary()` returns the complete inventory and descriptions; research reports
export it as CSV and JSON. `to_pandas()` flattens nested features, preserves nullable
boolean distinctions, parses dates, and excludes narrative fields by default. Optional
`drop_text=False`, `indicators_as_boolean=False`, and `unknown_as_na=False` retain the
corresponding raw representations. `concat_feature_frames` handles multiple records.

```python
from ad_hoc.hover_supplements import build_feature_table, stratified_sample

sample = stratified_sample(population, {
    (False, False): 100, (False, True): 300,
    (True, False): 100, (True, True): 300,
})  # Keys: (hover, positive approved supplement)
features = build_feature_table(results, sample)
```

Sampling is reproducible and without replacement. Every populated stratum needs a
positive sample size no larger than its population. Returned weights are `N/n`; a census
has weight 1. Pass sample metadata separately to analysis so these weights survive.
Claim-ID joins are one-to-one and reject duplicates or collisions. Unextracted, failed,
skipped, and successful sections have distinct status columns. Feature-level unknowns
remain missing, not negative. Extraction failures are not corrected by sampling weights.

## Analysis and modeling

```powershell
uv run python -m ad_hoc.hover_supplements analyze population.csv data/hover_research/report --extractions data/hover_research/extractions.jsonl --audited-metadata sample.jsonl --config research.json
```

CSV is supported for structured population/sample metadata; JSON and JSONL are also
supported. Bundles require the extraction command. Analysis does not call an LLM and
can be rerun independently. A population-only run needs no extractions. Required analysis
columns are `claim_id`, boolean `hover`, and `supplement_approved_amount`; the default
statistical configuration additionally expects `peril` and `sub_peril` (nullable).
Optional financial fields remain missing when absent. `sampling_weight` defaults to 1.

Example `research.json` for enriched adjustment:

```json
{
  "tier": "enriched",
  "covariates": ["peril", "baseline__property_complexity__stories"],
  "pretreatment_rationale": {
    "baseline__property_complexity__stories": "Physical property attribute predates capture selection."
  },
  "bootstrap_replicates": 500,
  "seed": 42
}
```

`ResearchConfig` selects one explicit covariate list. `structured` permits peril, sub-peril,
derived loss month, and FNOL delay; `enriched` adds baseline fields with explicit
pre-treatment rationales. `secondary` permits initial-estimate amounts and process/quality
features. Supplement fields, IDs, narratives, and weights cannot become covariates. The
reference schema calls its initial features baseline; that alone does not make them
pre-Hover variables. Quality and estimate-size variables are therefore secondary only.

Statistical fitting uses weighted logistic incidence and Gamma/log positive severity,
then standardizes both cohorts to the same observed population. Conditional standardized
severity uses predicted-incidence weights, so incidence times severity equals expected
dollars. Bootstrap resamples within Hover and supplied sampling strata and refits all
preprocessing and models. Intervals represent claim-sampling uncertainty; they do not
include LLM classification error or catastrophe/adjuster clustering. Redundant case-mix
columns are reported and removed. Collinearity of Hover with case mix/calendar makes
the comparison unsupported rather than silently dropping a confounder.

The full population supplies structured scorecards; weighted audited data supplies LLM
quality and mechanism analysis. Reports include coverage, missingness, effective sample
size, cohort distributions, date ranges, bootstrap failures, and unsupported-model reasons.
Mechanism flags overlap; their rates are not an additive decomposition. Primary mechanism
and avoidability distributions retain unknown categories, population shares, and shares
among approved supplements. Dollars by classification are associated claim dollars, not
recoverable savings or causal dollar allocations to individual mechanisms. The symmetric
incidence/severity decomposition does reconcile to the difference in mean approved dollars.

Prediction uses random forests and a GLM benchmark with preprocessing fit only on training
claims. Use chronological holdout when all loss dates are valid and varied; otherwise use
stratified holdout. Report weighted AUC, average precision, Brier score/calibration, severity
MAE, and combined dollar MAE. Permutation importance and partial dependence explain
prediction, not causal effects. Shallow trees discover segments using training case mix
(never splitting on Hover itself); cohort comparisons use held-out claims and require the
configured minimum count in each cohort. Small or single-cohort segments remain unsupported.

Outputs include CSV tables, `research.json`, `summary.md`, local Plotly HTML charts,
field-level evidence examples, and the complete feature dictionary. Returned predictive
objects retain fitted sklearn pipelines in memory; reports omit executable model objects.
Private research output under `backend/data/hover_research` is git-ignored.

## Business questions and explainability

Open `business_report.html` after `write_report` or any analysis/demo CLI run. This is a
self-contained, offline Plotly report organized around eight questions: outcomes, claim
mix and estimate quality, supplement drivers, potential avoidability, segments, prediction
drivers, individual claim explanations, and confidence/coverage. Charts separate dollars,
percentages, and percentage-point differences. Expandable tables retain exact estimates,
denominators, unknown counts, and interpretable GLM coefficient contrasts. The companion
`business_answers.csv`, `.json`, and `.md` provide concise question-level findings.

```python
from ad_hoc.hover_supplements import (
    business_question_answers, build_business_figures,
    claim_explanation_figure, render_business_report,
)

display(business_question_answers(report))
figures = build_business_figures(report)
figures["dollar_decomposition"].show()
explanations = report["predictive"]["explanations"]
if explanations["status"] == "success":
    claim_id = explanations["predictions"].claim_id.iloc[0]
    claim_explanation_figure(explanations, claim_id).show()
render_business_report(report, "data/hover_research/business")
```

Both rendering helpers also accept the deserialized `research.json`, so reports can be
rebuilt without models, credentials, extraction, or refitting. `build_business_figures`
returns ordinary Plotly figures for notebook display or custom exports. All displayed
claim/evidence text is HTML-escaped. Reports contain supplied claim data; keep exported
artifacts within the study's authorized audience.

SHAP is optional: install the `explainability` dependency group to enable it. Configure
`shap_enabled` (default true), `shap_max_claims` (200), and `shap_background_size` (100)
in `ResearchConfig` or the CLI configuration JSON. Missing SHAP, unsupported cohorts,
and explanation failures appear explicitly in the report; ordinary analysis still runs.

Held-out Tree SHAP explains the random forest's incidence probability in percentage
points and positive severity in dollars. Background samples come only from training
claims, sampled proportional to study weights; severity uses positive training claims.
One-hot categories and missingness indicators are grouped back to their original fields.
Every local explanation is checked to reconstruct the exact pipeline prediction. Global
charts show weighted mean absolute contributions, which measure magnitude, not direction;
signed contribution charts and claim waterfalls supply direction. Background IDs, method,
coverage, and reconstruction error remain in the exported explanation data.

The combined expected-dollar waterfall uses an exact symmetric product allocation of
the separate probability and severity contributions. It is **not joint SHAP** and its
baseline is the product of the two model reference predictions. It does not allocate
observed claim dollars to causes or identify recoverable savings. Evidence tables connect
baseline inputs to extraction citations and structured inputs to caller-supplied metadata.
Representative prediction examples include high/middle/low risk and the largest dollar
error, rather than selecting only favorable cases.

Interpret importance alongside held-out accuracy and the training-mean benchmark.
Correlated inputs can share or obscure importance; partial dependence can evaluate
implausible feature combinations. Segment rules use original units and compare held-out
cohorts only when both raw and effective counts meet the configured minimum. These are
exploratory associations. Supplement mechanism features never enter cutoff prediction.
See [TreeExplainer documentation](https://shap.readthedocs.io/en/latest/generated/shap.TreeExplainer.html)
and [permutation importance guidance](https://scikit-learn.org/stable/modules/permutation_importance.html).

## Validation

The report uses the supplied Liberty palette: blue `#1A1446`, dark teal `#06748C`,
medium teal `#28A3AF`, and yellow `#FFD000`. Each section states its target or measure
and provides an expandable methodology note. Statistical families/links, weighting,
bootstrap rules, preprocessing, actual train/holdout counts, and captured fitted forest
and segment-tree parameters remain available to technical reviewers. Older saved runs
without parameter metadata are explicitly identified instead of inventing settings.

The version-2 synthetic generator covers two years, four perils, heterogeneous property
complexity, lognormal initial costs, Gamma supplement severity, partial denials and
unresolved requests, eight primary mechanisms, overlapping drivers, varied avoidability,
and missing initial evidence. Cohort selection and outcomes contain programmed associations;
they are not calibrated to actual claims or evidence of Hover effectiveness. Offline test
models read explicit fictional field records in the evidence. This validates workflow
plumbing, not the accuracy of natural-language extraction. Demo reports carry a visible
synthetic banner; the CLI demo uses enriched physical-property and damage covariates.

```powershell
uv run --group explainability python -m ad_hoc.hover_supplements demo data/hover_research/liberty-demo --claims 800 --bootstrap 40
```

```powershell
uv run --group explainability pytest tests/test_hover_supplements.py tests/test_hover_outputs.py tests/test_review_agent_runtime_metadata.py
uv run ruff check ad_hoc tests/test_hover_supplements.py tests/test_hover_outputs.py
```

These tests use synthetic data and test models. They do not establish accuracy on real
claim files; representative-claim review is part of conducting the actual study.
