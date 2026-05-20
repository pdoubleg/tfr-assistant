from __future__ import annotations

import random

from app.schemas.optimizations import OptimizationCaseRecord, OptimizationCaseSplit


def apply_split_helper(
    cases: list[OptimizationCaseRecord],
    *,
    mode: str,
    seed: int = 0,
) -> list[OptimizationCaseSplit]:
    rng = random.Random(seed)
    ordered = list(cases)
    if mode in {"stratified_outcome", "stratified_outcome_issues"}:
        groups: dict[str, list[OptimizationCaseRecord]] = {}
        for case in ordered:
            issue_bucket = "multi" if case.issue_count > 1 else str(case.issue_count)
            key = case.outcome if mode == "stratified_outcome" else f"{case.outcome}:{issue_bucket}"
            groups.setdefault(key, []).append(case)
        ordered = []
        for group in groups.values():
            rng.shuffle(group)
        while any(groups.values()):
            for key in sorted(groups):
                if groups[key]:
                    ordered.append(groups[key].pop())
    else:
        rng.shuffle(ordered)
    total = len(ordered)
    train_cut = max(1, round(total * 0.6))
    val_cut = min(total, train_cut + max(1, round(total * 0.2)))
    splits: list[OptimizationCaseSplit] = []
    for index, case in enumerate(ordered):
        split = "train" if index < train_cut else "val" if index < val_cut else "test"
        splits.append(OptimizationCaseSplit(case_id=case.case_id, split=split))  # type: ignore[arg-type]
    return splits
