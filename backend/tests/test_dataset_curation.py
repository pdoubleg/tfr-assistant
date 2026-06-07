import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.models import Base
from app.schemas.datasets import (
    DatasetAppDbAddRequest,
    DatasetAppDbBrowseRequest,
    DatasetCandidateReferenceUpdate,
    DatasetCloneRequest,
    DatasetClusterRequest,
    DatasetPopulationCreate,
    DatasetPublishRequest,
    DatasetSampleRequest,
    DatasetSourceAddRequest,
    DatasetSourceBrowseRequest,
    DatasetSourceFetchRequest,
)
from app.schemas.evaluations import FeedbackCreate
from app.services.catalog import FormCatalog
from app.services.datasets import DatasetRepository, _cluster_vectors
from app.services.review_repository import ReviewRepository


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_cluster_vectors_supports_single_cluster_request() -> None:
    selected_k, labels, distances, silhouette = _cluster_vectors(
        [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]],
        min_k=1,
        max_k=1,
        seed=7,
    )

    assert selected_k == 1
    assert labels == [0, 0, 0]
    assert len(distances) == 3
    assert all(distance >= 0 for distance in distances)
    assert silhouette is None


@pytest.mark.anyio
async def test_dummy_source_fetch_clusters_and_publishes_dataset(tmp_path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        settings = Settings(
            data_dir=tmp_path / "data",
            dataset_embedding_model_dir=tmp_path / "missing-model",
        )
        async with session_factory() as session:
            repository = DatasetRepository(session, settings)
            population = await repository.create_population(
                DatasetPopulationCreate(
                    name="Test population",
                    form_id="tfr_default",
                    form_version="v0.1",
                )
            )

            response = await repository.fetch_source(
                population.id,
                DatasetSourceFetchRequest(
                    source_id="sister_app_placeholder",
                    params={"count": 6},
                ),
            )

            assert response.added_count == 6
            detail = await repository.get_population(population.id)
            assert detail.candidate_count == 6
            assert detail.r2_count == 6

            cluster = await repository.cluster_population(
                population.id,
                DatasetClusterRequest(min_clusters=2, max_clusters=3, seed=7),
            )
            assert cluster.feature_backend == "lexical"
            assert cluster.selected_k in {2, 3}
            assert sum(cluster.cluster_counts.values()) == 6

            dataset = await repository.publish_population(
                population.id,
                DatasetPublishRequest(name="Published test dataset"),
            )
            rows = await repository.list_published_rows(dataset.id)

            assert dataset.case_count == 6
            assert len(rows) == 6
            assert rows[0].metadata["source_key"] == "sister_app_placeholder"
            assert rows[0].cluster_id is not None
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_code_owned_source_can_preview_and_add_selected_rows(tmp_path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        settings = Settings(
            data_dir=tmp_path / "data",
            dataset_embedding_model_dir=tmp_path / "missing-model",
        )
        async with session_factory() as session:
            repository = DatasetRepository(session, settings)
            population = await repository.create_population(
                DatasetPopulationCreate(
                    name="Preview population",
                    form_id="tfr_default",
                    form_version="v0.1",
                )
            )
            preview = await repository.browse_source(
                "tfr_default",
                "v0.1",
                DatasetSourceBrowseRequest(
                    source_id="sister_app_placeholder",
                    params={"count": 4},
                ),
            )

            assert len(preview) == 4
            assert preview[0].source_id == "sister_app_placeholder"

            added = await repository.add_source_candidates(
                population.id,
                DatasetSourceAddRequest(
                    source_id="sister_app_placeholder",
                    params={"count": 4},
                    source_record_ids=[preview[1].source_record_id, preview[3].source_record_id],
                ),
            )
            detail = await repository.get_population(population.id)

            assert added.added_count == 2
            assert detail.candidate_count == 2
            assert {candidate.source_record_id for candidate in detail.candidates} == {
                preview[1].source_record_id,
                preview[3].source_record_id,
            }
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_outcome_sampling_preserves_candidate_outcome_split(tmp_path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        settings = Settings(
            data_dir=tmp_path / "data",
            dataset_embedding_model_dir=tmp_path / "missing-model",
        )
        async with session_factory() as session:
            repository = DatasetRepository(session, settings)
            population = await repository.create_population(
                DatasetPopulationCreate(
                    name="Outcome sample population",
                    form_id="tfr_default",
                    form_version="v0.1",
                )
            )
            await repository.fetch_source(
                population.id,
                DatasetSourceFetchRequest(
                    source_id="sister_app_placeholder",
                    params={"count": 6},
                ),
            )

            sample = await repository.sample_population(
                population.id,
                DatasetSampleRequest(mode="outcome", size=3, seed=11),
            )
            detail = await repository.get_population(population.id)
            included = [candidate for candidate in detail.candidates if candidate.included]
            outcome_counts: dict[str, int] = {}
            for candidate in included:
                outcome = str(candidate.metrics["outcome"])
                outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1

            assert sample.selected_count == 3
            assert outcome_counts == {"Does Not Meet": 1, "Meets": 2}
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_app_db_source_converts_completed_reviews(tmp_path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        settings = Settings(data_dir=tmp_path / "data")
        canonical = FormCatalog(settings.form_catalog_dir).get_form("tfr_default", "v0.1").canonical
        async with session_factory() as session:
            review = await ReviewRepository(session).create_from_agent_output(
                canonical,
                source="manual_entry",
                input_json={"claim_number": "CLAIM-123", "effective_date": "2026-05-31"},
            )
            await ReviewRepository(session).add_feedback(
                FeedbackCreate(
                    review_id=review.id,
                    score=2,
                    comment="Citations missed the contractor note.",
                )
            )
            reviewed = await ReviewRepository(session).get_review(review.id)
            assert reviewed.feedback_count == 1
            assert await ReviewRepository(session).edited_review_count() == 1
            repository = DatasetRepository(session, settings)
            population = await repository.create_population(
                DatasetPopulationCreate(
                    name="App DB population",
                    form_id="tfr_default",
                    form_version="v0.1",
                )
            )
            rows = await repository.browse_app_db_source(
                "tfr_default",
                "v0.1",
                DatasetAppDbBrowseRequest(
                    search="CLAIM-123",
                    include_feedback=True,
                    feedback_filter="low_score",
                ),
            )

            assert rows[0].review_id == review.id
            assert rows[0].feedback_count == 1
            assert rows[0].feedback_min_score == 2
            assert rows[0].feedback_latest_comment == "Citations missed the contractor note."

            added = await repository.add_app_db_source(
                population.id,
                DatasetAppDbAddRequest(review_ids=[review.id], include_feedback=True),
            )
            detail = await repository.get_population(population.id)

            assert added.added_count == 1
            assert detail.candidates[0].source_key == "app_db_reviews"
            assert detail.candidates[0].claim_number == "CLAIM-123"
            assert detail.candidates[0].metrics["feedback_count"] == 1
            assert detail.candidates[0].metadata["feedback"]["comments"] == [
                "Citations missed the contractor note."
            ]
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_candidate_reference_edit_invalidates_analysis_and_publishes_update(tmp_path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        settings = Settings(
            data_dir=tmp_path / "data",
            dataset_embedding_model_dir=tmp_path / "missing-model",
        )
        async with session_factory() as session:
            repository = DatasetRepository(session, settings)
            population = await repository.create_population(
                DatasetPopulationCreate(
                    name="Editable population",
                    form_id="tfr_default",
                    form_version="v0.1",
                )
            )
            await repository.fetch_source(
                population.id,
                DatasetSourceFetchRequest(
                    source_id="sister_app_placeholder",
                    params={"count": 4},
                ),
            )
            await repository.cluster_population(
                population.id,
                DatasetClusterRequest(min_clusters=2, max_clusters=2, seed=3),
            )
            await repository.sample_population(
                population.id,
                DatasetSampleRequest(mode="all"),
            )
            detail = await repository.get_population(population.id)
            candidate = detail.candidates[0]
            assert candidate.cluster_id is not None
            assert candidate.included is True

            edited_result = candidate.references[0].result.model_copy(
                deep=True,
                update={
                    "overall_outcome": "Does Not Meet",
                    "outcome_justification": "SME corrected this case before publish.",
                },
            )
            updated = await repository.update_candidate_reference(
                candidate.id,
                "R2",
                DatasetCandidateReferenceUpdate(
                    result=edited_result,
                    reviewer="sme",
                    source_metadata={"edited_for": "eval"},
                ),
            )
            edited_detail = await repository.get_population(population.id)

            assert updated.references[0].result.overall_outcome == "Does Not Meet"
            assert updated.metrics["outcome"] == "Does Not Meet"
            assert updated.metadata["curated_edited"] is True
            assert edited_detail.clustered_count == 0
            assert edited_detail.cluster_config["stale"] is True
            assert edited_detail.sample_config["stale"] is True
            assert [item.included for item in edited_detail.candidates].count(True) == 4

            dataset = await repository.publish_population(
                population.id,
                DatasetPublishRequest(name="Edited published dataset"),
            )
            rows = await repository.list_published_rows(dataset.id)
            edited_row = next(
                row for row in rows if row.metadata["dataset_candidate_id"] == candidate.id
            )

            assert edited_row.result.overall_outcome == "Does Not Meet"
            assert edited_row.metadata["candidate_metadata"]["curated_edited"] is True
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_published_population_rejects_candidate_reference_edit(tmp_path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        settings = Settings(data_dir=tmp_path / "data")
        async with session_factory() as session:
            repository = DatasetRepository(session, settings)
            population = await repository.create_population(
                DatasetPopulationCreate(
                    name="Published population",
                    form_id="tfr_default",
                    form_version="v0.1",
                )
            )
            await repository.fetch_source(
                population.id,
                DatasetSourceFetchRequest(
                    source_id="sister_app_placeholder",
                    params={"count": 1},
                ),
            )
            detail = await repository.get_population(population.id)
            candidate = detail.candidates[0]
            await repository.publish_population(
                population.id,
                DatasetPublishRequest(name="Immutable dataset"),
            )

            with pytest.raises(ValueError, match="immutable"):
                await repository.update_candidate_reference(
                    candidate.id,
                    "R2",
                    DatasetCandidateReferenceUpdate(result=candidate.references[0].result),
                )
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_clone_published_dataset_to_editable_draft_and_republish(tmp_path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        settings = Settings(
            data_dir=tmp_path / "data",
            dataset_embedding_model_dir=tmp_path / "missing-model",
        )
        async with session_factory() as session:
            repository = DatasetRepository(session, settings)
            population = await repository.create_population(
                DatasetPopulationCreate(
                    name="Original draft",
                    form_id="tfr_default",
                    form_version="v0.1",
                )
            )
            await repository.fetch_source(
                population.id,
                DatasetSourceFetchRequest(
                    source_id="sister_app_placeholder",
                    params={"count": 2},
                ),
            )
            published = await repository.publish_population(
                population.id,
                DatasetPublishRequest(name="Original dataset"),
            )

            cloned = await repository.clone_published_dataset(
                published.id,
                DatasetCloneRequest(name="Original dataset v2 draft"),
            )
            assert cloned.status == "draft"
            assert cloned.candidate_count == 2
            assert cloned.source_config["cloned_from_dataset_id"] == published.id
            assert cloned.candidates[0].metadata["cloned_from_dataset_id"] == published.id

            candidate = cloned.candidates[0]
            edited_result = candidate.references[0].result.model_copy(
                deep=True,
                update={"outcome_justification": "Cloned draft SME edit."},
            )
            await repository.update_candidate_reference(
                candidate.id,
                "R2",
                DatasetCandidateReferenceUpdate(result=edited_result, reviewer="sme"),
            )
            republished = await repository.publish_population(
                cloned.id,
                DatasetPublishRequest(name="Original dataset v2"),
            )
            rows = await repository.list_published_rows(republished.id)

            assert republished.id != published.id
            assert any(row.result.outcome_justification == "Cloned draft SME edit." for row in rows)
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_code_owned_source_materializes_selected_reviews_and_skips_duplicates(
    tmp_path,
) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        settings = Settings(data_dir=tmp_path / "data")
        async with session_factory() as session:
            repository = DatasetRepository(session, settings)
            preview = await repository.browse_source(
                "tfr_default",
                "v0.1",
                DatasetSourceBrowseRequest(
                    source_id="sister_app_placeholder",
                    params={"count": 3},
                ),
            )
            request = DatasetSourceAddRequest(
                source_id="sister_app_placeholder",
                params={"count": 3},
                source_record_ids=[preview[0].source_record_id, preview[2].source_record_id],
            )

            first = await repository.materialize_source_reviews("tfr_default", "v0.1", request)
            second = await repository.materialize_source_reviews("tfr_default", "v0.1", request)
            reviews = await ReviewRepository(session).list_reviews()
            app_rows = await repository.browse_app_db_source(
                "tfr_default",
                "v0.1",
                DatasetAppDbBrowseRequest(search=preview[0].claim_number),
            )

            assert first.created_count == 2
            assert first.skipped_count == 0
            assert second.created_count == 0
            assert second.skipped_count == 2
            assert len(reviews) == 2
            assert all(review.source.startswith("dataset:") for review in reviews)
            assert app_rows[0].claim_number == preview[0].claim_number
    finally:
        await engine.dispose()
