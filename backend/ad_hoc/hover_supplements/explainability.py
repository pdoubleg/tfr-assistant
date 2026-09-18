"""Auditable held-out Tree SHAP and a separately labeled two-part dollar bridge.

SHAP describes predictions, not the effect of changing a capture vendor. Background
rows are sampled only from training data, proportional to the study weights.
"""

import numpy as np
import pandas as pd

from .dataframes import feature_dictionary


def feature_label(feature):
    special = {
        "hover": "Hover use",
        "peril": "Loss peril",
        "sub_peril": "Loss sub-peril",
        "initial_estimate_amount": "Initial estimate ($)",
        "loss_month": "Loss month",
        "fnol_delay_days": "Days from loss to notice",
    }
    return special.get(feature, feature.split("__")[-1].replace("_", " ").capitalize())


def transformed_feature_metadata(preprocessor):
    """Map each fitted encoded column back to its original feature, including missingness."""
    rows = []
    for name, transformer, columns in preprocessor.transformers_:
        if not len(columns):
            continue
        if name == "numeric":
            imputer = transformer.named_steps["impute"]
            scaler = transformer.named_steps["scale"]
            names = imputer.get_feature_names_out(columns)
            for i, encoded in enumerate(names):
                original = encoded.removeprefix("missingindicator_")
                rows.append(
                    {
                        "feature": original,
                        "encoded": encoded,
                        "kind": "numeric",
                        "missing_indicator": encoded.startswith("missingindicator_"),
                        "mean": scaler.mean_[i],
                        "scale": scaler.scale_[i],
                    }
                )
        elif name == "categorical":
            encoder = transformer.named_steps["encode"]
            names = iter(encoder.get_feature_names_out(columns))
            for i, original in enumerate(columns):
                for j, category in enumerate(encoder.categories_[i]):
                    if encoder.drop_idx_ is not None and j == encoder.drop_idx_[i]:
                        continue
                    rows.append(
                        {
                            "feature": original,
                            "encoded": next(names),
                            "kind": "category",
                            "category": str(category),
                            "reference": (
                                str(encoder.categories_[i][encoder.drop_idx_[i]])
                                if encoder.drop_idx_ is not None
                                else "all categories absent"
                            ),
                            "missing_indicator": False,
                        }
                    )
    if len(rows) != len(preprocessor.get_feature_names_out()):
        raise ValueError("Cannot map all transformed features to original fields")
    return rows


def segment_definitions(tree, encoded_metadata):
    """Translate shallow-tree thresholds back to human-readable original feature units."""
    rows = []

    def visit(node, path):
        index = tree.tree_.feature[node]
        if index < 0:
            rows.append({"segment": node, "definition": " AND ".join(path) or "All claims"})
            return
        meta = encoded_metadata[index]
        label = feature_label(meta["feature"])
        threshold = tree.tree_.threshold[node]
        if meta["kind"] == "category":
            left, right = f"{label} is not {meta['category']}", f"{label} is {meta['category']}"
        elif meta["missing_indicator"]:
            left, right = f"{label} is recorded", f"{label} is missing"
        else:
            original_threshold = threshold * meta["scale"] + meta["mean"]
            left, right = (
                f"{label} <= {original_threshold:.3g}",
                f"{label} > {original_threshold:.3g}",
            )
        visit(tree.tree_.children_left[node], [*path, left])
        visit(tree.tree_.children_right[node], [*path, right])

    visit(0, [])
    return pd.DataFrame(rows)


def _tree_values(pipeline, background, rows, *, probability):
    import shap

    prep, forest = pipeline.named_steps["prepare"], pipeline.named_steps["forest"]
    encoded = prep.transform(rows)
    explainer = shap.TreeExplainer(
        forest,
        data=shap.maskers.Independent(prep.transform(background), max_samples=len(background)),
        feature_perturbation="interventional",
        model_output="probability" if probability else "raw",
    )
    values = np.asarray(explainer.shap_values(encoded, check_additivity=True))
    expected = np.asarray(explainer.expected_value)
    if probability:
        class_index = int(np.flatnonzero(forest.classes_ == 1)[0])
        values, base = values[:, :, class_index], float(expected[class_index])
        prediction = pipeline.predict_proba(rows)[:, class_index]
    else:
        base = float(expected.reshape(-1)[0])
        prediction = pipeline.predict(rows)
    metadata = transformed_feature_metadata(prep)
    grouped = pd.DataFrame(index=rows.index)
    for feature in rows.columns:
        indices = [i for i, meta in enumerate(metadata) if meta["feature"] == feature]
        grouped[feature] = values[:, indices].sum(axis=1) if indices else 0.0
    reconstructed = base + grouped.sum(axis=1).to_numpy()
    if not np.allclose(reconstructed, prediction, rtol=1e-5, atol=1e-6):
        raise ValueError("SHAP reconstruction does not match held-out predictions")
    return grouped, base, prediction, float(np.max(np.abs(reconstructed - prediction)))


def explain_tree_predictions(
    classifier,
    regressor,
    xtrain,
    xtest,
    train_metadata,
    test_metadata,
    *,
    seed=42,
    max_claims=200,
    background_size=100,
):
    """Explain a reproducible uniform subset of held-out claims; preserve original weights.

    Metadata frames must align by index with features and contain claim_id, hover,
    sampling_weight, and supplement_approved_amount. Never pass test rows as background.
    The regressor's background is drawn only from positive training claims.
    """
    if max_claims < 1 or background_size < 1:
        raise ValueError("Explanation budgets must be positive")
    if xtrain.empty or xtest.empty:
        return {"status": "unavailable", "reason": "Training and held-out claims are required"}
    if list(xtrain.columns) != list(xtest.columns):
        raise ValueError("Training and held-out feature columns must match")
    for metadata in (train_metadata, test_metadata):
        if metadata.claim_id.isna().any() or not metadata.claim_id.is_unique:
            raise ValueError("Explanation claim IDs must be unique and nonmissing")
        weights = metadata.sampling_weight.to_numpy(dtype=float)
        if not np.isfinite(weights).all() or (weights <= 0).any():
            raise ValueError("Explanation weights must be finite and positive")
    if not (train_metadata.supplement_approved_amount > 0).any():
        return {"status": "unavailable", "reason": "No positive-severity training background"}
    if not xtrain.index.equals(train_metadata.index) or not xtest.index.equals(test_metadata.index):
        raise ValueError("Explanation features and metadata must align by index")
    if set(train_metadata.claim_id) & set(test_metadata.claim_id):
        raise ValueError("Training and held-out claim IDs overlap")
    try:
        import shap
    except ImportError:
        return {
            "status": "unavailable",
            "reason": "Install the explainability dependency group for SHAP",
        }
    except Exception as exc:
        return {
            "status": "failed",
            "reason": f"SHAP could not initialize: {type(exc).__name__}: {exc}",
        }
    rng = np.random.default_rng(seed)
    positions = np.sort(rng.choice(len(xtest), size=min(max_claims, len(xtest)), replace=False))
    explained, metadata = xtest.iloc[positions], test_metadata.iloc[positions]

    def background_indices(frame):
        weights = frame.sampling_weight.to_numpy(dtype=float)
        return rng.choice(
            len(frame),
            size=min(background_size, len(frame)),
            replace=True,
            p=weights / weights.sum(),
        )

    incidence_background = background_indices(train_metadata)
    positive_mask = train_metadata.supplement_approved_amount > 0
    positive_metadata = train_metadata[positive_mask]
    severity_background = background_indices(positive_metadata)
    try:
        p_values, p_base, probabilities, p_error = _tree_values(
            classifier, xtrain.iloc[incidence_background], explained, probability=True
        )
        s_values, s_base, severities, s_error = _tree_values(
            regressor, xtrain[positive_mask].iloc[severity_background], explained, probability=False
        )
    except Exception as exc:
        return {
            "status": "failed",
            "reason": f"SHAP validation failed: {type(exc).__name__}: {exc}",
        }
    local = []
    for i, (_, row) in enumerate(explained.iterrows()):
        for feature in explained.columns:
            p_phi = float(p_values.iloc[i][feature])
            s_phi = float(s_values.iloc[i][feature])
            # This exact symmetric product bridge is NOT a joint SHAP explanation.
            dollars = p_phi * (s_base + severities[i]) / 2 + s_phi * (p_base + probabilities[i]) / 2
            local.append(
                {
                    "claim_id": metadata.iloc[i].claim_id,
                    "hover": metadata.iloc[i].hover,
                    "sampling_weight": metadata.iloc[i].sampling_weight,
                    "feature": feature,
                    "label": feature_label(feature),
                    "value": row[feature],
                    "incidence_shap_pp": p_phi * 100,
                    "severity_shap_dollars": s_phi,
                    "two_part_dollar_allocation": dollars,
                }
            )
    local_frame = pd.DataFrame(local)
    predictions = metadata[
        ["claim_id", "hover", "sampling_weight", "supplement_approved_amount"]
    ].copy()
    predictions["base_probability"] = p_base
    predictions["probability"] = probabilities
    predictions["base_severity"] = s_base
    predictions["conditional_severity"] = severities
    predictions["base_product_dollars"] = p_base * s_base
    predictions["expected_dollars"] = probabilities * severities
    allocation = local_frame.groupby("claim_id").two_part_dollar_allocation.sum()
    reconstruction = p_base * s_base + predictions.claim_id.map(allocation).to_numpy()
    if not np.allclose(reconstruction, predictions.expected_dollars, rtol=1e-5, atol=1e-4):
        return {"status": "failed", "reason": "Two-part dollar allocation does not reconcile"}
    global_rows = []
    for cohort, subset in [
        ("all", local_frame),
        ("Hover", local_frame[local_frame.hover]),
        ("Non-Hover", local_frame[~local_frame.hover]),
    ]:
        for feature, group in subset.groupby("feature"):
            for column in (
                "incidence_shap_pp",
                "severity_shap_dollars",
                "two_part_dollar_allocation",
            ):
                global_rows.append(
                    {
                        "cohort": cohort,
                        "feature": feature,
                        "label": feature_label(feature),
                        "output": column,
                        "mean_absolute_contribution": np.average(
                            group[column].abs(), weights=group.sampling_weight
                        ),
                        "mean_signed_contribution": np.average(
                            group[column], weights=group.sampling_weight
                        ),
                    }
                )
    return {
        "status": "success",
        "method": "Interventional Tree SHAP, original-feature aggregation",
        "shap_version": shap.__version__,
        "seed": seed,
        "explained_n": len(explained),
        "heldout_n": len(xtest),
        "sample_method": "uniform without replacement; original study weights",
        "background_method": (
            "training-only sampling proportional to study weights, with replacement"
        ),
        "incidence_background_ids": train_metadata.iloc[incidence_background].claim_id.tolist(),
        "severity_background_ids": positive_metadata.iloc[severity_background].claim_id.tolist(),
        "max_probability_reconstruction_error": p_error,
        "max_severity_reconstruction_error": s_error,
        "dollar_method": "Symmetric product allocation of separate SHAP values; NOT joint SHAP",
        "interpretation": "Prediction attribution, not causation or recoverable supplement dollars",
        "local_contributions": local_frame,
        "global_importance": pd.DataFrame(global_rows),
        "predictions": predictions.reset_index(drop=True),
    }


def explanation_evidence(explanations, results):
    """Connect model inputs to caller metadata or baseline extraction source references."""
    if explanations.get("status") != "success":
        return pd.DataFrame()
    by_id = {r.claim_id: r for r in results}
    dictionary = feature_dictionary().set_index("field").description.to_dict()
    rows = []
    for row in explanations["local_contributions"].to_dict("records"):
        feature = row["feature"]
        result = by_id.get(row["claim_id"])
        refs = []
        extracted_input = feature.startswith("baseline__") and feature != (
            "baseline__initial_estimate__initial_estimate_amount"
        )
        if result is not None and extracted_input:
            path = feature.removeprefix("baseline__").replace("__", ".")
            refs = [r.model_dump() for r in result.baseline.evidence if r.field_path == path]
        rows.append(
            {
                "claim_id": row["claim_id"],
                "feature": feature,
                "value": row["value"],
                "description": dictionary.get(feature, feature_label(feature)),
                "source": "baseline extraction" if extracted_input else "caller metadata",
                "evidence": refs,
                "missing_input": bool(pd.isna(row["value"])),
            }
        )
    return pd.DataFrame(rows)
