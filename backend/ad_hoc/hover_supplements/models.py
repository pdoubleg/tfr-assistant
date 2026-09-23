"""Initial-evidence features and one claim-level main/remaining supplement summary.

Pandas hints live in Annotated types; conversion is implemented in dataframes.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .dataframes import prepare_flat_dataframe as _prepare_flat_dataframe
from .pandas_types import Category, Count, Date, Indicator, Number, Text

# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

YesNoUnknown = Indicator
ComplexityLevel = Annotated[Literal["low", "moderate", "high", "unknown"], Category]
ConfidenceLevel = Annotated[Literal["low", "medium", "high", "unknown"], Category]

InitialIdentifiability = Annotated[
    Literal[
        "clearly_no",
        "probably_no",
        "unclear",
        "probably_yes",
        "clearly_yes",
    ],
    Category,
]

PotentialAvoidability = Annotated[
    Literal[
        "clearly_avoidable",
        "probably_avoidable",
        "unclear",
        "probably_unavoidable",
        "clearly_unavoidable",
        "not_applicable",
    ],
    Category,
]

PrimarySupplementMechanism = Annotated[
    Literal[
        "scope_expansion_missed_item",
        "scope_expansion_additional_area",
        "quantity_or_measurement_correction",
        "pricing_change",
        "concealed_or_hidden_damage",
        "matching",
        "code_or_ordinance",
        "overhead_and_profit",
        "repairability_or_repair_versus_replace_dispute",
        "contractor_scope_disagreement_other",
        "coverage_or_administrative",
        "new_loss_or_additional_event",
        "multiple",
        "other",
        "unclear",
        "not_applicable",
    ],
    Category,
]

SupplementOutcome = Annotated[
    Literal[
        "approved_in_full",
        "approved_in_part",
        "denied_in_full",
        "withdrawn_by_requester",
        "pending",
        "unclear",
        "not_applicable",
    ],
    Category,
]

PreventionArea = Annotated[
    Literal[
        "measurement_accuracy",
        "measurement_scope",
        "photo_documentation",
        "damage_assessment_or_repairability",
        "estimate_construction",
        "pricing_currency",
        "coverage_determination",
        "contractor_expectation_setting",
        "process_or_timing",
        "not_preventable",
        "unclear",
        "not_applicable",
    ],
    Category,
]

UnavoidableReason = Annotated[
    Literal[
        "concealed_until_demolition",
        "became_observable_later_without_demolition",
        "new_loss_or_additional_event",
        "physical_condition_changed",
        "code_or_ordinance_determination",
        "market_or_material_price_change",
        "insured_elected_scope_change",
        "third_party_information_required",
        "other",
        "not_applicable",
        "unclear",
    ],
    Category,
]


# ---------------------------------------------------------------------------
# Field helpers
#
# Pandas types travel in Annotated metadata; descriptions guide the LLM.
# ---------------------------------------------------------------------------


def indicator_field(description: str) -> Any:
    """Create a yes/no/unknown field that becomes nullable boolean in pandas."""
    return Field(
        default="unknown",
        description=description,
    )


def date_field(description: str) -> Any:
    """Create an optional date field that becomes datetime64 in pandas."""
    return Field(
        default=None,
        description=description,
    )


def text_field(description: str) -> Any:
    """Create optional narrative text that may be dropped from ML tables."""
    return Field(
        default=None,
        description=description,
    )


# ---------------------------------------------------------------------------
# Pandas conversion utilities
# ---------------------------------------------------------------------------


# ===========================================================================#
# FEATURE GROUP 1
# BASELINE / INITIAL-ESTIMATE FEATURES
# ===========================================================================#


class PropertyComplexityFeatures(BaseModel):
    """
    Describe physical and structural characteristics that influence how
    difficult the loss is to inspect, document, measure, and estimate.

    Use only information available by the initial-estimate cutoff. Do not use
    later supplement activity to retrospectively infer complexity.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    stories: Count = Field(
        default=None,
        ge=1,
        description=(
            "Number of above-ground stories for the affected structure when "
            "the value is explicitly stated or reliably documented."
        ),
    )

    structures_involved: Count = Field(
        default=None,
        ge=1,
        description=(
            "Number of distinct structures involved in the claimed loss, such "
            "as the dwelling, detached garage, shed, or other structure."
        ),
    )

    roof_involved: YesNoUnknown = indicator_field(
        "Whether roof damage or roof repair was part of the known loss scope "
        "by the initial-estimate cutoff."
    )

    exterior_involved: YesNoUnknown = indicator_field(
        "Whether exterior building components other than the roof were part "
        "of the known loss scope, such as siding, gutters, windows, fencing, "
        "or exterior finishes."
    )

    interior_involved: YesNoUnknown = indicator_field(
        "Whether interior building components or finishes were part of the "
        "known loss scope by the initial-estimate cutoff."
    )

    rooms_affected: Count = Field(
        default=None,
        ge=0,
        description=(
            "Approximate number of distinct interior rooms or spaces with "
            "documented claimed damage."
        ),
    )

    building_components_affected: Count = Field(
        default=None,
        ge=0,
        description=(
            "Approximate count of materially distinct damaged building "
            "component types, such as roofing, siding, drywall, flooring, "
            "cabinets, windows, or gutters."
        ),
    )

    overall_property_complexity: ComplexityLevel = Field(
        default="unknown",
        description=(
            "Overall physical complexity of the property for inspection and "
            "measurement. Use low for straightforward properties, moderate "
            "for meaningful complexity, high for properties with substantial "
            "geometry/access/component complexity, and unknown when the file "
            "does not support an assessment."
        ),
    )

    repair_complexity: ComplexityLevel = Field(
        default="unknown",
        description=(
            "Expected complexity of the known repairs at the initial-estimate "
            "stage. Consider number of trades, interconnected components, "
            "access difficulty, sequencing, and scope complexity."
        ),
    )


RoofRepairScope = Annotated[
    Literal[
        "repair",
        "partial_replacement",
        "full_replacement",
        "mixed",
        "unknown",
        "not_applicable",
    ],
    Category,
]


class RoofFeatures(BaseModel):
    """
    Describe roof characteristics known at the time of the initial estimate.

    These features are intended to capture roof-related case mix and estimating
    complexity independently of any later supplement.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    repairability_assessed_initially: YesNoUnknown = indicator_field(
        "Whether repairability was assessed by the initial-estimate cutoff."
    )
    repairability_test_performed_initially: YesNoUnknown = indicator_field(
        "Whether an objective repairability test was performed before the cutoff."
    )

    roof_present_in_scope: YesNoUnknown = indicator_field(
        "Whether the initial loss scope included repair or replacement of any roof component."
    )

    roof_squares: Number = Field(
        default=None,
        ge=0,
        description=(
            "Initial documented roof area in roofing squares, where one square "
            "represents approximately 100 square feet."
        ),
    )

    estimated_roof_squares: Number = Field(
        default=None,
        ge=0,
        description=(
            "Roofing SQ included in the initial carrier repair/replacement estimate, not total "
            "measured roof area. Record documented scope once; do not sum tear-off and install "
            "line items or combine unrelated buildings/materials. "
            "Null if no comparable SQ is stated."
        ),
    )
    initial_repair_scope: RoofRepairScope = Field(
        default="unknown",
        description=(
            "Initial carrier roof remedy: repair, partial replacement, full replacement, or mixed. "
            "Use not_applicable only when roofing is not involved. Initial evidence only."
        ),
    )

    roof_pitch: Annotated[str | None, Category] = Field(
        default=None,
        description=(
            "Documented roof pitch or slope. Preserve the source representation "
            "when possible, such as '6/12'. Do not infer a pitch when it is not "
            "supported by the file."
        ),
    )

    roof_facets_or_slopes: Count = Field(
        default=None,
        ge=0,
        description=(
            "Number of documented roof facets, planes, or slopes when the file "
            "provides enough information to determine the value."
        ),
    )

    multiple_roofing_materials: YesNoUnknown = indicator_field(
        "Whether multiple materially different roofing materials or systems "
        "were present on the affected structure."
    )

    multiple_layers: YesNoUnknown = indicator_field(
        "Whether the roof was documented as having multiple layers of roofing "
        "material relevant to repair or replacement."
    )

    steep_or_high_access: YesNoUnknown = indicator_field(
        "Whether steep pitch, significant height, or difficult access was "
        "documented as materially affecting inspection or repair complexity."
    )

    complex_geometry: YesNoUnknown = indicator_field(
        "Whether roof geometry was materially complex due to facets, valleys, "
        "hips, dormers, intersecting roof lines, or similar characteristics."
    )


class DamageCharacteristics(BaseModel):
    """
    Describe the nature and extent of damage known before the initial estimate
    was completed.

    These variables characterize the underlying loss rather than explaining
    what later happened during supplement handling.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    damage_extent: ComplexityLevel = Field(
        default="unknown",
        description=(
            "Overall extent of documented damage at the initial-estimate stage. "
            "Use low for localized/simple damage, moderate for broader damage, "
            "high for extensive multi-component or multi-area damage, and "
            "unknown when evidence is insufficient."
        ),
    )

    structural_damage: YesNoUnknown = indicator_field(
        "Whether documented damage involved structural components rather than "
        "only finishes or cosmetic components."
    )

    cosmetic_damage: YesNoUnknown = indicator_field(
        "Whether any material portion of the documented damage was cosmetic "
        "rather than impairing function or structural integrity."
    )

    water_damage: YesNoUnknown = indicator_field(
        "Whether water intrusion, resulting water damage, or wet building "
        "materials were documented as part of the loss."
    )

    contents_damage: YesNoUnknown = indicator_field(
        "Whether personal property or contents damage was documented in "
        "addition to building damage."
    )

    concealed_damage_possible: YesNoUnknown = indicator_field(
        "Whether the initial facts reasonably indicated potential damage that "
        "could be concealed behind finishes, roofing, walls, floors, or other "
        "materials and therefore not directly observable."
    )

    matching_issue_possible: YesNoUnknown = indicator_field(
        "Whether the initial facts indicated a potential matching issue, such "
        "as inability to reasonably match roofing, siding, flooring, paint, "
        "tile, or another repaired component."
    )

    code_upgrade_possible: YesNoUnknown = indicator_field(
        "Whether the initial facts indicated a plausible code, ordinance, or "
        "required-upgrade issue that could affect repair scope."
    )

    emergency_mitigation_performed: YesNoUnknown = indicator_field(
        "Whether emergency mitigation work had already occurred by the initial-estimate cutoff."
    )

    temporary_repairs_performed: YesNoUnknown = indicator_field(
        "Whether temporary repairs had already been performed by the initial-estimate cutoff."
    )


class InitialClaimContext(BaseModel):
    """
    Capture claim circumstances already present before completion of the
    initial estimate.

    These features are useful for distinguishing differences in case mix,
    contractor participation, inspection constraints, and unresolved issues
    between Hover and comparison claims.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    contractor_involved_before_initial_estimate: YesNoUnknown = indicator_field(
        "Whether a contractor, roofer, mitigation company, public adjuster, or "
        "other repair representative was materially involved before the initial "
        "estimate was completed."
    )

    contractor_estimate_available_before_initial_estimate: YesNoUnknown = indicator_field(
        "Whether a contractor or repair-provider estimate was available "
        "before the carrier's initial estimate was completed."
    )

    insured_disputing_scope_before_initial_estimate: YesNoUnknown = indicator_field(
        "Whether the insured had already raised a material disagreement "
        "about damage or repair scope before the initial estimate was "
        "completed."
    )

    contractor_disputing_scope_before_initial_estimate: YesNoUnknown = indicator_field(
        "Whether a contractor or repair representative had already raised "
        "a material disagreement about damage or repair scope before the "
        "initial estimate was completed."
    )

    prior_repairs_or_existing_damage_relevant: YesNoUnknown = indicator_field(
        "Whether prior repairs, pre-existing damage, deterioration, or another "
        "prior condition materially complicated evaluation of the current loss."
    )

    inspection_access_limited: YesNoUnknown = indicator_field(
        "Whether access restrictions prevented or materially limited inspection "
        "of an area or component relevant to the loss."
    )

    inspection_conditions_limited: YesNoUnknown = indicator_field(
        "Whether weather, safety, occupancy, debris, temporary coverings, "
        "lighting, or another condition materially limited the inspection."
    )

    unresolved_damage_questions_at_initial_estimate: YesNoUnknown = indicator_field(
        "Whether material questions about the existence or extent of damage "
        "were explicitly unresolved when the initial estimate was completed."
    )

    unresolved_coverage_questions_at_initial_estimate: YesNoUnknown = indicator_field(
        "Whether material coverage questions remained unresolved when the "
        "initial estimate was completed."
    )


class InitialDocumentationFeatures(BaseModel):
    """
    Evaluate the completeness and quality of claim documentation available for
    preparation of the initial estimate.

    Assess documentation as it existed at the cutoff. Do not use later-created
    photos or notes to conclude that the original documentation was adequate.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    measurement_scope: Annotated[
        Literal[
            "roof_only",
            "exterior_only",
            "roof_and_exterior",
            "roof_exterior_and_interior",
            "interior_only",
            "other",
            "not_applicable",
            "unknown",
        ],
        Category,
    ] = Field(default="unknown", description="Scope actually measured by the cutoff.")
    measurement_discrepancy_documented: YesNoUnknown = indicator_field(
        "Whether a measurement discrepancy was documented before the initial cutoff."
    )
    overview_and_close_up_photos_present: YesNoUnknown = indicator_field(
        "Whether initial supplied evidence documents both overview and close-up photographs."
    )
    all_damaged_elevations_or_slopes_photographed: Annotated[
        Literal[
            "yes",
            "no",
            "not_applicable",
            "unknown",
        ],
        Category,
    ] = Field(
        default="unknown",
        description=(
            "Whether all initially known damaged elevations/slopes were photographed. "
            "Use not_applicable when none were involved; unknown for insufficient evidence."
        ),
    )

    photo_documentation_adequate: YesNoUnknown = indicator_field(
        "Whether the initial photographic documentation appears sufficient to "
        "reasonably understand the major documented damaged areas and components."
    )

    notes_documentation_adequate: YesNoUnknown = indicator_field(
        "Whether initial inspection and claim notes appear sufficiently detailed "
        "to explain the material observed damage and estimating decisions."
    )

    measurements_documented: YesNoUnknown = indicator_field(
        "Whether measurements relevant to the initial repair scope were "
        "documented or otherwise supported."
    )

    all_visible_damage_documented: YesNoUnknown = indicator_field(
        "Whether all materially visible damage apparent from the available "
        "initial evidence appears to have been documented."
    )

    documentation_quality: ComplexityLevel = Field(
        default="unknown",
        description=(
            "Overall quality of initial claim documentation. Use low for "
            "material gaps or weak support, moderate for generally usable but "
            "imperfect documentation, high for comprehensive and well-supported "
            "documentation, and unknown when it cannot be assessed."
        ),
    )

    important_documentation_gaps_present: YesNoUnknown = indicator_field(
        "Whether one or more material gaps in photographs, measurements, notes, "
        "or other documentation could reasonably affect estimating accuracy."
    )


class InitialEstimateFeatures(BaseModel):
    """
    Characterize quality, completeness, and support for the original estimate
    using only information available at the initial-estimate cutoff.

    This section intentionally evaluates the initial estimate itself and should
    not use later supplement outcomes as evidence that the estimate was wrong.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    initial_estimate_amount: Number = Field(
        default=None,
        ge=0,
        description=(
            "Total initial estimate amount when clearly supported by the file. "
            "Use the relevant total estimate value consistently across claims."
        ),
    )

    repair_versus_replace_rationale_documented: Annotated[
        Literal[
            "yes",
            "no",
            "not_applicable",
            "unknown",
        ],
        Category,
    ] = Field(
        default="unknown",
        description=(
            "Whether the initial repair-versus-replace rationale was documented. "
            "Use not_applicable only when that decision did not arise."
        ),
    )

    scope_appears_complete_for_documented_damage: YesNoUnknown = indicator_field(
        "Whether the initial estimate appears to address all material damage "
        "that was documented and reasonably estimable at that time."
    )

    quantities_appear_supported: YesNoUnknown = indicator_field(
        "Whether material quantities used in the initial estimate appear "
        "consistent with documented measurements and observed scope."
    )

    measurements_appear_supported: YesNoUnknown = indicator_field(
        "Whether measurements underlying the initial estimate are documented "
        "or otherwise reasonably supported by the available evidence."
    )

    visible_damaged_items_omitted: YesNoUnknown = indicator_field(
        "Whether a materially damaged item that was visibly documented before "
        "the cutoff appears to have been omitted from the initial estimate."
    )

    potentially_incorrect_quantities_identified: YesNoUnknown = indicator_field(
        "Whether the information available at the initial-estimate stage itself "
        "indicates a potentially material quantity or measurement error."
    )

    matching_issue_addressed: YesNoUnknown = indicator_field(
        "When a matching concern was apparent initially, whether the initial "
        "estimate or claim handling meaningfully recognized or addressed it."
    )

    potential_code_issue_addressed: YesNoUnknown = indicator_field(
        "When a code or ordinance concern was apparent initially, whether the "
        "initial estimate or claim handling meaningfully recognized or "
        "addressed it."
    )

    potential_concealed_damage_acknowledged: YesNoUnknown = indicator_field(
        "Whether known potential for concealed or hidden damage was documented "
        "or otherwise acknowledged during the initial estimating process."
    )

    estimate_consistent_with_photos: YesNoUnknown = indicator_field(
        "Whether the initial estimate is materially consistent with the damage "
        "and affected components visible in the initial photographs."
    )

    estimate_consistent_with_claim_notes: YesNoUnknown = indicator_field(
        "Whether the initial estimate is materially consistent with the damage "
        "and repair scope described in the initial claim or inspection notes."
    )

    unresolved_scope_issue_at_estimate_completion: YesNoUnknown = indicator_field(
        "Whether a material scope issue was known to remain unresolved when "
        "the initial estimate was completed."
    )

    overall_initial_estimate_quality: ComplexityLevel = Field(
        default="unknown",
        description=(
            "Overall quality of the initial estimate based on completeness, "
            "support, consistency, and apparent accuracy. Use low for material "
            "deficiencies, moderate for generally reasonable but imperfect "
            "estimating, high for well-supported and comprehensive estimating, "
            "and unknown when assessment is not possible."
        ),
    )


class BaselineClaimFeatures(BaseModel):
    """
    Primary pre-supplement LLM feature group.

    This model represents the claim as it was known when the initial estimate
    was completed. Its purpose is to create case-mix, complexity, documentation,
    and initial-estimate variables that may safely be considered when comparing
    Hover and pre-Hover populations.

    STRICT TEMPORAL RULE:
    Do not allow subsequent supplement requests, revised estimates, reinspection
    findings, later contractor documentation, final estimates, or other later
    developments to influence these fields.

    Because these features precede the supplement process, they are the main
    LLM-derived candidates for adjustment, segmentation, predictive modeling,
    and treatment-effect heterogeneity analysis.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    initial_estimate_cutoff_date: Date = date_field(
        "Date representing the end of the information window allowed for "
        "baseline extraction, typically the date the initial estimate was "
        "completed or issued."
    )

    property_complexity: PropertyComplexityFeatures = Field(
        description=(
            "Physical property characteristics affecting inspection, "
            "measurement, and repair complexity."
        )
    )

    roof: RoofFeatures = Field(
        description=("Roof-specific characteristics known by the initial-estimate cutoff.")
    )

    damage: DamageCharacteristics = Field(
        description=(
            "Nature, extent, and characteristics of damage known during the "
            "initial estimating process."
        )
    )

    claim_context: InitialClaimContext = Field(
        description=(
            "Contextual claim circumstances, contractor participation, access "
            "limitations, disputes, and unresolved issues present initially."
        )
    )

    documentation: InitialDocumentationFeatures = Field(
        description=(
            "Assessment of the quality and completeness of documentation "
            "available for preparation of the initial estimate."
        )
    )

    initial_estimate: InitialEstimateFeatures = Field(
        description=(
            "Structured assessment of completeness, consistency, support, and "
            "quality of the initial estimate."
        )
    )

    overall_claim_complexity: ComplexityLevel = Field(
        default="unknown",
        description=(
            "Overall complexity of accurately inspecting, documenting, and "
            "estimating the claim at the initial stage. Consider the complete "
            "baseline claim rather than supplement activity."
        ),
    )

    baseline_summary: Text = text_field(
        "Concise factual summary of the claim as it appeared at the initial "
        "estimate cutoff. Do not mention or rely on later supplement outcomes."
    )

    def to_pandas(
        self,
        *,
        extra_columns: Mapping[str, Any] | None = None,
        drop_text: bool = True,
        indicators_as_boolean: bool = True,
        unknown_as_na: bool = True,
    ) -> pd.DataFrame:
        """
        Return a one-row flattened DataFrame of baseline features.

        Column names are prefixed with ``baseline__``. Nested attributes use
        ``__`` separators.

        ``extra_columns`` should be used for deterministic structured variables
        such as claim_id, Hover status, peril, sub-peril, DOL, FNOL date, or
        sampling weight rather than asking the LLM to reproduce those values.
        """
        return _prepare_flat_dataframe(
            self,
            column_prefix="baseline",
            extra_columns=extra_columns,
            drop_text=drop_text,
            indicators_as_boolean=indicators_as_boolean,
            unknown_as_na=unknown_as_na,
        )


# ===========================================================================#
# FEATURE GROUP 2
# SUPPLEMENT / POST-ESTIMATE MECHANISM FEATURES
# ===========================================================================#


class SupplementFinancialFeatures(BaseModel):
    """
    Extract financial values associated with the supplement and revised estimate.

    Prefer explicit documented values. Do not reconstruct dollar amounts from
    ambiguous narrative information when they cannot be reliably established.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    supplement_requested_amount: Number = Field(
        default=None,
        ge=0,
        description=(
            "Total additional amount requested through the supplement when "
            "clearly supported by the file."
        ),
    )

    supplement_approved_amount: Number = Field(
        default=None,
        ge=0,
        description=(
            "Total additional amount approved or paid because of the supplement "
            "when clearly supported by the file."
        ),
    )

    supplement_denied_amount: Number = Field(
        default=None,
        ge=0,
        description=(
            "Dollar amount of the supplement request that was explicitly denied "
            "or not accepted when the value is reliably determinable."
        ),
    )

    revised_estimate_amount: Number = Field(
        default=None,
        ge=0,
        description=(
            "Total revised carrier estimate amount after supplementation when "
            "clearly supported by the file."
        ),
    )

    supplement_pct_of_initial_estimate: Number = Field(
        default=None,
        ge=0,
        description=(
            "Approved supplement amount divided by the initial estimate amount. "
            "Represent the value as a decimal ratio, where 0.25 means 25%."
        ),
    )


class SupplementDrivers(BaseModel):
    """Any occurrence across the entire supplied history, not just the main request."""

    model_config = ConfigDict(extra="forbid")
    missed_item: YesNoUnknown = indicator_field("A documented damaged item/operation was omitted.")
    additional_area: YesNoUnknown = indicator_field("An additional room, slope or area was sought.")
    measurement_correction: YesNoUnknown = indicator_field(
        "An incorrect dimension, area or count contributed; exclude repairability disagreements."
    )
    pricing_change: YesNoUnknown = indicator_field("Pricing changes contributed to a request.")
    concealed_damage_after_demolition: YesNoUnknown = indicator_field(
        "Damage became discoverable only after demolition or removal."
    )
    later_visible_damage: YesNoUnknown = indicator_field(
        "Damage became observable later without demolition."
    )
    changed_condition: YesNoUnknown = indicator_field("Physical conditions changed after cutoff.")
    new_loss_or_event: YesNoUnknown = indicator_field("A new loss or event contributed.")
    matching: YesNoUnknown = indicator_field("Matching requirements contributed.")
    code_or_ordinance: YesNoUnknown = indicator_field("Code or ordinance requirements contributed.")
    overhead_and_profit: YesNoUnknown = indicator_field("Overhead and profit contributed.")
    repair_versus_replace: YesNoUnknown = indicator_field(
        "Known damage was disputed on repairability/remedy, rather than measurement accuracy."
    )
    other_contractor_scope_disagreement: YesNoUnknown = indicator_field(
        "Other contractor scope disagreement contributed."
    )
    coverage_or_administrative: YesNoUnknown = indicator_field(
        "Coverage or administrative issues contributed."
    )
    other: YesNoUnknown = indicator_field("Another documented driver contributed; explain it.")


class PreventionIndicators(BaseModel):
    """Supported prevention actions for any supplement in the history."""

    model_config = ConfigDict(extra="forbid")
    measurement_accuracy: YesNoUnknown = indicator_field(
        "Correcting an initially wrong measurement could have prevented a supplement."
    )
    measurement_scope: YesNoUnknown = indicator_field(
        "Measuring an omitted component could have prevented a supplement."
    )
    photo_documentation: YesNoUnknown = indicator_field(
        "Better photographs could have prevented a supplement."
    )
    damage_assessment_or_repairability: YesNoUnknown = indicator_field(
        "Better damage/repairability assessment or documentation could have prevented a supplement."
    )
    estimate_construction: YesNoUnknown = indicator_field(
        "Correct estimate construction from sound inputs could have prevented a supplement."
    )
    pricing_currency: YesNoUnknown = indicator_field(
        "Correct/current pricing could have prevented a supplement."
    )
    coverage_determination: YesNoUnknown = indicator_field(
        "A correct coverage determination could have prevented a supplement."
    )
    contractor_expectation_setting: YesNoUnknown = indicator_field(
        "Up-front communication could have prevented a request despite a correct estimate."
    )
    process_or_timing: YesNoUnknown = indicator_field(
        "Better timing, handoffs or sequencing could have prevented a supplement."
    )


class SupplementHistory(BaseModel):
    model_config = ConfigDict(extra="forbid")
    completeness: Annotated[Literal["complete", "partial", "unclear"], Category] = Field(
        default="unclear",
        description="Completeness of the supplement history in supplied evidence.",
    )
    total_count: Count = Field(
        default=None,
        ge=0,
        description=(
            "Exact number of distinct substantive requests. Revisions and negotiations within "
            "an unresolved request are one supplement. Null if the total is unsupported."
        ),
    )
    approved_count: Count = Field(
        default=None,
        ge=0,
        description=(
            "Exact count approved in full or part. Null if the whole-history count is unsupported."
        ),
    )
    denied_count: Count = Field(
        default=None,
        ge=0,
        description=("Exact count denied in full, excluding partial denials. Null if unsupported."),
    )
    pending_count: Count = Field(
        default=None,
        ge=0,
        description=(
            "Exact count still pending. Unknown disposition is not pending. Null if unsupported."
        ),
    )

    @model_validator(mode="after")
    def consistent_counts(self):
        if self.completeness != "complete" and self.total_count is not None:
            raise ValueError("Exact total_count requires complete history")
        counts = (self.approved_count, self.denied_count, self.pending_count)
        if (
            self.total_count is not None
            and sum(c for c in counts if c is not None) > self.total_count
        ):
            raise ValueError("Known disposition counts exceed total_count")
        return self


class RoofingSupplementFeatures(BaseModel):
    """Whole-history roofing facts, separate from the selected main supplement."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    revised_roof_squares: Number = Field(
        default=None,
        ge=0,
        description=(
            "Latest documented carrier roof-area measurement in SQ, not contractor-requested or "
            "repair/replacement scope SQ. Null when unsupported; do not copy initial area forward."
        ),
    )
    measured_sq_comparable: YesNoUnknown = indicator_field(
        "Whether initial and revised measured SQ cover the same roof/buildings and area basis. "
        "No for different structures, partial versus whole roofs, or incompatible waste bases."
    )
    revised_estimated_roof_squares: Number = Field(
        default=None,
        ge=0,
        description=(
            "Roofing repair/replacement SQ in the latest carrier-approved estimate. Exclude "
            "unapproved contractor requests and duplicate removal/install line items. "
            "Null if unknown."
        ),
    )
    estimated_sq_comparable: YesNoUnknown = indicator_field(
        "Whether initial and latest carrier scope SQ use comparable units, building/component "
        "coverage and waste conventions. Expanded repair area on the same roof is comparable; "
        "a newly included unrelated structure or incompatible waste basis is not."
    )
    final_repair_scope: RoofRepairScope = Field(
        default="unknown",
        description=(
            "Latest documented carrier-approved roof remedy; not the contractor's desired remedy."
        ),
    )
    repair_to_replace_requested: YesNoUnknown = indicator_field(
        "Any supplement sought to change an initial carrier roof repair to partial/full "
        "replacement. Include denied/pending requests. Do not infer from quantity growth alone."
    )
    repair_to_replace_approved: YesNoUnknown = indicator_field(
        "Whether the carrier approved any roof repair-to-partial/full-replacement supplement. "
        "Other approved dollars do not establish approval of this particular change."
    )


class SupplementMechanismFeatures(BaseModel):
    """One directly extracted claim summary; all primary fields refer to the same supplement.

    These retrospective fields are excluded from baseline prediction and primary adjustment.
    Dollar associations are claim dollars, never allocated causes or recoverable savings.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    supplement_present: YesNoUnknown = indicator_field(
        "Whether any substantive post-estimate request/revision exists, including denied/pending."
    )
    history: SupplementHistory = Field(
        default_factory=SupplementHistory,
        description="Whole-history completeness and exact counts where supported.",
    )
    primary_mechanism: PrimarySupplementMechanism = Field(
        default="unclear",
        description=(
            "Cause of the main supplement, selected by largest incremental approval, then request "
            "if none approved, then documented materiality if amounts cannot support ranking. "
            "Break ties by earliest documented request, then source order."
        ),
    )
    primary_selection_basis: Annotated[
        Literal[
            "approved_amount",
            "requested_amount",
            "qualitative_materiality",
            "unclear",
            "not_applicable",
        ],
        Category,
    ] = Field(
        default="unclear",
        description=(
            "Main supplement selection basis; explain incomplete comparisons in the summary."
        ),
    )
    primary_outcome: SupplementOutcome = Field(
        default="unclear",
        description="Disposition of the main supplement only; zero dollars do not prove denial.",
    )
    primary_initial_identifiability: Annotated[
        Literal[
            "clearly_no",
            "probably_no",
            "unclear",
            "probably_yes",
            "clearly_yes",
            "not_applicable",
        ],
        Category,
    ] = Field(
        default="unclear",
        description=(
            "Whether the main issue could reasonably have been identified at the initial estimate. "
            "Identifiability does not establish avoidability."
        ),
    )
    potentially_avoidable: PotentialAvoidability = Field(
        default="unclear",
        description=(
            "Avoidability of the MAIN supplement through reasonable initial carrier actions, "
            "without hindsight. Preventing a supplement does not establish indemnity savings."
        ),
    )
    avoidability_confidence: ConfidenceLevel = Field(
        default="unknown",
        description="Confidence in the main supplement's avoidability based on evidence quality.",
    )
    primary_prevention_area: PreventionArea = Field(
        default="unclear",
        description="Main supplement's most relevant prevention action area, if supported.",
    )
    primary_unavoidable_reason: UnavoidableReason = Field(
        default="unclear",
        description="Reason the main supplement was unavoidable; not_applicable when avoidable.",
    )
    primary_request_preventable: Annotated[
        Literal[
            "yes",
            "no",
            "unknown",
            "not_applicable",
        ],
        Category,
    ] = Field(
        default="unknown",
        description=(
            "Could the main request have been prevented, separately from estimate correctness? "
            "Assess even denied requests; not_applicable only if no supplement exists."
        ),
    )
    primary_prevention_action: Text = text_field(
        "Specific action and brief evidence-based rationale for preventing the main supplement; "
        "state none identified if supported. Do not estimate savings."
    )
    secondary_mechanism: PrimarySupplementMechanism = Field(
        default="unclear",
        description=(
            "Dominant cause among ALL remaining supplements, not the second chronological request. "
            "Use multiple for no dominant cause, unclear for insufficient evidence, "
            "not_applicable only when none remain."
        ),
    )
    remaining_outcome: Annotated[
        Literal[
            "approved_in_full",
            "approved_in_part",
            "denied_in_full",
            "withdrawn_by_requester",
            "pending",
            "mixed",
            "unclear",
            "not_applicable",
        ],
        Category,
    ] = Field(
        default="unclear",
        description=(
            "Outcome of all remaining supplements. Mixed requires established different outcomes; "
            "otherwise incomplete evidence is unclear, and no remainder is not_applicable."
        ),
    )
    remaining_avoidability: Annotated[
        Literal[
            "avoidable",
            "unavoidable",
            "mixed",
            "unclear",
            "not_applicable",
        ],
        Category,
    ] = Field(
        default="unclear",
        description=(
            "Avoidability across all remaining supplements; collapse clearly/probably into their "
            "direction. Mixed requires supported avoidable and unavoidable supplements."
        ),
    )
    drivers: SupplementDrivers = Field(
        default_factory=SupplementDrivers,
        description="Whole-history contributing drivers, including third and later supplements.",
    )
    prevention: PreventionIndicators = Field(
        default_factory=PreventionIndicators,
        description="Whole-history prevention areas; missing evidence is unknown, not no.",
    )
    any_potentially_avoidable: YesNoUnknown = indicator_field(
        "Whether ANY supplement was clearly/probably avoidable, even if main was unavoidable. "
        "A positive finding survives incomplete history; no requires coverage of the full history."
    )
    mechanism_summary: Text = text_field(
        "Concise whole-history narrative: main issue and selection, remaining activity, evidence, "
        "and uncertainty. Explain conflicting facts and incomplete financial comparisons."
    )
    financials: SupplementFinancialFeatures = Field(
        default_factory=SupplementFinancialFeatures,
        description="Explicit claim-level incremental amounts for QA, never allocations.",
    )
    roofing: RoofingSupplementFeatures = Field(
        default_factory=RoofingSupplementFeatures,
        description="Whole-history roof measurement/scope changes and request versus approval.",
    )

    @model_validator(mode="after")
    def consistent_history(self):
        if (
            self.roofing.repair_to_replace_approved == "yes"
            and self.roofing.repair_to_replace_requested == "no"
        ):
            raise ValueError("Approved repair-to-replacement conflicts with no such request")
        total = self.history.total_count
        outcome_count = {
            "approved_in_full": self.history.approved_count,
            "approved_in_part": self.history.approved_count,
            "denied_in_full": self.history.denied_count,
            "pending": self.history.pending_count,
        }.get(self.primary_outcome)
        if outcome_count == 0:
            raise ValueError("Main outcome conflicts with zero disposition count")
        if (
            total is not None
            and total > 1
            and any(
                getattr(self, name) == "not_applicable"
                for name in ("secondary_mechanism", "remaining_outcome", "remaining_avoidability")
            )
        ):
            raise ValueError("Multiple supplements require applicable remaining classifications")
        if total == 2 and "mixed" in (self.remaining_outcome, self.remaining_avoidability):
            raise ValueError(
                "Mixed remaining classifications require at least two other supplements"
            )
        if (
            self.any_potentially_avoidable == "no"
            and self.supplement_present != "no"
            and self.history.completeness != "complete"
        ):
            raise ValueError("No avoidable supplement requires complete history")
        if self.supplement_present == "yes" and total == 0:
            raise ValueError("Supplement presence conflicts with zero total_count")
        if self.supplement_present == "no":
            for name in ("repair_to_replace_requested", "repair_to_replace_approved"):
                if getattr(self.roofing, name) == "yes":
                    raise ValueError("No supplement conflicts with a roof replacement transition")
                setattr(self.roofing, name, "no")
            if any(
                (getattr(self.history, n) or 0) > 0
                for n in (
                    "total_count",
                    "approved_count",
                    "denied_count",
                    "pending_count",
                )
            ) or any(
                (getattr(self.financials, n) or 0) > 0
                for n in (
                    "supplement_requested_amount",
                    "supplement_approved_amount",
                    "supplement_denied_amount",
                )
            ):
                raise ValueError(
                    "No supplement conflicts with positive counts or supplement dollars"
                )
            if (
                any(
                    v == "yes"
                    for g in (self.drivers, self.prevention)
                    for v in g.model_dump().values()
                )
                or self.any_potentially_avoidable == "yes"
            ):
                raise ValueError("No supplement conflicts with positive supplement indicators")
            for name in (
                "primary_mechanism",
                "primary_selection_basis",
                "primary_outcome",
                "primary_initial_identifiability",
                "potentially_avoidable",
                "primary_prevention_area",
                "primary_unavoidable_reason",
                "primary_request_preventable",
                "secondary_mechanism",
                "remaining_outcome",
                "remaining_avoidability",
            ):
                if getattr(self, name) not in {"unknown", "unclear", "not_applicable"}:
                    raise ValueError("No supplement conflicts with supplement classification")
                setattr(self, name, "not_applicable")
            self.history = SupplementHistory(
                completeness="complete",
                total_count=0,
                approved_count=0,
                denied_count=0,
                pending_count=0,
            )
            self.drivers = SupplementDrivers(**dict.fromkeys(SupplementDrivers.model_fields, "no"))
            self.prevention = PreventionIndicators(
                **dict.fromkeys(PreventionIndicators.model_fields, "no")
            )
            self.any_potentially_avoidable = "no"
        elif total == 1:
            for name in ("secondary_mechanism", "remaining_outcome", "remaining_avoidability"):
                if getattr(self, name) not in {"unclear", "not_applicable"}:
                    raise ValueError("Single supplement conflicts with remaining classifications")
                setattr(self, name, "not_applicable")
        if self.any_potentially_avoidable == "no" and (
            self.potentially_avoidable in {"clearly_avoidable", "probably_avoidable"}
            or self.remaining_avoidability in {"avoidable", "mixed"}
        ):
            raise ValueError("Avoidability classifications conflict with any_potentially_avoidable")
        return self

    def to_pandas(
        self,
        *,
        extra_columns: Mapping[str, Any] | None = None,
        drop_text: bool = True,
        indicators_as_boolean: bool = True,
        unknown_as_na: bool = True,
    ) -> pd.DataFrame:
        """
        Return a one-row flattened DataFrame of supplement mechanism features.

        Column names are prefixed with ``supplement_mechanism__``.

        This representation is suited to mechanism analysis and descriptive
        comparison rather than primary adjustment for Hover's total effect.
        """
        return _prepare_flat_dataframe(
            self,
            column_prefix="supplement_mechanism",
            extra_columns=extra_columns,
            drop_text=drop_text,
            indicators_as_boolean=indicators_as_boolean,
            unknown_as_na=unknown_as_na,
        )


# ===========================================================================#
# OPTIONAL COMBINED OUTPUT
# ===========================================================================#


class ClaimLLMFeatures(BaseModel):
    """
    Combined LLM output containing both temporally distinct feature groups.

    ``baseline`` represents information available by completion of the original
    estimate.

    ``supplement_mechanism`` represents later information used to understand
    estimate revisions and supplement mechanisms.

    Keeping these groups structurally separate makes it harder for downstream
    analysis to accidentally use post-treatment mechanism variables as baseline
    adjustment variables.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    baseline: BaselineClaimFeatures = Field(
        description=(
            "Pre-supplement baseline characterization of the loss, property, "
            "documentation, and initial estimate."
        )
    )

    supplement_mechanism: SupplementMechanismFeatures = Field(
        description=(
            "Post-estimate characterization of supplement mechanisms and later estimate changes."
        )
    )

    def to_pandas(
        self,
        *,
        extra_columns: Mapping[str, Any] | None = None,
        drop_text: bool = True,
        indicators_as_boolean: bool = True,
        unknown_as_na: bool = True,
    ) -> pd.DataFrame:
        """
        Return one flattened analysis-ready claim row containing both groups.

        Baseline columns begin with ``baseline__`` and supplement columns begin
        with ``supplement_mechanism__``.

        ``extra_columns`` is the preferred location for authoritative structured
        data such as claim_id, Hover status, peril, sub-peril, DOL, FNOL date,
        initial estimate from the claim system, or sample weights.
        """
        return _prepare_flat_dataframe(
            self,
            column_prefix=None,
            extra_columns=extra_columns,
            drop_text=drop_text,
            indicators_as_boolean=indicators_as_boolean,
            unknown_as_na=unknown_as_na,
        )
