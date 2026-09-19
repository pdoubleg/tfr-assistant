"""Prediction reconstruction, business metrics, and portable report acceptance tests."""

import json

import numpy as np
import pandas as pd
import pytest

from ad_hoc.hover_supplements import ResearchConfig, run_analysis
from ad_hoc.hover_supplements.explainability import explain_tree_predictions
from ad_hoc.hover_supplements.modeling import run_predictive_research
from ad_hoc.hover_supplements.synthetic import synthetic_bundles
from ad_hoc.hover_supplements.visualization import (
    build_business_figures,
    business_question_answers,
    claim_explanation_figure,
    render_business_report,
)


@pytest.fixture(scope="module")
def explained():
    pytest.importorskip("shap")
    frame = pd.DataFrame([b.metadata() for b in synthetic_bundles(140)])
    frame.loc[:10, "initial_estimate_amount"] = np.nan
    frame["sampling_weight"] = 1 + np.arange(len(frame)) % 3
    config = ResearchConfig(
        tier="secondary",
        covariates=["peril", "initial_estimate_amount"],
        bootstrap_replicates=0,
        trees=10,
        shap_max_claims=15,
        shap_background_size=10,
    )
    result = run_predictive_research(frame, config)
    assert result["status"] == "success"
    assert result["explanations"]["status"] == "success", result["explanations"].get("reason")
    return frame, result


def test_shap_aggregation_additivity_and_training_only_background(explained):
    frame, result = explained
    explanation = result["explanations"]
    local = explanation["local_contributions"]
    predictions = explanation["predictions"].set_index("claim_id")
    assert set(local.feature) == {"hover", "peril", "initial_estimate_amount"}
    assert local.groupby("claim_id").size().eq(3).all()
    assert set(local.claim_id).issubset(result["test_claim_ids"])
    assert set(explanation["incidence_background_ids"]).issubset(result["train_claim_ids"])
    positive_ids = set(frame.loc[frame.supplement_approved_amount.gt(0), "claim_id"])
    assert set(explanation["severity_background_ids"]).issubset(positive_ids)
    totals = local.groupby("claim_id")[
        ["incidence_shap_pp", "severity_shap_dollars", "two_part_dollar_allocation"]
    ].sum()
    predictions = predictions.loc[totals.index]
    np.testing.assert_allclose(
        predictions.base_probability + totals.incidence_shap_pp / 100,
        predictions.probability,
        atol=1e-6,
    )
    np.testing.assert_allclose(
        predictions.base_severity + totals.severity_shap_dollars,
        predictions.conditional_severity,
        atol=0.001,
    )
    np.testing.assert_allclose(
        predictions.base_product_dollars + totals.two_part_dollar_allocation,
        predictions.expected_dollars,
        atol=0.001,
    )
    assert "NOT joint SHAP" in explanation["dollar_method"]
    assert "training_mean_baseline" in result["metrics"].model.values


def test_claim_waterfall_reconciles_when_truncated(explained):
    _, result = explained
    explanation = result["explanations"]
    claim_id = explanation["predictions"].claim_id.iloc[0]
    for output in ("incidence", "severity", "expected_dollars"):
        fig = claim_explanation_figure(explanation, claim_id, output=output, top_n=1)
        trace = fig.data[0]
        assert "Other features" in trace.x
        assert sum(trace.y[:-1]) == pytest.approx(trace.y[-1], rel=1e-5, abs=1e-4)
    with pytest.raises(ValueError, match="not in the explained"):
        claim_explanation_figure(explanation, "unknown")


def test_explanation_rejects_overlapping_claims(explained):
    frame, result = explained
    metadata = frame.iloc[:5]
    features = metadata[["hover", "peril", "initial_estimate_amount"]]
    with pytest.raises(ValueError, match="overlap"):
        explain_tree_predictions(
            result["classifier"], result["regressor"], features, features, metadata, metadata
        )


def test_business_answers_units_and_no_uncertainty_invention():
    scores = pd.DataFrame(
        [
            {"hover": False, "metric": "supplement_incidence", "estimate": 0.2},
            {"hover": True, "metric": "supplement_incidence", "estimate": 0.25},
        ]
    )
    report = {
        "tables": {"population_scorecard": scores},
        "selected_model": {
            "status": "success",
            "tier": "structured",
            "estimates": pd.DataFrame(
                [
                    {
                        "comparison": "difference",
                        "metric": "incidence",
                        "estimate": 0.05,
                        "lower_95": -0.02,
                        "upper_95": 0.12,
                    },
                ]
            ),
        },
    }
    answers = business_question_answers(report)
    assert "+5.0 percentage points" in answers.iloc[0].answer
    assert any("interval includes zero" in answer for answer in answers.answer)
    report["selected_model"]["estimates"]["lower_95"] = np.nan
    answers = business_question_answers(report)
    assert any("interval is unavailable" in answer for answer in answers.answer)


def test_business_report_without_shap_and_with_serialized_data(tmp_path):
    frame = pd.DataFrame([b.metadata() for b in synthetic_bundles(80)])
    report = run_analysis(
        frame, config=ResearchConfig(bootstrap_replicates=0, trees=10, shap_enabled=False)
    )
    figures = build_business_figures(report)
    assert set(
        ["supplement_incidence", "approved_dollars_per_claim", "calibration", "shap_status"]
    ).issubset(figures)
    assert figures["supplement_incidence"].layout.yaxis.title.text.endswith("(%)")
    assert figures["approved_dollars_per_claim"].layout.yaxis.title.text.endswith("($)")
    from ad_hoc.hover_supplements.runner import _json_safe

    serialized = json.loads(json.dumps(_json_safe(report)))
    path = render_business_report(serialized, tmp_path)
    html = path.read_text(encoding="utf-8")
    assert html.count('id="plot-') == len(figures)
    assert 'src="https://cdn.plot.ly' not in html
    assert "Disabled in ResearchConfig" in html
    for identifier in [
        "impact",
        "quality",
        "mechanisms",
        "avoidability",
        "segments",
        "explain",
        "claims",
        "coverage",
    ]:
        assert f'id="{identifier}"' in html
    assert (tmp_path / "business_answers.csv").exists()


def test_report_escapes_evidence_text(tmp_path):
    frame = pd.DataFrame([b.metadata() for b in synthetic_bundles(30)])
    report = run_analysis(
        frame, config=ResearchConfig(bootstrap_replicates=0, trees=5, shap_enabled=False)
    )
    payload = '<script>alert("claim")</script>'
    report["tables"]["representative_claims"] = pd.DataFrame(
        [{"claim_id": "demo", "summary": payload}]
    )
    html = render_business_report(report, tmp_path).read_text(encoding="utf-8")
    assert payload not in html
    assert "&lt;script&gt;" in html


def test_synthetic_diversity_reproducibility_and_method_metadata():
    from ad_hoc.hover_supplements.report_methods import methodology_details
    from ad_hoc.hover_supplements.synthetic import synthetic_models

    bundles = synthetic_bundles(400)
    assert [b.model_dump() for b in bundles] == [b.model_dump() for b in synthetic_bundles(400)]
    assert len({b.peril for b in bundles}) == 4
    assert (max(b.dol for b in bundles) - min(b.dol for b in bundles)).days > 700
    assert any(
        b.supplement_activity == "yes" and b.supplement_approved_amount == 0 for b in bundles
    )
    assert any(
        b.supplement_requested_amount > b.supplement_approved_amount + b.supplement_denied_amount
        for b in bundles
    )
    primary, avoidability, quality = set(), set(), set()
    for bundle in bundles:
        baseline, supplement = synthetic_models(bundle)
        quality.add(
            baseline.custom_output_args["features"]["documentation"]["documentation_quality"]
        )
        if bundle.supplement_activity == "yes":
            primary.add(supplement.custom_output_args["features"]["primary_mechanism"])
            avoidability.add(supplement.custom_output_args["features"]["potentially_avoidable"])
    assert len(primary) == 8
    assert len(avoidability) == 5
    assert quality == {"high", "moderate", "low", "unknown"}
    html = methodology_details(
        "explain",
        {
            "configuration": {"seed": 91, "covariates": ["<unsafe>"], "test_fraction": 0.3},
            "predictive": {
                "split": "chronological",
                "train_claim_ids": ["a"],
                "test_claim_ids": ["b"],
                "model_parameters": {"classifier": {"n_estimators": 17}},
            },
        },
    )
    assert "Seed 91" in html and "17" in html
    assert "train n=1" in html and "held-out n=1" in html
    assert "&lt;unsafe&gt;" in html and "<unsafe>" not in html
