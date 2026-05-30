from __future__ import annotations

import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.models import Base, OptimizationCandidateORM, OptimizationRunORM
from app.schemas.prompts import (
    OptimizationCandidatePromotion,
    PromptActivationUpdate,
    PromptAliasUpdate,
    PromptReference,
    PromptVersionCreate,
)
from app.services.catalog import FormCatalog
from app.services.optimization.utils import now_utc
from app.services.prompt_registry import PromptRegistryRepository


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
async def test_prompt_registry_bootstraps_versions_aliases_and_resolution(session) -> None:
    catalog = FormCatalog(get_settings().form_catalog_dir)
    repository = PromptRegistryRepository(session, catalog)

    families = await repository.list_form_families("tfr_default", form_version="v0.1")

    assert len(families) == 1
    family = families[0]
    assert family.versions
    assert {alias.alias for alias in family.aliases} >= {"baseline", "production"}
    active = next(
        activation
        for activation in family.activations
        if activation.scope == "form_version" and activation.form_version == "v0.1"
    )
    assert active.version_number == family.versions[-1].version_number

    edited = await repository.create_version(
        PromptVersionCreate(
            family_id=family.id,
            form_id="tfr_default",
            form_version="v0.1",
            text="Use the audit form carefully and explain evidence.",
            source_kind="manual_edit",
            commit_message="Test edited prompt.",
            alias="staging",
        )
    )
    await repository.set_alias(
        PromptAliasUpdate(family_id=family.id, alias="production", version_id=edited.id)
    )

    resolved = await repository.resolve(
        PromptReference(ref_type="alias", family_id=family.id, alias="production"),
        form_id="tfr_default",
        form_version="v0.1",
    )

    assert resolved.version_id == edited.id
    assert resolved.text == edited.text
    assert resolved.alias == "production"

    await repository.set_activation(
        PromptActivationUpdate(
            family_id=family.id,
            version_id=edited.id,
            form_version="v0.1",
            notes="Test activation.",
        )
    )
    active_resolved = await repository.resolve_active(
        form_id="tfr_default",
        form_version="v0.1",
    )
    assert active_resolved.version_id == edited.id
    assert active_resolved.activation_scope == "v0.1"


@pytest.mark.anyio
async def test_prompt_registry_registers_gepa_candidate_and_can_activate(session) -> None:
    catalog = FormCatalog(get_settings().form_catalog_dir)
    repository = PromptRegistryRepository(session, catalog)
    run = OptimizationRunORM(
        id="run-1",
        name="GEPA run",
        status="completed",
        form_id="tfr_default",
        form_version="v0.1",
        config_json={},
        split_json=[],
        best_score=0.91,
        original_score=0.72,
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    candidate = OptimizationCandidateORM(
        id="candidate-2",
        run_id=run.id,
        candidate_index=2,
        parent_indices_json=[0],
        status="best",
        candidate_json={"instructions": "Optimized candidate instructions."},
        score=0.91,
        metrics_json={"score": 0.91},
        created_at=now_utc(),
    )
    session.add_all([run, candidate])
    await session.commit()

    version = await repository.promote_optimization_candidate(
        OptimizationCandidatePromotion(
            run_id=run.id,
            candidate_index=2,
            activate_for_form_version=True,
        )
    )
    families = await repository.list_form_families("tfr_default", form_version="v0.1")
    family = families[0]
    active = next(
        activation
        for activation in family.activations
        if activation.scope == "form_version" and activation.form_version == "v0.1"
    )

    assert version.source_kind == "gepa_candidate"
    assert version.source_run_id == run.id
    assert version.source_candidate_index == 2
    assert active.version_id == version.id


@pytest.mark.anyio
async def test_prompt_registry_promotes_candidate_from_dag_artifact(session, tmp_path) -> None:
    dag_path = tmp_path / "dag.json"
    dag_path.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "candidate_index": 4,
                        "role": "best",
                        "score": 0.93,
                        "candidate": {"instructions": "Artifact candidate instructions."},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    run = OptimizationRunORM(
        id="run-artifact",
        name="GEPA artifact run",
        status="completed",
        form_id="tfr_default",
        form_version="v0.1",
        config_json={},
        split_json=[],
        artifacts_json={"dag": str(dag_path)},
        best_score=0.93,
        original_score=0.72,
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    session.add(run)
    await session.commit()

    version = await PromptRegistryRepository(
        session,
        FormCatalog(get_settings().form_catalog_dir),
    ).promote_optimization_candidate(
        OptimizationCandidatePromotion(run_id=run.id, candidate_index=4, alias="champion")
    )

    assert version.text == "Artifact candidate instructions."
    assert version.metrics["score"] == 0.93
    assert version.source_metadata["candidate_status"] == "best"
