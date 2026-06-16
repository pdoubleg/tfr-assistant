from __future__ import annotations

import random
from collections import Counter
from collections.abc import Hashable
from dataclasses import dataclass

from gepa.core.data_loader import DataLoader
from gepa.core.state import GEPAState

from app.models.audit import AuditResult
from app.services.optimization.metrics import select_references
from app.services.optimization.models import OptimizationDataInstance


@dataclass(frozen=True)
class AuditBatchProfile:
    outcome: str | None
    question_answers: tuple[tuple[str, str], ...]


class AuditBalancedBatchSampler:
    """Outcome-first minibatch sampler for structured audit optimization."""

    def __init__(
        self,
        *,
        minibatch_size: int,
        reference_policy: str,
        question_ids: tuple[str, ...] = ("Q1", "Q2", "Q3"),
        rng: random.Random | None = None,
    ) -> None:
        if minibatch_size < 1:
            raise ValueError("minibatch_size must be at least 1.")
        self.minibatch_size = minibatch_size
        self.reference_policy = reference_policy
        self.question_ids = question_ids
        self.rng = rng or random.Random(0)
        self._profiles_by_id: dict[Hashable, AuditBatchProfile] = {}
        self._available_question_values: dict[str, set[str]] = {}
        self._last_ids: tuple[Hashable, ...] = ()
        self._usage: Counter[Hashable] = Counter()
        self._tie_breakers: dict[Hashable, float] = {}

    def next_minibatch_ids(
        self,
        loader: DataLoader[Hashable, OptimizationDataInstance],
        state: GEPAState,
    ) -> list[Hashable]:
        all_ids = list(loader.all_ids())
        if not all_ids:
            raise ValueError("Cannot sample a minibatch from an empty loader.")

        self._refresh_profiles(loader, all_ids)
        selected: list[Hashable] = []
        selected_set: set[Hashable] = set()

        outcome_groups = self._outcome_groups(all_ids)
        outcome_labels = self._ordered_outcome_labels(outcome_groups, state)
        if len(outcome_labels) > 1:
            for outcome in outcome_labels[: self.minibatch_size]:
                candidate_id = self._best_candidate(
                    outcome_groups[outcome],
                    selected_set,
                    selected,
                    outcome_weight=0,
                )
                if candidate_id is not None:
                    selected.append(candidate_id)
                    selected_set.add(candidate_id)

        target_unique = min(self.minibatch_size, len(all_ids))
        while len(selected) < target_unique:
            candidate_id = self._best_candidate(
                all_ids,
                selected_set,
                selected,
                outcome_weight=5,
            )
            if candidate_id is None:
                break
            selected.append(candidate_id)
            selected_set.add(candidate_id)

        while len(selected) < self.minibatch_size:
            candidate_id = self._least_used_id(all_ids, selected)
            selected.append(candidate_id)

        self._usage.update(selected)
        return selected

    def _refresh_profiles(
        self,
        loader: DataLoader[Hashable, OptimizationDataInstance],
        all_ids: list[Hashable],
    ) -> None:
        ids_key = tuple(all_ids)
        if ids_key == self._last_ids and self._profiles_by_id:
            return

        self._last_ids = ids_key
        self._profiles_by_id = {}
        self._available_question_values = {question_id: set() for question_id in self.question_ids}
        self._tie_breakers = {item_id: self.rng.random() for item_id in all_ids}
        instances = loader.fetch(all_ids)

        for item_id, instance in zip(all_ids, instances, strict=True):
            profile = self._profile_for_instance(instance)
            self._profiles_by_id[item_id] = profile
            for question_id, answer in profile.question_answers:
                self._available_question_values.setdefault(question_id, set()).add(answer)

        self._usage = Counter({item_id: self._usage[item_id] for item_id in all_ids})

    def _profile_for_instance(self, instance: OptimizationDataInstance) -> AuditBatchProfile:
        references = [
            result for _, result in select_references(instance.references, self.reference_policy)
        ]
        outcome = _majority([reference.overall_outcome for reference in references])
        question_answers: list[tuple[str, str]] = []
        for question_id in self.question_ids:
            answer = _majority(
                [
                    answer
                    for reference in references
                    if (answer := _question_answer(reference, question_id)) is not None
                ]
            )
            if answer is not None:
                question_answers.append((question_id, answer))
        return AuditBatchProfile(outcome=outcome, question_answers=tuple(question_answers))

    def _outcome_groups(self, all_ids: list[Hashable]) -> dict[str, list[Hashable]]:
        groups: dict[str, list[Hashable]] = {}
        for item_id in all_ids:
            outcome = self._profiles_by_id[item_id].outcome
            if outcome:
                groups.setdefault(outcome, []).append(item_id)
        return groups

    def _ordered_outcome_labels(
        self,
        outcome_groups: dict[str, list[Hashable]],
        state: GEPAState,
    ) -> list[str]:
        labels = sorted(outcome_groups)
        if not labels:
            return []
        offset = int(getattr(state, "i", 0) or 0) % len(labels)
        return labels[offset:] + labels[:offset]

    def _best_candidate(
        self,
        candidate_ids: list[Hashable],
        selected_set: set[Hashable],
        selected: list[Hashable],
        *,
        outcome_weight: int,
    ) -> Hashable | None:
        available = [item_id for item_id in candidate_ids if item_id not in selected_set]
        if not available:
            return None
        selected_outcomes = {
            profile.outcome
            for item_id in selected
            if (profile := self._profiles_by_id[item_id]).outcome
        }
        selected_question_values: dict[str, set[str]] = {}
        for item_id in selected:
            for question_id, answer in self._profiles_by_id[item_id].question_answers:
                selected_question_values.setdefault(question_id, set()).add(answer)

        def ranking(item_id: Hashable) -> tuple[int, int, int, float]:
            profile = self._profiles_by_id[item_id]
            outcome_gain = (
                outcome_weight
                if profile.outcome is not None and profile.outcome not in selected_outcomes
                else 0
            )
            question_gain = self._question_gain(profile, selected_question_values)
            return (
                -(outcome_gain + question_gain),
                self._usage[item_id],
                selected.count(item_id),
                self._tie_breakers.get(item_id, 0.0),
            )

        return min(available, key=ranking)

    def _question_gain(
        self,
        profile: AuditBatchProfile,
        selected_question_values: dict[str, set[str]],
    ) -> int:
        gain = 0
        for question_id, answer in profile.question_answers:
            if len(self._available_question_values.get(question_id, set())) < 2:
                continue
            if answer not in selected_question_values.get(question_id, set()):
                gain += 1
        return gain

    def _least_used_id(self, all_ids: list[Hashable], selected: list[Hashable]) -> Hashable:
        def ranking(item_id: Hashable) -> tuple[int, int, float]:
            return (
                self._usage[item_id],
                selected.count(item_id),
                self._tie_breakers.get(item_id, 0.0),
            )

        return min(all_ids, key=ranking)


def _majority(values: list[str | None]) -> str | None:
    counts = Counter(value for value in values if value)
    if not counts:
        return None
    return min(counts, key=lambda value: (-counts[value], value))


def _question_answer(result: AuditResult, question_id: str) -> str | None:
    for question in result.questions:
        if question.id == question_id:
            return question.answer
    return None
