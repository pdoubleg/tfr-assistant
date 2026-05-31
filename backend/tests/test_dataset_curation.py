import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.models import Base
from app.schemas.datasets import (
    DatasetAppDbAddRequest,
    DatasetAppDbBrowseRequest,
    DatasetClusterRequest,
    DatasetPopulationCreate,
    DatasetPublishRequest,
    DatasetSampleRequest,
    DatasetSourceAddRequest,
    DatasetSourceBrowseRequest,
    DatasetSourceFetchRequest,
)
from app.services.catalog import FormCatalog
from app.services.datasets import DatasetRepository
from app.services.review_repository import ReviewRepository


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


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
                DatasetAppDbBrowseRequest(search="CLAIM-123"),
            )

            assert rows[0].review_id == review.id

            added = await repository.add_app_db_source(
                population.id,
                DatasetAppDbAddRequest(review_ids=[review.id]),
            )
            detail = await repository.get_population(population.id)

            assert added.added_count == 1
            assert detail.candidates[0].source_key == "app_db_reviews"
            assert detail.candidates[0].claim_number == "CLAIM-123"
    finally:
        await engine.dispose()
