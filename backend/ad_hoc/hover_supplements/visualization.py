"""Notebook figures and a portable, business-question-focused HTML research report."""

from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

from .explainability import feature_label
from .report_methods import methodology_details

COLORS = {"Non-Hover": "#707070", "Hover": "#06748C"}
OUTCOMES = {
    "supplement_incidence": (
        "How often are additional dollars approved?",
        "Approved supplement rate",
        "%",
        100,
    ),
    "conditional_approved_severity": (
        "How large are approved supplements?",
        "Dollars per approved supplement",
        "$",
        1,
    ),
    "approved_dollars_per_claim": (
        "What is the economic burden across all claims?",
        "Approved dollars per claim",
        "$",
        1,
    ),
    "supplement_ratio": (
        "How large are supplements relative to the initial estimate?",
        "Supplement / initial estimate",
        "%",
        100,
    ),
}


def _frame(value):
    return value.copy() if isinstance(value, pd.DataFrame) else pd.DataFrame(value or [])


def _cohorts(df):
    df = df.copy()
    df["cohort"] = df.hover.map({False: "Non-Hover", True: "Hover"})
    return df


def _style(fig, title, *, height=420):
    axis_labels = {
        "label": "",
        "category": "",
        "definition": "",
        "rate": "Positive findings among known answers (%)",
        "percent": "Positive findings among known answers (%)",
        "share_pct": "Share of approved supplemented claims (%)",
        "unknown_pct": "Claims with unknown findings (unweighted %)",
        "dollars_per_population_claim": "Associated approved dollars per population claim ($)",
        "standardized_difference": "Standardized difference (Hover minus Non-Hover)",
        "importance": "Increase in held-out Brier loss",
        "incidence_shap_pp": "Probability contribution (percentage points)",
        "incidence_pct": "Average predicted supplement probability (%)",
        "value": "Feature value",
        "mean_absolute_contribution": "Mean absolute prediction contribution",
    }
    for axis in (*fig.select_xaxes(), *fig.select_yaxes()):
        if axis.title.text in axis_labels:
            axis.title.text = axis_labels[axis.title.text]
    fig.update_layout(
        template="plotly_white",
        title=dict(text=title, x=0.02),
        height=height,
        font=dict(family="Arial, sans-serif", size=13, color="#1A1446"),
        margin=dict(l=35, r=30, t=75, b=55),
        legend_title_text="",
        colorway=["#06748C", "#1A1446", "#28A3AF", "#FFD000", "#707070"],
        paper_bgcolor="white",
        hoverlabel=dict(font_size=12),
    )
    return fig


def _empty(title, reason):
    fig = _style(go.Figure(), title, height=240)
    fig.add_annotation(
        text=escape(reason), x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def _number(value, unit="", signed=False):
    if value is None or not np.isfinite(float(value)):
        return "unavailable"
    prefix = "+" if signed and value > 0 else ""
    if unit == "$":
        return f"{'-' if value < 0 else prefix}${abs(value):,.0f}"
    return f"{prefix}{value:,.1f}{unit}"


def business_question_answers(report):
    """Deterministic statements with explicit population, units, and uncertainty."""
    rows = []
    scorecard = _frame(report.get("tables", {}).get("population_scorecard"))
    if not scorecard.empty:
        scorecard["estimate"] = pd.to_numeric(scorecard.estimate, errors="coerce")
    for metric, (question, _label, unit, scale) in OUTCOMES.items():
        data = scorecard[scorecard.metric.eq(metric)] if not scorecard.empty else pd.DataFrame()
        lookup = data.set_index("hover") if not data.empty else data
        if not data.empty and {False, True}.issubset(lookup.index):
            before, after = (
                lookup.loc[False, "estimate"] * scale,
                lookup.loc[True, "estimate"] * scale,
            )
            change_unit = " percentage points" if unit == "%" else "$"
            answer = (
                f"Non-Hover {_number(before, unit)}; Hover {_number(after, unit)}. "
                f"Raw difference: {_number(after - before, change_unit, signed=True)}."
            )
        else:
            answer = "A comparison requires both cohorts and known outcome values."
        rows.append(
            {
                "question": question,
                "answer": answer,
                "basis": "Full structured population; weighted descriptive comparison",
                "metric": metric,
                "interpretation": "Association; differences may reflect case mix or calendar time.",
            }
        )
    selected = report.get("selected_model", {})
    estimates = _frame(selected.get("estimates"))
    if selected.get("status") == "success" and not estimates.empty:
        for row in estimates[estimates.comparison.eq("difference")].to_dict("records"):
            scale, unit = (100, " percentage points") if row["metric"] == "incidence" else (1, "$")
            estimate = _number(row["estimate"] * scale, unit, signed=True)
            answer = f"Adjusted Hover minus Non-Hover: {estimate}."
            if pd.notna(row["lower_95"]) and pd.notna(row["upper_95"]):
                lower = _number(row["lower_95"] * scale, unit)
                upper = _number(row["upper_95"] * scale, unit)
                answer += f" 95% interval: {lower} to {upper}."
                if row["lower_95"] <= 0 <= row["upper_95"]:
                    answer += " The interval includes zero; the direction is uncertain."
            else:
                answer += " A reliable bootstrap interval is unavailable."
            rows.append(
                {
                    "question": "Does the difference remain after selected case-mix adjustment?",
                    "metric": row["metric"],
                    "answer": answer,
                    "basis": (
                        f"{selected.get('tier', 'selected')} model; common reference population"
                    ),
                    "interpretation": "Adjusted association, not a causal Hover effect.",
                }
            )
    else:
        rows.append(
            {
                "question": "Does the difference remain after adjustment?",
                "metric": "adjusted",
                "answer": selected.get("reason", "Adjusted modeling unavailable"),
                "basis": "Selected model",
                "interpretation": "No adjusted conclusion is supported.",
            }
        )
    details = _descriptive_answers(report)
    for question, answer, basis in [
        (
            "What caused supplements?",
            details["mechanisms"],
            "Weighted audited claims",
        ),
        (
            "Which supplements appear potentially avoidable?",
            details["avoidability"],
            "Evidence-based retrospective classifications",
        ),
        (
            "Did initial-estimate quality differ?",
            details["quality"],
            "Initial-evidence-only extraction",
        ),
        (
            "Which claims behave differently?",
            details["segments"],
            "Training-discovered, held-out-evaluated segments",
        ),
        (
            "Why did the model make a prediction?",
            details["prediction"],
            "Prediction explanation, not causation",
        ),
    ]:
        rows.append(
            {
                "question": question,
                "answer": answer,
                "basis": basis,
                "metric": "",
                "interpretation": "See evidence, denominators, and model support below.",
            }
        )
    return pd.DataFrame(rows)


def _descriptive_answers(report):
    scope = (
        "main supplement"
        if report.get("supplement_schema_version") == "2.0"
        else "aggregate history"
    )
    tables, predictive = report.get("tables", {}), report.get("predictive", {})
    answers = {
        "mechanisms": "No audited primary-mechanism comparison is available.",
        "avoidability": "No audited avoidability comparison is available.",
        "quality": "No supported initial-quality comparison is available.",
        "segments": "No held-out segment comparison meets both cohort support thresholds.",
        "prediction": "Predictive explanations are unavailable for this run.",
    }
    classifications = _frame(tables.get("classifications"))
    if not classifications.empty:
        descriptions, avoidable = [], []
        for hover, cohort in classifications.groupby("hover"):
            label = "Hover" if hover else "Non-Hover"
            mechanisms = cohort[cohort.classification.str.endswith("primary_mechanism")]
            mechanisms = mechanisms.dropna(subset=["approved_supplement_share"])
            if not mechanisms.empty:
                largest = mechanisms.loc[mechanisms.approved_supplement_share.idxmax()]
                category = str(largest.category).replace("_", " ")
                descriptions.append(
                    f"{label}: leading {scope} category {category} "
                    f"({_number(largest.approved_supplement_share * 100, '%')} "
                    "of approved supplemented claims)"
                )
            categories = cohort[cohort.classification.str.endswith("potentially_avoidable")]
            if not categories.empty and categories.approved_supplement_share.notna().any():
                selected = categories[
                    categories.category.isin(["clearly_avoidable", "probably_avoidable"])
                ]
                share = selected.approved_supplement_share.sum()
                avoidable.append(
                    f"{label}: {_number(share * 100, '%')} of approved supplemented "
                    f"claims whose {scope} was clearly/probably avoidable"
                )
        if descriptions:
            answers["mechanisms"] = (
                "; ".join(descriptions) + ". Unknown/unclear categories are retained."
            )
        if avoidable:
            answers["avoidability"] = "; ".join(avoidable) + ". This is not a savings estimate."
    quality = _frame(tables.get("audited_scorecard"))
    if not quality.empty:
        metric = "baseline__initial_estimate__scope_appears_complete_for_documented_damage"
        selected = quality[quality.metric.eq(metric) & quality.known_n.gt(0)]
        if selected.hover.nunique() == 2:
            values = selected.set_index("hover").estimate
            answers["quality"] = (
                f"Scope appears complete in {_number(values[False] * 100, '%')} "
                f"of known Non-Hover answers and {_number(values[True] * 100, '%')} "
                "of known Hover answers. Inspect other indicators and missing evidence separately."
            )
    segments = _frame(predictive.get("segment_comparisons"))
    if not segments.empty:
        supported = segments[segments.status.eq("exploratory")]
        if not supported.empty:
            answers["segments"] = (
                f"{len(supported)} of {len(segments)} discovered segments have "
                "enough held-out support in both cohorts for exploratory comparisons."
            )
    explanations = predictive.get("explanations", {})
    if explanations.get("status") == "success":
        importance = _frame(explanations["global_importance"])
        importance = importance[
            (importance.cohort == "all") & (importance.output == "incidence_shap_pp")
        ]
        largest = importance.loc[importance.mean_absolute_contribution.idxmax()]
        answers["prediction"] = (
            f"{largest.label} has the largest average absolute probability "
            f"contribution ({largest.mean_absolute_contribution:.2f} percentage points) "
            f"across {explanations['explained_n']} explained held-out claims. "
            "Magnitude does not imply direction or causal influence."
        )
    elif "reason" in explanations:
        answers["prediction"] = explanations["reason"]
    return answers


def claim_explanation_figure(explanations, claim_id, *, output="incidence", top_n=10):
    """Return an additive waterfall; residual features stay in an 'Other features' bar."""
    if explanations.get("status") != "success":
        return _empty(
            "Claim explanation unavailable", explanations.get("reason", "SHAP is unavailable")
        )
    specs = {
        "incidence": (
            "incidence_shap_pp",
            "base_probability",
            "probability",
            100,
            "Probability (%)",
        ),
        "severity": (
            "severity_shap_dollars",
            "base_severity",
            "conditional_severity",
            1,
            "Conditional severity ($)",
        ),
        "expected_dollars": (
            "two_part_dollar_allocation",
            "base_product_dollars",
            "expected_dollars",
            1,
            "Expected dollars per claim ($)",
        ),
    }
    if output not in specs or top_n < 1:
        raise ValueError("Choose incidence, severity, or expected_dollars and a positive top_n")
    column, base_col, prediction_col, scale, axis = specs[output]
    values = _frame(explanations["local_contributions"])
    values = values[values.claim_id.eq(claim_id)].copy()
    predictions = _frame(explanations["predictions"])
    target = predictions[predictions.claim_id.eq(claim_id)]
    if values.empty or len(target) != 1:
        raise ValueError("Claim is not in the explained held-out sample")
    values = values.iloc[np.argsort(-values[column].abs().to_numpy())]
    labels = []
    for row in values.head(top_n).to_dict("records"):
        value = "Missing (imputed)" if pd.isna(row["value"]) else str(row["value"])
        labels.append(f"{escape(row['label'])}<br>{escape(value[:60])}")
    contributions = values[column].head(top_n).tolist()
    if len(values) > top_n:
        labels.append("Other features")
        contributions.append(float(values[column].iloc[top_n:].sum()))
    base = float(target.iloc[0][base_col] * scale)
    prediction = float(target.iloc[0][prediction_col] * scale)
    if not np.isclose(base + sum(contributions), prediction, rtol=1e-5, atol=1e-4):
        raise ValueError("Displayed claim explanation does not reconcile")
    fig = go.Figure(
        go.Waterfall(
            x=["Training reference", *labels, "Prediction"],
            y=[base, *contributions, prediction],
            measure=["absolute", *(["relative"] * len(contributions)), "total"],
            increasing=dict(marker_color="#FFD000"),
            decreasing=dict(marker_color="#06748C"),
            totals=dict(marker_color="#1A1446"),
            text=[f"{x:,.2f}" for x in [base, *contributions, prediction]],
            textposition="outside",
            connector=dict(line_color="#C0BFC0"),
        )
    )
    method = "Two-part allocation (not joint SHAP)" if output == "expected_dollars" else "Tree SHAP"
    _style(fig, f"{method} · {escape(str(claim_id))}", height=480)
    fig.update_yaxes(title=axis)
    fig.update_xaxes(tickangle=-25)
    return fig


def build_business_figures(report):
    """Return named Plotly figures for notebook display or independent exports."""
    scope = (
        "Main supplement"
        if report.get("supplement_schema_version") == "2.0"
        else "Legacy aggregate"
    )
    tables, figures = report.get("tables", {}), {}
    scores = _frame(tables.get("population_scorecard"))
    for metric, (question, label, unit, scale) in OUTCOMES.items():
        data = scores[scores.metric.eq(metric)].copy() if not scores.empty else pd.DataFrame()
        if data.empty:
            figures[metric] = _empty(question, "No outcome data")
            continue
        data = _cohorts(data)
        data["display_value"] = data.estimate * scale
        fig = px.bar(
            data,
            x="cohort",
            y="display_value",
            color="cohort",
            color_discrete_map=COLORS,
            text_auto=".2f",
            hover_data=["known_n", "unknown_n", "denominator_weight", "effective_n"],
        )
        fig.update_yaxes(title=f"{label} ({unit})")
        fig.update_xaxes(title=None)
        figures[metric] = _style(fig, question)
    estimates = _frame(report.get("selected_model", {}).get("estimates"))
    if not estimates.empty:
        differences = estimates[estimates.comparison.eq("difference")]
        fig = make_subplots(
            rows=1,
            cols=3,
            subplot_titles=[
                "Incidence (percentage points)",
                "Conditional severity ($)",
                "Expected dollars per claim ($)",
            ],
        )
        for i, metric in enumerate(("incidence", "conditional_severity", "expected_dollars"), 1):
            row = differences[differences.metric.eq(metric)]
            if row.empty:
                continue
            row = row.iloc[0]
            scale = 100 if metric == "incidence" else 1
            if pd.notna(row.lower_95) and pd.notna(row.upper_95):
                fig.add_trace(
                    go.Scatter(
                        x=[row.lower_95 * scale, row.upper_95 * scale],
                        y=[0, 0],
                        mode="lines",
                        line=dict(width=4, color="#78E1E1"),
                        name="95% bootstrap interval",
                        showlegend=i == 1,
                    ),
                    row=1,
                    col=i,
                )
            fig.add_trace(
                go.Scatter(
                    x=[row.estimate * scale],
                    y=[0],
                    mode="markers",
                    marker=dict(size=12, color="#06748C"),
                    name="Adjusted difference",
                    showlegend=i == 1,
                ),
                row=1,
                col=i,
            )
            fig.add_vline(x=0, line_dash="dot", line_color="#707070", row=1, col=i)
        fig.update_yaxes(visible=False)
        figures["adjusted_differences"] = _style(
            fig, "Adjusted Hover minus Non-Hover · association, not causation", height=330
        )
    else:
        figures["adjusted_differences"] = _empty(
            "Adjusted comparison", report.get("selected_model", {}).get("reason", "Not available")
        )
    decomposition = report.get("population_decomposition", {})
    if decomposition.get("status") == "success":
        fig = go.Figure(
            go.Waterfall(
                x=["Incidence contribution", "Severity contribution", "Total difference"],
                y=[
                    decomposition["incidence_contribution"],
                    decomposition["severity_contribution"],
                    decomposition["total_difference"],
                ],
                measure=["relative", "relative", "total"],
                totals=dict(marker_color="#1A1446"),
            )
        )
        fig.update_yaxes(title="Hover minus Non-Hover approved dollars per claim ($)")
        figures["dollar_decomposition"] = _style(
            fig, "Is the dollar difference driven by frequency or size?"
        )
    quality = _frame(tables.get("audited_scorecard"))
    if not quality.empty:
        quality = quality[quality.metric.str.startswith("baseline__")].copy()
        if not quality.empty:
            quality = _cohorts(quality)
            quality["label"] = quality.metric.map(feature_label)
            quality["rate"] = quality.estimate * 100
            figures["initial_quality"] = _style(
                px.bar(
                    quality,
                    y="label",
                    x="rate",
                    color="cohort",
                    barmode="group",
                    color_discrete_map=COLORS,
                    hover_data=["known_n", "unknown_n", "denominator_weight"],
                ),
                "Initial documentation and estimate quality · % among known answers",
                height=max(480, quality.metric.nunique() * 37),
            )
            quality["unknown_pct"] = (
                quality.unknown_n / (quality.known_n + quality.unknown_n).replace(0, np.nan) * 100
            )
            figures["quality_unknowns"] = _style(
                px.bar(
                    quality,
                    y="label",
                    x="unknown_pct",
                    color="cohort",
                    barmode="group",
                    color_discrete_map=COLORS,
                ),
                "How much quality evidence is missing?",
                height=max(480, quality.metric.nunique() * 37),
            )
    mechanisms = _frame(tables.get("mechanism_rates"))
    if not mechanisms.empty:
        for denominator in ("all_claims", "approved_supplements"):
            data = mechanisms[
                (mechanisms.denominator == denominator)
                & mechanisms.mechanism.str.contains(
                    r"__(?:drivers|scope|quantity|pricing|additional_costs|discovery|initiation)__",
                    regex=True,
                )
            ].copy()
            ranking = (
                data.groupby("mechanism")
                .rate.max()
                .dropna()
                .sort_values(ascending=False)
                .head(20)
                .index
            )
            data = _cohorts(data[data.mechanism.isin(ranking)])
            data["label"] = data.mechanism.map(
                lambda s: s.split("__")[1].replace("_", " ").title() + ": " + feature_label(s)
            )
            data["percent"] = data.rate * 100
            if not data.empty:
                figures[f"mechanisms_{denominator}"] = _style(
                    px.bar(
                        data,
                        y="label",
                        x="percent",
                        color="cohort",
                        barmode="group",
                        color_discrete_map=COLORS,
                        hover_data=["positive_n", "unknown_n", "denominator_weight"],
                    ),
                    f"Supplement drivers · {denominator.replace('_', ' ')} · % among known answers",
                    height=max(480, len(ranking) * 35),
                )
    if not mechanisms.empty:
        prevention = mechanisms[
            mechanisms.mechanism.str.contains("__prevention__", regex=False)
            & mechanisms.denominator.eq("all_claims")
        ].copy()
        if not prevention.empty:
            prevention = _cohorts(prevention)
            prevention["label"] = prevention.mechanism.map(feature_label)
            prevention["percent"] = prevention.rate * 100
            figures["prevention_areas"] = _style(
                px.bar(
                    prevention,
                    y="label",
                    x="percent",
                    color="cohort",
                    barmode="group",
                    color_discrete_map=COLORS,
                    hover_data=["positive_n", "unknown_n", "denominator_weight"],
                ),
                "Prevention areas across the whole history · % among known claims",
                height=520,
            )
    prevention_dollars = _frame(tables.get("prevention_area_dollars"))
    if not prevention_dollars.empty:
        prevention_dollars = _cohorts(prevention_dollars)
        prevention_dollars["label"] = prevention_dollars.prevention_area.map(feature_label)
        figures["prevention_area_dollars"] = _style(
            px.bar(
                prevention_dollars,
                y="label",
                x="dollars_per_population_claim",
                color="cohort",
                barmode="group",
                color_discrete_map=COLORS,
                hover_data=[
                    "associated_approved_dollars",
                    "positive_n",
                    "known_dollars_n",
                    "unknown_dollars_n",
                    "unknown_classification_n",
                    "population_denominator_weight",
                ],
            ),
            "Dollars associated with prevention areas · not savings",
            height=520,
        )
        figures["prevention_area_dollars"].update_xaxes(
            title="Associated approved supplement dollars per population claim ($)",
            tickprefix="$",
        )
    history = _frame(tables.get("supplement_history"))
    if not history.empty:
        history = _cohorts(history)
        history["percent"] = history.repeat_rate * 100
        figures["repeat_supplements"] = _style(
            px.bar(
                history,
                x="denominator",
                y="percent",
                color="cohort",
                barmode="group",
                color_discrete_map=COLORS,
                hover_data=["known_n", "unknown_n", "partial_history_n"],
            ),
            "Claims with multiple supplements · % among known counts",
        )
    classifications = _frame(tables.get("classifications"))
    if not classifications.empty:
        for suffix, title in (
            ("primary_mechanism", f"{scope} mechanism"),
            ("potentially_avoidable", f"{scope} avoidability"),
            ("secondary_mechanism", "Remaining supplements: dominant mechanism"),
            ("primary_outcome", "Main supplement outcome"),
            ("remaining_outcome", "Remaining supplements: outcomes"),
            ("remaining_avoidability", "Remaining supplements: avoidability"),
            ("primary_prevention_area", "Main supplement prevention area"),
        ):
            data = _cohorts(classifications[classifications.classification.str.endswith(suffix)])
            if data.empty:
                continue
            data["category"] = data.category.fillna("unknown").str.replace("_", " ")
            data["share_pct"] = data.approved_supplement_share * 100
            figures[suffix] = _style(
                px.bar(
                    data,
                    y="category",
                    x="share_pct",
                    color="cohort",
                    barmode="group",
                    color_discrete_map=COLORS,
                    hover_data=["claims_n", "classification_unknown_n"],
                ),
                f"{title} · share of approved supplemented claims (%)",
            )
            if suffix == "potentially_avoidable":
                data["dollars_per_population_claim"] = (
                    data.associated_approved_dollars / data.population_denominator_weight
                )
                figures["avoidability_dollars"] = _style(
                    px.bar(
                        data,
                        y="category",
                        x="dollars_per_population_claim",
                        color="cohort",
                        barmode="group",
                        color_discrete_map=COLORS,
                    ),
                    "Dollars associated with avoidability categories · not savings",
                )
    balance = _frame(report.get("selected_model", {}).get("covariate_balance"))
    if not balance.empty:
        balance["label"] = balance.feature.map(feature_label) + balance.level.fillna("").map(
            lambda s: f": {s}" if str(s) else ""
        )
        figures["case_mix"] = _style(
            px.scatter(
                balance,
                x="standardized_difference",
                y="label",
                hover_data=["hover_known_n", "non_hover_known_n"],
            ),
            "Were the selected case-mix characteristics different?",
        )
        figures["case_mix"].add_vline(x=0, line_dash="dot")
    predictive = report.get("predictive", {})
    if predictive.get("status") != "success":
        figures["predictive_status"] = _empty(
            "Predictive model", predictive.get("reason", "Unavailable")
        )
        return figures
    calibration = _frame(predictive.get("calibration"))
    fig = px.scatter(calibration, x="predicted", y="observed", size="n", hover_data=["n"])
    fig.add_trace(
        go.Scatter(x=[0, 1], y=[0, 1], mode="lines", line_dash="dot", name="Perfect calibration")
    )
    fig.update_xaxes(range=[0, 1], title="Predicted supplement probability")
    fig.update_yaxes(range=[0, 1], title="Observed supplement frequency")
    figures["calibration"] = _style(fig, "Can the model's predicted probabilities be trusted?")
    importance = _frame(predictive.get("permutation_importance"))
    importance["label"] = importance.feature.map(feature_label)
    importance = importance.sort_values("importance").tail(20)
    figures["permutation_importance"] = _style(
        px.bar(importance, y="label", x="importance", error_x="std"),
        "Which inputs improve held-out accuracy? · increase in Brier loss",
    )
    dependence = _frame(predictive.get("partial_dependence"))
    for feature, data in dependence.groupby("feature"):
        data = data.copy()
        data["incidence_pct"] = data.incidence * 100
        figures[f"dependence_{feature}"] = _style(
            px.line(data, x="value", y="incidence_pct", markers=True),
            f"Model response to {feature_label(feature)} · average predicted probability (%)",
        )
    segments = _frame(predictive.get("segment_comparisons"))
    if not segments.empty:
        segments = segments[segments.status.eq("exploratory")].copy()
        if not segments.empty:
            definitions = _frame(predictive.get("segment_definitions"))
            segments = segments.merge(definitions, on="segment", validate="one_to_one")
            segments["difference_pp"] = segments.incidence_difference * 100
            figures["segments"] = _style(
                px.scatter(segments, x="difference_pp", y="definition", hover_data=["segment"]),
                "Held-out segment differences · Hover minus Non-Hover (percentage points)",
            )
            figures["segments"].add_vline(x=0, line_dash="dot")
    explanations = predictive.get("explanations", {})
    if explanations.get("status") == "success":
        global_values = _frame(explanations["global_importance"])
        for output, title in (
            ("incidence_shap_pp", "Probability explanation (percentage points)"),
            ("severity_shap_dollars", "Conditional severity explanation ($)"),
        ):
            data = global_values[(global_values.cohort == "all") & (global_values.output == output)]
            data = data.sort_values("mean_absolute_contribution").tail(15)
            figures[output] = _style(
                px.bar(data, x="mean_absolute_contribution", y="label"),
                f"Global SHAP · {title} · magnitude, not direction",
            )
        local = _cohorts(_frame(explanations["local_contributions"]))
        ranking = (
            global_values[
                (global_values.cohort == "all") & (global_values.output == "incidence_shap_pp")
            ]
            .nlargest(12, "mean_absolute_contribution")
            .feature
        )
        local = local[local.feature.isin(ranking)].copy()
        local["value"] = local.value.astype(str)
        figures["shap_distribution"] = _style(
            px.strip(
                local,
                x="incidence_shap_pp",
                y="label",
                color="cohort",
                color_discrete_map=COLORS,
                hover_data=["claim_id", "value"],
            ),
            "Which inputs push individual predictions up or down?",
            height=max(420, len(ranking) * 40),
        )
        figures["shap_distribution"].add_vline(x=0, line_dash="dot")
    else:
        figures["shap_status"] = _empty(
            "SHAP explanations", explanations.get("reason", "Unavailable")
        )
    return figures


def _table(df, *, limit=30):
    df = _frame(df)
    if df.empty:
        return '<p class="muted">No supported data for this view.</p>'
    note = (
        f"<p class='muted'>Showing {min(limit, len(df))} of {len(df)} rows; "
        "full tables are exported as CSV.</p>"
        if len(df) > limit
        else ""
    )
    return (
        note
        + '<div class="table-wrap">'
        + df.head(limit).to_html(
            index=False, escape=True, na_rep="Not available", float_format=lambda x: f"{x:,.4g}"
        )
        + "</div>"
    )


def render_business_report(report, output_dir):
    """Write one self-contained HTML report plus question/answer tables; no server required."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    figures = build_business_figures(report)
    answers = business_question_answers(report)
    answers.to_csv(directory / "business_answers.csv", index=False)
    answers.to_json(directory / "business_answers.json", orient="records", indent=2)
    (directory / "business_answers.md").write_text(
        "\n\n".join(
            f"### {r['question']}\n\n{r['answer']}\n\nBasis: {r['basis']}"
            for r in answers.to_dict("records")
        ),
        encoding="utf-8",
    )
    first_plot = True

    def chart(key):
        nonlocal first_plot
        if key not in figures:
            return ""
        html = pio.to_html(
            figures[key],
            full_html=False,
            include_plotlyjs=True if first_plot else False,
            config={"responsive": True, "displaylogo": False},
            div_id=f"plot-{key}",
        )
        first_plot = False
        return '<div class="chart">' + html + "</div>"

    sections = []
    tables, predictive = report.get("tables", {}), report.get("predictive", {})

    def section(identifier, title, intro, body):
        sections.append(
            f'<section id="{identifier}"><h2>{escape(title)}</h2>'
            f"<p>{escape(intro)}</p>{methodology_details(identifier, report)}{body}</section>"
        )

    outcome_answers = answers[answers.metric.isin(OUTCOMES)]
    cards = "".join(
        f'<article class="card"><h3>{escape(r["question"])}</h3>'
        f"<p>{escape(r['answer'])}</p></article>"
        for r in outcome_answers.to_dict("records")
    )
    section(
        "impact",
        "1. Did supplement outcomes change?",
        "Full structured population. Each chart has its own units. Hover is "
        "compared with Non-Hover; a historical cohort may also differ in calendar"
        " conditions.",
        '<div class="cards">'
        + cards
        + "</div>"
        + '<div class="grid">'
        + "".join(chart(k) for k in OUTCOMES)
        + "</div>"
        + chart("adjusted_differences")
        + chart("dollar_decomposition")
        + "<details><summary>Exact outcome estimates, denominators and uncertainty</summary>"
        + _table(tables.get("population_scorecard"))
        + _table(report.get("selected_model", {}).get("estimates"))
        + "<p>Model coefficients describe conditional associations. Odds ratios are not "
        "probability ratios; severity multipliers concern positive approved dollars only. "
        "Contrasts below use original feature units, holding other inputs fixed.</p>"
        + _table(report.get("selected_model", {}).get("coefficients"))
        + "</details>",
    )
    section(
        "quality",
        "2. Were the claims different, and did estimate quality differ?",
        "Case-mix differences can explain raw outcome differences. Quality "
        "indicators use only initial evidence. Higher is better for some "
        "indicators and worse for others; there is no composite score.",
        chart("case_mix")
        + chart("initial_quality")
        + chart("quality_unknowns")
        + _table(report.get("selected_model", {}).get("covariate_balance")),
    )
    section(
        "mechanisms",
        "3. What specifically drove supplements?",
        "Main-supplement categories describe one selected request per claim. "
        "Remaining classifications cover all other requests. Flags cover the entire history and "
        "must not be added. Flag charts show up to 20 frequent drivers; the full "
        "inventory and unknown counts remain in the tables. Rates use known "
        "answers within the named denominator.",
        chart("primary_mechanism")
        + chart("secondary_mechanism")
        + chart("primary_outcome")
        + chart("remaining_outcome")
        + chart("repeat_supplements")
        + _table(tables.get("supplement_history"))
        + chart("mechanisms_all_claims")
        + chart("mechanisms_approved_supplements")
        + "<details><summary>All driver classifications and denominators</summary>"
        + _table(tables.get("mechanism_rates"), limit=10000)
        + "</details>",
    )
    section(
        "avoidability",
        "4. Which supplements appear potentially avoidable?",
        "Main and remaining supplements are classified separately from retrospective evidence. "
        "Dollars are "
        "associated claim dollars per population claim, not estimated savings or "
        "allocations to individual causes. Unclear cases are retained.",
        chart("potentially_avoidable")
        + chart("remaining_avoidability")
        + chart("primary_prevention_area")
        + chart("prevention_areas")
        + chart("prevention_area_dollars")
        + "<p class='muted'>Prevention-area dollars use documented approved supplement amounts "
        "on claims with that area marked yes, weighted per population claim. Areas overlap: "
        "the same claim dollars may appear in several bars. Do not sum the bars or interpret "
        "them as savings. Missing classifications and amounts are reported below.</p>"
        + "<details><summary>Prevention-area dollars and coverage</summary>"
        + _table(tables.get("prevention_area_dollars"))
        + "</details>"
        + chart("avoidability_dollars")
        + _table(tables.get("classifications")),
    )
    section(
        "segments",
        "5. Which kinds of claims behave differently?",
        "Segment rules are discovered in training data and evaluated on held-out "
        "claims. Only segments meeting the minimum raw and effective counts in "
        "both cohorts get an exploratory difference. Imputed feature values can "
        "participate in rules.",
        chart("segments")
        + _table(predictive.get("segment_definitions"))
        + _table(predictive.get("segments"))
        + _table(predictive.get("segment_comparisons")),
    )
    explanation = predictive.get("explanations", {})
    section(
        "explain",
        "6. Why does the model predict supplementation?",
        "Read accuracy before importance. Permutation importance measures held-"
        "out performance loss and its error bars show permutation variability, "
        "not confidence intervals. SHAP describes prediction contributions "
        "relative to a training reference. Correlated inputs can share or dilute "
        "importance; neither method establishes causality.",
        _table(predictive.get("metrics"))
        + chart("calibration")
        + chart("permutation_importance")
        + chart("shap_status")
        + chart("predictive_status")
        + chart("incidence_shap_pp")
        + chart("severity_shap_dollars")
        + chart("shap_distribution")
        + "<details><summary>Model response curves — not causal what-if estimates</summary>"
        "<p>Partial dependence changes one feature while leaving others fixed; correlated "
        "or implausible combinations may be evaluated. "
        "These curves have no causal interpretation.</p>"
        + "".join(chart(k) for k in figures if k.startswith("dependence_"))
        + "</details>",
    )
    examples_html = ""
    if explanation.get("status") == "success":
        predictions = _frame(explanation["predictions"])
        predictions["absolute_error"] = (
            predictions.expected_dollars - predictions.supplement_approved_amount
        ).abs()
        ordered = predictions.sort_values(["probability", "claim_id"])
        selections = [
            ("Highest predicted risk", ordered.iloc[-1].claim_id),
            ("Middle predicted risk", ordered.iloc[len(ordered) // 2].claim_id),
            ("Lowest predicted risk", ordered.iloc[0].claim_id),
        ]
        if predictions.absolute_error.notna().any():
            selections.append(
                (
                    "Largest dollar prediction error",
                    predictions.loc[predictions.absolute_error.idxmax(), "claim_id"],
                )
            )
        seen = set()
        evidence = _frame(explanation.get("evidence"))
        for purpose, claim_id in selections:
            if claim_id in seen:
                continue
            seen.add(claim_id)
            key = f"claim-{len(seen)}"
            figures[key] = claim_explanation_figure(explanation, claim_id)
            figures[key + "-dollars"] = claim_explanation_figure(
                explanation, claim_id, output="expected_dollars"
            )
            examples_html += (
                f"<h3>{escape(purpose)} · {escape(str(claim_id))}</h3>"
                + chart(key)
                + chart(key + "-dollars")
            )
            examples_html += _table(predictions[predictions.claim_id.eq(claim_id)])
            if not evidence.empty:
                examples_html += (
                    "<details><summary>Input values and source evidence</summary>"
                    + _table(evidence[evidence.claim_id.eq(claim_id)], limit=1000)
                    + "</details>"
                )
        examples_html = (
            f"<p>Explained {explanation['explained_n']} of "
            f"{explanation['heldout_n']} held-out claims. "
            "Examples are selected by predicted risk and error, not by whether "
            "they support a Hover benefit.</p>" + examples_html
        )
    section(
        "claims",
        "7. Can we inspect and substantiate individual explanations?",
        "Waterfalls reconcile to model predictions. The combined dollar bridge is"
        " a symmetric allocation of separate probability/severity SHAP "
        "contributions, not joint SHAP. Its reference is a product of two model "
        "references, not mean observed dollars. Source links identify extraction "
        "provenance; they do not prove a causal explanation.",
        examples_html
        + "<details><summary>Evidence-linked representative mechanism claims</summary>"
        + _table(tables.get("representative_claims"), limit=1000)
        + "</details>",
    )
    model_status = [
        {
            "model": k,
            "status": report.get(k, {}).get("status"),
            "reason": report.get(k, {}).get("reason", report.get(k, {}).get("interval_status", "")),
            "analysis_n": report.get(k, {}).get("analysis_n"),
        }
        for k in ("structured_model", "selected_model", "predictive")
    ]
    section(
        "coverage",
        "8. How much confidence should we place in these results?",
        "Review data coverage, calendar overlap, missingness, and model support. "
        "Study weights do not correct extraction failures or unmeasured "
        "confounding. Bootstrap intervals quantify claim sampling, not LLM error "
        "or event-level clustering.",
        _table(model_status)
        + _table(tables.get("audit_coverage"))
        + "<details><summary>Legacy aggregates (excluded from main/remaining metrics)</summary>"
        + _table(tables.get("legacy_aggregate_claims"))
        + "</details>"
        + _table(tables.get("population_calendar_coverage"))
        + "<details><summary>Missingness and extraction coverage details</summary>"
        + _table(tables.get("audit_missingness"), limit=10000)
        + "</details>"
        + "<details><summary>Complete feature dictionary</summary>"
        + _table(tables.get("feature_dictionary"), limit=10000)
        + "</details>",
    )
    nav = "".join(
        f'<a href="#{identifier}">{label}</a>'
        for identifier, label in [
            ("impact", "Impact"),
            ("quality", "Quality & mix"),
            ("mechanisms", "Drivers"),
            ("avoidability", "Avoidability"),
            ("segments", "Segments"),
            ("explain", "Explainability"),
            ("claims", "Claim examples"),
            ("coverage", "Coverage"),
        ]
    )
    html = (Path(__file__).parent / "templates" / "report_header.html").read_text(encoding="utf-8")
    if report.get("synthetic"):
        html += (
            '<div class="scope"><strong>SYNTHETIC DEMONSTRATION</strong> · '
            "Fictional claims and programmed extraction outputs. Patterns are designed "
            "to exercise the workflow, not estimate Hover effectiveness.</div>"
        )
    if report.get("supplement_schema_version") != "2.0":
        html += (
            '<div class="scope">Historical report: supplement classifications describe the '
            "aggregate history, not a selected main supplement. Main/remaining details require "
            "schema-v2 extraction.</div>"
        )
    html += "<nav>" + nav + "</nav><main>" + "".join(sections) + "</main>"
    research_link = (
        'Full machine-readable results: <a href="research.json">research.json</a>; '
        if (directory / "research.json").exists()
        else ""
    )
    html += (
        "<footer>Local research artifact. Charts work offline. "
        + research_link
        + "Question summaries: "
        '<a href="business_answers.csv">business_answers.csv</a>.</footer></body></html>'
    )
    path = directory / "business_report.html"
    path.write_text(html, encoding="utf-8")
    return path
