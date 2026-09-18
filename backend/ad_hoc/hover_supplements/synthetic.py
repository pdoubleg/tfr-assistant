"""Deterministic fictional fixtures and test-model outputs; never sends an API request."""

from datetime import date, timedelta

import numpy as np
from pydantic_ai.models.test import TestModel

from .agents import unknown_features
from .contracts import BaselineOutput, ClaimBundle, Evidence, EvidenceReference, SupplementOutput
from .models import BaselineClaimFeatures, SupplementMechanismFeatures


def synthetic_bundles(n=400, seed=42):
    rng = np.random.default_rng(seed)
    bundles = []
    for i in range(n):
        hover = bool(rng.integers(2))
        roof = bool(rng.integers(2))
        present = rng.random() < (0.4 - 0.12 * hover + 0.12 * roof)
        approved = round(float(rng.gamma(3, 500 + 100 * roof)), 2) if present else 0.0
        denied_request = not present and rng.random() < 0.1
        requested = approved + (200 if present or denied_request else 0)
        activity = present or denied_request
        loss_date = date(2024, 1, 1) + timedelta(days=i % 365)
        cutoff = loss_date + timedelta(days=7)
        initial_amount = round(float(rng.uniform(3000, 20000)), 2)
        initial = Evidence(
            id="initial",
            source="Fictional initial estimate",
            kind="estimate",
            date=cutoff,
            text=f"Synthetic fixture. Roof involved: {'yes' if roof else 'no'}. "
            f"Initial estimate: {initial_amount}. Photographic documentation is adequate.",
        )
        later = (
            [
                Evidence(
                    id="later",
                    source="Fictional supplement",
                    kind="estimate",
                    date=cutoff + timedelta(days=20),
                    text=f"Synthetic fixture. Measurement correction requested. "
                    f"Additional requested: {requested}; approved: {approved}; denied: 200.",
                )
            ]
            if activity
            else []
        )
        bundles.append(
            ClaimBundle(
                claim_id=f"SYN-{i:05}",
                hover=hover,
                peril="hail" if roof else "water",
                sub_peril="storm" if roof else "pipe",
                dol=loss_date,
                fnol_date=loss_date + timedelta(days=1),
                initial_estimate_cutoff=cutoff,
                initial_estimate_amount=initial_amount,
                supplement_approved_amount=approved,
                supplement_requested_amount=requested,
                supplement_denied_amount=200 if activity else 0,
                revised_estimate_amount=initial_amount + approved,
                supplement_activity="yes" if activity else "no",
                initial_evidence=[initial],
                later_evidence=later,
            )
        )
    return bundles


def synthetic_models(bundle):
    baseline = unknown_features(BaselineClaimFeatures)
    baseline.property_complexity.roof_involved = "yes" if bundle.peril == "hail" else "no"
    baseline.documentation.photo_documentation_adequate = "yes"
    baseline.initial_estimate.initial_estimate_amount = bundle.initial_estimate_amount
    baseline.baseline_summary = "Fictional fixture for local workflow validation."
    evidence = [
        EvidenceReference(
            field_path=path, evidence_ids=["initial"], explanation="Explicit in fixture."
        )
        for path in (
            "property_complexity.roof_involved",
            "documentation.photo_documentation_adequate",
            "initial_estimate.initial_estimate_amount",
        )
    ]
    supplement = unknown_features(SupplementMechanismFeatures)
    supplement.supplement_present = "yes" if bundle.supplement_activity == "yes" else "no"
    refs = []
    if bundle.supplement_activity == "yes":
        supplement.quantity.measurement_correction = "yes"
        supplement.primary_mechanism = "quantity_change"
        supplement.mechanism_summary = "Fictional measurement correction; avoidability is unknown."
        for name in (
            "supplement_approved_amount",
            "supplement_requested_amount",
            "supplement_denied_amount",
        ):
            setattr(supplement.financials, name, getattr(bundle, name))
        refs = [
            EvidenceReference(
                field_path=path, evidence_ids=["later"], explanation="Explicit in fixture."
            )
            for path in (
                "supplement_present",
                "quantity.measurement_correction",
                "primary_mechanism",
                "financials.supplement_approved_amount",
                "financials.supplement_requested_amount",
                "financials.supplement_denied_amount",
            )
        ]
    return (
        TestModel(
            call_tools=[],
            custom_output_args=BaselineOutput(features=baseline, evidence=evidence).model_dump(
                mode="json"
            ),
        ),
        TestModel(
            call_tools=[],
            custom_output_args=SupplementOutput(features=supplement, evidence=refs).model_dump(
                mode="json"
            ),
        ),
    )
