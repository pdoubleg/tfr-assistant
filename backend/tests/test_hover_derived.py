"""Derived claim features keep measurement, scope, and missing evidence distinct."""

import json

import pandas as pd
import pytest
from pydantic import ValidationError

from ad_hoc.hover_supplements.analysis import derived_analysis
from ad_hoc.hover_supplements.dataframes import build_feature_table, feature_dictionary
from ad_hoc.hover_supplements.derived import DERIVED_FEATURES, derive_claim_features
from ad_hoc.hover_supplements.modeling import ResearchConfig
from ad_hoc.hover_supplements.models import SupplementMechanismFeatures
from ad_hoc.hover_supplements.visualization import build_business_figures, render_business_report


def roofing_frame():
    return pd.DataFrame(
        {
            "claim_id": ["repair-approved", "repair-denied", "incomparable", "unknown-roof"],
            "hover": [True, True, False, False],
            "peril": ["hail"] * 4,
            "sampling_weight": [1, 3, 1, 1],
            "initial_estimate_amount": [1000] * 4,
            "supplement_approved_amount": [500, 0, 100, 100],
            "baseline__roof__roof_present_in_scope": [True, True, True, pd.NA],
            "baseline__roof__initial_repair_scope": ["repair"] * 4,
            "baseline__roof__roof_squares": [20, 20, 20, 20],
            "baseline__roof__estimated_roof_squares": [2, 2, 2, 2],
            "supplement_mechanism__roofing__revised_roof_squares": [20, 22, 30, 30],
            "supplement_mechanism__roofing__revised_estimated_roof_squares": [22, 2, 22, 22],
            "supplement_mechanism__roofing__measured_sq_comparable": [True, True, False, True],
            "supplement_mechanism__roofing__estimated_sq_comparable": [True, True, "unknown", True],
            "supplement_mechanism__roofing__repair_to_replace_requested": [
                True,
                True,
                "unknown",
                True,
            ],
            "supplement_mechanism__roofing__repair_to_replace_approved": [
                True,
                False,
                "unknown",
                True,
            ],
        }
    )


def test_roof_measurements_and_estimated_scope_are_separate_nullable_comparisons():
    frame = derive_claim_features(roofing_frame())
    assert frame.derived__roof_measured_sq_delta.iloc[:2].tolist() == [0, 2]
    assert frame.derived__roof_estimated_sq_delta.iloc[:2].tolist() == [20, 0]
    assert frame.derived__roof_estimated_sq_pct_change.iloc[0] == 10
    assert not frame.derived__roof_measured_sq_changed.iloc[0]
    assert frame.derived__roof_estimated_sq_increased.iloc[0]
    assert frame.derived__roof_measured_sq_delta.iloc[2:].isna().all()
    assert frame.derived__roof_estimated_sq_delta.iloc[2:].isna().all()
    assert pd.isna(frame.derived__roof_involved.iloc[3])  # Hail alone proves nothing.
    assert frame.derived__roof_repair_to_replace_requested.iloc[1]
    assert not frame.derived__roof_repair_to_replace_approved.iloc[1]
    pd.testing.assert_frame_equal(frame, derive_claim_features(frame))


def test_dates_ratios_and_zero_roof_area_do_not_invent_values():
    source = roofing_frame()
    source["dol"] = ["2026-01-01", "bad", "2026-01-05", None]
    source["fnol_date"] = ["2026-01-03", "2026-01-03", "2026-01-03", None]
    source["initial_estimate_cutoff"] = ["2026-01-10", None, None, None]
    source["baseline__initial_estimate_cutoff_date"] = [None, "2026-01-09", None, None]
    source["supplement_requested_amount"] = [1000, 500, 0, None]
    source["initial_estimate_amount"] = [2000, 0, None, 2000]
    source.loc[0, "baseline__roof__roof_squares"] = 0
    frame = derive_claim_features(source)
    assert frame.derived__days_loss_to_fnol.iloc[0] == 2
    assert frame.derived__days_fnol_to_estimate.iloc[:2].tolist() == [7, 6]
    assert frame.derived__days_loss_to_estimate.iloc[0] == 9
    assert frame.derived__days_loss_to_fnol.iloc[1:].isna().all()
    assert frame.derived__request_to_initial_ratio.iloc[0] == 0.5
    assert frame.derived__request_to_initial_ratio.iloc[1:].isna().all()
    assert frame.derived__approval_rate_of_request.iloc[:2].tolist() == [0.5, 0]
    assert frame.derived__approval_rate_of_request.iloc[2:].isna().all()
    assert pd.isna(frame.derived__roof_measured_sq_pct_change.iloc[0])
    assert frame.supplement_approved_amount.equals(source.supplement_approved_amount)
    assert not any("denied_amount_computed" in c for c in frame)


def test_partial_documentation_and_nullable_history_flags():
    frame = derive_claim_features(
        pd.DataFrame(
            {
                "baseline__documentation__photo_documentation_adequate": ["yes", "unknown", "no"],
                "baseline__documentation__notes_documentation_adequate": [False, pd.NA, True],
                "baseline__documentation__all_damaged_elevations_or_slopes_photographed": [
                    "not_applicable",
                    "unknown",
                    "yes",
                ],
                "supplement_mechanism__prevention__measurement_accuracy": [True, False, False],
                "supplement_mechanism__prevention__measurement_scope": [pd.NA, pd.NA, False],
                "supplement_mechanism__potentially_avoidable": [
                    "probably_avoidable",
                    "unclear",
                    "clearly_unavoidable",
                ],
                "supplement_mechanism__avoidability_confidence": ["high", "high", "low"],
            }
        )
    )
    assert frame.derived__documentation_observed_count.tolist() == [2, 0, 3]
    assert frame.derived__documentation_index.iloc[0] == 0.5
    assert pd.isna(frame.derived__documentation_index.iloc[1])
    assert frame.derived__documentation_index.iloc[2] == pytest.approx(2 / 3)
    assert frame.derived__measurement_addressable.iloc[0]
    assert pd.isna(frame.derived__measurement_addressable.iloc[1])
    assert not frame.derived__measurement_addressable.iloc[2]
    assert frame.derived__main_avoidability_label_usable.tolist() == [True, False, False]
    assert pd.isna(frame.derived__main_avoidable_binary.iloc[1])


def test_flat_table_without_extraction_and_empty_input_preserve_dtypes():
    source = roofing_frame()[
        [
            "claim_id",
            "hover",
            "initial_estimate_amount",
            "supplement_approved_amount",
            "sampling_weight",
        ]
    ]
    frame = build_feature_table([], source)
    assert len(frame) == frame.claim_id.nunique() == 4
    assert frame.derived__roof_measured_sq_delta.isna().all()
    assert frame.derived__roof_repair_to_replace_requested.isna().all()
    assert frame.supplement_status.eq("not_extracted").all()
    dictionary = feature_dictionary(include_derived=True)
    assert len(dictionary) == 124 + len(DERIVED_FEATURES)
    for field in dictionary.loc[dictionary.source.eq("computed")].itertuples():
        assert str(frame[field.field].dtype) == field.type
    assert derive_claim_features(pd.DataFrame()).empty


def test_roof_request_approval_consistency_and_unknown_defaults():
    old = SupplementMechanismFeatures(supplement_present="unknown")
    assert old.roofing.repair_to_replace_approved == "unknown"
    assert old.roofing.revised_roof_squares is None
    absent = SupplementMechanismFeatures(supplement_present="no")
    assert absent.roofing.repair_to_replace_requested == "no"
    assert absent.roofing.revised_estimated_roof_squares is None
    with pytest.raises(ValidationError):
        SupplementMechanismFeatures(
            roofing={"repair_to_replace_requested": "no", "repair_to_replace_approved": "yes"}
        )


@pytest.mark.parametrize(
    "field",
    [
        "derived__roof_measured_sq_delta",
        "derived__main_avoidable_binary",
        "baseline__roof__initial_repair_scope",
    ],
)
def test_derived_retrospective_and_estimate_scope_features_are_not_primary_covariates(field):
    with pytest.raises(ValueError):
        ResearchConfig(covariates=[field]).validate()


def test_roof_report_weighted_denominators_flat_exports_and_serialization(tmp_path):
    source = roofing_frame()
    tables = derived_analysis(source, source)
    metrics = tables["roofing_metrics"]
    approved = metrics.loc[
        metrics.hover & metrics.metric.eq("derived__roof_repair_to_replace_approved")
    ].iloc[0]
    assert approved.estimate == 0.25
    assert approved.known_n == 2 and approved.denominator_weight == 4
    assert len(tables["roofing_claims"]) == tables["roofing_claims"].claim_id.nunique() == 3
    assert tables["roofing_coverage"].unknown_roof_n.sum() == 1
    # Saved reports round-trip nullable fields through JSON, then rebuild all charts.
    report = {"tables": {k: json.loads(v.to_json(orient="records")) for k, v in tables.items()}}
    figures = build_business_figures(report)
    assert {
        "roof_measured_sq",
        "roof_estimated_sq",
        "roof_repair_transitions",
        "derived_timing",
        "derived_ratios",
    } <= set(figures)
    measured = figures["roof_measured_sq"].data[0]
    assert len(measured.x) == 2
    html = render_business_report(report, tmp_path).read_text(encoding="utf-8")
    assert "What changed on roofing claims?" in html
    assert "roof_repair_transitions" in html
    assert "known" in html
