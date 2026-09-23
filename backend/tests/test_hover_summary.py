"""Acceptance coverage for the single-row, main-and-remaining supplement contract."""

import asyncio
import json

import pandas as pd
import pytest
from pydantic import ValidationError
from pydantic_ai.models.test import TestModel as OfflineModel

from ad_hoc.hover_supplements import agents
from ad_hoc.hover_supplements.analysis import mechanism_analysis
from ad_hoc.hover_supplements.contracts import (
    EvidenceReference,
    ExtractionResult,
    PassResult,
    SupplementOutput,
)
from ad_hoc.hover_supplements.dataframes import build_feature_table, feature_dictionary
from ad_hoc.hover_supplements.evidence import EvidenceStore
from ad_hoc.hover_supplements.modeling import ResearchConfig
from ad_hoc.hover_supplements.models import (
    BaselineClaimFeatures,
    SupplementHistory,
    SupplementMechanismFeatures,
)
from ad_hoc.hover_supplements.runner import extract_batch, run_analysis
from ad_hoc.hover_supplements.synthetic import synthetic_bundles, synthetic_models
from ad_hoc.hover_supplements.visualization import render_business_report
from app.core.llm import LLMModelAPI, LLMModelConfig

CONFIG = LLMModelConfig(model_name="test", api=LLMModelAPI.TEST)


@pytest.fixture
def bundle():
    return next(b for b in synthetic_bundles(20) if b.supplement_activity == "yes")


def summary(**overrides):
    values = dict(
        supplement_present="yes",
        history=dict(
            completeness="complete",
            total_count=3,
            approved_count=1,
            denied_count=1,
            pending_count=1,
        ),
        primary_mechanism="quantity_or_measurement_correction",
        primary_selection_basis="approved_amount",
        primary_outcome="approved_in_full",
        potentially_avoidable="probably_avoidable",
        primary_prevention_area="measurement_accuracy",
        secondary_mechanism="multiple",
        remaining_outcome="mixed",
        remaining_avoidability="mixed",
        drivers=dict(measurement_correction="yes", concealed_damage_after_demolition="yes"),
        prevention=dict(measurement_accuracy="yes"),
        any_potentially_avoidable="yes",
        mechanism_summary="Main measurement correction; later denied and pending requests.",
    )
    values.update(overrides)
    return SupplementMechanismFeatures(**values)


def result_for(bundle, features):
    return ExtractionResult(
        claim_id=bundle.claim_id,
        baseline=PassResult(
            status="success", features=agents.unknown_features(BaselineClaimFeatures)
        ),
        supplement=PassResult(status="success", features=features),
    )


def cited_output(features, evidence_id="later"):
    refs = []
    for field in feature_dictionary(type(features)).to_dict("records"):
        path = field["field"].replace("__", ".")
        value = features
        for name in path.split("."):
            value = getattr(value, name)
        if value is not None and value not in {"unknown", "unclear", "not_applicable"}:
            refs.append(
                EvidenceReference(
                    field_path=path,
                    evidence_ids=[evidence_id],
                    explanation="Explicit fictional fixture fact.",
                )
            )
    return SupplementOutput(features=features, evidence=refs)


@pytest.mark.parametrize(
    "activity,amount,expected",
    [
        ("no", 0, "skipped"),
        ("unknown", 0, "success"),
        ("yes", 0, "success"),
        ("no", 100, "success"),
        ("unknown", 100, "success"),
    ],
)
@pytest.mark.parametrize(
    "field",
    [
        "supplement_requested_amount",
        "supplement_approved_amount",
        "supplement_denied_amount",
    ],
)
def test_structured_gate_calls_one_supplement_extraction(
    bundle, monkeypatch, activity, amount, expected, field
):
    values = dict(
        supplement_activity=activity,
        supplement_requested_amount=0,
        supplement_approved_amount=0,
        supplement_denied_amount=0,
    )
    values[field] = amount
    bundle = bundle.model_copy(update=values)
    calls = []

    async def fake_extract(bundle, stage, config, model=None):
        calls.append(stage)
        features = (
            agents.unknown_features(BaselineClaimFeatures)
            if stage == "baseline"
            else SupplementMechanismFeatures()
        )
        return PassResult(status="success", features=features)

    monkeypatch.setattr(agents, "_extract", fake_extract)
    result = asyncio.run(agents.extract_claim(bundle, CONFIG))
    assert result.supplement.status == expected
    assert calls == (["baseline"] if expected == "skipped" else ["baseline", "supplement"])
    if expected == "skipped":
        assert result.supplement.features.history.total_count == 0
        assert result.supplement.features.primary_outcome == "not_applicable"
    if amount and activity == "no":
        assert any(d.get("resolved_from_amounts") == "yes" for d in result.discrepancies)


def test_extractor_can_confirm_absence_and_preserves_conflicting_structured_amounts(bundle):
    baseline, _ = synthetic_models(bundle)
    features = SupplementMechanismFeatures(supplement_present="no")
    # Only absence needs citation; zero counts and N/A fields follow deterministically.
    output = SupplementOutput(
        features=features,
        evidence=[
            EvidenceReference(
                field_path="supplement_present",
                evidence_ids=["later"],
                explanation="No request found.",
            )
        ],
    )
    model = OfflineModel(call_tools=[], custom_output_args=output.model_dump(mode="json"))
    result = asyncio.run(
        agents.extract_claim(bundle, CONFIG, baseline_model=baseline, supplement_model=model)
    )
    assert result.supplement.status == "success", result.supplement.error
    assert any(d.get("extracted") == "no" for d in result.discrepancies)
    frame = build_feature_table([result], [bundle.metadata()])
    assert frame.iloc[0].supplement_approved_amount == bundle.supplement_approved_amount
    assert not frame.iloc[0]["supplement_mechanism__supplement_present"]
    assert frame.iloc[0]["supplement_mechanism__history__total_count"] == 0


def test_whole_history_stays_one_flat_claim_row(bundle):
    result = result_for(bundle, summary())
    frame = build_feature_table(
        [result], [dict(bundle.metadata(), sampling_weight=7)], drop_text=False
    )
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["supplement_mechanism__remaining_outcome"] == "mixed"
    assert row["supplement_mechanism__drivers__concealed_damage_after_demolition"]
    assert row["supplement_mechanism__history__total_count"] == 3
    assert row.sampling_weight == 7
    assert "later denied" in row["supplement_mechanism__mechanism_summary"]
    assert not any(isinstance(v, (list, dict)) for v in row)
    analysis = mechanism_analysis(frame)
    repeat = analysis["supplement_history"]
    assert repeat.repeat_rate.eq(1).all()
    assert repeat.denominator_weight.eq(7).all()
    main = analysis["classifications"].query(
        "classification == 'supplement_mechanism__primary_mechanism'"
    )
    assert main.associated_approved_dollars.sum() == bundle.supplement_approved_amount * 7


def test_partial_history_preserves_positive_finding_and_unknown_count(bundle):
    features = summary(history=dict(completeness="partial"))
    frame = build_feature_table([result_for(bundle, features)], [bundle.metadata()])
    assert pd.isna(frame.iloc[0]["supplement_mechanism__history__total_count"])
    assert frame.iloc[0]["supplement_mechanism__any_potentially_avoidable"]
    assert pd.isna(frame.iloc[0]["supplement_mechanism__drivers__matching"])
    assert mechanism_analysis(frame)["supplement_history"].repeat_rate.isna().all()


@pytest.mark.parametrize(
    "history",
    [
        dict(completeness="partial", total_count=2),
        dict(completeness="complete", total_count=2, approved_count=2, denied_count=1),
        dict(completeness="complete", total_count=-1),
        dict(completeness="complete", total_count=1.5),
    ],
)
def test_invalid_counts_rejected(history):
    with pytest.raises(ValidationError):
        SupplementHistory(**history)


@pytest.mark.parametrize(
    "changes",
    [
        {"supplement_present": "no"},
        {"history": {"completeness": "complete", "total_count": 0}},
        {"history": {"completeness": "complete", "total_count": 1}},
        {"any_potentially_avoidable": "no"},
    ],
)
def test_contradictory_history_rejected(changes):
    with pytest.raises(ValidationError):
        summary(**changes)


def test_one_request_with_multiple_documents_has_no_remaining_classifications():
    features = SupplementMechanismFeatures(
        supplement_present="yes",
        history=SupplementHistory(completeness="complete", total_count=1),
        mechanism_summary="Three revised documents and negotiations for one unresolved request.",
    )
    assert features.secondary_mechanism == "not_applicable"
    assert features.remaining_outcome == "not_applicable"
    assert features.remaining_avoidability == "not_applicable"


def test_one_remaining_supplement_cannot_have_mixed_classifications():
    with pytest.raises(ValidationError, match="at least two other"):
        summary(history=dict(completeness="complete", total_count=2))


@pytest.mark.parametrize(
    "outcome,basis,approved,denied,pending",
    [
        ("approved_in_full", "approved_amount", 1, 0, 0),
        ("approved_in_part", "approved_amount", 1, 0, 0),
        ("denied_in_full", "requested_amount", 0, 1, 0),
        ("pending", "requested_amount", 0, 0, 1),
        ("withdrawn_by_requester", "qualitative_materiality", None, None, None),
    ],
)
def test_single_pass_preserves_main_selection_and_outcome(
    bundle,
    outcome,
    basis,
    approved,
    denied,
    pending,
):
    """Scripted outputs validate runtime plumbing, not natural-language ranking accuracy."""
    features = SupplementMechanismFeatures(
        supplement_present="yes",
        history=dict(
            completeness="complete",
            total_count=1,
            approved_count=approved,
            denied_count=denied,
            pending_count=pending,
        ),
        primary_mechanism="pricing_change",
        primary_outcome=outcome,
        primary_selection_basis=basis,
    )
    output = cited_output(features)
    model = OfflineModel(call_tools=[], custom_output_args=output.model_dump(mode="json"))
    result = asyncio.run(agents.extract_supplement(bundle, CONFIG, model=model))
    assert result.status == "success", result.error
    assert result.usage["requests"] == 1
    assert result.features.primary_selection_basis == basis
    assert result.features.primary_outcome == outcome
    assert result.features.secondary_mechanism == "not_applicable"


def test_old_saved_report_labels_are_aggregate_not_main():
    from ad_hoc.hover_supplements.visualization import build_business_figures

    report = {
        "tables": {
            "classifications": pd.DataFrame(
                [
                    {
                        "hover": False,
                        "classification": "supplement_mechanism__primary_mechanism",
                        "category": "quantity_change",
                        "approved_supplement_share": 1,
                        "claims_n": 1,
                        "classification_unknown_n": 0,
                    }
                ]
            )
        }
    }
    figures = build_business_figures(report)
    assert figures["primary_mechanism"].layout.title.text.startswith("Legacy aggregate")


def test_repairability_dispute_does_not_imply_measurement_prevention():
    features = summary(
        primary_mechanism="repairability_or_repair_versus_replace_dispute",
        primary_prevention_area="damage_assessment_or_repairability",
        drivers={"measurement_correction": "no", "repair_versus_replace": "yes"},
        prevention={
            "measurement_accuracy": "no",
            "measurement_scope": "no",
            "damage_assessment_or_repairability": "yes",
        },
    )
    row = features.to_pandas().iloc[0]
    assert not row["supplement_mechanism__prevention__measurement_accuracy"]
    assert row["supplement_mechanism__drivers__repair_versus_replace"]


def test_annotated_dtypes_raw_categories_and_no_llm_pandas_metadata():
    features = SupplementMechanismFeatures(supplement_present="no")
    frame = features.to_pandas()
    assert frame["supplement_mechanism__history__total_count"].dtype == "Int64"
    assert frame["supplement_mechanism__financials__supplement_approved_amount"].dtype == "Float64"
    assert frame.iloc[0]["supplement_mechanism__primary_request_preventable"] == "not_applicable"
    assert frame["supplement_mechanism__primary_request_preventable"].dtype == "string"
    assert not any("is_not_applicable" in c for c in frame)
    raw = SupplementMechanismFeatures().to_pandas(indicators_as_boolean=False, unknown_as_na=False)
    assert raw.iloc[0]["supplement_mechanism__drivers__matching"] == "unknown"
    assert "pandas_kind" not in json.dumps(SupplementMechanismFeatures.model_json_schema())
    with pytest.raises(ValueError, match="collides"):
        features.to_pandas(extra_columns={"supplement_mechanism__primary_outcome": "bad"})


def test_failed_and_unextracted_sections_remain_missing(bundle):
    result = result_for(bundle, summary())
    result.supplement = PassResult(status="failed", error="fixture failure")
    other = bundle.model_copy(update={"claim_id": "not-extracted"})
    frame = build_feature_table([result], [bundle.metadata(), other.metadata()])
    assert frame["supplement_mechanism__history__total_count"].isna().all()
    assert frame.supplement_status.tolist() == ["failed", "not_extracted"]


def test_financial_qa_does_not_compute_denials_or_overwrite_authoritative_values(bundle):
    features = summary(
        financials={
            "supplement_requested_amount": 9999,
            "supplement_approved_amount": 120,
            "revised_estimate_amount": 35000,
        }
    )
    frame = build_feature_table([result_for(bundle, features)], [bundle.metadata()])
    row = frame.iloc[0]
    assert pd.isna(row["supplement_mechanism__financials__supplement_denied_amount"])
    assert row["supplement_mechanism__financials__revised_estimate_amount"] == 35000
    assert row.supplement_approved_amount == bundle.supplement_approved_amount
    assert row["supplement_mechanism__financials__supplement_requested_amount"] == 9999


def test_legacy_results_preserved_without_inventing_main_labels(bundle):
    payload = result_for(bundle, summary()).model_dump(mode="json")
    payload["schema_version"] = payload["prompt_version"] = "1.0"
    old = {
        "supplement_present": "yes",
        "primary_mechanism": "quantity_change",
        "potentially_avoidable": "probably_avoidable",
        "scope": {"missed_item": "yes"},
    }
    payload["supplement"]["features"] = old
    result = ExtractionResult.model_validate(payload)
    assert result.is_legacy and result.features is None
    assert result.supplement.features.aggregate == old
    assert ExtractionResult.model_validate_json(result.model_dump_json()) == result
    frame = build_feature_table([result], [bundle.metadata()])
    assert frame.iloc[0]["legacy_supplement__primary_mechanism"] == "quantity_change"
    assert pd.isna(frame.iloc[0]["supplement_mechanism__primary_mechanism"])
    assert pd.isna(frame.iloc[0]["supplement_mechanism__history__total_count"])
    analysis = mechanism_analysis(frame)
    assert analysis["classifications"].empty
    assert len(analysis["legacy_aggregate_claims"]) == 1


def test_summary_citations_cover_new_fields_and_only_accessible_evidence(bundle):
    features = summary()
    store = EvidenceStore(tuple(bundle.initial_evidence + bundle.later_evidence))
    refs = cited_output(features).evidence
    store.validate_references(features, refs)
    with pytest.raises(ValueError, match="requires evidence"):
        store.validate_references(
            features, [r for r in refs if r.field_path != "remaining_outcome"]
        )
    with pytest.raises(ValueError, match="outside"):
        store.validate_references(features, cited_output(features, "unavailable").evidence)


@pytest.mark.parametrize(
    "field",
    [
        "baseline__roof__repairability_assessed_initially",
        "baseline__roof__repairability_test_performed_initially",
        "baseline__documentation__measurement_discrepancy_documented",
        "supplement_mechanism__remaining_outcome",
        "supplement_mechanism__history__total_count",
    ],
)
def test_new_post_treatment_fields_cannot_be_primary_covariates(field):
    with pytest.raises(ValueError):
        ResearchConfig(
            tier="enriched",
            covariates=[field],
            pretreatment_rationale={field: "Not a valid override."},
        ).validate()


def test_offline_report_contains_main_remaining_prevention_and_history(tmp_path):
    bundles = synthetic_bundles(70)
    results = asyncio.run(extract_batch(bundles, CONFIG, demo=True))
    assert all(r.status == "success" for r in results)
    frame = pd.DataFrame([b.metadata() for b in bundles])
    report = run_analysis(
        frame,
        results=results,
        config=ResearchConfig(bootstrap_replicates=0, trees=5, shap_enabled=False),
    )
    assert len(report["tables"]["feature_table"]) == len(frame)
    assert "supplement_mechanism__mechanism_summary" in report["tables"]["feature_table"]
    html = render_business_report(report, tmp_path).read_text(encoding="utf-8")
    for text in (
        "Main supplement outcome",
        "Remaining supplements",
        "Prevention areas",
        "Claims with multiple supplements",
        "What changed on roofing claims?",
        "Measured roof area",
        "Roof repair to replacement",
    ):
        assert text in html
