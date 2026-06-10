import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import Base
from app.schemas.reviews import (
    BatchCreateRequest,
    BatchReviewInput,
    ReviewFinalization,
    ReviewGenerateRequest,
    ReviewUpdate,
)
from app.services.audit_generation import AuditGenerationService, BatchReviewGenerationService
from app.services.catalog import FormCatalog
from app.services.review_repository import ReviewRepository


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


@pytest.mark.anyio
async def test_batch_pause_resume_and_retry_failed_reviews(session):
    repository = ReviewRepository(session)
    batch = await repository.create_batch(
        total_count=3,
        input_json={"name": "Pilot", "form_id": "tfr_default", "form_version": "v0.3"},
    )
    await repository.create_review_placeholder(
        form_id="tfr_default",
        form_version="v0.3",
        source="batch",
        batch_id=batch.id,
        status="completed",
    )
    await repository.create_review_placeholder(
        form_id="tfr_default",
        form_version="v0.3",
        source="batch",
        batch_id=batch.id,
        status="failed",
    )
    await repository.create_review_placeholder(
        form_id="tfr_default",
        form_version="v0.3",
        source="batch",
        batch_id=batch.id,
        status="queued",
    )

    paused = await repository.pause_batch(batch.id)
    assert paused.status == "paused"
    assert paused.completed_count == 1
    assert paused.failed_count == 1
    assert paused.queued_count == 1
    assert paused.progress_percent == 66.7

    resumed = await repository.resume_batch(batch.id)
    assert resumed.status == "running"

    retrying = await repository.retry_failed_batch_reviews(batch.id)
    assert retrying.status == "running"
    assert retrying.completed_count == 1
    assert retrying.failed_count == 0
    assert retrying.queued_count == 2
    assert retrying.progress_percent == 33.3


@pytest.mark.anyio
async def test_batch_summary_tracks_review_volume_by_form(session):
    repository = ReviewRepository(session)
    batch = await repository.create_batch(
        total_count=2,
        input_json={"name": "Volume", "form_id": "water", "form_version": "v1"},
    )
    await repository.create_review_placeholder(
        form_id="water",
        form_version="v1",
        source="batch",
        batch_id=batch.id,
        status="completed",
    )
    await repository.create_review_placeholder(
        form_id="water",
        form_version="v1",
        source="batch",
        batch_id=batch.id,
        status="failed",
    )

    summary = await repository.batch_summary()

    assert summary.total_reviews == 2
    assert summary.completed_reviews == 1
    assert summary.failed_reviews == 1
    assert summary.form_volume[0].form_id == "water"
    assert summary.form_volume[0].total_count == 2


@pytest.mark.anyio
async def test_synthetic_batch_creates_synth_claims_and_source(session):
    service = BatchReviewGenerationService(session)
    batch = await service.create_batch(
        BatchCreateRequest(
            name="Synthetic pilot",
            form_id="tfr_default",
            form_version="v0.3",
            synthetic=True,
            synthetic_count=2,
            input_mode="synthetic",
            generation_prompt="Make both reviews Meets with all Yes answers.",
        )
    )
    reviews = await ReviewRepository(session).list_reviews(batch_id=batch.id)

    assert batch.source == "synthetic"
    assert len(reviews) == 2
    assert {review.source for review in reviews} == {"synthetic"}
    assert all(
        (review.input_json or {}).get("claim_number", "").startswith("SYNTH_") for review in reviews
    )
    assert all((review.input_json or {}).get("generation_prompt") for review in reviews)


@pytest.mark.anyio
async def test_normal_batch_keeps_generation_prompt_out_of_runtime_context(session):
    service = BatchReviewGenerationService(session)
    batch = await service.create_batch(
        BatchCreateRequest(
            name="Normal pilot",
            form_id="tfr_default",
            form_version="v0.3",
            generation_prompt="Legacy batch prompt.",
            items=[
                BatchReviewInput(
                    claim_number="CLAIM-001",
                    instructions="Legacy row instructions.",
                    prompt="Legacy row prompt.",
                    generation_prompt="Legacy row generation prompt.",
                )
            ],
        )
    )
    reviews = await ReviewRepository(session).list_reviews(batch_id=batch.id)
    input_json = reviews[0].input_json or {}

    assert input_json["prompt"] == ""
    assert input_json["instructions"] == ""
    assert input_json["generation_prompt"] == "Legacy row generation prompt."


@pytest.mark.anyio
async def test_manual_entry_batch_queues_manual_results_and_completes_without_agent(session):
    service = BatchReviewGenerationService(session)
    canonical = (
        FormCatalog(service.settings.form_catalog_dir)
        .get_form(
            "tfr_default",
            "v0.3",
        )
        .canonical.model_copy(deep=True)
    )

    batch = await service.create_batch(
        BatchCreateRequest(
            name="Manual entries",
            form_id="tfr_default",
            form_version="v0.3",
            input_mode="manual_entry",
            items=[
                BatchReviewInput(
                    claim_number="MANUAL-001",
                    effective_date="2026-05-18",
                    manual_result=canonical,
                )
            ],
        )
    )
    reviews = await ReviewRepository(session).list_reviews(batch_id=batch.id)

    assert batch.source == "manual_entry"
    assert len(reviews) == 1
    assert reviews[0].source == "manual_entry"
    assert reviews[0].status == "queued"
    assert (reviews[0].input_json or {}).get("manual_result")

    completed = await AuditGenerationService(session).generate_for_review(
        reviews[0].id,
        ReviewGenerateRequest.model_validate(reviews[0].input_json or {}),
    )

    assert completed.status == "completed"
    assert completed.source == "manual_entry"
    assert completed.original is not None
    assert completed.original.form_id == "tfr_default"
    assert (completed.input_json or {}).get("claim_number") == "MANUAL-001"


@pytest.mark.anyio
async def test_manual_entry_allows_yes_without_evidence_and_driver_without_citation(session):
    service = BatchReviewGenerationService(session)
    manual_result = (
        FormCatalog(service.settings.form_catalog_dir)
        .get_form(
            "exterior_hail",
            "v0.1",
        )
        .canonical.model_copy(deep=True)
    )
    manual_result.overall_outcome = "Does Not Meet"
    manual_result.outcome_justification = "Manual reviewer found one room-level support issue."

    manual_result.questions[0].answer = "Yes"
    manual_result.questions[0].comments = ""
    manual_result.questions[0].citations = ""

    manual_result.questions[1].answer = "No"
    manual_result.questions[1].comments = None
    manual_result.questions[1].citations = None
    manual_result.questions[1].sub_questions[0].answer = True
    manual_result.questions[1].sub_questions[
        0
    ].reasoning = "Photos do not support the dining room repair area."
    manual_result.questions[1].sub_questions[0].citations = ""
    manual_result.questions[1].sub_questions[1].answer = False
    manual_result.questions[1].sub_questions[1].reasoning = ""
    manual_result.questions[1].sub_questions[1].citations = ""

    manual_result.questions[2].answer = "Yes"
    manual_result.questions[2].comments = ""
    manual_result.questions[2].citations = ""

    batch = await service.create_batch(
        BatchCreateRequest(
            name="Flexible manual entry",
            form_id="exterior_hail",
            form_version="v0.1",
            input_mode="manual_entry",
            items=[
                BatchReviewInput(
                    claim_number="MANUAL-002",
                    effective_date="2026-05-18",
                    manual_result=manual_result,
                )
            ],
        )
    )
    reviews = await ReviewRepository(session).list_reviews(batch_id=batch.id)

    completed = await AuditGenerationService(session).generate_for_review(
        reviews[0].id,
        ReviewGenerateRequest.model_validate(reviews[0].input_json or {}),
    )

    assert completed.status == "completed"
    assert completed.original is not None
    assert completed.original.questions[0].answer == "Yes"
    assert completed.original.questions[0].comments == ""
    assert completed.original.questions[1].sub_questions
    assert completed.original.questions[1].sub_questions[0].answer is True
    assert completed.original.questions[1].sub_questions[0].citations == ""


@pytest.mark.anyio
async def test_finalization_tracks_dates_and_resets_on_user_edit(session):
    repository = ReviewRepository(session)
    service = AuditGenerationService(session)
    canonical = service.catalog.get_form("tfr_default", "v0.3").canonical.model_copy(deep=True)
    review = await repository.create_from_agent_output(
        canonical,
        source="manual_entry",
        input_json={"claim_number": "FINAL-001"},
    )

    assert review.finalized is False
    assert review.first_finalized_at is None
    assert review.last_finalized_at is None

    finalized = await repository.finalize_review(
        review.id,
        ReviewFinalization(user_version=canonical),
    )

    assert finalized.finalized is True
    assert finalized.first_finalized_at is not None
    assert finalized.last_finalized_at is not None
    first_finalized_at = finalized.first_finalized_at
    last_finalized_at = finalized.last_finalized_at

    edited_result = finalized.user_version.model_copy(deep=True)
    edited_result.outcome_justification = "Reviewer adjusted the validation narrative."
    edited = await repository.update_user_version(
        review.id,
        ReviewUpdate(user_version=edited_result),
    )

    assert edited.finalized is False
    assert edited.first_finalized_at == first_finalized_at
    assert edited.last_finalized_at == last_finalized_at

    refinalized = await repository.finalize_review(review.id, ReviewFinalization())

    assert refinalized.finalized is True
    assert refinalized.first_finalized_at == first_finalized_at
    assert refinalized.last_finalized_at is not None
    assert refinalized.last_finalized_at >= last_finalized_at


@pytest.mark.anyio
async def test_batch_validation_rejects_mixed_forms_and_bad_intake_rows(session):
    service = BatchReviewGenerationService(session)

    with pytest.raises(ValueError, match="must use one form"):
        await service.create_batch(
            BatchCreateRequest(
                name="Mixed forms",
                form_id="tfr_default",
                form_version="v0.3",
                items=[
                    BatchReviewInput(
                        claim_number="123",
                        form_id="exterior_hail",
                        form_version="v0.1",
                    )
                ],
            )
        )

    with pytest.raises(ValueError, match="exactly one selected document"):
        await service.create_batch(
            BatchCreateRequest(
                name="Intake",
                form_id="tfr_default",
                form_version="v0.3",
                input_mode="completed_intake",
                items=[BatchReviewInput(source_file_ids=[])],
            )
        )
