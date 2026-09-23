"""Associated prevention dollars are weighted, overlapping, and distinct from savings."""

import json

import pandas as pd
import pytest

from ad_hoc.hover_supplements.analysis import mechanism_analysis
from ad_hoc.hover_supplements.runner import _json_safe
from ad_hoc.hover_supplements.visualization import build_business_figures, render_business_report


def prevention_frame():
    return pd.DataFrame(
        {
            "claim_id": list("abcdefg"),
            "hover": [False] * 5 + [True] * 2,
            "sampling_weight": [2, 1, 1, 1, 1, 1, 1],
            "supplement_approved_amount": [100, 400, None, 0, 900, 0, None],
            "supplement_mechanism__prevention__process_or_timing": pd.array(
                [True, True, True, False, None, False, True], dtype="boolean"
            ),
            "supplement_mechanism__prevention__pricing_currency": pd.array(
                [True, False, None, False, None, None, None], dtype="boolean"
            ),
            "supplement_mechanism__prevention__measurement_scope": pd.array(
                [False] * 7, dtype="boolean"
            ),
        }
    )


def test_prevention_dollars_use_weighted_claim_amounts_and_preserve_missingness():
    tables = mechanism_analysis(prevention_frame())
    dollars = tables["prevention_area_dollars"].set_index(["hover", "prevention_area"])
    prefix = "supplement_mechanism__prevention__"
    process = dollars.loc[(False, prefix + "process_or_timing")]
    pricing = dollars.loc[(False, prefix + "pricing_currency")]
    assert process.associated_approved_dollars == 600
    assert process.population_denominator_weight == 6
    assert process.dollars_per_population_claim == 100
    assert process.unknown_dollars_n == 1
    assert process.unknown_classification_n == 1
    assert pricing.associated_approved_dollars == 200  # Same first claim can contribute twice.
    assert pricing.dollars_per_population_claim == pytest.approx(200 / 6)
    assert pricing.unknown_classification_n == 2
    # Positive cases with no known amount and wholly unknown classifications stay missing.
    assert pd.isna(dollars.loc[(True, prefix + "process_or_timing"), "associated_approved_dollars"])
    assert pd.isna(dollars.loc[(True, prefix + "pricing_currency"), "associated_approved_dollars"])
    assert dollars.loc[(True, prefix + "measurement_scope"), "associated_approved_dollars"] == 0
    assert "associated_approved_dollars" not in tables["mechanism_rates"]


def test_prevention_dollars_render_after_percentage_chart_from_saved_report(tmp_path):
    report = {
        "supplement_schema_version": "2.0",
        "tables": mechanism_analysis(prevention_frame()),
    }
    saved = json.loads(json.dumps(_json_safe(report)))
    figures = build_business_figures(saved)
    chart = figures["prevention_area_dollars"]
    assert chart.layout.xaxis.title.text.endswith("per population claim ($)")
    assert "not savings" in chart.layout.title.text
    non_hover = next(trace for trace in chart.data if trace.name == "Non-Hover")
    bars = dict(zip(non_hover.y, non_hover.x, strict=True))
    assert bars["Process or timing"] == 100
    assert bars["Pricing currency"] == pytest.approx(200 / 6)
    assert bars["Measurement scope"] == 0
    html = render_business_report(saved, tmp_path).read_text(encoding="utf-8")
    assert html.index('id="plot-prevention_areas"') < html.index(
        'id="plot-prevention_area_dollars"'
    )
    assert "the same claim dollars may appear in several bars" in html

    # Older saved reports lack this table; percentage charts still render without failure.
    del saved["tables"]["prevention_area_dollars"]
    assert "prevention_areas" in build_business_figures(saved)
    assert "prevention_area_dollars" not in build_business_figures(saved)
