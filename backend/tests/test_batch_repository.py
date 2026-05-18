import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import Base
from app.schemas.reviews import BatchCreateRequest, BatchReviewInput
from app.services.audit_generation import BatchReviewGenerationService
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
        input_json={"name": "Pilot", "form_id": "tfr_default", "form_version": "v0.1"},
    )
    await repository.create_review_placeholder(
        form_id="tfr_default",
        form_version="v0.1",
        source="batch",
        batch_id=batch.id,
        status="completed",
    )
    await repository.create_review_placeholder(
        form_id="tfr_default",
        form_version="v0.1",
        source="batch",
        batch_id=batch.id,
        status="failed",
    )
    await repository.create_review_placeholder(
        form_id="tfr_default",
        form_version="v0.1",
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
            form_version="v0.1",
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
async def test_batch_validation_rejects_mixed_forms_and_bad_intake_rows(session):
    service = BatchReviewGenerationService(session)

    with pytest.raises(ValueError, match="must use one form"):
        await service.create_batch(
            BatchCreateRequest(
                name="Mixed forms",
                form_id="tfr_default",
                form_version="v0.1",
                items=[
                    BatchReviewInput(
                        claim_number="123",
                        form_id="interior_water",
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
                form_version="v0.1",
                input_mode="completed_intake",
                items=[BatchReviewInput(source_file_ids=[])],
            )
        )
