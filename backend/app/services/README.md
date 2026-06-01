# Services Developer Notes

## Adding Code-Owned Dataset Sources

The Datasets page can populate candidate rows from code-owned sources. These are named backend fetchers, usually backed by a hand-written SQL/Snowflake query plus Python mapping helpers. The UI does not expose freeform SQL; users select a registered form, select one of the sources available for that form, load preview rows, select rows, and add them to the candidate pool.

The source boundary is `CanonicalDatasetCandidate` in `app/schemas/datasets.py`. Your helper can do any query or conversion work internally, but it should return:

```python
list[CanonicalDatasetCandidate]
```

### Candidate Contract

Each candidate needs a stable source identity, claim metadata, the input/instructions that should be used for future eval runs, and at least one reference result:

```python
CanonicalDatasetCandidate(
    source_key="sister_app_ready_query",
    source_kind="external_named_query",
    source_label="Sister App Ready Query",
    source_record_id="stable-row-id-from-source",
    claim_number="CLAIM-123",
    effective_date="2026-05-31",
    instructions="Review the sister-app audit packet.",
    input={
        "claim_number": "CLAIM-123",
        "packet_summary": "...",
    },
    references=[
        DatasetReference(
            reference_kind="R2",
            result=audit_result,
            reviewer="reviewer@example.com",
            source_metadata={
                "sister_review_id": "abc-123",
                "query_version": "v1",
            },
        )
    ],
    metadata={
        "sister_review_id": "abc-123",
        "snowflake_query_id": "01b...",
        "source_batch": "2026-05-prod",
    },
    tags=["sister-app", "prod"],
)
```

`result` must be an `AuditResult`: either `AuditFormResult` or `AuditFormWithFinancialsResult` from `app/models/audit.py`. If your helper starts from dictionaries, parse them into the audit contract before creating candidates.

Important rules:

- `source_record_id` must be stable across preview and add. The backend reruns the fetcher when adding selected rows, then filters by `source_record_id`.
- Reference results must match the selected registered form: `form_id`, `form_version`, and `form_kind`.
- Candidates must include at least one reference result before they can be added or published.
- Prefer `R2` when available. `R1` plus `R2` is supported when both references are useful.
- Put source-system IDs and query details in `metadata` and/or reference `source_metadata`; these are preserved into published eval case metadata.

### Wiring A New Source

Most wiring lives in `DatasetSourceRegistry` inside `app/services/datasets.py`.

1. Add or import your helper. Keep Snowflake-specific code behind the helper, not spread through the generic dataset service.

```python
def fetch_sister_app_ready_candidates(
    *,
    form_id: str,
    form_version: str,
    params: dict[str, Any],
) -> list[CanonicalDatasetCandidate]:
    # Run query, convert rows, validate/map results, return candidates.
    ...
```

2. Add a `DatasetSourceDefinition`.

```python
sister_app_ready_source = DatasetSourceDefinition(
    id="sister_app_ready_query",
    label="Sister App Ready Query",
    kind="external_named_query",
    description="Fetches completed sister-app audit rows from the approved query.",
)
```

3. Return the source from `list_for_form` only when it applies to the selected form/version.

```python
def list_for_form(self, form_id: str, form_version: str) -> list[DatasetSourceRecord]:
    self.catalog.get_form(form_id, form_version)
    sources = [self.placeholder_source]
    if form_id == "tfr_default" and form_version == "v0.1":
        sources.append(self.sister_app_ready_source)
    return [
        DatasetSourceRecord(
            id=source.id,
            label=source.label,
            kind=source.kind,
            form_id=form_id,
            form_versions=[form_version],
            description=source.description,
            params_schema={
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100}
                },
            },
        )
        for source in sources
    ]
```

4. Dispatch from `fetch`.

```python
def fetch(
    self,
    source_id: str,
    *,
    form_id: str,
    form_version: str,
    params: dict[str, Any] | None = None,
) -> list[CanonicalDatasetCandidate]:
    if source_id == self.placeholder_source.id:
        ...
    if source_id == self.sister_app_ready_source.id:
        return fetch_sister_app_ready_candidates(
            form_id=form_id,
            form_version=form_version,
            params=params or {},
        )
    raise KeyError(f"Unknown dataset source: {source_id}")
```

5. Add a focused backend test similar to `test_code_owned_source_can_preview_and_add_selected_rows` in `tests/test_dataset_curation.py`.

The test should verify:

- The source appears for the expected form and not for unrelated forms when applicable.
- Preview returns stable `source_record_id` values.
- Adding selected preview rows creates the expected candidates.
- Published rows preserve source metadata.

### UI Params

The current Datasets page passes a simple `count` parameter for code-owned sources. If a source needs more controls, such as date range, status, region, or query variant, extend the Code-Owned Source panel in `frontend/app/datasets/page.tsx` and pass those values through the existing `params` object.

Keep the source id stable and version meaningful query changes in either the source id, metadata, or both. For example:

- `sister_app_ready_query_v1`
- `sister_app_high_dollar_v1`
- `sister_app_denials_v2`

### What Happens After Add

Once candidates are added to the pool, the generic dataset flow takes over:

- dedupe is based on source identity plus reference payloads
- candidates can be included/excluded manually
- clustering and sampling can annotate candidates
- publishing writes immutable records to `eval_datasets`, `eval_cases`, and `eval_ground_truths`
- Home, Dashboard, Evaluation, GEPA, and chat-selected-row SQL context can consume the published dataset
