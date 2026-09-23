"""Local checkpoints, independent analysis reruns, and report artifacts."""

import asyncio
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from .agents import BASELINE_INSTRUCTIONS, SUPPLEMENT_INSTRUCTIONS, extract_claim
from .analysis import (
    decompose_dollar_difference,
    derived_analysis,
    diagnostics,
    mechanism_analysis,
    representative_claims,
    scorecards,
)
from .contracts import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    BaselineOutput,
    ExtractionResult,
    SupplementOutput,
)
from .dataframes import build_feature_table, feature_dictionary
from .explainability import explanation_evidence
from .modeling import ResearchConfig, fit_statistical_models, run_predictive_research


def cache_key(bundle, model_config, *, demo=False):
    payload = {
        "bundle": bundle.model_dump(mode="json"),
        "model": model_config.model_dump(mode="json"),
        "schema_version": SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "prompts": [BASELINE_INSTRUCTIONS, SUPPLEMENT_INSTRUCTIONS],
        "schemas": [BaselineOutput.model_json_schema(), SupplementOutput.model_json_schema()],
        "demo": demo,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


async def extract_batch(bundles, model_config, *, checkpoint_dir=None, concurrency=1, demo=False):
    if concurrency < 1:
        raise ValueError("concurrency must be positive")
    if len({b.claim_id for b in bundles}) != len(bundles):
        raise ValueError("Duplicate claim IDs in batch")
    directory = Path(checkpoint_dir) if checkpoint_dir else None
    if directory:
        directory.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(concurrency)

    async def one(bundle):
        key = cache_key(bundle, model_config, demo=demo)
        path = directory / f"{key}.json" if directory else None
        if path and path.exists():
            try:
                cached = ExtractionResult.model_validate_json(path.read_text(encoding="utf-8"))
                if (
                    cached.cache_key == key
                    and cached.claim_id == bundle.claim_id
                    and cached.status == "success"
                ):
                    return cached
            except (ValueError, OSError):
                pass  # Invalid/incomplete checkpoints are not successful extractions.
        async with semaphore:
            kwargs = {}
            if demo:
                from .synthetic import synthetic_models

                baseline, supplement = synthetic_models(bundle)
                kwargs = {"baseline_model": baseline, "supplement_model": supplement}
            result = await extract_claim(bundle, model_config, **kwargs)
            result.cache_key = key
            if path:
                temporary = path.with_suffix(".tmp")
                temporary.write_text(result.model_dump_json(indent=2), encoding="utf-8")
                temporary.replace(path)
            return result

    return await asyncio.gather(*(one(bundle) for bundle in bundles))


def run_analysis(population, *, results=(), audited_metadata=None, config=None):
    """Population scorecards always use the full structured frame; LLM analyses use audited data."""
    config = config or ResearchConfig()
    feature_table = build_feature_table(
        results, audited_metadata if audited_metadata is not None else population, drop_text=False
    )
    # Do not inflate the audited sample by silently using unaudited population rows.
    audited = feature_table[feature_table.extraction_status.ne("not_extracted")].copy()
    tables = {
        "population_scorecard": scorecards(population),
        "feature_table": feature_table,
        "audited_scorecard": scorecards(audited),
        "feature_dictionary": feature_dictionary(include_derived=True),
        "representative_claims": representative_claims(results),
        **{f"population_{k}": v for k, v in diagnostics(population).items()},
        **{f"audit_{k}": v for k, v in diagnostics(feature_table).items()},
        **mechanism_analysis(audited),
        **derived_analysis(population, audited),
    }
    structured_config = ResearchConfig(
        seed=config.seed, bootstrap_replicates=config.bootstrap_replicates
    )
    source = audited if any(c.startswith("baseline__") for c in config.covariates) else population
    stats = fit_statistical_models(population, structured_config)
    selected = fit_statistical_models(source, config) if config != structured_config else stats
    predictive = run_predictive_research(source, config)
    if predictive.get("explanations", {}).get("status") == "success":
        predictive["explanations"]["evidence"] = explanation_evidence(
            predictive["explanations"], results
        )
    return {
        "tables": tables,
        "supplement_schema_version": SCHEMA_VERSION,
        "synthetic": bool(results)
        and all(
            r.baseline.features is not None
            and (r.baseline.features.baseline_summary or "").startswith("Fictional fixture")
            for r in results
        ),
        "population_decomposition": decompose_dollar_difference(population),
        "structured_model": stats,
        "selected_model": selected,
        "predictive": predictive,
        "configuration": asdict(config),
    }


def _json_safe(value):
    if isinstance(value, pd.DataFrame):
        return json.loads(value.to_json(orient="records", date_format="iso"))
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items() if k not in {"classifier", "regressor"}}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, float) and not pd.notna(value):
        return None
    if hasattr(value, "item"):
        return _json_safe(value.item())
    return value


def write_report(report, output_dir):
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    def write_tables(value, prefix=""):
        if isinstance(value, pd.DataFrame):
            value.to_csv(directory / f"{prefix}.csv", index=False)
        elif isinstance(value, dict):
            for key, child in value.items():
                write_tables(child, f"{prefix}_{key}".strip("_"))

    write_tables(report)
    (directory / "research.json").write_text(
        json.dumps(_json_safe(report), indent=2, allow_nan=False), encoding="utf-8"
    )
    lines = [
        "# Hover supplement research",
        "",
        "Adjusted associations, not causal effects.",
        "",
        "Approved additional dollars define incidence. Denied requests remain mechanism evidence.",
        "Associated dollars by avoidability category are not estimates of recoverable savings.",
        "Overlapping mechanism flags do not form an additive dollar decomposition.",
        "",
        "## Population scorecard",
        "",
        "```",
        report["tables"]["population_scorecard"].to_string(index=False),
        "```",
        "",
        "## Model status",
        "",
    ]
    for name in ("structured_model", "selected_model", "predictive"):
        model = report[name]
        detail = model.get("reason", model.get("interval_status", "held-out evaluation"))
        lines.append(f"- {name}: {model['status']}; {detail}")
    lines.extend(
        [
            "",
            "Inspect coverage, calendar coverage, missingness, "
            "and bootstrap failures before interpretation.",
            "Selection weights do not automatically correct extraction failures "
            "or unmeasured case-mix differences.",
            "Segments are exploratory. Inspect held-out cohort counts before comparing them.",
        ]
    )
    (directory / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    from .visualization import render_business_report

    render_business_report(report, directory)
    return directory
