"""Temporary CLI for manually exercising the review agent with prompt variants.

Example:
    uv run python -m app.test_agent \
        --prompt "Please run a TFR audit for this file." \
        --prompt "Create a fictitious example audit for demo purposes." \
        --questionnaire-path "data/form_catalog/tfr_default__v0.1.json" \
        --output-dir "data/tmp/review-agent-tests"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.agents.review_agent import run_file_review_agent

SAMPLE_PROMPTS: tuple[str, ...] = (
    "Please create a test review form with all No answers and a does not meet rating.",
    "Please create a test review form with all Yes answers and a meets rating.",
    "Create a fictitious example audit so I can inspect the output shape.",
)


@dataclass(slots=True)
class ReviewAgentTestArgs:
    """CLI arguments for the temporary review-agent runner."""

    prompts: list[str]
    claim_number: str
    effective_date: str
    instructions: str
    questionnaire_path: str
    tools: list[str]
    knowledge_docs: list[str]
    output_dir: Path | None


def parse_args(argv: Sequence[str] | None = None) -> ReviewAgentTestArgs:
    """Parse CLI arguments for the temporary review-agent runner.

    Args:
        argv: Optional argument list for tests or programmatic invocation.

    Returns:
        Parsed runner arguments.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Call the review agent with one or more prompts and print the "
            "structured AuditFormResult returned for each run."
        )
    )
    parser.add_argument(
        "--prompt",
        dest="prompts",
        action="append",
        default=None,
        help=(
            "Prompt to send to the review agent. Repeat this flag to compare "
            "multiple prompts. If omitted, three built-in sample prompts are used."
        ),
    )
    parser.add_argument(
        "--claim-number",
        default="",
        help="Optional claim number forwarded to the review agent.",
    )
    parser.add_argument(
        "--effective-date",
        default="",
        help="Optional effective date forwarded to the review agent.",
    )
    parser.add_argument(
        "--instructions",
        default="",
        help="Optional additional instructions appended to every prompt run.",
    )
    parser.add_argument(
        "--questionnaire-path",
        default="data/form_catalog/tfr_default__v0.1.json",
        help="Optional path to the questionnaire JSON file.",
    )
    parser.add_argument(
        "--tool",
        dest="tools",
        action="append",
        default=None,
        help="Optional form tool name to expose to the review agent. Repeat to pass multiple.",
    )
    parser.add_argument(
        "--knowledge-doc",
        dest="knowledge_docs",
        action="append",
        default=None,
        help="Optional knowledge document name or ID. Repeat to pass multiple.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/tmp/review-agent-tests",
        help="Optional directory where each prompt result will be saved as JSON.",
    )
    parsed = parser.parse_args(argv)

    # Default sample prompts make it easy to smoke test the runner with no arguments.
    prompts = parsed.prompts or list(SAMPLE_PROMPTS)
    output_dir = Path(parsed.output_dir) if parsed.output_dir else None
    return ReviewAgentTestArgs(
        prompts=prompts,
        claim_number=parsed.claim_number,
        effective_date=parsed.effective_date,
        instructions=parsed.instructions,
        questionnaire_path=parsed.questionnaire_path,
        tools=parsed.tools or [],
        knowledge_docs=parsed.knowledge_docs or [],
        output_dir=output_dir,
    )


def _write_result(output_dir: Path, prompt_index: int, result_json: str) -> Path:
    """Persist a single review-agent response to disk.

    Args:
        output_dir: Target directory for result files.
        prompt_index: One-based prompt index.
        result_json: Serialized `AuditFormResult`.

    Returns:
        Path to the saved JSON file.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"prompt_{prompt_index:02d}.json"
    output_path.write_text(result_json, encoding="utf-8")
    return output_path


async def run_prompts(args: ReviewAgentTestArgs) -> int:
    """Run the review agent sequentially for each requested prompt.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Process exit code. Returns `0` on success and `1` if any prompt fails.
    """

    failure_count = 0
    total_prompts = len(args.prompts)

    # Sequential execution keeps console output readable and avoids overlapping API calls.
    for index, prompt in enumerate(args.prompts, start=1):
        print(f"\n=== Prompt {index}/{total_prompts} ===")
        print(prompt)

        try:
            result = await run_file_review_agent(
                claim_number=args.claim_number,
                effective_date=args.effective_date,
                path_to_questionnaire=args.questionnaire_path,
                runtime_context="\n\n".join(part for part in [prompt, args.instructions] if part),
                tools=args.tools,
                knowledge_docs=args.knowledge_docs,
            )
        except Exception as exc:
            failure_count += 1
            print("Status: FAILED")
            print(str(exc))
            continue

        result_json = result.model_dump_json(indent=2)
        print("Status: OK")
        print(result_json)

        if args.output_dir is not None:
            output_path = _write_result(args.output_dir, index, result_json)
            print(f"Saved JSON: {output_path}")

    return 1 if failure_count else 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the temporary review-agent runner.

    Args:
        argv: Optional argument list for tests or programmatic invocation.

    Returns:
        Process exit code.
    """

    args = parse_args(argv)
    return asyncio.run(run_prompts(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
