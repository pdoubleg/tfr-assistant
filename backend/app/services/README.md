# Services Developer Notes

## Dataset Curation

Dataset candidates now enter the curation flow from completed application reviews in the app
database. `DatasetRepository` remains the public service import:

```python
from app.services.datasets import DatasetRepository
```

The implementation is split by responsibility:

- `app/services/datasets/repository.py` owns persistence and the public dataset operations.
- `app/services/datasets/clustering.py` owns vectorization, clustering, and sampling helpers.
- `app/services/datasets/serialization.py` owns text shaping for dataset candidates.

The app-DB source maps completed `AuditReviewORM` rows into `CanonicalDatasetCandidate` records.
Each mapped candidate keeps the source review/version ids in both the candidate input and metadata
so published eval rows remain traceable back to the originating review.

## Candidate Contract

Every candidate needs a stable source identity, claim metadata, input/instructions for future eval
runs, and at least one reference result:

```python
CanonicalDatasetCandidate(
    source_key="app_db_reviews",
    source_kind="app_db_reviews",
    source_label="Application DB Reviews",
    source_record_id=f"{review.id}:{version.id}",
    claim_number="CLAIM-123",
    effective_date="2026-05-31",
    instructions="Review the completed audit packet.",
    input={
        "claim_number": "CLAIM-123",
        "source_review_id": review.id,
        "source_result_version_id": version.id,
    },
    references=[
        DatasetReference(
            reference_kind="R2",
            result=audit_result,
            reviewer="app-db",
            source_metadata={
                "review_id": review.id,
                "result_version_id": version.id,
            },
        )
    ],
    metadata={"review_id": review.id},
    tags=["app-db", review.source],
)
```

Important rules:

- `source_record_id` must stay stable for a given review/result version pair.
- Reference results must match the selected registered form: `form_id`, `form_version`, and
  `form_kind`.
- Candidates must include at least one reference result before they can be added or published.
- Feedback metadata is optional, but when included it is preserved into published eval case metadata.

## What Happens After Add

Once reviews are added to a draft population, the generic dataset flow takes over:

- dedupe is based on source identity plus reference payloads
- candidates can be included or excluded manually
- clustering and sampling annotate candidates
- publishing writes immutable records to `eval_datasets`, `eval_cases`, and `eval_ground_truths`
- Home, Dashboard, Evaluation, optimization, and chat-selected-row SQL context can consume the
  published dataset
