# Services Developer Notes

## Dataset Curation

Dataset candidates can enter a draft population from two places:

- completed application reviews in the app database
- code-owned sources backed by developer-written SQL queries and Python mapping helpers

`DatasetRepository` remains the public service import:

```python
from app.services.datasets import DatasetRepository
```

The implementation is split by responsibility:

- `app/services/datasets/repository.py` owns persistence and public dataset operations.
- `app/services/datasets/sources.py` owns code-owned source definitions and fetch dispatch.
- `app/services/datasets/clustering.py` owns vectorization, clustering, and sampling helpers.
- `app/services/datasets/serialization.py` owns text shaping for dataset candidates.

## Adding Code-Owned Sources

Code-owned sources are named backend fetchers. They are usually backed by a hand-written SQL or
Snowflake query plus a Python mapper. The UI does not expose freeform SQL; users choose one of the
registered sources, preview rows, select rows, and add them to the candidate pool.

The source boundary is `CanonicalDatasetCandidate` in `app/schemas/datasets.py`. A helper can do
any query or conversion work internally, but it must return:

```python
list[CanonicalDatasetCandidate]
```

The template source lives in `app/services/datasets/sources.py`:

```python
def fetch_from_example_code_owned_query(
    *,
    catalog: FormCatalog,
    form_id: str,
    form_version: str,
    params: dict[str, Any],
) -> list[CanonicalDatasetCandidate]:
    ...
```

To add a real source:

1. Add a fetch helper that returns `list[CanonicalDatasetCandidate]`.
2. Add a `DatasetSourceDefinition` with a stable `id`, label, kind, description, and params schema.
3. Add the definition to `CODE_OWNED_SOURCES`.
4. Dispatch to the helper from `fetch_source_candidates`.
5. Add a focused test that lists the source, previews rows, adds selected rows, and verifies
   published metadata.

## Candidate Contract

Every candidate needs a stable source identity, claim metadata, input/instructions for future eval
runs, and at least one reference result:

```python
CanonicalDatasetCandidate(
    source_key="example_code_owned_query",
    source_kind="external_named_query",
    source_label="Example Code-Owned Query",
    source_record_id="stable-row-id-from-source",
    claim_number="CLAIM-123",
    effective_date="2026-05-31",
    instructions="Review the source packet.",
    input={"claim_number": "CLAIM-123"},
    references=[
        DatasetReference(
            reference_kind="R2",
            result=audit_result,
            reviewer="source-system-or-reviewer",
            source_metadata={"external_review_id": "abc-123"},
        )
    ],
    metadata={"external_review_id": "abc-123"},
    tags=["code-owned"],
)
```

Important rules:

- `source_record_id` must be stable across preview and add.
- Reference results must match the selected registered form: `form_id`, `form_version`, and
  `form_kind`.
- Candidates must include at least one reference result before they can be added or published.
- Prefer `R2` when available. `R1` plus `R2` is supported when both references are useful.
- Put source-system IDs and query details in `metadata` or reference `source_metadata`; these are
  preserved into published eval case metadata.

## What Happens After Add

Once candidates are added to a draft population, the generic dataset flow takes over:

- dedupe is based on source identity plus reference payloads
- candidates can be included or excluded manually
- clustering and sampling annotate candidates
- publishing writes immutable records to `eval_datasets`, `eval_cases`, and `eval_ground_truths`
- Home, Dashboard, Evaluation, optimization, and chat-selected-row SQL context can consume the
  published dataset
