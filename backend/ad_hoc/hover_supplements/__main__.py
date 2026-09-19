"""Run from backend: python -m ad_hoc.hover_supplements --help."""

import argparse
import asyncio
import json
from pathlib import Path

import pandas as pd

from app.core.llm import LLMModelAPI, LLMModelConfig

from .contracts import ClaimBundle, ExtractionResult
from .modeling import ResearchConfig
from .runner import extract_batch, run_analysis, write_report


def read_records(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    if text.lstrip().startswith("["):
        return json.loads(text)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Standalone Hover supplement research")
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract", help="Extract JSON/JSONL claim bundles")
    extract.add_argument("input", type=Path)
    extract.add_argument("output", type=Path)
    extract.add_argument("--checkpoints", type=Path)
    extract.add_argument("--concurrency", type=int, default=1)
    extract.add_argument(
        "--model-config", type=Path, help="Existing LLMModelConfig JSON; no credentials"
    )
    analyze = commands.add_parser("analyze", help="Rerun research without LLM calls")
    analyze.add_argument("population", type=Path, help="Structured population CSV or JSON/JSONL")
    analyze.add_argument("output", type=Path)
    analyze.add_argument("--extractions", type=Path)
    analyze.add_argument(
        "--audited-metadata", type=Path, help="Sample metadata including sampling_weight"
    )
    analyze.add_argument("--config", type=Path, help="ResearchConfig JSON")
    analyze.add_argument("--bootstrap", type=int, default=None)
    demo = commands.add_parser("demo", help="Fictional end-to-end workflow; no credentials")
    demo.add_argument("output", type=Path)
    demo.add_argument("--claims", type=int, default=400)
    demo.add_argument("--bootstrap", type=int, default=500)
    args = parser.parse_args(argv)
    if args.command == "extract":
        bundles = [ClaimBundle.model_validate(x) for x in read_records(args.input)]
        if args.model_config:
            config = LLMModelConfig.model_validate_json(
                args.model_config.read_text(encoding="utf-8")
            )
        else:
            from app.core.config import get_settings

            config = get_settings().audit_llm_config()
        results = asyncio.run(
            extract_batch(
                bundles, config, checkpoint_dir=args.checkpoints, concurrency=args.concurrency
            )
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            "\n".join(r.model_dump_json() for r in results) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "success": sum(r.status == "success" for r in results),
                    "failed": sum(r.status == "failed" for r in results),
                }
            )
        )
        return 1 if any(r.status == "failed" for r in results) else 0
    if args.command == "demo":
        from .synthetic import synthetic_bundles

        bundles = synthetic_bundles(args.claims)
        config = LLMModelConfig(model_name="test", api=LLMModelAPI.TEST)
        results = asyncio.run(
            extract_batch(bundles, config, checkpoint_dir=args.output / "checkpoints", demo=True)
        )
        population = pd.DataFrame([b.metadata() for b in bundles])
        research_config = ResearchConfig(
            tier="enriched",
            covariates=[
                "peril",
                "baseline__property_complexity__stories",
                "baseline__damage__damage_extent",
            ],
            pretreatment_rationale={
                "baseline__property_complexity__stories": "Fictional property predates capture.",
                "baseline__damage__damage_extent": "Fictional damage generated before capture.",
            },
            bootstrap_replicates=args.bootstrap,
        )
        report = run_analysis(population, results=results, config=research_config)
        args.output.mkdir(parents=True, exist_ok=True)
        population.to_csv(args.output / "population.csv", index=False)
        (args.output / "bundles.jsonl").write_text(
            "\n".join(b.model_dump_json() for b in bundles), encoding="utf-8"
        )
        (args.output / "extractions.jsonl").write_text(
            "\n".join(r.model_dump_json() for r in results), encoding="utf-8"
        )
    else:

        def read_frame(path):
            return (
                pd.read_csv(path, dtype={"claim_id": str})
                if path.suffix == ".csv"
                else pd.DataFrame(read_records(path))
            )

        population = read_frame(args.population)
        results = (
            [ExtractionResult.model_validate(x) for x in read_records(args.extractions)]
            if args.extractions
            else []
        )
        metadata = read_frame(args.audited_metadata) if args.audited_metadata else None
        config_data = json.loads(args.config.read_text(encoding="utf-8")) if args.config else {}
        if args.bootstrap is not None:
            config_data["bootstrap_replicates"] = args.bootstrap
        research_config = ResearchConfig(**config_data)
        report = run_analysis(
            population, results=results, audited_metadata=metadata, config=research_config
        )
    write_report(report, args.output)
    print(f"Research artifacts: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
