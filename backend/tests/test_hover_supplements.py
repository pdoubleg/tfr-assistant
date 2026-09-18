"""Offline acceptance tests for standalone extraction and research behavior."""

import asyncio
import json
import os
import subprocess
import sys
from datetime import date

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError
from pydantic_ai.models.test import TestModel as OfflineModel

from ad_hoc.hover_supplements import (
    ClaimBundle,
    ResearchConfig,
    build_feature_table,
    decompose_dollar_difference,
    extract_batch,
    extract_claim,
    feature_dictionary,
    fit_statistical_models,
    mechanism_analysis,
    run_predictive_research,
    scorecards,
    stratified_sample,
)
from ad_hoc.hover_supplements.agents import unknown_features
from ad_hoc.hover_supplements.contracts import BaselineOutput, EvidenceReference
from ad_hoc.hover_supplements.dataframes import derive_outcomes
from ad_hoc.hover_supplements.evidence import EvidenceStore
from ad_hoc.hover_supplements.models import (
    BaselineClaimFeatures,
    ClaimLLMFeatures,
    SupplementMechanismFeatures,
)
from ad_hoc.hover_supplements.runner import cache_key
from ad_hoc.hover_supplements.synthetic import synthetic_bundles, synthetic_models
from app.core.llm import LLMModelAPI, LLMModelConfig

TEST_CONFIG = LLMModelConfig(model_name="test", api=LLMModelAPI.TEST)


@pytest.fixture
def bundle():
    return next(b for b in synthetic_bundles(20) if b.supplement_activity == "yes")


def run_claim(bundle, **kwargs):
    baseline, supplement = synthetic_models(bundle)
    return asyncio.run(
        extract_claim(
            bundle,
            TEST_CONFIG,
            baseline_model=kwargs.get("baseline_model", baseline),
            supplement_model=supplement,
        )
    )


def test_reference_schema_inventory_and_conversion():
    dictionary = feature_dictionary()
    assert len(dictionary) == 124
    assert dictionary.field.is_unique
    assert dictionary.description.notna().all()
    baseline = unknown_features(BaselineClaimFeatures)
    baseline.property_complexity.roof_involved = "no"
    baseline.initial_estimate_cutoff_date = date(2024, 1, 3)
    supplement = unknown_features(SupplementMechanismFeatures)
    combined = ClaimLLMFeatures(baseline=baseline, supplement_mechanism=supplement)
    assert ClaimLLMFeatures.model_validate_json(combined.model_dump_json()) == combined
    df = combined.to_pandas()
    assert df["baseline__property_complexity__roof_involved"].dtype == "boolean"
    assert not df.iloc[0]["baseline__property_complexity__roof_involved"]
    assert pd.isna(df.iloc[0]["baseline__property_complexity__exterior_involved"])
    assert pd.api.types.is_datetime64_any_dtype(df["baseline__initial_estimate_cutoff_date"])
    assert "baseline__baseline_summary" not in df
    assert "baseline__baseline_summary" in combined.to_pandas(drop_text=False)
    assert set(supplement.to_pandas()) == {c for c in df if c.startswith("supplement_mechanism__")}


def test_evidence_cutoff_duplicate_ids_and_scope(bundle):
    payload = bundle.model_dump()
    payload["initial_evidence"][0]["date"] = date(2099, 1, 1)
    with pytest.raises(ValidationError, match="after the cutoff"):
        ClaimBundle.model_validate(payload)
    payload = bundle.model_dump()
    payload["later_evidence"][0]["id"] = "initial"
    with pytest.raises(ValidationError, match="unique"):
        ClaimBundle.model_validate(payload)
    store = EvidenceStore(tuple(bundle.initial_evidence))
    with pytest.raises(ValueError, match="unavailable"):
        store.get_evidence("later")
    with pytest.raises(ValueError, match="outside"):
        store.validate_references(
            unknown_features(BaselineClaimFeatures),
            [
                EvidenceReference(
                    field_path="damage.water_damage",
                    evidence_ids=["later"],
                    explanation="Not available",
                )
            ],
        )


def test_baseline_rejects_later_citation_and_outcomes_do_not_leak(bundle):
    features = unknown_features(BaselineClaimFeatures)
    output = BaselineOutput(
        features=features,
        evidence=[
            EvidenceReference(
                field_path="damage.water_damage",
                evidence_ids=["later"],
                explanation="Invalid later citation",
            )
        ],
    )
    model = OfflineModel(call_tools=[], custom_output_args=output.model_dump(mode="json"))
    result = run_claim(bundle, baseline_model=model)
    assert result.baseline.status == "failed"
    assert result.supplement.status == "success"
    assert result.status == "failed"


def test_denied_request_runs_and_no_activity_skips(bundle):
    denied = bundle.model_copy(update={"supplement_approved_amount": 0.0})
    result = run_claim(denied)
    assert result.supplement.status == "success"
    assert result.supplement.features.financials.supplement_pct_of_initial_estimate == 0
    no_activity = next(b for b in synthetic_bundles(20) if b.supplement_activity == "no")
    skipped = run_claim(no_activity)
    assert skipped.supplement.status == "skipped"
    assert skipped.supplement.features.primary_mechanism == "not_applicable"
    assert skipped.status == "success"


def test_id_join_authority_missing_amount_and_discrepancy(bundle):
    baseline, _ = synthetic_models(bundle)
    baseline.custom_output_args["features"]["initial_estimate"]["initial_estimate_amount"] = 999
    result = run_claim(bundle, baseline_model=baseline)
    assert result.discrepancies[0]["authoritative"] == bundle.initial_estimate_amount
    other = bundle.model_copy(update={"claim_id": "other", "supplement_approved_amount": None})
    frame = build_feature_table([result], [other.metadata(), bundle.metadata()])
    assert frame.iloc[0].extraction_status == "not_extracted"
    assert pd.isna(frame.iloc[0].supplement_incidence)
    assert frame.iloc[1].initial_estimate_amount == bundle.initial_estimate_amount
    assert frame.iloc[1]["baseline__initial_estimate__initial_estimate_amount"] == 999
    assert frame.iloc[1].supplement_ratio == pytest.approx(
        bundle.supplement_approved_amount / bundle.initial_estimate_amount
    )
    with pytest.raises(ValueError, match="unique"):
        build_feature_table([result, result], [bundle.metadata()])
    zeros = derive_outcomes(pd.DataFrame([dict(bundle.metadata(), initial_estimate_amount=0)]))
    assert pd.isna(zeros.iloc[0].supplement_ratio)


def test_weighted_scorecard_decomposition_and_sampling():
    frame = pd.DataFrame(
        {
            "claim_id": list("abcd"),
            "hover": [False, False, True, True],
            "supplement_approved_amount": [0, 100, 0, 200],
            "sampling_weight": [3, 1, 1, 1],
        }
    )
    scores = scorecards(frame).set_index(["hover", "metric"])
    assert scores.loc[(False, "supplement_incidence"), "estimate"] == 0.25
    assert scores.loc[(True, "approved_dollars_per_claim"), "estimate"] == 100
    d = decompose_dollar_difference(frame)
    assert d["incidence_contribution"] == 37.5
    assert d["severity_contribution"] == 37.5
    assert d["total_difference"] == 75
    population = pd.concat(
        [frame.assign(claim_id=frame.claim_id + str(i)) for i in range(4)], ignore_index=True
    )
    sample = stratified_sample(
        population, {(h, s): 2 for h in (False, True) for s in (False, True)}
    )
    assert len(sample) == 8
    assert (sample.inclusion_probability == 0.5).all()
    assert (sample.sampling_weight == 2).all()
    assert sample.equals(
        stratified_sample(population, {(h, s): 2 for h in (False, True) for s in (False, True)})
    )


def test_overlapping_mechanisms_do_not_duplicate_dollars(bundle):
    result = run_claim(bundle)
    result.supplement.features.scope.missed_item = "yes"
    frame = build_feature_table([result], [bundle.metadata()])
    analysis = mechanism_analysis(frame)
    flags = analysis["mechanism_rates"]
    assert "associated_approved_dollars" not in flags
    assert len(flags[(flags.positive_n == 1) & (flags.denominator == "all_claims")]) >= 2
    groups = analysis["classifications"]
    primary = groups[groups.classification.str.endswith("primary_mechanism")]
    assert primary.associated_approved_dollars.sum() == bundle.supplement_approved_amount


def test_checkpoint_resume_and_failed_not_reused(tmp_path, bundle, monkeypatch):
    from ad_hoc.hover_supplements import runner

    results = asyncio.run(extract_batch([bundle], TEST_CONFIG, checkpoint_dir=tmp_path, demo=True))
    assert results[0].status == "success"
    original = runner.extract_claim
    calls = []

    async def counting(*args, **kwargs):
        calls.append(True)
        return await original(*args, **kwargs)

    monkeypatch.setattr(runner, "extract_claim", counting)
    asyncio.run(extract_batch([bundle], TEST_CONFIG, checkpoint_dir=tmp_path, demo=True))
    assert not calls
    result = results[0]
    result.baseline.status = "failed"
    path = tmp_path / f"{result.cache_key}.json"
    path.write_text(result.model_dump_json(), encoding="utf-8")
    rerun = asyncio.run(extract_batch([bundle], TEST_CONFIG, checkpoint_dir=tmp_path, demo=True))
    assert calls and rerun[0].status == "success"
    assert cache_key(bundle, TEST_CONFIG, demo=True) != cache_key(bundle, TEST_CONFIG)
    changed = bundle.model_copy(update={"hover": not bundle.hover})
    assert cache_key(changed, TEST_CONFIG) != cache_key(bundle, TEST_CONFIG)


@pytest.mark.parametrize(
    "column,tier",
    [
        ("supplement_mechanism__scope__missed_item", "secondary"),
        ("initial_estimate_amount", "structured"),
        ("baseline__documentation__photo_documentation_adequate", "enriched"),
        ("baseline__property_complexity__roof_involved", "enriched"),
        ("claim_id", "structured"),
    ],
)
def test_covariate_restrictions(column, tier):
    with pytest.raises(ValueError):
        ResearchConfig(covariates=[column], tier=tier).validate()


def test_statistical_models_and_bootstrap_reproducibility():
    rng = np.random.default_rng(7)
    n = 600
    hover = np.arange(n) % 2 == 0
    incidence = rng.random(n) < np.where(hover, 0.7, 0.25)
    frame = pd.DataFrame(
        {
            "claim_id": [str(i) for i in range(n)],
            "hover": hover,
            "supplement_approved_amount": incidence * rng.gamma(4, 100, n),
        }
    )
    config = ResearchConfig(covariates=[], bootstrap_replicates=30)
    result = fit_statistical_models(frame, config)
    assert result["status"] == "success", result.get("reason")
    assert result["interval_status"] == "available"
    delta = (
        result["estimates"].query("comparison == 'difference' and metric == 'incidence'").iloc[0]
    )
    assert 0.3 < delta.estimate < 0.6
    assert delta.lower_95 > 0
    repeat = fit_statistical_models(frame, config)
    pd.testing.assert_frame_equal(result["estimates"], repeat["estimates"])
    unsupported = fit_statistical_models(frame.assign(supplement_approved_amount=0), config)
    assert unsupported["status"] == "unsupported"


def test_predictive_holdout_and_preprocessing_isolation():
    frame = pd.DataFrame([b.metadata() for b in synthetic_bundles(150)])
    frame.loc[frame.index[-30:], "peril"] = "ONLY_IN_TEST"
    config = ResearchConfig(covariates=["peril"], trees=10, bootstrap_replicates=0)
    result = run_predictive_research(frame, config)
    assert result["status"] == "success"
    assert result["split"] == "chronological"
    assert not set(result["train_claim_ids"]) & set(result["test_claim_ids"])
    encoder = (
        result["classifier"]
        .named_steps["prepare"]
        .named_transformers_["categorical"]
        .named_steps["encode"]
    )
    assert "ONLY_IN_TEST" not in encoder.categories_[0]
    assert not result["calibration"].empty
    assert not result["partial_dependence"].empty
    assert not result["segments"].empty


def test_package_import_without_credentials_or_database():
    env = {k: v for k, v in os.environ.items() if "OPENAI" not in k}
    script = """
import sys
import ad_hoc.hover_supplements
assert 'app.main' not in sys.modules
assert 'app.services.audit_generation' not in sys.modules
assert not any(k.startswith('app.db') for k in sys.modules)
"""
    subprocess.run([sys.executable, "-c", script], check=True, env=env, timeout=60)


def test_actual_baseline_tool_calls_never_receive_later_evidence(bundle):
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    from ad_hoc.hover_supplements.agents import extract_baseline

    payload = bundle.model_dump()
    payload["later_evidence"][0]["text"] = "LATER_ONLY_MARKER_912345"
    payload["supplement_approved_amount"] = 912345
    bundle = ClaimBundle.model_validate(payload)
    snapshots = []

    def fake_model(messages, info):
        snapshots.append(repr(messages) + str(info.instructions))
        if len(snapshots) == 1:
            part = ToolCallPart("list_evidence", {})
        elif len(snapshots) == 2:
            part = ToolCallPart("get_evidence", {"evidence_id": "initial"})
        else:
            output = BaselineOutput(features=unknown_features(BaselineClaimFeatures))
            part = ToolCallPart(info.output_tools[0].name, output.model_dump(mode="json"))
        return ModelResponse(parts=[part])

    result = asyncio.run(extract_baseline(bundle, TEST_CONFIG, model=FunctionModel(fake_model)))
    assert result.status == "success", result.error
    assert "Fictional initial estimate" in snapshots[-1]
    assert all("912345" not in snapshot for snapshot in snapshots)
    assert all("'hover':" not in snapshot for snapshot in snapshots)


def test_factual_findings_require_citations(bundle):
    model, _ = synthetic_models(bundle)
    model.custom_output_args["evidence"] = []
    result = run_claim(bundle, baseline_model=model)
    assert result.baseline.status == "failed"
    assert result.baseline.usage["requests"] > 0


def test_redundant_covariates_and_confounded_hover():
    frame = pd.DataFrame([b.metadata() for b in synthetic_bundles(250)])
    result = fit_statistical_models(frame, ResearchConfig(bootstrap_replicates=0))
    assert result["status"] == "success", result.get("reason")
    assert result["redundant_columns"]
    confounded = frame.assign(peril=np.where(frame.hover, "after", "before"))
    result = fit_statistical_models(
        confounded, ResearchConfig(covariates=["peril"], bootstrap_replicates=0)
    )
    assert result["status"] == "unsupported"
    assert "confounded" in result["reason"]


def test_cli_population_analysis_without_extraction(tmp_path):
    from ad_hoc.hover_supplements.__main__ import main

    frame = pd.DataFrame([b.metadata() for b in synthetic_bundles(80)])
    population_path = tmp_path / "population.csv"
    frame.to_csv(population_path, index=False)
    assert (
        main(["analyze", str(population_path), str(tmp_path / "report"), "--bootstrap", "0"]) == 0
    )
    assert (tmp_path / "report" / "summary.md").exists()
    report = json.loads((tmp_path / "report" / "research.json").read_text(encoding="utf-8"))
    assert report["tables"]["population_scorecard"]
    assert report["tables"]["audit_coverage"][0]["extraction_status__not_extracted__n"] > 0


def test_all_missing_covariates_and_missing_columns_are_supported_results():
    frame = pd.DataFrame([b.metadata() for b in synthetic_bundles(100)])
    missing_values = frame.assign(peril=None, sub_peril=None)
    assert (
        fit_statistical_models(missing_values, ResearchConfig(bootstrap_replicates=0))["status"]
        == "success"
    )
    absent_columns = frame.drop(columns=["peril", "sub_peril"])
    assert fit_statistical_models(absent_columns)["status"] == "unsupported"
    assert run_predictive_research(absent_columns)["status"] == "unsupported"
