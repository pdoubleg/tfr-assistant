"""Weighted descriptive research. No model fitting or external services."""

import numpy as np
import pandas as pd

from .dataframes import derive_outcomes, feature_dictionary, validate_claim_ids


def weighted_mean(values, weights):
    values = pd.to_numeric(values, errors="coerce").astype(float)
    valid = values.notna()
    return float(np.average(values[valid], weights=weights[valid])) if valid.any() else np.nan


def effective_sample_size(weights):
    return float(weights.sum() ** 2 / (weights**2).sum()) if len(weights) else 0.0


def stratified_sample(population, sample_sizes: dict[tuple[bool, bool], int], *, seed=42):
    """Sample Hover x approved-incidence strata; retain exact inclusion probabilities."""
    df = derive_outcomes(population)
    validate_claim_ids(df)
    if df.supplement_incidence.isna().any():
        raise ValueError("Sampling requires known approved supplement amounts")
    parts = []
    for key, group in df.groupby(["hover", "supplement_incidence"], observed=True, sort=True):
        n = sample_sizes.get(key)
        if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= len(group):
            raise ValueError(
                f"Stratum {key} requires an integer sample size from 1 to {len(group)}"
            )
        selected = group.sort_values("claim_id").sample(n=n, random_state=seed).copy()
        selected["sampling_stratum"] = f"{int(key[0])}:{int(key[1])}"
        selected["inclusion_probability"] = n / len(group)
        selected["sampling_weight"] = len(group) / n
        parts.append(selected)
    return pd.concat(parts, ignore_index=True) if parts else df


def scorecards(frame):
    df = derive_outcomes(frame)
    rows = []
    for hover, group in df.groupby("hover"):
        metrics = {
            "supplement_incidence": group.supplement_incidence,
            "approved_dollars_per_claim": group.supplement_approved_amount,
            "conditional_approved_severity": group.supplement_approved_amount.where(
                group.supplement_approved_amount > 0
            ),
            "supplement_ratio": group.supplement_ratio,
        }
        metrics.update(
            {
                c: group[c]
                for c in (
                    "supplement_requested_amount",
                    "supplement_approved_amount",
                    "supplement_denied_amount",
                    "revised_estimate_amount",
                )
            }
        )
        for col in group:
            if col.startswith(("baseline__documentation__", "baseline__initial_estimate__")):
                if pd.api.types.is_bool_dtype(group[col]):
                    metrics[col] = group[col]
                elif col.endswith(("documentation_quality", "overall_initial_estimate_quality")):
                    for level in ("low", "moderate", "high"):
                        metrics[f"{col}={level}"] = group[col].eq(level).where(group[col].notna())
        for metric, values in metrics.items():
            known = values.notna()
            ineligible = pd.Series(False, index=group.index)
            if metric == "conditional_approved_severity":
                ineligible = group.supplement_approved_amount.eq(0)
            elif metric == "supplement_ratio":
                ineligible = group.initial_estimate_amount.eq(0)
            rows.append(
                {
                    "hover": hover,
                    "metric": metric,
                    "estimate": weighted_mean(values, group.sampling_weight),
                    "known_n": int(known.sum()),
                    "unknown_n": int((~known & ~ineligible).sum()),
                    "ineligible_n": int(ineligible.sum()),
                    "denominator_weight": float(group.loc[known, "sampling_weight"].sum()),
                    "effective_n": effective_sample_size(group.loc[known, "sampling_weight"]),
                }
            )
    return pd.DataFrame(rows)


def decompose_dollar_difference(frame):
    if frame.empty:
        return {"status": "unsupported", "reason": "No claims available"}
    table = scorecards(frame).pivot(index="hover", columns="metric", values="estimate")
    needed = {False, True}
    if not needed.issubset(table.index):
        return {"status": "unsupported", "reason": "Both Hover cohorts are required"}
    p0, p1 = table.loc[False, "supplement_incidence"], table.loc[True, "supplement_incidence"]
    s0, s1 = (
        table.loc[False, "conditional_approved_severity"],
        table.loc[True, "conditional_approved_severity"],
    )
    if not np.isfinite([p0, p1, s0, s1]).all():
        return {
            "status": "unsupported",
            "reason": "Both cohorts need positive approved supplements",
        }
    incidence = (p1 - p0) * (s1 + s0) / 2
    severity = (s1 - s0) * (p1 + p0) / 2
    return {
        "status": "success",
        "incidence_contribution": incidence,
        "severity_contribution": severity,
        "total_difference": p1 * s1 - p0 * s0,
    }


def mechanism_analysis(frame):
    df = derive_outcomes(frame)
    legacy = (
        df.loc[df.supplement_schema.eq("legacy_aggregate")].copy()
        if "supplement_schema" in df
        else pd.DataFrame()
    )
    if "supplement_schema" in df:
        df = df.loc[df.supplement_schema.ne("legacy_aggregate")].copy()
    rows, prevention_dollars = [], []
    columns = [
        r["field"]
        for r in feature_dictionary().to_dict("records")
        if r["pandas_kind"] == "indicator" and r["field"].startswith("supplement_mechanism__")
    ]
    for hover, group in df.groupby("hover"):
        for denominator, subset in (
            ("all_claims", group),
            ("approved_supplements", group[group.supplement_incidence.fillna(False)]),
        ):
            for col in columns:
                if col not in subset:
                    continue
                values = subset[col].copy()
                if "supplement_status" in subset:
                    values = values.mask(subset.supplement_status.eq("skipped"), False)
                known = values.notna()
                if denominator == "all_claims" and "__prevention__" in col:
                    positive = subset.loc[values.eq(True).fillna(False)]
                    associated = (
                        (positive.supplement_approved_amount * positive.sampling_weight).sum(
                            min_count=1
                        )
                        if len(positive)
                        else 0.0
                        if known.any()
                        else np.nan
                    )
                    population_weight = float(subset.sampling_weight.sum())
                    prevention_dollars.append(
                        {
                            "hover": hover,
                            "prevention_area": col,
                            "associated_approved_dollars": associated,
                            "dollars_per_population_claim": associated / population_weight
                            if population_weight
                            else np.nan,
                            "population_denominator_weight": population_weight,
                            "positive_n": len(positive),
                            "unknown_classification_n": int((~known).sum()),
                            "known_dollars_n": int(
                                positive.supplement_approved_amount.notna().sum()
                            ),
                            "unknown_dollars_n": int(
                                positive.supplement_approved_amount.isna().sum()
                            ),
                        }
                    )
                rows.append(
                    {
                        "hover": hover,
                        "denominator": denominator,
                        "mechanism": col,
                        "rate": weighted_mean(values, subset.sampling_weight),
                        "positive_n": int(values.fillna(False).sum()),
                        "unknown_n": int((~known).sum()),
                        "total_n": len(subset),
                        "denominator_weight": float(subset.loc[known, "sampling_weight"].sum()),
                    }
                )
    distributions = []
    for col in (
        "supplement_mechanism__primary_mechanism",
        "supplement_mechanism__potentially_avoidable",
        "supplement_mechanism__primary_outcome",
        "supplement_mechanism__secondary_mechanism",
        "supplement_mechanism__remaining_outcome",
        "supplement_mechanism__remaining_avoidability",
        "supplement_mechanism__primary_prevention_area",
    ):
        if col not in df:
            continue
        for (hover, category), g in df.groupby(["hover", col], dropna=False):
            cohort = df[df.hover.eq(hover)]
            approved_cohort = cohort[cohort.supplement_incidence.fillna(False)]
            approved_group = g[g.supplement_incidence.fillna(False)]
            denominator = float(cohort.sampling_weight.sum())
            approved_denominator = float(approved_cohort.sampling_weight.sum())
            distributions.append(
                {
                    "hover": hover,
                    "classification": col,
                    "category": category,
                    "claims_n": len(g),
                    "claims_weight": g.sampling_weight.sum(),
                    "population_denominator_weight": denominator,
                    "population_share": g.sampling_weight.sum() / denominator,
                    "approved_supplement_denominator_weight": approved_denominator,
                    "approved_supplement_share": (
                        approved_group.sampling_weight.sum() / approved_denominator
                        if approved_denominator
                        else np.nan
                    ),
                    "classification_unknown_n": int(
                        (cohort[col].isna() | cohort[col].isin(["unclear", "unknown"])).sum()
                    ),
                    "associated_approved_dollars": (
                        g.supplement_approved_amount * g.sampling_weight
                    ).sum(min_count=1),
                    "unknown_dollars_n": int(g.supplement_approved_amount.isna().sum()),
                }
            )
    history = []
    for hover, group in df.groupby("hover"):
        count_col = "supplement_mechanism__history__total_count"
        if count_col not in group:
            continue
        counts = group[count_col]
        active = group["supplement_mechanism__supplement_present"].eq(True).fillna(False)
        for denominator, subset in (("all_claims", group), ("supplement_activity", group[active])):
            values = counts.loc[subset.index]
            known = values.notna()
            history.append(
                {
                    "hover": hover,
                    "denominator": denominator,
                    "repeat_rate": weighted_mean(values.gt(1).where(known), subset.sampling_weight),
                    "mean_count": weighted_mean(values, subset.sampling_weight),
                    "known_n": int(known.sum()),
                    "unknown_n": int((~known).sum()),
                    "denominator_weight": float(subset.loc[known, "sampling_weight"].sum()),
                    "partial_history_n": int(
                        subset["supplement_mechanism__history__completeness"].eq("partial").sum()
                    ),
                }
            )
    return {
        "mechanism_rates": pd.DataFrame(rows),
        "prevention_area_dollars": pd.DataFrame(prevention_dollars),
        "classifications": pd.DataFrame(distributions),
        "supplement_history": pd.DataFrame(history),
        "legacy_aggregate_claims": legacy,
    }


def diagnostics(frame):
    df = derive_outcomes(frame)
    overview, missing, balance, calendar = [], [], [], []
    for hover, group in df.groupby("hover"):
        row = {
            "hover": hover,
            "claims_n": len(group),
            "population_weight": group.sampling_weight.sum(),
            "effective_n": effective_sample_size(group.sampling_weight),
        }
        for status_col in ("extraction_status", "baseline_status", "supplement_status"):
            if status_col in group:
                for status, g in group.groupby(status_col, dropna=False):
                    row[f"{status_col}__{status}__n"] = len(g)
                    row[f"{status_col}__{status}__weight"] = g.sampling_weight.sum()
        overview.append(row)
        for col in group:
            missing.append(
                {
                    "hover": hover,
                    "field": col,
                    "missing_n": int(group[col].isna().sum()),
                    "missing_weight": group.loc[group[col].isna(), "sampling_weight"].sum(),
                }
            )
        for col in ("peril", "sub_peril"):
            if col in group:
                for level, g in group.groupby(col, dropna=False):
                    balance.append(
                        {
                            "hover": hover,
                            "field": col,
                            "level": level,
                            "share": g.sampling_weight.sum() / group.sampling_weight.sum(),
                        }
                    )
        for col in ("dol", "fnol_date"):
            if col in group:
                dates = pd.to_datetime(group[col], errors="coerce")
                calendar.append(
                    {
                        "hover": hover,
                        "field": col,
                        "first": dates.min(),
                        "last": dates.max(),
                        "unknown_n": int(dates.isna().sum()),
                    }
                )
    return {
        "coverage": pd.DataFrame(overview),
        "missingness": pd.DataFrame(missing),
        "cohort_balance": pd.DataFrame(balance),
        "calendar_coverage": pd.DataFrame(calendar),
    }


def representative_claims(results, *, per_category=3):
    rows, counts = [], {}
    for result in sorted(results, key=lambda r: r.claim_id):
        features = result.supplement.features
        if features is None or result.supplement.status != "success" or result.is_legacy:
            continue
        category = features.primary_mechanism
        if counts.get(category, 0) >= per_category:
            continue
        counts[category] = counts.get(category, 0) + 1
        rows.append(
            {
                "claim_id": result.claim_id,
                "primary_mechanism": category,
                "primary_outcome": features.primary_outcome,
                "main_avoidability": features.potentially_avoidable,
                "secondary_mechanism": features.secondary_mechanism,
                "remaining_outcome": features.remaining_outcome,
                "remaining_avoidability": features.remaining_avoidability,
                "summary": features.mechanism_summary,
                "evidence": [ref.model_dump() for ref in result.supplement.evidence],
            }
        )
    return pd.DataFrame(rows)
