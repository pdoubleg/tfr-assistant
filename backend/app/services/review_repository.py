import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config import get_settings
from app.db.models import (
    AuditBatchORM,
    AuditBatchTemplateORM,
    AuditQuestionAnswerORM,
    AuditResultVersionORM,
    AuditReviewORM,
    AuditSubQuestionAnswerORM,
    EvaluationORM,
    FeedbackORM,
)
from app.models.audit import AuditFormResult
from app.schemas.evaluations import EvaluationCreate, EvaluationRecord, FeedbackCreate
from app.schemas.reviews import (
    BatchRecord,
    BatchReviewInput,
    BatchTemplateCreate,
    BatchTemplateRecord,
    BatchTemplateUpdate,
    ReviewRecord,
    ReviewUpdate,
)
from app.services.catalog import FormCatalog


def _now() -> datetime:
    return datetime.now(UTC)


def _payload_for(result: AuditFormResult) -> dict[str, Any]:
    return result.model_dump(mode="json")


def _payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _ensure_registered_form(form_id: str, form_version: str) -> None:
    try:
        FormCatalog(get_settings().form_catalog_dir).get_form(form_id, form_version)
    except KeyError as exc:
        raise ValueError(
            f"Registered form {form_id}@{form_version} was not found in the form catalog."
        ) from exc


def _repair_result_payload_for_read(payload: dict[str, Any]) -> dict[str, Any]:
    repaired = json.loads(json.dumps(payload))
    questions = repaired.get("questions")
    if not isinstance(questions, list):
        return repaired

    for question in questions:
        if not isinstance(question, dict):
            continue

        answer = question.get("answer")
        sub_questions = question.get("sub_questions")
        if not isinstance(sub_questions, list):
            sub_questions = []
            question["sub_questions"] = sub_questions

        if answer == "Yes":
            question["sub_questions"] = []
            continue

        if answer != "No":
            continue

        if not sub_questions:
            question["sub_questions"] = [
                {
                    "id": f"{question.get('id', 'Q')}.legacy",
                    "text": "Legacy stored result did not include a driver option.",
                    "reasoning": (
                        "Read repair added this placeholder so the saved review can be displayed."
                    ),
                    "citations": "",
                    "answer": True,
                    "help_text": None,
                }
            ]
            continue

        if not any(
            bool(sub_question.get("answer"))
            for sub_question in sub_questions
            if isinstance(sub_question, dict)
        ):
            first_subquestion = next(
                (sub_question for sub_question in sub_questions if isinstance(sub_question, dict)),
                None,
            )
            if first_subquestion is not None:
                first_subquestion["answer"] = True
                first_subquestion["reasoning"] = (
                    first_subquestion.get("reasoning")
                    or "Read repair marked this existing driver as applicable for display."
                )

    return repaired


class ReviewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_reviews(self, batch_id: str | None = None) -> list[ReviewRecord]:
        statement = select(AuditReviewORM).order_by(AuditReviewORM.updated_at.desc())
        if batch_id:
            statement = statement.where(AuditReviewORM.batch_id == batch_id)
        records = (await self.session.scalars(statement)).all()
        return [await self._review_to_schema(record) for record in records]

    async def get_review(self, review_id: str) -> ReviewRecord:
        record = await self._get_review_orm(review_id)
        return await self._review_to_schema(record)

    async def list_batch_templates(self) -> list[BatchTemplateRecord]:
        statement = select(AuditBatchTemplateORM).order_by(AuditBatchTemplateORM.updated_at.desc())
        templates = (await self.session.scalars(statement)).all()
        return [await self._batch_template_to_schema(template) for template in templates]

    async def get_batch_template(self, template_id: str) -> BatchTemplateRecord:
        template = await self._get_batch_template_orm(template_id)
        return await self._batch_template_to_schema(template)

    async def create_batch_template(self, request: BatchTemplateCreate) -> BatchTemplateRecord:
        _ensure_registered_form(request.form_id, request.form_version)
        record = AuditBatchTemplateORM(
            id=str(uuid4()),
            name=request.name.strip(),
            description=request.description.strip(),
            form_id=request.form_id,
            form_version=request.form_version,
            synthetic=request.synthetic,
            synthetic_count=request.synthetic_count,
            input_mode=request.input_mode,
            excel_column_map=request.excel_column_map,
            items_json=[item.model_dump(mode="json") for item in request.items],
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return await self._batch_template_to_schema(record)

    async def update_batch_template(
        self,
        template_id: str,
        request: BatchTemplateUpdate,
    ) -> BatchTemplateRecord:
        record = await self._get_batch_template_orm(template_id)
        latest_run = await self._latest_batch_for_template(template_id)
        if latest_run and latest_run.status == "running":
            raise ValueError("Batch configuration is locked while the latest run is in progress.")
        _ensure_registered_form(request.form_id, request.form_version)

        record.description = request.description.strip()
        record.form_id = request.form_id
        record.form_version = request.form_version
        record.synthetic = request.synthetic
        record.synthetic_count = request.synthetic_count
        record.input_mode = request.input_mode
        record.excel_column_map = request.excel_column_map
        record.items_json = [item.model_dump(mode="json") for item in request.items]
        record.updated_at = _now()
        await self.session.commit()
        await self.session.refresh(record)
        return await self._batch_template_to_schema(record)

    async def create_review_placeholder(
        self,
        *,
        form_id: str,
        form_version: str,
        source: str,
        batch_id: str | None = None,
        input_json: dict[str, Any] | None = None,
        status: str = "queued",
    ) -> ReviewRecord:
        review_id = str(uuid4())
        record = AuditReviewORM(
            id=review_id,
            batch_id=batch_id,
            form_id=form_id,
            form_version=form_version,
            status=status,
            source=source,
            input_json=input_json,
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        if batch_id:
            await self.refresh_batch_counts(batch_id)
        return await self._review_to_schema(record)

    async def create_from_agent_output(
        self,
        result: AuditFormResult,
        *,
        source: str = "api",
        batch_id: str | None = None,
        input_json: dict[str, Any] | None = None,
    ) -> ReviewRecord:
        record = AuditReviewORM(
            id=str(uuid4()),
            batch_id=batch_id,
            form_id=result.form_id,
            form_version=result.form_version,
            status="running",
            source=source,
            input_json=input_json,
        )
        self.session.add(record)
        await self.session.flush()
        await self._save_completed_result(record, result, created_by="agent")
        await self.session.commit()
        await self.session.refresh(record)
        if batch_id:
            await self.refresh_batch_counts(batch_id)
        return await self._review_to_schema(record)

    async def mark_review_running(self, review_id: str) -> ReviewRecord:
        record = await self._get_review_orm(review_id)
        record.status = "running"
        record.error_message = None
        record.updated_at = _now()
        await self.session.commit()
        await self.session.refresh(record)
        if record.batch_id:
            await self.refresh_batch_counts(record.batch_id)
        return await self._review_to_schema(record)

    async def complete_review_with_result(
        self,
        review_id: str,
        result: AuditFormResult,
        *,
        created_by: str = "agent",
    ) -> ReviewRecord:
        record = await self._get_review_orm(review_id)
        await self._save_completed_result(record, result, created_by=created_by)
        await self.session.commit()
        await self.session.refresh(record)
        if record.batch_id:
            await self.refresh_batch_counts(record.batch_id)
        return await self._review_to_schema(record)

    async def mark_review_failed(self, review_id: str, message: str) -> ReviewRecord:
        record = await self._get_review_orm(review_id)
        record.status = "failed"
        record.error_message = message
        record.updated_at = _now()
        await self.session.commit()
        await self.session.refresh(record)
        if record.batch_id:
            await self.refresh_batch_counts(record.batch_id)
        return await self._review_to_schema(record)

    async def update_user_version(self, review_id: str, update: ReviewUpdate) -> ReviewRecord:
        record = await self._get_review_orm(review_id)
        if record.status != "completed":
            raise ValueError("Only completed reviews can be edited.")
        if update.user_version.form_id != record.form_id:
            raise ValueError("User version form_id must match the review.")
        if update.user_version.form_version != record.form_version:
            raise ValueError("User version form_version must match the review.")

        version = await self._create_result_version(
            record,
            update.user_version,
            kind="user",
            created_by="user",
        )
        record.current_user_result_version_id = version.id
        record.updated_at = _now()
        await self.session.commit()
        await self.session.refresh(record)
        return await self._review_to_schema(record)

    async def create_batch(
        self,
        *,
        total_count: int,
        template_id: str | None = None,
        input_json: dict[str, Any] | None = None,
    ) -> BatchRecord:
        now = _now()
        batch = AuditBatchORM(
            id=str(uuid4()),
            template_id=template_id,
            status="queued",
            source="batch",
            total_count=total_count,
            input_json=input_json,
            started_at=now,
        )
        self.session.add(batch)
        await self.session.commit()
        await self.session.refresh(batch)
        return self._batch_to_schema(batch)

    async def get_batch(self, batch_id: str) -> BatchRecord:
        batch = await self.session.get(AuditBatchORM, batch_id)
        if not batch:
            raise KeyError(f"Unknown batch: {batch_id}")
        return await self.refresh_batch_counts(batch_id)

    async def refresh_batch_counts(self, batch_id: str) -> BatchRecord:
        batch = await self.session.get(AuditBatchORM, batch_id)
        if not batch:
            raise KeyError(f"Unknown batch: {batch_id}")

        total = await self._count_reviews(batch_id)
        completed = await self._count_reviews(batch_id, "completed")
        failed = await self._count_reviews(batch_id, "failed")
        running = await self._count_reviews(batch_id, "running")
        batch.total_count = total
        batch.completed_count = completed
        batch.failed_count = failed
        if total == 0:
            batch.status = "queued"
        elif completed + failed >= total:
            batch.status = "failed" if failed else "completed"
            batch.completed_at = batch.completed_at or _now()
        elif running:
            batch.status = "running"
            batch.completed_at = None
        else:
            batch.status = "queued"
            batch.completed_at = None
        if batch.status == "running" and not batch.started_at:
            batch.started_at = _now()
        batch.updated_at = _now()
        await self.session.commit()
        await self.session.refresh(batch)
        return self._batch_to_schema(batch)

    async def add_feedback(self, feedback: FeedbackCreate) -> FeedbackCreate:
        await self._get_review_orm(feedback.review_id)
        self.session.add(
            FeedbackORM(
                id=str(uuid4()),
                review_id=feedback.review_id,
                rating=feedback.rating,
                comment=feedback.comment,
            )
        )
        await self.session.commit()
        return feedback

    async def add_evaluation(self, evaluation: EvaluationCreate) -> EvaluationRecord:
        await self._get_review_orm(evaluation.review_id)
        record = EvaluationORM(
            id=str(uuid4()),
            review_id=evaluation.review_id,
            evaluator=evaluation.evaluator,
            score=evaluation.score,
            notes=evaluation.notes,
            payload_json=evaluation.payload,
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return self._evaluation_to_schema(record)

    async def list_evaluations(self, review_id: str | None = None) -> list[EvaluationRecord]:
        statement = select(EvaluationORM).order_by(EvaluationORM.created_at.desc())
        if review_id:
            statement = statement.where(EvaluationORM.review_id == review_id)
        records = (await self.session.scalars(statement)).all()
        return [self._evaluation_to_schema(record) for record in records]

    async def feedback_count(self) -> int:
        return await self.session.scalar(select(func.count(FeedbackORM.id))) or 0

    async def review_count(self) -> int:
        return await self.session.scalar(select(func.count(AuditReviewORM.id))) or 0

    async def edited_review_count(self) -> int:
        original = aliased(AuditResultVersionORM)
        user_version = aliased(AuditResultVersionORM)
        statement = select(func.count(AuditReviewORM.id)).where(
            AuditReviewORM.original_result_version_id.is_not(None),
            AuditReviewORM.current_user_result_version_id.is_not(None),
        )
        statement = (
            statement.join(
                original,
                original.id == AuditReviewORM.original_result_version_id,
            )
            .join(
                user_version,
                user_version.id == AuditReviewORM.current_user_result_version_id,
            )
            .where(original.payload_hash != user_version.payload_hash)
        )
        return await self.session.scalar(statement) or 0

    async def _save_completed_result(
        self,
        record: AuditReviewORM,
        result: AuditFormResult,
        *,
        created_by: str,
    ) -> None:
        stamped = result.model_copy(deep=True, update={"id": record.id})
        original = await self._create_result_version(
            record,
            stamped,
            kind="original",
            created_by=created_by,
        )
        user = await self._create_result_version(
            record,
            stamped,
            kind="user",
            created_by=created_by,
        )
        record.form_id = stamped.form_id
        record.form_version = stamped.form_version
        record.status = "completed"
        record.error_message = None
        record.original_result_version_id = original.id
        record.current_user_result_version_id = user.id
        record.updated_at = _now()

    async def _create_result_version(
        self,
        record: AuditReviewORM,
        result: AuditFormResult,
        *,
        kind: str,
        created_by: str,
    ) -> AuditResultVersionORM:
        revision_statement = select(func.max(AuditResultVersionORM.revision)).where(
            AuditResultVersionORM.review_id == record.id,
            AuditResultVersionORM.kind == kind,
        )
        revision = (await self.session.scalar(revision_statement) or 0) + 1
        payload = _payload_for(result.model_copy(deep=True, update={"id": record.id}))
        version = AuditResultVersionORM(
            id=str(uuid4()),
            review_id=record.id,
            kind=kind,
            revision=revision,
            payload_json=payload,
            payload_hash=_payload_hash(payload),
            created_by=created_by,
        )
        self.session.add(version)
        await self.session.flush()
        self._add_projection_rows(record.id, version.id, kind, result)
        return version

    def _add_projection_rows(
        self,
        review_id: str,
        version_id: str,
        kind: str,
        result: AuditFormResult,
    ) -> None:
        for question_position, question in enumerate(result.questions, start=1):
            self.session.add(
                AuditQuestionAnswerORM(
                    id=str(uuid4()),
                    result_version_id=version_id,
                    review_id=review_id,
                    kind=kind,
                    question_id=question.id,
                    question_text=question.text,
                    answer=question.answer,
                    position=question_position,
                )
            )
            for sub_position, sub_question in enumerate(question.sub_questions, start=1):
                self.session.add(
                    AuditSubQuestionAnswerORM(
                        id=str(uuid4()),
                        result_version_id=version_id,
                        review_id=review_id,
                        kind=kind,
                        question_id=question.id,
                        subquestion_id=sub_question.id,
                        subquestion_text=sub_question.text,
                        answer=sub_question.answer,
                        reasoning=sub_question.reasoning,
                        citations=sub_question.citations,
                        position=sub_position,
                    )
                )

    async def _review_to_schema(self, record: AuditReviewORM) -> ReviewRecord:
        original = await self._load_result(record.original_result_version_id, record.id)
        user_version = await self._load_result(record.current_user_result_version_id, record.id)
        return ReviewRecord(
            id=record.id,
            form_id=record.form_id,
            form_version=record.form_version,
            status=record.status,  # type: ignore[arg-type]
            source=record.source,  # type: ignore[arg-type]
            batch_id=record.batch_id,
            input_json=record.input_json,
            original=original,
            user_version=user_version,
            error_message=record.error_message,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    async def _load_result(
        self,
        version_id: str | None,
        review_id: str,
    ) -> AuditFormResult | None:
        if not version_id:
            return None
        version = await self.session.get(AuditResultVersionORM, version_id)
        if not version:
            return None
        try:
            result = AuditFormResult.model_validate(version.payload_json)
        except ValidationError:
            try:
                result = AuditFormResult.model_validate(
                    _repair_result_payload_for_read(version.payload_json)
                )
            except ValidationError:
                return None
        return result.model_copy(deep=True, update={"id": review_id})

    async def _get_review_orm(self, review_id: str) -> AuditReviewORM:
        record = await self.session.get(AuditReviewORM, review_id)
        if not record:
            raise KeyError(f"Unknown review: {review_id}")
        return record

    async def _get_batch_template_orm(self, template_id: str) -> AuditBatchTemplateORM:
        record = await self.session.get(AuditBatchTemplateORM, template_id)
        if not record:
            raise KeyError(f"Unknown batch template: {template_id}")
        return record

    async def _count_reviews(self, batch_id: str, status: str | None = None) -> int:
        statement = select(func.count(AuditReviewORM.id)).where(AuditReviewORM.batch_id == batch_id)
        if status:
            statement = statement.where(AuditReviewORM.status == status)
        return await self.session.scalar(statement) or 0

    async def _latest_batch_for_template(self, template_id: str) -> AuditBatchORM | None:
        statement = (
            select(AuditBatchORM)
            .where(AuditBatchORM.template_id == template_id)
            .order_by(AuditBatchORM.created_at.desc())
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def _batch_count_for_template(self, template_id: str) -> int:
        statement = select(func.count(AuditBatchORM.id)).where(
            AuditBatchORM.template_id == template_id
        )
        return await self.session.scalar(statement) or 0

    async def _batch_template_to_schema(
        self,
        template: AuditBatchTemplateORM,
    ) -> BatchTemplateRecord:
        latest_run = await self._latest_batch_for_template(template.id)
        latest_run_schema = await self.refresh_batch_counts(latest_run.id) if latest_run else None
        run_count = await self._batch_count_for_template(template.id)
        items = [BatchReviewInput.model_validate(item) for item in template.items_json or []]
        return BatchTemplateRecord(
            id=template.id,
            name=template.name,
            description=template.description,
            form_id=template.form_id,
            form_version=template.form_version,
            synthetic=template.synthetic,
            synthetic_count=template.synthetic_count,
            input_mode=template.input_mode,  # type: ignore[arg-type]
            excel_column_map=template.excel_column_map or {},
            items=items,
            item_count=template.synthetic_count if template.synthetic else len(items),
            latest_run=latest_run_schema,
            run_count=run_count,
            created_at=template.created_at,
            updated_at=template.updated_at,
        )

    def _batch_to_schema(self, batch: AuditBatchORM) -> BatchRecord:
        input_json = batch.input_json or {}
        started_at = batch.started_at or batch.created_at
        completed_at = batch.completed_at
        duration_seconds = None
        if completed_at:
            duration_seconds = max(0.0, (completed_at - started_at).total_seconds())
        return BatchRecord(
            id=batch.id,
            template_id=batch.template_id,
            name=str(input_json.get("name") or ""),
            description=str(input_json.get("description") or ""),
            status=batch.status,  # type: ignore[arg-type]
            source=batch.source,
            total_count=batch.total_count,
            completed_count=batch.completed_count,
            failed_count=batch.failed_count,
            input_json=batch.input_json,
            error_message=batch.error_message,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration_seconds,
            created_at=batch.created_at,
            updated_at=batch.updated_at,
        )

    def _evaluation_to_schema(self, evaluation: EvaluationORM) -> EvaluationRecord:
        return EvaluationRecord(
            id=evaluation.id,
            review_id=evaluation.review_id,
            evaluator=evaluation.evaluator,
            score=evaluation.score,
            notes=evaluation.notes,
            payload=evaluation.payload_json,
            created_at=evaluation.created_at,
        )
