"""Deterministic features on the complete flat claim table; never extracted by an LLM."""

import numpy as np
import pandas as pd

DERIVED_FEATURES = {
    "days_loss_to_fnol": ("count", "Days from DOL to FNOL; invalid or reversed dates are missing."),
    "days_fnol_to_estimate": ("count", "Days from FNOL to the initial-estimate cutoff."),
    "days_loss_to_estimate": ("count", "Days from DOL to the initial-estimate cutoff."),
    "request_to_initial_ratio": ("number", "Structured incremental request / initial estimate."),
    "approval_rate_of_request": (
        "number",
        "Structured approved / requested increment; not a denial calculation.",
    ),
    "documentation_index": (
        "number",
        "Share of observed initial documentation indicators that are yes (0–1).",
    ),
    "documentation_observed_count": (
        "count",
        "Number of usable indicators out of six; N/A and unknown excluded.",
    ),
    "main_avoidable_binary": (
        "indicator",
        "Main clearly/probably avoidable versus unavoidable; unclear/N/A missing.",
    ),
    "main_avoidability_label_usable": (
        "indicator",
        "Main binary label exists and confidence is medium/high.",
    ),
    "measurement_addressable": (
        "indicator",
        "Any measurement accuracy/scope prevention indicator is yes; unknown propagates.",
    ),
    "roof_involved": (
        "indicator",
        "Roof documented in initial scope or property features; not inferred from peril.",
    ),
    "roof_measured_sq_delta": (
        "number",
        "Latest carrier roof area minus initial roof area, only on a comparable basis (SQ).",
    ),
    "roof_measured_sq_pct_change": (
        "number",
        "Comparable measured SQ delta / positive initial roof SQ; a fraction.",
    ),
    "roof_estimated_sq_delta": (
        "number",
        "Latest carrier repair/replacement scope SQ minus initial scope SQ, if comparable.",
    ),
    "roof_estimated_sq_pct_change": (
        "number",
        "Comparable estimated-scope SQ delta / positive initial scope SQ; a fraction.",
    ),
    "roof_measured_sq_changed": (
        "indicator",
        "Comparable documented roof-area measurements differ; unavailable comparisons missing.",
    ),
    "roof_estimated_sq_increased": (
        "indicator",
        "Comparable carrier-estimated repair/replacement SQ increased.",
    ),
    "roof_repair_to_replace_requested": (
        "indicator",
        "Any documented roofing repair-to-replacement request, including denied/pending.",
    ),
    "roof_repair_to_replace_approved": (
        "indicator",
        "Any documented carrier-approved roofing repair-to-replacement supplement.",
    ),
}


def derived_feature_dictionary():
    return pd.DataFrame(
        [
            {
                "field": "derived__" + name,
                "description": description,
                "pandas_kind": kind,
                "type": {"count": "Int64", "number": "Float64", "indicator": "boolean"}[kind],
                "choices": [],
                "source": "computed",
            }
            for name, (kind, description) in DERIVED_FEATURES.items()
        ]
    )


def _safe_ratio(numerator, denominator):
    return (numerator / denominator.where(denominator > 0)).astype("Float64")


def derive_claim_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute supported features without requiring new structured-data models.

    Inputs use existing unprefixed metadata (dol, fnol_date, initial_estimate_cutoff,
    financial amounts) and flattened baseline/supplement columns. No cohort-dependent
    z-scores or fabricated zeros. Re-running replaces computed columns and is idempotent.
    """
    out = frame.copy()

    def col(name):
        return out[name] if name in out else pd.Series(pd.NA, index=out.index)

    def number(name):
        values = pd.to_numeric(col(name), errors="coerce").astype("Float64")
        return values.where(np.isfinite(values))

    def indicator(name):
        return col(name).map({True: True, False: False, "yes": True, "no": False}).astype("boolean")

    def dates(values):
        return pd.to_datetime(values, errors="coerce", utc=True, format="mixed").dt.normalize()

    def days(later, earlier):
        values = (dates(later) - dates(earlier)).dt.days.astype("Int64")
        return values.where(values >= 0)

    cutoff = col("initial_estimate_cutoff")
    cutoff = cutoff.where(cutoff.notna(), col("baseline__initial_estimate_cutoff_date"))
    features = {
        "days_loss_to_fnol": days(col("fnol_date"), col("dol")),
        "days_fnol_to_estimate": days(cutoff, col("fnol_date")),
        "days_loss_to_estimate": days(cutoff, col("dol")),
        "request_to_initial_ratio": _safe_ratio(
            number("supplement_requested_amount"), number("initial_estimate_amount")
        ),
        "approval_rate_of_request": _safe_ratio(
            number("supplement_approved_amount"), number("supplement_requested_amount")
        ),
    }
    documentation = pd.DataFrame(
        {
            name: indicator("baseline__documentation__" + name)
            for name in (
                "photo_documentation_adequate",
                "notes_documentation_adequate",
                "measurements_documented",
                "all_visible_damage_documented",
                "overview_and_close_up_photos_present",
                "all_damaged_elevations_or_slopes_photographed",
            )
        },
        index=out.index,
    )
    features["documentation_index"] = documentation.astype("Float64").mean(axis=1).astype("Float64")
    features["documentation_observed_count"] = documentation.notna().sum(axis=1).astype("Int64")
    avoidable = (
        col("supplement_mechanism__potentially_avoidable")
        .map(
            {
                "clearly_avoidable": True,
                "probably_avoidable": True,
                "probably_unavoidable": False,
                "clearly_unavoidable": False,
            }
        )
        .astype("boolean")
    )
    features["main_avoidable_binary"] = avoidable
    features["main_avoidability_label_usable"] = (
        avoidable.notna()
        & col("supplement_mechanism__avoidability_confidence").isin(["medium", "high"])
    ).astype("boolean")
    features["measurement_addressable"] = indicator(
        "supplement_mechanism__prevention__measurement_accuracy"
    ) | indicator("supplement_mechanism__prevention__measurement_scope")
    roof = indicator("baseline__roof__roof_present_in_scope") | indicator(
        "baseline__property_complexity__roof_involved"
    )
    features["roof_involved"] = roof
    for kind, initial_col, revised_col in (
        ("measured", "roof_squares", "revised_roof_squares"),
        ("estimated", "estimated_roof_squares", "revised_estimated_roof_squares"),
    ):
        initial = number("baseline__roof__" + initial_col)
        revised = number("supplement_mechanism__roofing__" + revised_col)
        comparable = indicator(f"supplement_mechanism__roofing__{kind}_sq_comparable")
        delta = (revised - initial).where(comparable & roof)
        features[f"roof_{kind}_sq_delta"] = delta
        features[f"roof_{kind}_sq_pct_change"] = _safe_ratio(delta, initial)
        name = f"roof_{kind}_sq_" + ("changed" if kind == "measured" else "increased")
        features[name] = (delta.abs().gt(1e-6) if kind == "measured" else delta.gt(1e-6)).where(
            delta.notna()
        )
    for event in ("requested", "approved"):
        features[f"roof_repair_to_replace_{event}"] = indicator(
            "supplement_mechanism__roofing__repair_to_replace_" + event
        ).where(roof)
    computed = pd.DataFrame({"derived__" + k: v for k, v in features.items()}, index=out.index)
    return pd.concat([out.drop(columns=list(computed), errors="ignore"), computed], axis=1)
