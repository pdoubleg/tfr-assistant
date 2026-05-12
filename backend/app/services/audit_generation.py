import asyncio
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.review_agent import run_file_review_agent
from app.core.config import Settings, get_settings
from app.db.session import AsyncSessionLocal
from app.models.audit import AuditFormResult, merge_with_canonical
from app.schemas.forms import AuditFormDefinition
from app.schemas.reviews import (
    BatchCreateRequest,
    BatchRecord,
    BatchReviewInput,
    ReviewGenerateRequest,
    ReviewRecord,
)
from app.services.catalog import FormCatalog
from app.services.review_repository import ReviewRepository
from app.services.status_reporter import NullStatusReporter, StatusReporter


class AuditFormGenerator(Protocol):
    async def generate(
        self,
        request: ReviewGenerateRequest,
        canonical: AuditFormDefinition,
    ) -> AuditFormResult: ...


class AuditResultValidator:
    def align_to_canonical(
        self,
        result: AuditFormResult,
        canonical: AuditFormDefinition,
    ) -> AuditFormResult:
        return merge_with_canonical(
            result,
            canonical.canonical,
            form_id=canonical.id,
            form_version=canonical.version,
            title=canonical.title,
            description=canonical.canonical.description,
        )


class SyntheticAuditFormGenerator:
    async def generate(
        self,
        request: ReviewGenerateRequest,
        canonical: AuditFormDefinition,
    ) -> AuditFormResult:
        result = canonical.canonical.model_copy(deep=True)
        questions = []
        for index, question in enumerate(result.questions, start=1):
            if question.sub_questions:
                sub_questions = [
                    sub_question.model_copy(
                        update={
                            "answer": sub_index == 1,
                            "reasoning": (
                                "Synthetic review evidence supports this opportunity."
                                if sub_index == 1
                                else ""
                            ),
                            "citations": (
                                f"Synthetic file note {index}; photo set {index:02d}."
                                if sub_index == 1
                                else ""
                            ),
                        }
                    )
                    for sub_index, sub_question in enumerate(question.sub_questions, start=1)
                ]
                questions.append(
                    question.model_copy(
                        update={
                            "comments": None,
                            "citations": None,
                            "sub_questions": sub_questions,
                        }
                    )
                )
            else:
                questions.append(
                    question.model_copy(
                        update={
                            "comments": (
                                question.comments
                                or "Synthetic review evidence supports this question answer."
                            ),
                            "citations": (
                                question.citations
                                or f"Synthetic file note {index}; document set {index:02d}."
                            ),
                            "sub_questions": None,
                        }
                    )
                )

        outcome = (
            "Does Not Meet" if any(question.answer == "No" for question in questions) else "Meets"
        )
        return result.model_copy(
            update={
                "title": self._title_for(request, canonical),
                "questions": questions,
                "overall_outcome": outcome,
                "outcome_justification": (
                    "Synthetic review generated for local development and smoke testing."
                ),
            }
        )

    def _title_for(self, request: ReviewGenerateRequest, canonical: AuditFormDefinition) -> str:
        if request.claim_number:
            return f"Claim {request.claim_number} {canonical.title}"
        return f"Synthetic {canonical.title}"


@dataclass(slots=True)
class AgentAuditFormGenerator:
    catalog: FormCatalog

    async def generate(
        self,
        request: ReviewGenerateRequest,
        canonical: AuditFormDefinition,
    ) -> AuditFormResult:
        form_path = self.catalog.path_for(canonical.id, canonical.version)
        return await run_file_review_agent(
            claim_number=request.claim_number,
            effective_date=request.effective_date,
            instructions=request.instructions,
            path_to_questionnaire=str(form_path),
            user_prompt=request.prompt,
            audit_scope=canonical.audit_scope or "",
            tool_instructions=canonical.tool_instructions or "",
        )


@dataclass(slots=True)
class AuditGenerationService:
    session: AsyncSession
    settings: Settings = field(default_factory=get_settings)
    catalog: FormCatalog = field(init=False)
    repository: ReviewRepository = field(init=False)
    validator: AuditResultValidator = field(init=False)

    def __post_init__(self) -> None:
        self.catalog = FormCatalog(self.settings.form_catalog_dir)
        self.repository = ReviewRepository(self.session)
        self.validator = AuditResultValidator()

    async def generate_new_review(
        self,
        request: ReviewGenerateRequest,
        *,
        source: str,
        reporter: StatusReporter | None = None,
    ) -> ReviewRecord:
        reporter = reporter or NullStatusReporter()
        reporter.in_progress("Preparing audit review record...", progress=15)
        review = await self.repository.create_review_placeholder(
            form_id=request.form_id,
            form_version=request.form_version,
            source=source,
            input_json=request.model_dump(mode="json"),
            status="running",
        )
        return await self.generate_for_review(
            review.id,
            request,
            reporter=reporter,
        )

    async def generate_for_review(
        self,
        review_id: str,
        request: ReviewGenerateRequest,
        *,
        reporter: StatusReporter | None = None,
    ) -> ReviewRecord:
        reporter = reporter or NullStatusReporter()
        try:
            reporter.in_progress("Loading canonical audit form...", progress=25)
            canonical = self.catalog.get_form(request.form_id, request.form_version)
            await self.repository.mark_review_running(review_id)

            reporter.in_progress("Running audit form generator...", progress=45)
            generator = self._generator_for(request)
            generated = await generator.generate(request, canonical)

            reporter.in_progress("Validating generated audit output...", progress=75)
            aligned = self.validator.align_to_canonical(generated, canonical)

            reporter.in_progress(
                "Saving immutable original and editable user version...",
                progress=90,
            )
            review = await self.repository.complete_review_with_result(review_id, aligned)
            reporter.completed("Audit review saved.", progress=100)
            return review
        except Exception as exc:
            reporter.error("Audit review generation failed.", progress=100)
            return await self.repository.mark_review_failed(review_id, str(exc))

    def _generator_for(self, request: ReviewGenerateRequest) -> AuditFormGenerator:
        if request.synthetic:
            return SyntheticAuditFormGenerator()
        return AgentAuditFormGenerator(self.catalog)


@dataclass(slots=True)
class ChatReviewGenerationService:
    session: AsyncSession
    settings: Settings = field(default_factory=get_settings)

    async def generate(
        self,
        request: ReviewGenerateRequest,
        *,
        reporter: StatusReporter | None = None,
    ) -> ReviewRecord:
        service = AuditGenerationService(self.session, self.settings)
        return await service.generate_new_review(
            request,
            source="chat_tool",
            reporter=reporter,
        )


@dataclass(slots=True)
class BatchReviewGenerationService:
    session: AsyncSession
    settings: Settings = field(default_factory=get_settings)
    repository: ReviewRepository = field(init=False)

    def __post_init__(self) -> None:
        self.repository = ReviewRepository(self.session)

    async def create_batch(self, request: BatchCreateRequest) -> BatchRecord:
        self._validate_registered_forms(request)
        items = self._items_for_request(request)
        batch = await self.repository.create_batch(
            total_count=len(items),
            input_json=request.model_dump(mode="json"),
        )
        for item in items:
            review_request = self._request_from_item(item, request)
            input_json = review_request.model_dump(mode="json")
            input_json["batch_run_name"] = request.name
            input_json["batch_description"] = request.description
            input_json["batch_id"] = batch.id
            await self.repository.create_review_placeholder(
                form_id=review_request.form_id,
                form_version=review_request.form_version,
                source="batch",
                batch_id=batch.id,
                input_json=input_json,
            )
        return await self.repository.refresh_batch_counts(batch.id)

    async def create_batch_from_template(self, template_id: str) -> BatchRecord:
        template = await self.repository.get_batch_template(template_id)
        request = BatchCreateRequest(
            name=template.name,
            description=template.description,
            form_id=template.form_id,
            form_version=template.form_version,
            synthetic=template.synthetic,
            synthetic_count=template.synthetic_count,
            input_mode=template.input_mode,
            excel_column_map=template.excel_column_map,
            items=template.items,
        )
        self._validate_registered_forms(request)
        items = self._items_for_request(request)
        batch = await self.repository.create_batch(
            total_count=len(items),
            template_id=template.id,
            input_json=request.model_dump(mode="json"),
        )
        for item in items:
            review_request = self._request_from_item(item, request)
            input_json = review_request.model_dump(mode="json")
            input_json["batch_run_name"] = template.name
            input_json["batch_description"] = template.description
            input_json["batch_template_id"] = template.id
            input_json["batch_id"] = batch.id
            await self.repository.create_review_placeholder(
                form_id=review_request.form_id,
                form_version=review_request.form_version,
                source="batch",
                batch_id=batch.id,
                input_json=input_json,
            )
        return await self.repository.refresh_batch_counts(batch.id)

    async def run_batch(self, batch_id: str) -> None:
        reviews = await self.repository.list_reviews(batch_id=batch_id)
        semaphore = asyncio.Semaphore(max(1, self.settings.batch_concurrency))

        async def run_review(review: ReviewRecord) -> None:
            if review.status != "queued":
                return
            async with semaphore:
                async with AsyncSessionLocal() as session:
                    repository = ReviewRepository(session)
                    fresh = await repository.get_review(review.id)
                    if fresh.status != "queued":
                        return
                    request = ReviewGenerateRequest.model_validate(fresh.input_json or {})
                    service = AuditGenerationService(session, self.settings)
                    await service.generate_for_review(fresh.id, request)

        await asyncio.gather(*(run_review(review) for review in reviews))

    def _request_from_item(
        self,
        item: BatchReviewInput,
        batch_request: BatchCreateRequest,
    ) -> ReviewGenerateRequest:
        return ReviewGenerateRequest(
            prompt=item.prompt,
            claim_number=item.claim_number,
            effective_date=item.effective_date,
            instructions=item.instructions,
            form_id=item.form_id or batch_request.form_id,
            form_version=item.form_version or batch_request.form_version,
            source_file_ids=item.source_file_ids,
            synthetic=batch_request.synthetic if item.synthetic is None else item.synthetic,
        )

    def _items_for_request(self, request: BatchCreateRequest) -> list[BatchReviewInput]:
        if request.synthetic:
            count = request.synthetic_count or len(request.items)
            if count <= 0:
                return request.items
            return [
                BatchReviewInput(
                    claim_number=item.claim_number,
                    effective_date=item.effective_date,
                    instructions=item.instructions,
                    prompt=item.prompt,
                    source_file_ids=item.source_file_ids,
                    form_id=item.form_id,
                    form_version=item.form_version,
                    synthetic=item.synthetic,
                )
                for item in (
                    request.items
                    if request.items
                    else [BatchReviewInput(synthetic=True) for _ in range(count)]
                )
            ][:count]
        return request.items

    def _validate_registered_forms(self, request: BatchCreateRequest) -> None:
        catalog = FormCatalog(self.settings.form_catalog_dir)
        pairs = [(request.form_id, request.form_version)]
        pairs.extend(
            (
                item.form_id or request.form_id,
                item.form_version or request.form_version,
            )
            for item in request.items
        )
        for form_id, form_version in pairs:
            try:
                catalog.get_form(form_id, form_version)
            except KeyError as exc:
                raise ValueError(
                    f"Registered form {form_id}@{form_version} was not found in the form catalog."
                ) from exc


async def run_batch_job(batch_id: str, settings: Settings | None = None) -> None:
    async with AsyncSessionLocal() as session:
        service = BatchReviewGenerationService(session, settings or get_settings())
        await service.run_batch(batch_id)
