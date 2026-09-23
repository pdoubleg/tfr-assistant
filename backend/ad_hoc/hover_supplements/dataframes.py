"""Schema-driven conversion, financial derivation, and ID-based metadata joins."""

from collections.abc import Mapping, Sequence
from typing import Literal, get_args, get_origin

import numpy as np
import pandas as pd
from pydantic import BaseModel

from .pandas_types import pandas_kind


def feature_dictionary(model_type=None, prefix="", *, include_derived=False) -> pd.DataFrame:
    if model_type is None:
        from .models import ClaimLLMFeatures

        model_type = ClaimLLMFeatures
    rows = []
    for name, info in model_type.model_fields.items():
        path = f"{prefix}__{name}" if prefix else name
        typ = info.annotation
        if isinstance(typ, type) and issubclass(typ, BaseModel):
            rows.extend(feature_dictionary(typ, path).to_dict("records"))
        else:
            rows.append(
                {
                    "field": path,
                    "description": info.description,
                    "pandas_kind": pandas_kind(info),
                    "type": str(typ),
                    "choices": list(get_args(typ)) if get_origin(typ) is Literal else [],
                }
            )
    frame = pd.DataFrame(rows)
    if include_derived:
        from .derived import derived_feature_dictionary

        frame["source"] = "extracted"
        frame = pd.concat([frame, derived_feature_dictionary()], ignore_index=True)
    return frame


def prepare_flat_dataframe(
    model: BaseModel,
    *,
    column_prefix=None,
    extra_columns=None,
    drop_text=True,
    indicators_as_boolean=True,
    unknown_as_na=True,
) -> pd.DataFrame:
    df = pd.json_normalize([model.model_dump(mode="python")], sep="__")
    for row in feature_dictionary(type(model)).to_dict("records"):
        col, kind = row["field"], row["pandas_kind"]
        if col not in df:
            continue
        if kind == "text" and drop_text:
            df = df.drop(columns=col)
        elif kind == "indicator" and indicators_as_boolean:
            df[col] = df[col].map({"yes": True, "no": False, "unknown": pd.NA}).astype("boolean")
        elif kind == "date":
            df[col] = pd.to_datetime(df[col])
        elif kind in {"count", "number"}:
            df[col] = pd.to_numeric(df[col]).astype("Int64" if kind == "count" else "Float64")
        elif kind in {"category", "indicator", "text"}:
            df[col] = df[col].astype("string")
            if unknown_as_na:
                df[col] = df[col].replace("unknown", pd.NA)
    if column_prefix:
        df = df.add_prefix(column_prefix + "__")
    for name, value in (extra_columns or {}).items():
        if name in df:
            raise ValueError(f"Metadata collides with feature: {name}")
        df[name] = value
    return df


def concat_feature_frames(models: Sequence[BaseModel], *, extra_rows=None, **kwargs):
    if extra_rows is not None and len(extra_rows) != len(models):
        raise ValueError("extra_rows must have the same length as models")
    frames = [
        m.to_pandas(extra_columns=extra_rows[i] if extra_rows else None, **kwargs)
        for i, m in enumerate(models)
    ]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def validate_claim_ids(df):
    if "claim_id" not in df or df.claim_id.isna().any() or df.claim_id.duplicated().any():
        raise ValueError("A unique nonmissing claim_id is required for every row")


def derive_outcomes(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in (
        "initial_estimate_amount",
        "supplement_approved_amount",
        "supplement_requested_amount",
        "supplement_denied_amount",
        "revised_estimate_amount",
    ):
        if col not in df:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="raise").astype(float)
        if (df[col].dropna() < 0).any() or np.isinf(df[col]).any():
            raise ValueError(f"{col} must contain finite nonnegative amounts")
    approved = df.supplement_approved_amount
    df["supplement_incidence"] = approved.gt(0).astype("boolean").mask(approved.isna())
    df["supplement_ratio"] = approved / df.initial_estimate_amount.where(
        df.initial_estimate_amount > 0
    )
    if "sampling_weight" not in df:
        df["sampling_weight"] = 1.0
    w = pd.to_numeric(df.sampling_weight, errors="raise")
    if w.isna().any() or (~np.isfinite(w)).any() or (w <= 0).any():
        raise ValueError("sampling_weight must be finite and positive")
    df["sampling_weight"] = w.astype(float)
    if "hover" not in df or df.hover.isna().any() or not df.hover.isin([True, False]).all():
        raise ValueError("hover must contain booleans")
    df["hover"] = df.hover.astype(bool)
    return df


def build_feature_table(results, metadata: pd.DataFrame | Sequence[Mapping], *, drop_text=True):
    metadata = metadata.copy() if isinstance(metadata, pd.DataFrame) else pd.DataFrame(metadata)
    validate_claim_ids(metadata)
    dictionary = feature_dictionary().to_dict("records")
    if set(metadata) & {r["field"] for r in dictionary}:
        raise ValueError("Metadata collides with extracted feature columns")
    rows = []
    for result in results:
        row = {
            "claim_id": result.claim_id,
            "supplement_schema": "legacy_aggregate" if result.is_legacy else "main_summary",
            "supplement_activity_conflict": any(
                d.get("field") == "supplement_activity" for d in result.discrepancies
            ),
            "extraction_status": result.status,
            "baseline_status": result.baseline.status,
            "supplement_status": result.supplement.status,
        }
        for part, prefix in (
            (result.baseline, "baseline"),
            (result.supplement, "supplement_mechanism"),
        ):
            if part.features is not None and part.status in {"success", "skipped"}:
                if prefix == "supplement_mechanism" and result.is_legacy:
                    # Never reinterpret aggregate findings as findings about the main request.
                    row.update(
                        pd.json_normalize([part.features.aggregate], sep="__")
                        .add_prefix("legacy_supplement__")
                        .iloc[0]
                        .to_dict()
                    )
                    continue
                row.update(
                    prepare_flat_dataframe(part.features, column_prefix=prefix, drop_text=drop_text)
                    .iloc[0]
                    .to_dict()
                )
        rows.append(row)
    features = (
        pd.DataFrame(rows)
        if rows
        else pd.DataFrame(
            columns=[
                "claim_id",
                "supplement_schema",
                "supplement_activity_conflict",
                "extraction_status",
                "baseline_status",
                "supplement_status",
            ]
        )
    )
    validate_claim_ids(features)
    if set(features.claim_id) - set(metadata.claim_id):
        raise ValueError("Extraction result has no matching metadata")
    if (set(features) & set(metadata)) - {"claim_id"}:
        raise ValueError("Metadata collides with extracted feature columns")
    joined = metadata.merge(features, on="claim_id", how="left", validate="one_to_one")
    for col in ("extraction_status", "baseline_status", "supplement_status"):
        joined[col] = joined[col].fillna("not_extracted")
    joined["supplement_activity_conflict"] = joined.supplement_activity_conflict.astype("boolean")
    absent = {
        r["field"]: pd.Series(pd.NA, index=joined.index)
        for r in dictionary
        if r["field"] not in joined and not (drop_text and r["pandas_kind"] == "text")
    }
    joined = pd.concat([joined, pd.DataFrame(absent, index=joined.index)], axis=1)
    for row in dictionary:
        col, kind = row["field"], row["pandas_kind"]
        if col not in joined:
            continue
        if kind == "indicator":
            joined[col] = joined[col].astype("boolean")
        elif kind in {"count", "number"}:
            joined[col] = pd.to_numeric(joined[col]).astype(
                "Int64" if kind == "count" else "Float64"
            )
        elif kind == "date":
            joined[col] = pd.to_datetime(joined[col])
        elif kind in {"category", "text"}:
            joined[col] = joined[col].astype("string")
    joined = derive_outcomes(joined)
    # Analysis uses system amounts; original extracted values remain available for QA.
    joined["supplement_mechanism__financials__supplement_pct_of_initial_estimate"] = (
        joined.supplement_ratio
    )
    from .derived import derive_claim_features

    return derive_claim_features(joined)
