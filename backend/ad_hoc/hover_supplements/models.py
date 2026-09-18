"""Feature definitions ported from the user-supplied Hover planning conversation.

Source: https://chatgpt.com/share/6aac6fae-a418-83ea-bb97-b22e29431a0d
Field descriptions and enums are retained; conversion is implemented in dataframes.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from .dataframes import prepare_flat_dataframe as _prepare_flat_dataframe

# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

YesNoUnknown = Literal["yes", "no", "unknown"]
ComplexityLevel = Literal["low", "moderate", "high", "unknown"]
ConfidenceLevel = Literal["low", "medium", "high", "unknown"]

InitialIdentifiability = Literal[
    "clearly_no",
    "probably_no",
    "unclear",
    "probably_yes",
    "clearly_yes",
]

PotentialAvoidability = Literal[
    "clearly_avoidable",
    "probably_avoidable",
    "unclear",
    "probably_unavoidable",
    "clearly_unavoidable",
    "not_applicable",
]

PrimarySupplementMechanism = Literal[
    "scope_expansion",
    "quantity_change",
    "pricing_change",
    "hidden_damage",
    "matching",
    "code_or_ordinance",
    "overhead_and_profit",
    "contractor_disagreement",
    "coverage_or_administrative",
    "multiple",
    "other",
    "unclear",
    "not_applicable",
]


# ---------------------------------------------------------------------------
# Field helpers
#
# pandas_kind is deliberately embedded in the Pydantic schema metadata so the
# same schema that guides the LLM also tells to_pandas() how to prepare data.
# ---------------------------------------------------------------------------


def indicator_field(description: str) -> Any:
    """Create a yes/no/unknown field that becomes nullable boolean in pandas."""
    return Field(
        default="unknown",
        description=description,
        json_schema_extra={"pandas_kind": "indicator"},
    )


def date_field(description: str) -> Any:
    """Create an optional date field that becomes datetime64 in pandas."""
    return Field(
        default=None,
        description=description,
        json_schema_extra={"pandas_kind": "date"},
    )


def text_field(description: str) -> Any:
    """Create optional narrative text that may be dropped from ML tables."""
    return Field(
        default=None,
        description=description,
        json_schema_extra={"pandas_kind": "text"},
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

    stories: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Number of above-ground stories for the affected structure when "
            "the value is explicitly stated or reliably documented."
        ),
    )

    structures_involved: int | None = Field(
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

    rooms_affected: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Approximate number of distinct interior rooms or spaces with "
            "documented claimed damage."
        ),
    )

    building_components_affected: int | None = Field(
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


class RoofFeatures(BaseModel):
    """
    Describe roof characteristics known at the time of the initial estimate.

    These features are intended to capture roof-related case mix and estimating
    complexity independently of any later supplement.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    roof_present_in_scope: YesNoUnknown = indicator_field(
        "Whether the initial loss scope included repair or replacement of any roof component."
    )

    roof_squares: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Initial documented roof area in roofing squares, where one square "
            "represents approximately 100 square feet."
        ),
    )

    roof_pitch: str | None = Field(
        default=None,
        description=(
            "Documented roof pitch or slope. Preserve the source representation "
            "when possible, such as '6/12'. Do not infer a pitch when it is not "
            "supported by the file."
        ),
    )

    roof_facets_or_slopes: int | None = Field(
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

    initial_estimate_amount: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Total initial estimate amount when clearly supported by the file. "
            "Use the relevant total estimate value consistently across claims."
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

    initial_estimate_cutoff_date: date | None = date_field(
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

    baseline_summary: str | None = text_field(
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


class ScopeExpansionDrivers(BaseModel):
    """
    Identify whether the repair scope increased after the initial estimate and
    characterize the specific mechanisms responsible for that increase.

    Multiple drivers may be true for the same claim.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    scope_expanded: YesNoUnknown = indicator_field(
        "Whether the later estimate or supplement added materially new repair "
        "scope beyond the initial estimate."
    )

    missed_item: YesNoUnknown = indicator_field(
        "Whether a damaged item or repair operation was omitted from the "
        "initial estimate and later added."
    )

    additional_damaged_area: YesNoUnknown = indicator_field(
        "Whether the later estimate added a room, elevation, slope, structure, "
        "or other damaged area that was not included initially."
    )

    demolition_increased: YesNoUnknown = indicator_field(
        "Whether demolition, tear-out, removal, or access-related scope "
        "materially increased after the initial estimate."
    )

    additional_layers_or_materials: YesNoUnknown = indicator_field(
        "Whether additional material layers, assemblies, or component layers "
        "were later included in the repair scope."
    )

    matching_issue: YesNoUnknown = indicator_field(
        "Whether matching considerations materially caused or contributed to scope expansion."
    )

    hidden_or_concealed_damage: YesNoUnknown = indicator_field(
        "Whether previously concealed or non-observable damage materially "
        "caused or contributed to scope expansion."
    )

    code_required_scope: YesNoUnknown = indicator_field(
        "Whether building code, ordinance, or required upgrade considerations "
        "materially added repair scope."
    )

    contractor_requested_scope: YesNoUnknown = indicator_field(
        "Whether a contractor or repair representative requested materially "
        "additional repair scope beyond the initial estimate."
    )

    added_items_count: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Approximate number of distinct repair line items or components "
            "newly added after the initial estimate when reliably determinable."
        ),
    )

    added_rooms_or_areas_count: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Approximate number of newly added rooms, elevations, roof areas, "
            "structures, or other materially distinct damage areas."
        ),
    )


class QuantityChangeDrivers(BaseModel):
    """
    Characterize revisions to measurements, quantities, dimensions, labor
    amounts, or material amounts after the initial estimate.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    quantities_changed: YesNoUnknown = indicator_field(
        "Whether one or more material repair quantities changed between the "
        "initial and later estimate."
    )

    measurement_correction: YesNoUnknown = indicator_field(
        "Whether corrected or revised measurements materially contributed to the supplement."
    )

    dimensions_changed: YesNoUnknown = indicator_field(
        "Whether documented dimensions materially changed after the initial estimate."
    )

    roof_squares_changed: YesNoUnknown = indicator_field(
        "Whether the estimated number of roofing squares materially changed."
    )

    material_quantity_changed: YesNoUnknown = indicator_field(
        "Whether the quantity of a repair material materially changed."
    )

    labor_quantity_changed: YesNoUnknown = indicator_field(
        "Whether labor hours, labor units, or another labor quantity materially changed."
    )

    initial_roof_squares: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Roofing squares reflected in the initial estimate when the value "
            "can be reliably established."
        ),
    )

    revised_roof_squares: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Roofing squares reflected after revision or supplementation when "
            "the value can be reliably established."
        ),
    )

    material_quantity_change_pct: float | None = Field(
        default=None,
        description=(
            "Approximate percentage change in a material quantity when a "
            "meaningful comparable quantity can be calculated from the file."
        ),
    )


class PricingChangeDrivers(BaseModel):
    """
    Identify supplements primarily associated with price changes rather than
    new physical repair scope.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    pricing_materially_changed: YesNoUnknown = indicator_field(
        "Whether changes in pricing materially contributed to the supplement."
    )

    unit_price_changed: YesNoUnknown = indicator_field(
        "Whether one or more unit prices materially changed from the initial estimate."
    )

    labor_rate_changed: YesNoUnknown = indicator_field(
        "Whether a change in labor rate materially contributed to the supplement."
    )

    material_price_changed: YesNoUnknown = indicator_field(
        "Whether a change in material pricing materially contributed to the supplement."
    )

    pricing_database_or_price_list_changed: YesNoUnknown = indicator_field(
        "Whether use of a different estimating price list, database version, "
        "location, or pricing period materially contributed to the change."
    )

    market_condition_adjustment: YesNoUnknown = indicator_field(
        "Whether documented local market conditions or actual contractor costs "
        "materially exceeded initial estimating assumptions."
    )


class AdditionalCostDrivers(BaseModel):
    """
    Capture identifiable cost categories that may be added after the original
    estimate even when the underlying physical damage is largely unchanged.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    code_or_ordinance_added: YesNoUnknown = indicator_field(
        "Whether code, ordinance, permit-driven upgrade, or required compliance "
        "costs were materially added after the initial estimate."
    )

    matching_added: YesNoUnknown = indicator_field(
        "Whether additional cost attributable to matching considerations was "
        "materially added after the initial estimate."
    )

    overhead_and_profit_added: YesNoUnknown = indicator_field(
        "Whether contractor overhead and profit was newly added or materially "
        "increased after the initial estimate."
    )

    permit_or_fee_added: YesNoUnknown = indicator_field(
        "Whether permits, inspections, engineering charges, disposal fees, or "
        "similar required fees were materially added."
    )

    equipment_or_access_cost_added: YesNoUnknown = indicator_field(
        "Whether scaffolding, lifts, steep/high charges, access equipment, "
        "mobilization, or similar costs were materially added."
    )

    code_related_amount: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Approximate dollar amount attributable to code or ordinance "
            "changes when separately identifiable."
        ),
    )

    matching_related_amount: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Approximate dollar amount attributable to matching when separately identifiable."
        ),
    )

    overhead_and_profit_amount: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Approximate dollar amount attributable to newly added or increased "
            "overhead and profit when separately identifiable."
        ),
    )


class SupplementDiscoveryFeatures(BaseModel):
    """
    Determine whether genuinely new information or newly observable damage
    emerged after the initial estimate.

    These features help separate potentially preventable initial-estimate
    deficiencies from changes that could not reasonably have been known earlier.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    new_damage_discovered: YesNoUnknown = indicator_field(
        "Whether material damage not known at the initial-estimate stage was later discovered."
    )

    concealed_damage_discovered_after_demolition: YesNoUnknown = indicator_field(
        "Whether material damage became discoverable only after demolition, "
        "tear-off, removal of finishes, or another invasive repair step."
    )

    additional_damage_became_visible_later: YesNoUnknown = indicator_field(
        "Whether material damage became observable later even if formal "
        "demolition was not required."
    )

    condition_changed_after_initial_estimate: YesNoUnknown = indicator_field(
        "Whether the physical condition materially changed after the initial "
        "estimate in a way that affected repair scope or cost."
    )

    new_loss_or_additional_event_occurred: YesNoUnknown = indicator_field(
        "Whether a later event, additional damage occurrence, or separate loss "
        "materially contributed to the revised scope or amount."
    )

    later_information_required_to_identify_change: YesNoUnknown = indicator_field(
        "Whether information unavailable at the initial-estimate stage was "
        "reasonably necessary to identify the later change."
    )


class SupplementInitiationFeatures(BaseModel):
    """
    Capture who or what initiated reconsideration of the original estimate and
    the nature of any estimate disagreement.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    contractor_initiated: YesNoUnknown = indicator_field(
        "Whether a contractor or repair representative initiated or materially "
        "prompted the supplement request."
    )

    insured_initiated: YesNoUnknown = indicator_field(
        "Whether the insured initiated or materially prompted the supplement request."
    )

    adjuster_initiated: YesNoUnknown = indicator_field(
        "Whether the carrier adjuster independently initiated or materially "
        "prompted revision of the estimate."
    )

    reinspection_initiated: YesNoUnknown = indicator_field(
        "Whether findings from a reinspection initiated or materially prompted "
        "revision of the estimate."
    )

    contractor_estimate_received: YesNoUnknown = indicator_field(
        "Whether a contractor estimate was received as part of or before the supplement process."
    )

    contractor_estimate_amount: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Total contractor estimate amount associated with the supplement "
            "when the amount can be reliably determined."
        ),
    )

    disagreement_with_initial_scope: YesNoUnknown = indicator_field(
        "Whether disagreement with the physical repair scope of the initial "
        "estimate materially contributed to supplementation."
    )

    disagreement_with_initial_pricing: YesNoUnknown = indicator_field(
        "Whether disagreement with pricing in the initial estimate materially "
        "contributed to supplementation."
    )


class InitialIdentifiabilityFeatures(BaseModel):
    """
    Capture factual evidence needed to assess whether the later supplement
    could reasonably have been anticipated or incorporated initially.

    Prefer these lower-level factual questions over asking the LLM whether
    Hover itself caused, prevented, or failed to prevent a supplement.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    supplemented_damage_visible_initially: YesNoUnknown = indicator_field(
        "Whether the damage ultimately included in the supplement was physically "
        "visible or reasonably observable at the initial inspection."
    )

    supplemented_damage_in_initial_photos: YesNoUnknown = indicator_field(
        "Whether the damage ultimately included in the supplement is visible or "
        "otherwise materially documented in initial photographs."
    )

    supplemented_damage_in_initial_notes: YesNoUnknown = indicator_field(
        "Whether the damage ultimately included in the supplement was described "
        "or materially referenced in initial claim or inspection notes."
    )

    supplemented_component_known_initially: YesNoUnknown = indicator_field(
        "Whether the component later supplemented was known to be damaged or "
        "implicated in the loss during the initial estimating process."
    )

    supplemented_component_in_initial_estimate: YesNoUnknown = indicator_field(
        "Whether the component later supplemented was already represented in "
        "the initial estimate, even if its quantity or scope later changed."
    )

    accurate_quantity_possible_initially: YesNoUnknown = indicator_field(
        "Whether the later-supported quantity or measurement could reasonably "
        "have been obtained during the initial inspection using information and "
        "access available at that time."
    )

    later_demolition_required_for_discovery: YesNoUnknown = indicator_field(
        "Whether demolition, tear-off, removal, or another invasive step was "
        "required before the supplemented condition could reasonably be known."
    )

    later_information_required: YesNoUnknown = indicator_field(
        "Whether material information unavailable during the initial estimating "
        "process was required to support the later supplement."
    )

    could_reasonably_have_been_identified_initially: InitialIdentifiability = Field(
        default="unclear",
        description=(
            "Overall evidence-based assessment of whether the supplemented "
            "scope or condition could reasonably have been identified "
            "during the original inspection and estimating process. Use "
            "clearly_yes only when evidence strongly supports initial "
            "identifiability; probably_yes when more likely than not; "
            "unclear when evidence is insufficient or conflicting; "
            "probably_no when later discovery was likely necessary; and "
            "clearly_no when the condition could not reasonably have been "
            "identified initially."
        ),
    )


class SupplementFinancialFeatures(BaseModel):
    """
    Extract financial values associated with the supplement and revised estimate.

    Prefer explicit documented values. Do not reconstruct dollar amounts from
    ambiguous narrative information when they cannot be reliably established.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    supplement_requested_amount: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Total additional amount requested through the supplement when "
            "clearly supported by the file."
        ),
    )

    supplement_approved_amount: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Total additional amount approved or paid because of the supplement "
            "when clearly supported by the file."
        ),
    )

    supplement_denied_amount: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Dollar amount of the supplement request that was explicitly denied "
            "or not accepted when the value is reliably determinable."
        ),
    )

    revised_estimate_amount: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Total revised carrier estimate amount after supplementation when "
            "clearly supported by the file."
        ),
    )

    supplement_pct_of_initial_estimate: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Approved supplement amount divided by the initial estimate amount. "
            "Represent the value as a decimal ratio, where 0.25 means 25%."
        ),
    )


class SupplementMechanismFeatures(BaseModel):
    """
    Primary post-estimate LLM feature group.

    This model retrospectively describes what changed after the initial estimate,
    why the estimate changed, who initiated reconsideration, what new information
    emerged, and whether the later change appears potentially identifiable at
    the original estimating stage.

    These variables are primarily intended for:
    - supplement mechanism decomposition,
    - root-cause analysis,
    - operational improvement analysis,
    - analysis of potentially avoidable supplements,
    - descriptive comparison between Hover and pre-Hover claims.

    CAUSAL WARNING:
    Most fields in this model occur downstream of the original estimating
    process. They generally should NOT be included as covariates in the primary
    model estimating Hover's total effect on supplement incidence or dollars.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    supplement_present: YesNoUnknown = indicator_field(
        "Whether the claim had a material post-initial-estimate supplement or "
        "comparable estimate revision."
    )

    scope: ScopeExpansionDrivers = Field(
        description=("Features describing new or expanded physical repair scope.")
    )

    quantity: QuantityChangeDrivers = Field(
        description=(
            "Features describing changes to measurements, dimensions, material "
            "quantities, roof quantities, or labor quantities."
        )
    )

    pricing: PricingChangeDrivers = Field(
        description=(
            "Features describing price-based changes independent of physical scope expansion."
        )
    )

    additional_costs: AdditionalCostDrivers = Field(
        description=(
            "Features describing code, matching, overhead and profit, fees, "
            "equipment, access, and similar additional cost categories."
        )
    )

    discovery: SupplementDiscoveryFeatures = Field(
        description=(
            "Features describing newly discovered damage, later-observable "
            "conditions, or other genuinely new information."
        )
    )

    initiation: SupplementInitiationFeatures = Field(
        description=(
            "Features describing who initiated supplementation and the nature "
            "of disagreements with the initial estimate."
        )
    )

    initial_identifiability: InitialIdentifiabilityFeatures = Field(
        description=(
            "Factual evidence used to evaluate whether the supplemented issue "
            "could reasonably have been identified initially."
        )
    )

    financials: SupplementFinancialFeatures = Field(
        description=(
            "Extracted supplement request, approval, denial, and revised estimate financial values."
        )
    )

    primary_mechanism: PrimarySupplementMechanism = Field(
        default="unclear",
        description=(
            "Best high-level characterization of the dominant reason for the "
            "supplement. Use multiple when several materially important "
            "mechanisms contributed and no single mechanism dominates; "
            "not_applicable when there was no supplement; and unclear when the "
            "file does not support a reliable classification."
        ),
    )

    potentially_avoidable: PotentialAvoidability = Field(
        default="unclear",
        description=(
            "Overall assessment of whether the supplement appears potentially "
            "avoidable through an accurate and complete initial inspection and "
            "estimate. Use this as a summarized analytic classification rather "
            "than a statement that Hover itself caused or could have prevented "
            "the supplement."
        ),
    )

    mechanism_summary: str | None = text_field(
        "Concise factual explanation of the principal changes between the "
        "initial estimate and later supplement, including the strongest evidence "
        "for the identified mechanisms."
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
