from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.review_agent import DEFAULT_REVIEW_INSTRUCTIONS
from app.db.models import (
    OptimizationCandidateORM,
    OptimizationRunORM,
    PromptActivationORM,
    PromptAliasORM,
    PromptFamilyORM,
    PromptVersionORM,
)
from app.schemas.forms import AuditFormDefinition
from app.schemas.prompts import (
    OptimizationCandidatePromotion,
    PromptActivationRecord,
    PromptActivationUpdate,
    PromptAliasRecord,
    PromptAliasUpdate,
    PromptFamilyRecord,
    PromptReference,
    PromptVersionCreate,
    PromptVersionRecord,
    ResolvedPrompt,
)
from app.services.catalog import FormCatalog


def prompt_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def form_schema_fingerprint(definition: AuditFormDefinition) -> str:
    payload = {
        "form_id": definition.id,
        "questions": [
            {
                "id": question.id,
                "text": question.text,
                "sub_questions": [
                    {"id": sub.id, "text": sub.text} for sub in (question.sub_questions or [])
                ],
            }
            for question in definition.canonical.questions
        ],
        "tools": definition.tools or [],
        "knowledge_docs": definition.knowledge_docs or [],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def activation_scope_key(scope: str, form_version: str | None = None) -> str:
    return form_version if scope == "form_version" and form_version else "*"


class PromptRegistryRepository:
    def __init__(self, session: AsyncSession, catalog: FormCatalog) -> None:
        self.session = session
        self.catalog = catalog

    async def list_form_families(
        self,
        form_id: str,
        *,
        form_version: str | None = None,
        bootstrap: bool = True,
    ) -> list[PromptFamilyRecord]:
        if bootstrap and form_version:
            await self.bootstrap_form_prompt(form_id, form_version)
        rows = (
            await self.session.scalars(
                select(PromptFamilyORM)
                .where(PromptFamilyORM.form_id == form_id)
                .order_by(PromptFamilyORM.task.asc(), PromptFamilyORM.prompt_kind.asc())
            )
        ).all()
        return [await self._family_to_schema(row) for row in rows]

    async def bootstrap_form_prompt(
        self,
        form_id: str,
        form_version: str,
    ) -> PromptFamilyRecord:
        definition = self.catalog.get_form(form_id, form_version)
        family = await self.ensure_family(form_id)
        text = definition.instructions or DEFAULT_REVIEW_INSTRUCTIONS
        text_hash = prompt_text_hash(text)
        existing_count = await self.session.scalar(
            select(func.count(PromptVersionORM.id)).where(PromptVersionORM.family_id == family.id)
        )
        version = await self.session.scalar(
            select(PromptVersionORM)
            .where(PromptVersionORM.family_id == family.id)
            .where(PromptVersionORM.text_hash == text_hash)
            .order_by(PromptVersionORM.version_number.asc())
        )
        if version is None:
            created = await self.create_version(
                PromptVersionCreate(
                    family_id=family.id,
                    form_id=form_id,
                    form_version=form_version,
                    text=text,
                    source_kind="form_default",
                    commit_message=f"Imported default instructions from {form_id}@{form_version}.",
                    created_by="system",
                    applicable_form_versions=[form_version],
                ),
                commit=False,
            )
            version = await self.session.get(PromptVersionORM, created.id)
        elif form_version not in (version.applicable_form_versions_json or []):
            version.applicable_form_versions_json = [
                *(version.applicable_form_versions_json or []),
                form_version,
            ]
            self.session.add(version)
            await self.session.flush()
        if version is not None:
            await self.set_alias(
                PromptAliasUpdate(family_id=family.id, alias="baseline", version_id=version.id),
                commit=False,
            )
            await self.ensure_activation(
                family_id=family.id,
                version_id=version.id,
                form_version=form_version,
                commit=False,
            )
        production_alias = await self.session.scalar(
            select(PromptAliasORM).where(
                PromptAliasORM.family_id == family.id,
                PromptAliasORM.alias == "production",
            )
        )
        if version is not None and (not existing_count or production_alias is None):
            await self.set_alias(
                PromptAliasUpdate(family_id=family.id, alias="production", version_id=version.id),
                commit=False,
            )
            await self.ensure_activation(
                family_id=family.id,
                version_id=version.id,
                form_version=None,
                scope="form_default",
                commit=False,
            )
        await self.session.commit()
        return await self._family_to_schema(family)

    async def ensure_family(self, form_id: str) -> PromptFamilyORM:
        family = await self.session.scalar(
            select(PromptFamilyORM).where(
                PromptFamilyORM.form_id == form_id,
                PromptFamilyORM.task == "audit_review",
                PromptFamilyORM.prompt_kind == "instructions",
            )
        )
        if family:
            return family
        family = PromptFamilyORM(
            id=str(uuid4()),
            form_id=form_id,
            task="audit_review",
            prompt_kind="instructions",
            name="Audit Review Instructions",
            description="Selectable instruction prompts for registered audit form review.",
            metadata_json={
                "mlflow_compatible": True,
                "uri_template": "prompts:/{form_id}/audit_review/instructions@{alias_or_version}",
            },
        )
        self.session.add(family)
        await self.session.flush()
        return family

    async def create_version(
        self,
        request: PromptVersionCreate,
        *,
        commit: bool = True,
    ) -> PromptVersionRecord:
        family = (
            await self.session.get(PromptFamilyORM, request.family_id)
            if request.family_id
            else await self.ensure_family(request.form_id)
        )
        if family is None:
            raise KeyError("Prompt family not found.")
        fingerprint = ""
        if request.form_version:
            definition = self.catalog.get_form(request.form_id, request.form_version)
            fingerprint = form_schema_fingerprint(definition)
        next_version = (
            await self.session.scalar(
                select(func.max(PromptVersionORM.version_number)).where(
                    PromptVersionORM.family_id == family.id
                )
            )
            or 0
        ) + 1
        applicable_versions = request.applicable_form_versions or (
            [request.form_version] if request.form_version else []
        )
        record = PromptVersionORM(
            id=str(uuid4()),
            family_id=family.id,
            version_number=next_version,
            text=request.text.strip(),
            text_hash=prompt_text_hash(request.text.strip()),
            components_json={"instructions": request.text.strip()},
            source_kind=request.source_kind,
            source_run_id=request.source_run_id,
            source_candidate_index=request.source_candidate_index,
            source_metadata_json=request.source_metadata,
            commit_message=request.commit_message.strip(),
            created_by=request.created_by,
            metrics_json=request.metrics,
            applicable_form_versions_json=applicable_versions,
            form_schema_fingerprint=fingerprint,
            external_prompt_uri=request.external_prompt_uri,
        )
        self.session.add(record)
        await self.session.flush()
        if request.alias:
            await self.set_alias(
                PromptAliasUpdate(family_id=family.id, alias=request.alias, version_id=record.id),
                commit=False,
            )
        if commit:
            await self.session.commit()
            await self.session.refresh(record)
        return self._version_to_schema(record)

    async def ensure_activation(
        self,
        *,
        family_id: str,
        version_id: str,
        form_version: str | None,
        scope: str = "form_version",
        commit: bool = True,
    ) -> PromptActivationRecord:
        key = activation_scope_key(scope, form_version)
        record = await self.session.scalar(
            select(PromptActivationORM).where(
                PromptActivationORM.family_id == family_id,
                PromptActivationORM.scope_key == key,
            )
        )
        if record is None:
            record = PromptActivationORM(
                id=str(uuid4()),
                family_id=family_id,
                version_id=version_id,
                scope_key=key,
                scope=scope,
                form_version=form_version if scope == "form_version" else None,
                activated_by="system",
                notes="Initialized from registered form instructions.",
            )
            self.session.add(record)
            await self.session.flush()
        if commit:
            await self.session.commit()
            await self.session.refresh(record)
        version = await self.session.get(PromptVersionORM, record.version_id)
        return self._activation_to_schema(
            record,
            {version.id: version.version_number} if version else {},
        )

    async def set_activation(
        self,
        request: PromptActivationUpdate,
        *,
        commit: bool = True,
    ) -> PromptActivationRecord:
        version = await self.session.get(PromptVersionORM, request.version_id)
        if not version or version.family_id != request.family_id:
            raise ValueError("Active prompt target version does not belong to the family.")
        scope_key = activation_scope_key(request.scope, request.form_version)
        record = await self.session.scalar(
            select(PromptActivationORM).where(
                PromptActivationORM.family_id == request.family_id,
                PromptActivationORM.scope_key == scope_key,
            )
        )
        if record is None:
            record = PromptActivationORM(
                id=str(uuid4()),
                family_id=request.family_id,
                version_id=request.version_id,
                scope_key=scope_key,
                scope=request.scope,
                form_version=request.form_version,
                activated_by=request.activated_by,
                notes=request.notes.strip(),
            )
            self.session.add(record)
        else:
            record.version_id = request.version_id
            record.scope = request.scope
            record.form_version = request.form_version
            record.activated_by = request.activated_by
            record.notes = request.notes.strip()
        await self.session.flush()
        if commit:
            await self.session.commit()
            await self.session.refresh(record)
        return self._activation_to_schema(record, {version.id: version.version_number})

    async def set_alias(
        self,
        request: PromptAliasUpdate,
        *,
        commit: bool = True,
    ) -> PromptAliasRecord:
        version = await self.session.get(PromptVersionORM, request.version_id)
        if not version or version.family_id != request.family_id:
            raise ValueError("Alias target prompt version does not belong to the family.")
        record = await self.session.scalar(
            select(PromptAliasORM).where(
                PromptAliasORM.family_id == request.family_id,
                PromptAliasORM.alias == request.alias,
            )
        )
        if record is None:
            record = PromptAliasORM(
                id=str(uuid4()),
                family_id=request.family_id,
                alias=request.alias,
                version_id=request.version_id,
            )
            self.session.add(record)
        else:
            record.version_id = request.version_id
        await self.session.flush()
        if commit:
            await self.session.commit()
            await self.session.refresh(record)
        return self._alias_to_schema(record, {version.id: version.version_number})

    async def promote_optimization_candidate(
        self,
        request: OptimizationCandidatePromotion,
    ) -> PromptVersionRecord:
        run = await self.session.get(OptimizationRunORM, request.run_id)
        if not run:
            raise KeyError("Optimization run not found.")
        try:
            await self.bootstrap_form_prompt(run.form_id, run.form_version)
        except KeyError:
            # Promotion can still preserve a candidate for older/orphaned runs, but
            # registered forms get their baseline prompt imported first.
            pass
        candidate = await self.session.scalar(
            select(OptimizationCandidateORM).where(
                OptimizationCandidateORM.run_id == request.run_id,
                OptimizationCandidateORM.candidate_index == request.candidate_index,
            )
        )
        artifact_candidate = (
            self._candidate_from_dag_artifact(run, request.candidate_index)
            if candidate is None
            else None
        )
        if not candidate and artifact_candidate is None:
            raise KeyError("Optimization candidate not found.")
        candidate_json = (
            candidate.candidate_json if candidate is not None else artifact_candidate["candidate"]
        )
        text = str((candidate_json or {}).get("instructions") or "").strip()
        if not text:
            raise ValueError("Optimization candidate does not include instructions text.")
        version = await self.create_version(
            PromptVersionCreate(
                form_id=run.form_id,
                form_version=run.form_version,
                text=text,
                source_kind="gepa_candidate",
                source_run_id=run.id,
                source_candidate_index=request.candidate_index,
                source_metadata={
                    "optimization_run_name": run.name,
                    "candidate_status": (
                        candidate.status if candidate is not None else artifact_candidate["role"]
                    ),
                },
                commit_message=request.commit_message
                or f"Promoted GEPA candidate {request.candidate_index} from {run.name}.",
                created_by=request.created_by,
                metrics={
                    "score": (
                        candidate.score if candidate is not None else artifact_candidate["score"]
                    ),
                    "run_best_score": run.best_score,
                    "run_original_score": run.original_score,
                    "candidate_metrics": (
                        candidate.metrics_json or {} if candidate is not None else {}
                    ),
                },
                applicable_form_versions=[run.form_version],
                alias=request.alias,
            )
        )
        if request.activate_for_form_version:
            await self.set_activation(
                PromptActivationUpdate(
                    family_id=version.family_id,
                    version_id=version.id,
                    form_version=run.form_version,
                    activated_by=request.created_by,
                    notes=f"Activated from GEPA candidate {request.candidate_index} in {run.name}.",
                )
            )
        return version

    def _candidate_from_dag_artifact(
        self,
        run: OptimizationRunORM,
        candidate_index: int,
    ) -> dict[str, Any] | None:
        artifact_path = str((run.artifacts_json or {}).get("dag") or "")
        if not artifact_path:
            return None
        try:
            with open(artifact_path, encoding="utf-8") as file_obj:
                payload = json.load(file_obj)
        except OSError:
            return None
        for node in payload.get("nodes") or []:
            if node.get("candidate_index") == candidate_index:
                return {
                    "candidate": node.get("candidate") or {},
                    "role": str(node.get("role") or "candidate"),
                    "score": node.get("score"),
                }
        return None

    async def resolve(
        self,
        ref: PromptReference,
        *,
        form_id: str,
        form_version: str,
    ) -> ResolvedPrompt:
        if ref.ref_type == "manual":
            text = ref.manual_text.strip()
            return ResolvedPrompt(
                ref=ref,
                text=text,
                text_hash=prompt_text_hash(text),
                form_id=form_id,
                source_kind="manual",
            )
        if ref.ref_type == "form_default":
            definition = self.catalog.get_form(form_id, form_version)
            text = definition.instructions or DEFAULT_REVIEW_INSTRUCTIONS
            return ResolvedPrompt(
                ref=ref,
                text=text,
                text_hash=prompt_text_hash(text),
                form_id=form_id,
                source_kind="form_default",
            )
        version: PromptVersionORM | None = None
        alias: str | None = None
        if ref.ref_type == "version":
            version = await self.session.get(PromptVersionORM, ref.version_id)
        elif ref.ref_type == "alias":
            alias = ref.alias
            alias_record = await self.session.scalar(
                select(PromptAliasORM).where(
                    PromptAliasORM.family_id == ref.family_id,
                    PromptAliasORM.alias == ref.alias,
                )
            )
            if alias_record:
                version = await self.session.get(PromptVersionORM, alias_record.version_id)
        if version is None:
            raise KeyError("Prompt reference could not be resolved.")
        family = await self.session.get(PromptFamilyORM, version.family_id)
        return ResolvedPrompt(
            ref=ref,
            text=version.text,
            text_hash=version.text_hash,
            family_id=version.family_id,
            version_id=version.id,
            version_number=version.version_number,
            alias=alias,
            form_id=family.form_id if family else form_id,
            source_kind=version.source_kind,
            external_prompt_uri=version.external_prompt_uri,
        )

    async def resolve_active(
        self,
        *,
        form_id: str,
        form_version: str,
    ) -> ResolvedPrompt:
        await self.bootstrap_form_prompt(form_id, form_version)
        family = await self.ensure_family(form_id)
        activation = await self._activation_for_family(family.id, form_version)
        if activation is None:
            definition = self.catalog.get_form(form_id, form_version)
            text = definition.instructions or DEFAULT_REVIEW_INSTRUCTIONS
            return ResolvedPrompt(
                ref=PromptReference(ref_type="form_default", form_id=form_id),
                text=text,
                text_hash=prompt_text_hash(text),
                form_id=form_id,
                source_kind="form_default",
                activation_scope=form_version,
            )
        version = await self.session.get(PromptVersionORM, activation.version_id)
        if version is None:
            raise KeyError("Active prompt version could not be resolved.")
        return ResolvedPrompt(
            ref=PromptReference(
                ref_type="version",
                family_id=family.id,
                version_id=version.id,
                form_id=form_id,
            ),
            text=version.text,
            text_hash=version.text_hash,
            family_id=family.id,
            version_id=version.id,
            version_number=version.version_number,
            form_id=form_id,
            source_kind=version.source_kind,
            activation_scope=activation.scope_key,
            external_prompt_uri=version.external_prompt_uri,
        )

    async def _activation_for_family(
        self,
        family_id: str,
        form_version: str,
    ) -> PromptActivationORM | None:
        exact = await self.session.scalar(
            select(PromptActivationORM).where(
                PromptActivationORM.family_id == family_id,
                PromptActivationORM.scope_key == form_version,
            )
        )
        if exact is not None:
            return exact
        return await self.session.scalar(
            select(PromptActivationORM).where(
                PromptActivationORM.family_id == family_id,
                PromptActivationORM.scope_key == "*",
            )
        )

    async def _family_to_schema(self, family: PromptFamilyORM) -> PromptFamilyRecord:
        versions = (
            await self.session.scalars(
                select(PromptVersionORM)
                .where(PromptVersionORM.family_id == family.id)
                .order_by(PromptVersionORM.version_number.desc())
            )
        ).all()
        aliases = (
            await self.session.scalars(
                select(PromptAliasORM)
                .where(PromptAliasORM.family_id == family.id)
                .order_by(PromptAliasORM.alias.asc())
            )
        ).all()
        activations = (
            await self.session.scalars(
                select(PromptActivationORM)
                .where(PromptActivationORM.family_id == family.id)
                .order_by(PromptActivationORM.scope_key.asc())
            )
        ).all()
        version_numbers = {version.id: version.version_number for version in versions}
        return PromptFamilyRecord(
            id=family.id,
            form_id=family.form_id,
            task=family.task,  # type: ignore[arg-type]
            prompt_kind=family.prompt_kind,  # type: ignore[arg-type]
            name=family.name,
            description=family.description,
            external_registry_uri=family.external_registry_uri,
            metadata=family.metadata_json or {},
            aliases=[self._alias_to_schema(alias, version_numbers) for alias in aliases],
            activations=[
                self._activation_to_schema(activation, version_numbers)
                for activation in activations
            ],
            versions=[self._version_to_schema(version) for version in versions],
            created_at=family.created_at,
            updated_at=family.updated_at,
        )

    def _version_to_schema(self, record: PromptVersionORM) -> PromptVersionRecord:
        return PromptVersionRecord(
            id=record.id,
            family_id=record.family_id,
            version_number=record.version_number,
            text=record.text,
            text_hash=record.text_hash,
            source_kind=record.source_kind,  # type: ignore[arg-type]
            source_run_id=record.source_run_id,
            source_candidate_index=record.source_candidate_index,
            source_metadata=record.source_metadata_json or {},
            commit_message=record.commit_message,
            created_by=record.created_by,
            metrics=record.metrics_json or {},
            applicable_form_versions=record.applicable_form_versions_json or [],
            form_schema_fingerprint=record.form_schema_fingerprint,
            external_prompt_uri=record.external_prompt_uri,
            created_at=record.created_at,
        )

    def _alias_to_schema(
        self,
        record: PromptAliasORM,
        version_numbers: dict[str, int] | None = None,
    ) -> PromptAliasRecord:
        version_number = (version_numbers or {}).get(record.version_id)
        return PromptAliasRecord(
            id=record.id,
            family_id=record.family_id,
            alias=record.alias,
            version_id=record.version_id,
            version_number=version_number,
            updated_at=record.updated_at,
        )

    def _activation_to_schema(
        self,
        record: PromptActivationORM,
        version_numbers: dict[str, int] | None = None,
    ) -> PromptActivationRecord:
        version_number = (version_numbers or {}).get(record.version_id)
        return PromptActivationRecord(
            id=record.id,
            family_id=record.family_id,
            version_id=record.version_id,
            version_number=version_number,
            scope=record.scope,  # type: ignore[arg-type]
            form_version=record.form_version,
            activated_by=record.activated_by,
            notes=record.notes,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
