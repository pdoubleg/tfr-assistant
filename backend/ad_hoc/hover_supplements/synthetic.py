"""Reproducible fictional study with heterogeneous claims; no empirical Hover calibration."""

import json
from datetime import date, timedelta

import numpy as np
from pydantic_ai.models.test import TestModel

from .agents import unknown_features
from .contracts import BaselineOutput, ClaimBundle, Evidence, EvidenceReference, SupplementOutput
from .models import (
    BaselineClaimFeatures,
    PreventionIndicators,
    SupplementDrivers,
    SupplementMechanismFeatures,
)

SYNTHETIC_VERSION = "3"


def _set(features, path, value):
    parts = path.split(".")
    target = features
    for part in parts[:-1]:
        target = getattr(target, part)
    setattr(target, parts[-1], value)


def synthetic_bundles(n=400, seed=42):
    """Stylized case mix, adoption trends, missing documentation and overlapping drivers.

    Programmed associations exercise research tools; they are not estimates of Hover benefit.
    Fixture fields are recorded explicitly in evidence and read by the offline TestModel.
    """
    rng = np.random.default_rng(seed)
    bundles = []
    mechanisms = [
        "quantity_or_measurement_correction",
        "scope_expansion_missed_item",
        "concealed_or_hidden_damage",
        "pricing_change",
        "matching",
        "code_or_ordinance",
        "overhead_and_profit",
        "repairability_or_repair_versus_replace_dispute",
    ]
    for i in range(n):
        day = int(rng.integers(730))
        loss_date = date(2023, 1, 1) + timedelta(days=day)
        peril = str(rng.choice(["hail", "wind", "water", "fire"], p=[0.36, 0.24, 0.32, 0.08]))
        roof = peril in {"hail", "wind"}
        stories = int(rng.choice([1, 2, 3], p=[0.48, 0.44, 0.08]))
        complex_claim = stories == 3 or rng.random() < 0.25
        extent = str(rng.choice(["low", "moderate", "high"], p=[0.30, 0.50, 0.20]))
        hover = bool(rng.random() < (0.25 + 0.20 * roof + 0.20 * day / 730))
        adequate = bool(rng.random() < (0.60 + 0.20 * hover - 0.10 * complex_claim))
        omitted = bool(rng.random() < (0.12 + 0.16 * (not adequate)))
        quantity_error = bool(rng.random() < (0.18 - 0.07 * hover + 0.10 * complex_claim))
        rooms = int(rng.integers(1, 7)) if not roof else 0
        delay = int(rng.choice([1, 2, 4, 10, 21], p=[0.35, 0.30, 0.20, 0.10, 0.05]))
        cutoff = loss_date + timedelta(days=delay + int(rng.integers(3, 15)))
        initial_amount = round(
            float(rng.lognormal(9.1 + 0.25 * complex_claim + 0.35 * (extent == "high"), 0.55)), 2
        )
        baseline = {
            "property_complexity.roof_involved": "yes" if roof else "no",
            "property_complexity.stories": stories,
            "property_complexity.structures_involved": int(rng.choice([1, 2], p=[0.86, 0.14])),
            "property_complexity.rooms_affected": rooms,
            "property_complexity.interior_involved": "no" if roof else "yes",
            "property_complexity.exterior_involved": "yes" if roof else "no",
            "property_complexity.overall_property_complexity": "high"
            if complex_claim
            else "moderate",
            "damage.damage_extent": extent,
            "damage.water_damage": "yes" if peril == "water" else "no",
            "damage.structural_damage": "yes" if peril == "fire" and extent == "high" else "no",
            "damage.concealed_damage_possible": "yes" if peril in {"water", "fire"} else "unknown",
            "damage.matching_issue_possible": "yes" if roof else "unknown",
            "roof.roof_present_in_scope": "yes" if roof else "no",
            "roof.roof_squares": round(float(rng.uniform(15, 55)), 1) if roof else None,
            "roof.complex_geometry": ("yes" if complex_claim else "no") if roof else "unknown",
            "documentation.measurement_scope": "roof_only" if roof else "interior_only",
            "documentation.measurement_discrepancy_documented": "yes" if quantity_error else "no",
            "documentation.overview_and_close_up_photos_present": "yes" if adequate else "unknown",
            "documentation.all_damaged_elevations_or_slopes_photographed": (
                "yes" if adequate else "unknown"
            )
            if roof
            else "not_applicable",
            "roof.repairability_assessed_initially": "yes" if roof and adequate else "unknown",
            "roof.repairability_test_performed_initially": "unknown",
            "initial_estimate.repair_versus_replace_rationale_documented": (
                "yes" if adequate else "unknown"
            )
            if roof
            else "not_applicable",
            "documentation.photo_documentation_adequate": "yes" if adequate else "no",
            "documentation.notes_documentation_adequate": str(
                rng.choice(["yes", "no", "unknown"], p=[0.75, 0.17, 0.08])
            ),
            "documentation.measurements_documented": "yes" if not quantity_error else "no",
            "documentation.all_visible_damage_documented": "no" if omitted else "yes",
            "documentation.documentation_quality": "high"
            if adequate and not omitted
            else "low"
            if not adequate
            else "moderate",
            "documentation.important_documentation_gaps_present": "no" if adequate else "yes",
            "initial_estimate.initial_estimate_amount": initial_amount,
            "initial_estimate.scope_appears_complete_for_documented_damage": "no"
            if omitted
            else "yes",
            "initial_estimate.visible_damaged_items_omitted": "yes" if omitted else "no",
            "initial_estimate.quantities_appear_supported": "no" if quantity_error else "yes",
            "initial_estimate.measurements_appear_supported": "no" if quantity_error else "yes",
            "initial_estimate.potentially_incorrect_quantities_identified": "yes"
            if quantity_error
            else "no",
            "initial_estimate.estimate_consistent_with_photos": "yes"
            if adequate and not omitted
            else "unknown",
            "initial_estimate.overall_initial_estimate_quality": "high"
            if adequate and not omitted and not quantity_error
            else "moderate",
            "claim_context.inspection_access_limited": "yes"
            if complex_claim and rng.random() < 0.4
            else "no",
            "overall_claim_complexity": "high" if complex_claim or extent == "high" else "moderate",
        }
        # Missing source facts, not negative findings; keep amounts and roof involvement known.
        for field in [
            "property_complexity.stories",
            "roof.roof_squares",
            "documentation.documentation_quality",
            "initial_estimate.scope_appears_complete_for_documented_damage",
        ]:
            if rng.random() < 0.08:
                baseline[field] = None if field.endswith(("stories", "roof_squares")) else "unknown"
        probability = 1 / (
            1
            + np.exp(
                -(
                    -1.3
                    + 0.65 * complex_claim
                    + 0.65 * (extent == "high")
                    + 0.6 * omitted
                    + 0.5 * quantity_error
                    - 0.22 * hover
                )
            )
        )
        present = rng.random() < probability
        denied_request = not present and rng.random() < 0.13
        activity = present or denied_request
        approved = (
            round(float(rng.gamma(2.2, initial_amount * (0.045 + 0.025 * complex_claim))), 2)
            if present
            else 0.0
        )
        denied = (
            round(float(rng.uniform(150, 1600)), 2)
            if denied_request or (present and rng.random() < 0.28)
            else 0.0
        )
        # Some requests remain partly unresolved; never infer denied from requested minus approved.
        pending = (
            round(float(rng.uniform(100, 700)), 2) if activity and rng.random() < 0.12 else 0.0
        )
        requested = round(approved + denied + pending, 2)
        supplement = {}
        if activity:
            weights = np.array(
                [
                    2 + 5 * quantity_error,
                    2 + 5 * omitted,
                    1 + 4 * (not roof),
                    2,
                    1 + 2 * roof,
                    1.5,
                    1,
                    1.5,
                ],
                dtype=float,
            )
            primary = str(rng.choice(mechanisms, p=weights / weights.sum()))
            flags = {
                "quantity_or_measurement_correction": "measurement_correction",
                "scope_expansion_missed_item": "missed_item",
                "concealed_or_hidden_damage": "concealed_damage_after_demolition",
                "pricing_change": "pricing_change",
                "matching": "matching",
                "code_or_ordinance": "code_or_ordinance",
                "overhead_and_profit": "overhead_and_profit",
                "repairability_or_repair_versus_replace_dispute": "repair_versus_replace",
            }
            for field in SupplementDrivers.model_fields:
                supplement["drivers." + field] = "no"
            for field in PreventionIndicators.model_fields:
                supplement["prevention." + field] = "no"
            drivers = [primary]
            total = int(rng.choice([1, 2, 3], p=[0.55, 0.30, 0.15]))
            if pending:
                total = max(total, 2)
            if total > 1 or rng.random() < 0.35:
                drivers.append(str(rng.choice([m for m in mechanisms if m != primary])))
            for driver in drivers:
                supplement["drivers." + flags[driver]] = "yes"
            avoidability = (
                str(
                    rng.choice(
                        ["clearly_avoidable", "probably_avoidable", "unclear"], p=[0.3, 0.5, 0.2]
                    )
                )
                if primary in {"quantity_or_measurement_correction", "scope_expansion_missed_item"}
                else str(
                    rng.choice(
                        ["clearly_unavoidable", "probably_unavoidable", "unclear"],
                        p=[0.25, 0.45, 0.3],
                    )
                )
            )
            avoidable = avoidability in {"clearly_avoidable", "probably_avoidable"}
            prevention = {
                "quantity_or_measurement_correction": "measurement_accuracy",
                "scope_expansion_missed_item": "estimate_construction",
            }.get(primary, "not_preventable" if avoidability != "unclear" else "unclear")
            if avoidable:
                supplement["prevention." + prevention] = "yes"
            remaining_avoidable = total > 1 and drivers[-1] in {
                "quantity_or_measurement_correction",
                "scope_expansion_missed_item",
            }
            if remaining_avoidable:
                area = (
                    "measurement_accuracy"
                    if drivers[-1] == "quantity_or_measurement_correction"
                    else "estimate_construction"
                )
                supplement["prevention." + area] = "yes"
            primary_outcome = (
                ("approved_in_part" if denied else "approved_in_full")
                if approved
                else "denied_in_full"
            )
            pending_count = int(pending > 0)
            remaining_outcome = (
                "not_applicable"
                if total == 1
                else "mixed"
                if pending and total > 2
                else "pending"
                if pending
                else "approved_in_full"
                if approved
                else "denied_in_full"
            )
            supplement.update(
                {
                    "supplement_present": "yes",
                    "history.completeness": "complete",
                    "history.total_count": total,
                    "history.approved_count": total - pending_count if approved else 0,
                    "history.denied_count": 0 if approved else total - pending_count,
                    "history.pending_count": pending_count,
                    "primary_mechanism": primary,
                    "primary_selection_basis": "approved_amount"
                    if approved
                    else "requested_amount",
                    "primary_outcome": primary_outcome,
                    "potentially_avoidable": avoidability,
                    "avoidability_confidence": "medium",
                    "primary_prevention_area": prevention,
                    "primary_unavoidable_reason": "not_applicable" if avoidable else "unclear",
                    "primary_request_preventable": "unknown",
                    "primary_prevention_action": "Include the item or correct the measurement."
                    if avoidable
                    else "No prevention action established in this fictional file.",
                    "primary_initial_identifiability": "probably_yes"
                    if avoidable
                    else "probably_no"
                    if primary == "concealed_or_hidden_damage"
                    else "unclear",
                    "secondary_mechanism": drivers[-1] if total > 1 else "not_applicable",
                    "remaining_outcome": remaining_outcome,
                    "remaining_avoidability": "not_applicable"
                    if total == 1
                    else "mixed"
                    if total > 2 and remaining_avoidable
                    else "avoidable"
                    if remaining_avoidable
                    else "unavoidable",
                    "any_potentially_avoidable": "yes"
                    if avoidable or remaining_avoidable
                    else "unknown"
                    if avoidability == "unclear"
                    else "no",
                    "mechanism_summary": f"Fictional history: {total} requests. Main: {primary}; "
                    f"other drivers: {', '.join(drivers[1:]) or 'none'}. "
                    f"Main selected by largest {'approval' if approved else 'request'} increment. "
                    f"Main avoidability: {avoidability}; unresolved dollars: ${pending:,.2f}.",
                }
            )
            if i % 17 == 0:
                supplement["history.completeness"] = "partial"
                for name in ("total_count", "approved_count", "denied_count", "pending_count"):
                    supplement["history." + name] = None
                for name, value in list(supplement.items()):
                    if value == "no" or (name.startswith("remaining_") and value != "mixed"):
                        supplement[name] = "unknown" if value == "no" else "unclear"
                if total == 1:
                    supplement["secondary_mechanism"] = "unclear"
                supplement["mechanism_summary"] = supplement["mechanism_summary"].replace(
                    f"Fictional history: {total} requests.", "Fictional partial history."
                )
                supplement["mechanism_summary"] += (
                    " Supplied history is incomplete; totals are unknown."
                )
            if i % 19 == 0:
                supplement["primary_selection_basis"] = "qualitative_materiality"
                supplement["mechanism_summary"] = supplement["mechanism_summary"].replace(
                    f"Main selected by largest {'approval' if approved else 'request'} increment. ",
                    "",
                )
                supplement["mechanism_summary"] += (
                    " Individual amounts cannot establish ranking; materiality used."
                )
        initial = Evidence(
            id="initial",
            source="Fictional initial estimate",
            kind="estimate",
            date=cutoff,
            text=f"Fictional fixture v{SYNTHETIC_VERSION}. {peril.title()} "
            f"damage to a {stories}-story property. "
            f"Initial estimate ${initial_amount:,.2f}. Inspection "
            f"quality varies by access and documentation.\n"
            "FIXTURE_FIELDS=" + json.dumps(baseline, sort_keys=True),
        )
        later = (
            [
                Evidence(
                    id="later",
                    source="Fictional supplement review",
                    kind="estimate",
                    date=cutoff + timedelta(days=int(rng.integers(14, 100))),
                    text=f"Fictional supplement review. Requested ${requested}; "
                    f"approved ${approved}; explicitly denied ${denied}; "
                    f"pending ${pending}.\n"
                    "FIXTURE_FIELDS=" + json.dumps(supplement, sort_keys=True),
                )
            ]
            if activity
            else []
        )
        bundles.append(
            ClaimBundle(
                claim_id=f"SYN-{i:05}",
                hover=hover,
                peril=peril,
                sub_peril={
                    "hail": "hailstorm",
                    "wind": "windstorm",
                    "water": "pipe",
                    "fire": "smoke",
                }[peril],
                dol=loss_date,
                fnol_date=loss_date + timedelta(days=delay),
                initial_estimate_cutoff=cutoff,
                initial_estimate_amount=initial_amount,
                supplement_approved_amount=approved,
                supplement_requested_amount=requested,
                supplement_denied_amount=denied,
                revised_estimate_amount=initial_amount + approved,
                supplement_activity="yes" if activity else "no",
                initial_evidence=[initial],
                later_evidence=later,
            )
        )
    return bundles


def synthetic_models(bundle):
    baseline = unknown_features(BaselineClaimFeatures)
    supplement = unknown_features(SupplementMechanismFeatures)
    baseline.baseline_summary = (
        "Fictional fixture v3 for local workflow validation; not an empirical claim."
    )
    refs = []
    for features, evidence in [
        (baseline, bundle.initial_evidence),
        (supplement, bundle.later_evidence),
    ]:
        references = []
        for record in evidence:
            if "FIXTURE_FIELDS=" not in record.text:
                continue
            fields = json.loads(record.text.split("FIXTURE_FIELDS=", 1)[1])
            for path, value in fields.items():
                _set(features, path, value)
                if value is not None and value not in ("unknown", "unclear", "not_applicable"):
                    references.append(
                        EvidenceReference(
                            field_path=path,
                            evidence_ids=[record.id],
                            explanation="Explicit fictional source fact.",
                        )
                    )
        refs.append(references)
    baseline.initial_estimate.initial_estimate_amount = bundle.initial_estimate_amount
    if bundle.supplement_activity == "yes":
        for name in (
            "supplement_approved_amount",
            "supplement_requested_amount",
            "supplement_denied_amount",
        ):
            setattr(supplement.financials, name, getattr(bundle, name))
            refs[1].append(
                EvidenceReference(
                    field_path="financials." + name,
                    evidence_ids=["later"],
                    explanation="Explicit fictional financial record.",
                )
            )
    else:
        supplement.supplement_present = "no"
    supplement = SupplementMechanismFeatures.model_validate(supplement.model_dump())
    return (
        TestModel(
            call_tools=[],
            custom_output_args=BaselineOutput(features=baseline, evidence=refs[0]).model_dump(
                mode="json"
            ),
        ),
        TestModel(
            call_tools=[],
            custom_output_args=SupplementOutput(features=supplement, evidence=refs[1]).model_dump(
                mode="json"
            ),
        ),
    )
