"""Explicitly selected covariates, two-part associations, and held-out prediction."""

import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    mean_absolute_error,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier, export_text

from .analysis import diagnostics, effective_sample_size, weighted_mean
from .dataframes import derive_outcomes, feature_dictionary, validate_claim_ids


@dataclass
class ResearchConfig:
    covariates: list[str] = field(default_factory=lambda: ["peril", "sub_peril"])
    tier: str = "structured"
    pretreatment_rationale: dict[str, str] = field(default_factory=dict)
    seed: int = 42
    bootstrap_replicates: int = 500
    test_fraction: float = 0.25
    trees: int = 200
    min_segment_size: int = 20
    shap_enabled: bool = True
    shap_max_claims: int = 200
    shap_background_size: int = 100

    def validate(self):
        if self.tier not in {"structured", "enriched", "secondary"}:
            raise ValueError("tier must be structured, enriched, or secondary")
        if len(self.covariates) != len(set(self.covariates)):
            raise ValueError("Duplicate covariates")
        if self.bootstrap_replicates < 0 or not 0 < self.test_fraction < 1:
            raise ValueError("Invalid bootstrap count or test fraction")
        if self.trees < 1 or self.min_segment_size < 2:
            raise ValueError("Invalid tree or segment size")
        if self.shap_max_claims < 1 or self.shap_background_size < 1:
            raise ValueError("SHAP budgets must be positive")
        dictionary = feature_dictionary().set_index("field")
        for col in self.covariates:
            if col in {"claim_id", "hover", "sampling_weight", "inclusion_probability"} or (
                "supplement" in col or col in {"revised_estimate_amount", "extraction_status"}
            ):
                raise ValueError(
                    f"Outcome, identifier, or post-estimate covariate prohibited: {col}"
                )
            if col in dictionary.index and dictionary.loc[col, "pandas_kind"] in {"text", "date"}:
                raise ValueError(f"Narrative/date feature must not enter directly: {col}")
            if col.startswith("baseline__"):
                if col not in dictionary.index:
                    raise ValueError(f"Unknown baseline covariate: {col}")
                if self.tier == "structured":
                    raise ValueError("Structured models cannot include baseline LLM features")
                process = col.startswith(
                    ("baseline__documentation__", "baseline__initial_estimate__")
                )
                if process and self.tier != "secondary":
                    raise ValueError("Initial process/estimate features are secondary only")
                if (
                    self.tier != "secondary"
                    and not self.pretreatment_rationale.get(col, "").strip()
                ):
                    raise ValueError(f"Pre-treatment rationale required: {col}")
            elif col == "initial_estimate_amount":
                if self.tier != "secondary":
                    raise ValueError("Initial estimate amount is secondary only")
            elif col not in {"peril", "sub_peril", "loss_month", "fnol_delay_days"}:
                raise ValueError(f"Not in the structured covariate allowlist: {col}")


def _prepare(frame, config):
    config.validate()
    df = derive_outcomes(frame)
    validate_claim_ids(df)
    if "dol" in df:
        dates = pd.to_datetime(df.dol, errors="coerce")
        df["loss_month"] = dates.dt.strftime("%Y-%m")
        if "fnol_date" in df:
            df["fnol_delay_days"] = (pd.to_datetime(df.fnol_date, errors="coerce") - dates).dt.days
    absent = set(config.covariates) - set(df)
    if absent:
        raise UnsupportedModel(f"Missing covariate columns: {sorted(absent)}")
    extracted_amount = "baseline__initial_estimate__initial_estimate_amount"
    if extracted_amount in config.covariates:
        df[extracted_amount] = df.initial_estimate_amount
    if any(c.startswith("baseline__") for c in config.covariates) and "baseline_status" in df:
        df = df[df.baseline_status.eq("success")].copy()
    return df[df.supplement_approved_amount.notna()].copy()


def _x(df, config):
    x = df[["hover", *config.covariates]].copy()
    for col in x:
        if pd.api.types.is_numeric_dtype(x[col]) or pd.api.types.is_bool_dtype(x[col]):
            x[col] = pd.to_numeric(x[col]).astype(float)
        else:
            x[col] = x[col].map(lambda v: str(v) if pd.notna(v) else np.nan).astype(object)
    return x


def _preprocessor(x):
    numeric = list(x.select_dtypes(include="number").columns)
    categorical = [c for c in x if c not in numeric]
    return ColumnTransformer(
        [
            (
                "numeric",
                Pipeline(
                    [
                        (
                            "impute",
                            SimpleImputer(
                                strategy="median", add_indicator=True, keep_empty_features=True
                            ),
                        ),
                        ("scale", StandardScaler()),
                    ]
                ),
                numeric,
            ),
            (
                "categorical",
                Pipeline(
                    [
                        (
                            "impute",
                            SimpleImputer(
                                strategy="constant", fill_value="missing", keep_empty_features=True
                            ),
                        ),
                        (
                            "encode",
                            OneHotEncoder(
                                handle_unknown="ignore", drop="first", sparse_output=False
                            ),
                        ),
                    ]
                ),
                categorical,
            ),
        ],
        verbose_feature_names_out=False,
    )


class UnsupportedModel(ValueError):
    pass


def _fit_two_part(df, config):
    import statsmodels.api as sm
    from statsmodels.tools.sm_exceptions import PerfectSeparationWarning

    y = (df.supplement_approved_amount > 0).astype(int)
    if y.nunique() < 2 or df.hover.nunique() < 2:
        raise UnsupportedModel("Training requires both cohorts and both incidence classes")
    x = _x(df, config)
    prep = _preprocessor(x)
    encoded = prep.fit_transform(x)
    # Keep independent case-mix columns first. Never discard a confounder merely
    # to retain Hover: a redundant Hover column makes the comparison unsupported.
    encoded_names = prep.get_feature_names_out()
    indices = [i for i, name in enumerate(encoded_names) if name != "hover"]
    indices += [i for i, name in enumerate(encoded_names) if name == "hover"]
    keep, dropped = [], []
    design = np.ones((len(df), 1))
    for index in indices:
        candidate = np.column_stack([design, encoded[:, index]])
        if np.linalg.matrix_rank(candidate) > design.shape[1]:
            keep.append(index)
            design = candidate
        elif encoded_names[index] == "hover":
            raise UnsupportedModel(
                "Hover is confounded with the selected case-mix/calendar columns"
            )
        else:
            dropped.append(encoded_names[index])
    design = sm.add_constant(encoded[:, keep], has_constant="add")
    positive = y.to_numpy() == 1
    if len(df) <= design.shape[1] + 1 or positive.sum() <= design.shape[1] + 1:
        raise UnsupportedModel("Too few claims/positive supplements for the selected covariates")
    if np.linalg.matrix_rank(design) != design.shape[1] or (
        np.linalg.matrix_rank(design[positive]) != design.shape[1]
    ):
        raise UnsupportedModel(
            "Covariates/cohort are collinear or positive-severity overlap is absent"
        )
    with warnings.catch_warnings():
        warnings.simplefilter("error", PerfectSeparationWarning)
        incidence = sm.GLM(
            y, design, family=sm.families.Binomial(), freq_weights=df.sampling_weight
        ).fit(maxiter=100)
        severity = sm.GLM(
            df.loc[positive, "supplement_approved_amount"],
            design[positive],
            family=sm.families.Gamma(sm.families.links.Log()),
            freq_weights=df.loc[positive, "sampling_weight"],
        ).fit(maxiter=100)
    if not incidence.converged or not severity.converged:
        raise UnsupportedModel("GLM did not converge")
    names = ["intercept", *prep.get_feature_names_out()[keep]]
    coefficients = pd.DataFrame(
        {
            "feature": names,
            "incidence_log_odds": incidence.params.to_numpy(),
            "severity_log_mean": severity.params.to_numpy(),
        }
    )
    from .explainability import feature_label, transformed_feature_metadata

    encoded_metadata = transformed_feature_metadata(prep)
    contrasts, odds_ratios, severity_multipliers = ["Intercept"], [np.nan], [np.nan]
    for position, index in enumerate(keep, 1):
        meta = encoded_metadata[index]
        step = 1.0
        if meta["kind"] == "numeric":
            if meta["missing_indicator"]:
                contrast = f"{feature_label(meta['feature'])}: missing versus recorded"
            else:
                step = 1000 if meta["feature"].endswith(("_amount", "_dollars")) else 1
                contrast = f"{feature_label(meta['feature'])}: increase of {step:g} original units"
            factor = step / meta["scale"]
        else:
            contrast = (
                f"{feature_label(meta['feature'])}: {meta['category']} versus {meta['reference']}"
            )
            factor = 1
        contrasts.append(contrast)
        odds_ratios.append(float(np.exp(np.asarray(incidence.params)[position] * factor)))
        severity_multipliers.append(float(np.exp(np.asarray(severity.params)[position] * factor)))
    coefficients["contrast"] = contrasts
    coefficients["odds_ratio"] = odds_ratios
    coefficients["severity_multiplier"] = severity_multipliers
    coefficients.attrs["redundant_columns"] = dropped

    def predict(reference):
        design = sm.add_constant(prep.transform(_x(reference, config))[:, keep], has_constant="add")
        p, s = np.asarray(incidence.predict(design)), np.asarray(severity.predict(design))
        if not np.isfinite(p).all() or not np.isfinite(s).all():
            raise UnsupportedModel("Nonfinite model predictions")
        return p, s, p * s

    return predict, coefficients


def _standardize(predict, reference):
    estimates = {}
    for cohort in (False, True):
        hypothetical = reference.assign(hover=cohort)
        p, s, dollars = predict(hypothetical)
        w = reference.sampling_weight.to_numpy()
        incidence = float(np.average(p, weights=w))
        expected = float(np.average(dollars, weights=w))
        # Conditional severity is weighted by predicted incidence, preserving p*s identity.
        estimates[cohort] = (incidence, expected / incidence if incidence else np.nan, expected)
    return np.array(
        [
            *estimates[False],
            *estimates[True],
            *(np.array(estimates[True]) - np.array(estimates[False])),
        ]
    )


def _covariate_balance(df, config):
    rows = []
    for col in config.covariates:
        values = df[col]
        numeric = pd.api.types.is_numeric_dtype(values) or pd.api.types.is_bool_dtype(values)
        levels = [None] if numeric else sorted(values.dropna().unique(), key=str)
        for level in levels:
            measurement = values if numeric else values.eq(level).where(values.notna())
            group_stats = {}
            for cohort in (False, True):
                subset = df.hover.eq(cohort) & measurement.notna()
                v = pd.to_numeric(measurement[subset]).astype(float)
                w = df.loc[subset, "sampling_weight"]
                mean = weighted_mean(v, w)
                variance = float(np.average((v - mean) ** 2, weights=w)) if len(v) else np.nan
                group_stats[cohort] = (mean, variance, int(subset.sum()))
            m0, v0, n0 = group_stats[False]
            m1, v1, n1 = group_stats[True]
            pooled_sd = np.sqrt((v0 + v1) / 2)
            rows.append(
                {
                    "feature": col,
                    "level": level,
                    "non_hover_mean": m0,
                    "hover_mean": m1,
                    "non_hover_known_n": n0,
                    "hover_known_n": n1,
                    "standardized_difference": (m1 - m0) / pooled_sd if pooled_sd > 0 else np.nan,
                }
            )
    return pd.DataFrame(rows)


def fit_statistical_models(frame, config=None):
    config = config or ResearchConfig()
    try:
        df = _prepare(frame, config)
    except UnsupportedModel as exc:
        return {
            "status": "unsupported",
            "reason": str(exc),
            "input_n": len(frame),
            "analysis_n": 0,
            "tier": config.tier,
            "diagnostics": diagnostics(frame),
        }
    result = {
        "status": "unsupported",
        "tier": config.tier,
        "interpretation": "Adjusted associations, not causal effects",
        "input_n": len(frame),
        "analysis_n": len(df),
        "diagnostics": diagnostics(frame),
        "bootstrap_failures": [],
        "covariate_balance": _covariate_balance(df, config),
    }
    try:
        predict, coefficients = _fit_two_part(df, config)
        point = _standardize(predict, df)
    except (ValueError, ArithmeticError, np.linalg.LinAlgError, Warning) as exc:
        result["reason"] = str(exc)
        return result
    rng = np.random.default_rng(config.seed)
    draws = []
    strata = ["hover"] + (["sampling_stratum"] if "sampling_stratum" in df else [])
    groups = list(df.groupby(strata, observed=True))
    for _ in range(config.bootstrap_replicates):
        sample = pd.concat(
            [g.iloc[rng.integers(0, len(g), len(g))] for _, g in groups], ignore_index=True
        )
        try:
            replicate_predict, _ = _fit_two_part(sample, config)
            draws.append(_standardize(replicate_predict, sample))
        except (ValueError, ArithmeticError, np.linalg.LinAlgError, Warning) as exc:
            result["bootstrap_failures"].append(str(exc))
    # Refuse deceptively precise intervals from a small surviving set of fits.
    enough = len(draws) >= max(30, int(config.bootstrap_replicates * 0.8))
    bounds = np.quantile(draws, [0.025, 0.975], axis=0) if enough else np.full((2, 9), np.nan)
    labels = [
        (group, metric)
        for group in ("non_hover", "hover", "difference")
        for metric in ("incidence", "conditional_severity", "expected_dollars")
    ]
    result.update(
        status="success",
        coefficients=coefficients,
        redundant_columns=coefficients.attrs["redundant_columns"],
        bootstrap_successes=len(draws),
        interval_status="available" if enough else "insufficient_successful_replicates",
        estimates=pd.DataFrame(
            [
                {
                    "comparison": group,
                    "metric": metric,
                    "estimate": point[i],
                    "lower_95": bounds[0, i],
                    "upper_95": bounds[1, i],
                }
                for i, (group, metric) in enumerate(labels)
            ]
        ),
    )
    return result


def _prediction_metrics(y, amount, p, severity, weights):
    positive = y == 1
    return {
        "roc_auc": roc_auc_score(y, p, sample_weight=weights) if y.nunique() == 2 else np.nan,
        "average_precision": average_precision_score(y, p, sample_weight=weights)
        if y.nunique() == 2
        else np.nan,
        "brier_score": brier_score_loss(y, p, sample_weight=weights),
        "severity_mae": mean_absolute_error(
            amount[positive], severity[positive], sample_weight=weights[positive]
        )
        if positive.any()
        else np.nan,
        "dollars_mae": mean_absolute_error(amount, p * severity, sample_weight=weights),
    }


def run_predictive_research(frame, config=None):
    config = config or ResearchConfig()
    try:
        df = _prepare(frame, config).reset_index(drop=True)
    except UnsupportedModel as exc:
        return {"status": "unsupported", "reason": str(exc), "input_n": len(frame), "analysis_n": 0}
    result = {
        "status": "unsupported",
        "input_n": len(frame),
        "analysis_n": len(df),
        "interpretation": "Held-out prediction and exploratory segment associations",
    }
    if len(df) < 20 or df.supplement_incidence.nunique() < 2:
        return dict(result, reason="Need at least 20 claims and both incidence classes")
    dates = pd.to_datetime(df.get("dol", pd.Series(pd.NaT, index=df.index)), errors="coerce")
    chronological = dates.notna().all() and dates.nunique() > 1
    try:
        if chronological:
            cutoff = dates.sort_values().iloc[
                min(int(len(df) * (1 - config.test_fraction)), len(df) - 1)
            ]
            train, test = df[dates < cutoff], df[dates >= cutoff]
        else:
            train, test = train_test_split(
                df,
                test_size=config.test_fraction,
                random_state=config.seed,
                stratify=df.supplement_incidence.astype(int),
            )
    except ValueError as exc:
        return dict(result, reason=str(exc))
    if len(train) < 10 or len(test) < 2 or train.supplement_incidence.nunique() < 2:
        return dict(
            result, reason="Holdout leaves insufficient training claims or incidence classes"
        )
    xtrain, xtest = _x(train, config), _x(test, config)
    ytrain, ytest = train.supplement_incidence.astype(int), test.supplement_incidence.astype(int)
    positive = ytrain == 1
    if positive.sum() < 5:
        return dict(result, reason="Need at least five positive training supplements")
    classifier = Pipeline(
        [
            ("prepare", _preprocessor(xtrain)),
            (
                "forest",
                RandomForestClassifier(
                    n_estimators=config.trees,
                    min_samples_leaf=5,
                    random_state=config.seed,
                    n_jobs=1,
                ),
            ),
        ]
    )
    regressor = Pipeline(
        [
            ("prepare", _preprocessor(xtrain)),
            (
                "forest",
                RandomForestRegressor(
                    n_estimators=config.trees,
                    min_samples_leaf=5,
                    random_state=config.seed,
                    n_jobs=1,
                ),
            ),
        ]
    )
    classifier.fit(xtrain, ytrain, forest__sample_weight=train.sampling_weight)
    regressor.fit(
        xtrain[positive],
        train.loc[positive, "supplement_approved_amount"],
        forest__sample_weight=train.loc[positive, "sampling_weight"],
    )
    p, s = classifier.predict_proba(xtest)[:, 1], regressor.predict(xtest)
    metrics = {
        "random_forest": _prediction_metrics(
            ytest, test.supplement_approved_amount, p, s, test.sampling_weight
        )
    }
    base_p = float(np.average(ytrain, weights=train.sampling_weight))
    base_s = float(
        np.average(
            train.loc[positive, "supplement_approved_amount"],
            weights=train.loc[positive, "sampling_weight"],
        )
    )
    metrics["training_mean_baseline"] = _prediction_metrics(
        ytest,
        test.supplement_approved_amount,
        np.full(len(test), base_p),
        np.full(len(test), base_s),
        test.sampling_weight,
    )
    try:
        glm_predict, _ = _fit_two_part(train, config)
        gp, gs, _ = glm_predict(test)
        metrics["glm"] = _prediction_metrics(
            ytest, test.supplement_approved_amount, gp, gs, test.sampling_weight
        )
    except (ValueError, ArithmeticError, np.linalg.LinAlgError, Warning) as exc:
        result["glm_comparison_unavailable"] = str(exc)
    importance = permutation_importance(
        classifier,
        xtest,
        ytest,
        scoring="neg_brier_score",
        n_repeats=5,
        random_state=config.seed,
        sample_weight=test.sampling_weight,
    )
    importances = pd.DataFrame(
        {
            "feature": xtest.columns,
            "importance": importance.importances_mean,
            "std": importance.importances_std,
        }
    )
    dependence = []
    for col in xtrain:
        values = xtrain[col].dropna()
        grid = (
            np.unique(values.quantile([0, 0.25, 0.5, 0.75, 1]))
            if (pd.api.types.is_numeric_dtype(values))
            else values.value_counts().head(5).index
        )
        for value in grid:
            hypothetical = xtest.assign(**{col: value})
            dp = classifier.predict_proba(hypothetical)[:, 1]
            ds = regressor.predict(hypothetical)
            dependence.append(
                {
                    "feature": col,
                    "value": value,
                    "incidence": np.average(dp, weights=test.sampling_weight),
                    "expected_dollars": np.average(dp * ds, weights=test.sampling_weight),
                }
            )
    encoded_train = classifier.named_steps["prepare"].transform(xtrain)
    segment_names = classifier.named_steps["prepare"].get_feature_names_out()
    segment_keep = segment_names != "hover"
    segment_names = segment_names[segment_keep]
    segment_train = encoded_train[:, segment_keep]
    segment_test = classifier.named_steps["prepare"].transform(xtest)[:, segment_keep]
    if not len(segment_names):
        segment_names = ["all_claims"]
        segment_train = np.zeros((len(train), 1))
        segment_test = np.zeros((len(test), 1))
    from .explainability import (
        explain_tree_predictions,
        segment_definitions,
        transformed_feature_metadata,
    )

    segment_metadata = [
        m
        for m in transformed_feature_metadata(classifier.named_steps["prepare"])
        if m["feature"] != "hover"
    ]
    if not segment_metadata:
        segment_metadata = [
            {
                "feature": "all_claims",
                "kind": "numeric",
                "mean": 0,
                "scale": 1,
                "missing_indicator": False,
            }
        ]
    segment_tree = DecisionTreeClassifier(
        max_depth=2, min_samples_leaf=config.min_segment_size, random_state=config.seed
    )
    segment_tree.fit(segment_train, ytrain, sample_weight=train.sampling_weight)
    leaves = segment_tree.apply(segment_test)
    segments = []
    for (leaf, hover), group in test.assign(segment=leaves).groupby(["segment", "hover"]):
        segments.append(
            {
                "segment": leaf,
                "hover": hover,
                "n": len(group),
                "effective_n": effective_sample_size(group.sampling_weight),
                "incidence": weighted_mean(group.supplement_incidence, group.sampling_weight),
                "approved_dollars_per_claim": weighted_mean(
                    group.supplement_approved_amount, group.sampling_weight
                ),
            }
        )
    comparisons = []
    segment_frame = pd.DataFrame(segments)
    for leaf, group in segment_frame.groupby("segment"):
        supported = (
            group.hover.nunique() == 2
            and group.n.min() >= config.min_segment_size
            and group.effective_n.min() >= config.min_segment_size
        )
        row = {
            "segment": leaf,
            "status": "exploratory" if supported else "insufficient_cohort_counts",
        }
        if supported:
            indexed = group.set_index("hover")
            row["incidence_difference"] = (
                indexed.loc[True, "incidence"] - indexed.loc[False, "incidence"]
            )
            row["dollars_difference"] = (
                indexed.loc[True, "approved_dollars_per_claim"]
                - indexed.loc[False, "approved_dollars_per_claim"]
            )
        comparisons.append(row)
    calibration = []
    predictions = test[
        ["claim_id", "hover", "sampling_weight", "supplement_approved_amount"]
    ].copy()
    predictions["probability"], predictions["expected_dollars"] = p, p * s
    predictions["observed"] = ytest
    predictions["bin"] = np.minimum((p * 10).astype(int), 9)
    for bin_id, group in predictions.groupby("bin"):
        calibration.append(
            {
                "bin": bin_id,
                "n": len(group),
                "predicted": weighted_mean(group.probability, group.sampling_weight),
                "observed": weighted_mean(group.observed, group.sampling_weight),
            }
        )
    result.update(
        status="success",
        split="chronological" if chronological else "stratified",
        train_claim_ids=train.claim_id.tolist(),
        test_claim_ids=test.claim_id.tolist(),
        metrics=pd.DataFrame(metrics).T.reset_index(names="model"),
        calibration=pd.DataFrame(calibration),
        predictions=predictions,
        permutation_importance=importances,
        partial_dependence=pd.DataFrame(dependence),
        segments=pd.DataFrame(segments),
        segment_comparisons=pd.DataFrame(comparisons),
        segment_rules=export_text(
            segment_tree,
            feature_names=list(segment_names),
        ),
        classifier=classifier,
        regressor=regressor,
        segment_definitions=segment_definitions(segment_tree, segment_metadata),
        model_parameters={
            "classifier": classifier.named_steps["forest"].get_params(),
            "positive_severity_regressor": regressor.named_steps["forest"].get_params(),
            "segment_tree": segment_tree.get_params(),
        },
    )
    result["explanations"] = (
        explain_tree_predictions(
            classifier,
            regressor,
            xtrain,
            xtest,
            train,
            test,
            seed=config.seed,
            max_claims=config.shap_max_claims,
            background_size=config.shap_background_size,
        )
        if config.shap_enabled
        else {"status": "disabled", "reason": "Disabled in ResearchConfig"}
    )
    return result
