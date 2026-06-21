from __future__ import annotations

import re
from collections.abc import Iterable

from .models import ExtractedItem, TextChunk

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9\-_/]*", re.I)

FOCUS_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "hail": (
        "hail",
        "wind",
        "storm",
        "roof",
        "siding",
        "cosmetic",
        "marring",
        "denting",
        "matching",
        "replacement cost",
        "actual cash value",
        "acv",
        "rcv",
        "depreciation",
        "wear and tear",
        "exclusion",
        "deductible",
        "ordinance or law",
        "valuation",
        "loss settlement",
        "protective safeguard",
    ),
    "wind": (
        "wind",
        "windstorm",
        "hail",
        "storm",
        "roof",
        "siding",
        "cosmetic",
        "deductible",
        "valuation",
        "loss settlement",
    ),
    "water": (
        "water",
        "flood",
        "sewer",
        "drain",
        "backup",
        "surface water",
        "rain",
        "leak",
        "mold",
        "fungus",
        "rot",
        "wear and tear",
        "deductible",
    ),
    "fire": (
        "fire",
        "smoke",
        "explosion",
        "sprinkler",
        "protective safeguard",
        "ordinance or law",
        "debris removal",
        "business income",
        "extra expense",
    ),
    "theft": (
        "theft",
        "burglary",
        "dishonesty",
        "money",
        "securities",
        "inventory",
        "entrustment",
        "mysterious disappearance",
        "police report",
    ),
    "business income": (
        "business income",
        "business interruption",
        "extra expense",
        "period of restoration",
        "civil authority",
        "dependent property",
        "waiting period",
        "suspension",
        "operations",
    ),
    "auto": (
        "auto",
        "vehicle",
        "hired auto",
        "non-owned auto",
        "physical damage",
        "collision",
        "comprehensive",
        "symbol",
        "covered auto",
    ),
    "liability": (
        "liability",
        "bodily injury",
        "property damage",
        "occurrence",
        "advertising injury",
        "personal injury",
        "insured contract",
        "additional insured",
        "exclusion",
        "defense",
    ),
}

GENERAL_COVERAGE_TERMS: tuple[str, ...] = (
    "coverage",
    "covered",
    "exclusion",
    "exception",
    "limit",
    "sublimit",
    "deductible",
    "retention",
    "condition",
    "definition",
    "endorsement",
    "amend",
    "replace",
    "delete",
    "form",
    "schedule",
    "valuation",
    "loss payment",
    "loss settlement",
    "actual cash value",
    "replacement cost",
    "depreciation",
    "duties in the event",
    "notice of loss",
    "proof of loss",
    "period of restoration",
)


def normalize_terms(text: str) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for term in _WORD_RE.findall(text.lower()):
        if len(term) > 2 and term not in seen:
            seen.add(term)
            terms.append(term)
    return terms


def infer_focus_terms(focus_area: str | None) -> list[str]:
    if not focus_area:
        return []
    text = focus_area.lower()
    terms = normalize_terms(text)
    expanded: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        normalized = term.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            expanded.append(normalized)

    for term in terms:
        add(term)
    for key, extras in FOCUS_EXPANSIONS.items():
        if key in text:
            for term in extras:
                add(term)
    for term in GENERAL_COVERAGE_TERMS:
        add(term)
    return expanded


def _contains(text: str, term: str) -> bool:
    if " " in term:
        return term in text
    return bool(re.search(rf"\b{re.escape(term)}\b", text))


def focus_score(text: str, focus_area: str | None) -> int:
    if not focus_area:
        return 1
    haystack = text.lower()
    return sum(1 for term in infer_focus_terms(focus_area) if _contains(haystack, term))


def select_chunks(chunks: list[TextChunk], focus_area: str | None) -> tuple[list[TextChunk], int]:
    if not focus_area:
        return chunks, 0

    selected: list[TextChunk] = []
    skipped = 0
    first_chunk_by_doc: set[str] = set()
    for chunk in chunks:
        is_first_for_doc = chunk.doc_id not in first_chunk_by_doc
        first_chunk_by_doc.add(chunk.doc_id)
        score = focus_score(f"{chunk.file}\n{chunk.text}", focus_area)
        if score > 0 or is_first_for_doc:
            selected.append(chunk)
        else:
            skipped += 1
    return selected, skipped


def relevance_rank(value: str) -> int:
    return {"direct": 0, "potential": 1, "context": 2, "not_relevant": 3}.get(value, 4)


def item_sort_key(item: ExtractedItem) -> tuple[int, int, str]:
    type_rank = {
        "coverage": 0,
        "limit": 1,
        "deductible": 2,
        "exclusion": 3,
        "condition": 4,
        "definition": 5,
        "endorsement": 6,
        "form": 7,
        "schedule": 8,
        "other": 9,
    }.get(item.item_type, 9)
    return (relevance_rank(item.relevance), type_rank, item.title.lower())


def dedupe_items(items: Iterable[ExtractedItem]) -> list[ExtractedItem]:
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[ExtractedItem] = []
    for item in items:
        quote = item.evidence[0].quote[:120].lower() if item.evidence else ""
        key = (
            item.item_type,
            item.title.strip().lower(),
            (item.value or "").strip().lower(),
            quote,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return sorted(deduped, key=item_sort_key)
