"""Human-readable method notes, grounded in saved configuration and fitted parameters."""

import json
from html import escape


def methodology_details(section, report):
    config = report.get("configuration", {})
    predictive = report.get("predictive", {})
    forest = predictive.get("model_parameters", {}).get("classifier", {})
    inputs = ", ".join(["hover", *config.get("covariates", [])])
    target = {
        "impact": (
            "Outcome: positive approved additional dollars. Requests with zero "
            "approved dollars count as no approved supplement, not as missing claims."
        ),
        "quality": (
            "Measures: initial-evidence quality and pre-treatment case mix; "
            "quality features are secondary adjustment only."
        ),
        "mechanisms": (
            "Measures: main and remaining classifications plus whole-history drivers. "
            "All-claim views include denied requests."
        ),
        "avoidability": (
            "Measure: main and remaining avoidability plus whole-history prevention areas; "
            "not predicted recoverable savings."
        ),
        "segments": (
            "Tree target: approved-supplement incidence. Segment comparisons use "
            "held-out observed dollars."
        ),
        "explain": (
            "Prediction targets: approval incidence and positive approved "
            "dollars. Expected dollars = probability × positive severity."
        ),
        "claims": (
            "Explanations target model predictions at the initial-estimate "
            "cutoff, not the causes of actual claim payments."
        ),
        "coverage": (
            "Scope: full structured population for basic outcomes; weighted "
            "audited claims for extracted findings."
        ),
    }[section]
    common = [
        ("Analysis tier", config.get("tier", "Not recorded")),
        ("Selected model inputs", inputs),
        (
            "Reproducibility",
            f"Seed {config.get('seed', 'not recorded')}; "
            "saved results can be re-rendered without fitting.",
        ),
    ]
    notes = {
        "impact": [
            (
                "Estimands",
                (
                    "Weighted approval incidence; severity among positive approved "
                    "claims; approved dollars per claim; mean claim-level "
                    "approved/initial ratio. Missing outcomes are excluded explicitly, "
                    "not treated as zero."
                ),
            ),
            (
                "Statistical model",
                (
                    "Statsmodels GLM: Binomial with logit link for incidence; Gamma with "
                    "log link among positive approved claims. IRLS, maximum 100 "
                    "iterations. Study weights enter as frequency weights."
                ),
            ),
            (
                "Standardization",
                (
                    "Set Hover to each status over the same reference claims and average "
                    "predictions with study weights. These are adjusted associations. "
                    "Conditional severity uses predicted-incidence weights."
                ),
            ),
            (
                "Uncertainty",
                f"{config.get('bootstrap_replicates', 'Not recorded')} "
                f"configured bootstrap replicates; refit preprocessing "
                f"and both GLMs per replicate within cohort/sampling "
                f"strata. 95% percentile intervals require at least "
                f"30 successful fits and 80% success.",
            ),
            (
                "Dollar decomposition",
                (
                    "Symmetric identity: Δp × mean(s) + Δs × mean(p), where p is "
                    "incidence and s is conditional severity. The terms sum to the raw "
                    "dollar difference."
                ),
            ),
            *common,
        ],
        "quality": [
            (
                "Evidence boundary",
                (
                    "Baseline extraction only sees caller-designated initial evidence. "
                    "Later documents are excluded. Unknown answers remain distinct from "
                    "negative findings."
                ),
            ),
            (
                "Balance",
                (
                    "Standardized mean differences compare selected covariates before "
                    "adjustment. Zero indicates balance; this does not test unmeasured "
                    "confounding."
                ),
            ),
            (
                "Quality rates",
                (
                    "Weighted positive findings among known answers. Missingness chart "
                    "uses unweighted claim counts. Higher is not always better: omitted "
                    "items and documentation gaps are adverse findings."
                ),
            ),
        ],
        "mechanisms": [
            (
                "Extraction",
                (
                    "A separate structured Pydantic AI pass compares initial and later "
                    "evidence; caller financials remain authoritative. Synthetic runs use "
                    "programmed TestModel outputs, not a live LLM."
                ),
            ),
            (
                "Denominators",
                (
                    "Driver flags show positive findings among known answers within all "
                    "claims or positive-approved claims. Primary categories are mutually "
                    "exclusive; overlapping flags must not be summed."
                ),
            ),
            (
                "Provenance",
                (
                    "Field-path citations point to supplied evidence IDs. They support "
                    "review, not automatic verification of the interpretation."
                ),
            ),
        ],
        "avoidability": [
            (
                "Classification",
                (
                    "Evidence-based retrospective assessment with unclear cases retained. "
                    "No deterministic rule converts model predictions into avoidability."
                ),
            ),
            (
                "Dollar accounting",
                (
                    "Each claim contributes its approved dollars to its single "
                    "avoidability class, divided by population weight in the chart. "
                    "Associated dollars are not a causal allocation or savings estimate."
                ),
            ),
            (
                "Prevention-area dollars",
                (
                    "Sum documented approved supplement dollars times study weights for claims "
                    "with the prevention area marked yes, then divide by all audited cohort "
                    "claim weight. Areas overlap, so claim dollars can appear in several bars. "
                    "Missing classifications and positive-claim dollar amounts are reported; "
                    "totals include only documented amounts and are not additive savings."
                ),
            ),
        ],
        "segments": [
            (
                "Discovery model",
                (
                    "Sklearn DecisionTreeClassifier; maximum depth 2; weighted training "
                    "incidence target; Hover itself is excluded from split variables."
                ),
            ),
            (
                "Support threshold",
                f"Minimum {config.get('min_segment_size', 'not recorded')} "
                f"raw AND effective held-out claims in each cohort. "
                f"Unsupported leaves remain visible in tables.",
            ),
            (
                "Interpretation",
                (
                    "Rules use original feature units after inverting numeric scaling. "
                    "Missing values can be imputed. Leaf differences are exploratory, not "
                    "validated treatment-effect estimates."
                ),
            ),
        ],
        "explain": [
            (
                "Forest settings",
                f"Trees: {forest.get('n_estimators', 'not recorded')}; "
                f"minimum leaf size: {forest.get('min_samples_leaf', 'not recorded')}; "
                f"maximum depth: {forest.get('max_depth', 'not recorded')} "
                "(None means unlimited). Exact classifier, severity-regressor and "
                "segment-tree settings are captured below; their defaults can differ.",
            ),
            (
                "Model families",
                (
                    "Sklearn RandomForestClassifier for incidence and "
                    "RandomForestRegressor trained only on positive approved dollars. "
                    "Independent preprocessing is fit on each training population. GLM "
                    "and training-mean benchmarks use the same holdout."
                ),
            ),
            (
                "Split",
                f"Actual split: {predictive.get('split', 'unavailable')}; "
                f"train n={len(predictive.get('train_claim_ids', []))}, "
                f"held-out n={len(predictive.get('test_claim_ids', []))}. "
                f"Requested holdout fraction={config.get('test_fraction', 'not recorded')}. "
                f"Chronological when complete dates permit; otherwise "
                f"stratified by outcome.",
            ),
            (
                "Preprocessing",
                (
                    "Training-only median imputation with missing indicators and numeric "
                    "scaling; categorical imputation and one-hot encoding. Unseen "
                    "categories map to the reference encoding. Supplement features are "
                    "prohibited."
                ),
            ),
            (
                "Accuracy",
                (
                    "ROC AUC and average precision measure ranking (higher better); Brier "
                    "loss measures probability error (lower better); severity MAE uses "
                    "positive cases and dollar MAE uses all held-out cases. All use study "
                    "weights."
                ),
            ),
            (
                "Permutation / response curves",
                (
                    "Five held-out permutations per feature, scored by increase in Brier "
                    "loss. Error bars are permutation variability. Partial dependence "
                    "averages counterfactual model inputs; correlated features can create "
                    "unrealistic combinations."
                ),
            ),
            *common,
        ],
        "claims": [
            (
                "SHAP",
                (
                    "Interventional Tree SHAP with training-only, "
                    "study-weight-proportional background samples; positive-only "
                    "background for severity. Encoded contributions are grouped to "
                    "original features and checked for additivity."
                ),
            ),
            (
                "Budget",
                f"At most {config.get('shap_max_claims', 'not recorded')} "
                "uniformly sampled held-out claims; "
                f"{config.get('shap_background_size', 'not recorded')} "
                f"background draws per model. Global averages retain "
                f"study weights.",
            ),
            (
                "Dollar bridge",
                (
                    "For each feature: probability SHAP × mean(reference,predicted "
                    "severity) + severity SHAP × mean(reference,predicted probability). "
                    "Exact product reconciliation, but not joint SHAP."
                ),
            ),
            (
                "Example selection",
                (
                    "High, middle and low predicted incidence plus largest dollar error; "
                    "duplicates removed. Sources refer to model inputs, not proof of "
                    "causal drivers."
                ),
            ),
        ],
        "coverage": [
            (
                "Sampling",
                (
                    "Stratified audit inclusion probabilities produce inverse-probability "
                    "study weights. Effective n = (sum weights)² / sum squared weights."
                ),
            ),
            (
                "Limits",
                (
                    "Weights do not correct extraction failures. Bootstrap intervals omit "
                    "LLM error and event/adjuster clustering. Calendar range overlap "
                    "alone does not establish comparable cohorts."
                ),
            ),
        ],
    }[section]
    body = (
        "<dl>"
        + "".join(f"<dt>{escape(k)}</dt><dd>{escape(str(v))}</dd>" for k, v in notes)
        + "</dl>"
    )
    if section in {"explain", "segments"}:
        params = predictive.get("model_parameters")
        body += (
            "<h4>Fitted estimator parameters</h4><pre>"
            + escape(
                json.dumps(params, indent=2)
                if params
                else (
                    "Parameters were not captured in this saved run; rerun analysis to record them."
                )
            )
            + "</pre>"
        )
    return (
        f'<p class="target">{escape(target)}</p><details class="method">'
        "<summary>Methodology · targets, assumptions and implementation</summary>"
        + body
        + "</details>"
    )
