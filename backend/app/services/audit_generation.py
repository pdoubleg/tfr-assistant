from dataclasses import dataclass, field
from typing import Protocol
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.review_agent import (
    AuditIntakeFailure,
    run_completed_intake_agent,
    run_file_review_agent,
    run_synthetic_review_agent,
)
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
from app.services.intake_documents import IntakeDocumentStore
from app.services.review_repository import ReviewRepository
from app.services.status_reporter import NullStatusReporter, StatusReporter


@dataclass(slots=True)
class GeneratedAuditResult:
    result: AuditFormResult
    input_json_updates: dict[str, object] = field(default_factory=dict)


class AuditFormGenerator(Protocol):
    async def generate(
        self,
        request: ReviewGenerateRequest,
        canonical: AuditFormDefinition,
    ) -> GeneratedAuditResult: ...


class AuditResultValidator:
    def align_to_canonical(
        self,
        result: AuditFormResult,
        canonical: AuditFormDefinition,
        *,
        require_citations: bool = True,
        require_yes_question_evidence: bool = True,
    ) -> AuditFormResult:
        return merge_with_canonical(
            result,
            canonical.canonical,
            form_id=canonical.id,
            form_version=canonical.version,
            title=canonical.title,
            description=canonical.canonical.description,
            require_citations=require_citations,
            require_yes_question_evidence=require_yes_question_evidence,
        )


@dataclass(slots=True)
class AgentAuditFormGenerator:
    catalog: FormCatalog
    settings: Settings
    mode: str = "review"

    async def generate(
        self,
        request: ReviewGenerateRequest,
        canonical: AuditFormDefinition,
    ) -> GeneratedAuditResult:
        form_path = self.catalog.path_for(canonical.id, canonical.version)
        if self.mode == "synthetic":
            result = await run_synthetic_review_agent(
                claim_number=request.claim_number,
                effective_date=request.effective_date,
                instructions=request.instructions or request.generation_prompt,
                path_to_questionnaire=str(form_path),
                user_prompt=request.prompt or request.generation_prompt,
                knowledge_docs=canonical.knowledge_docs,
                active_settings=self.settings,
            )
        else:
            result = await run_file_review_agent(
                claim_number=request.claim_number,
                effective_date=request.effective_date,
                instructions=request.instructions,
                path_to_questionnaire=str(form_path),
                user_prompt=request.prompt,
                tools=canonical.tools,
                knowledge_docs=canonical.knowledge_docs,
                active_settings=self.settings,
            )
        return GeneratedAuditResult(result=result)


class AuditIntakeFailureError(RuntimeError):
    def __init__(self, failure: AuditIntakeFailure) -> None:
        message = failure.reason
        if failure.details:
            message = f"{message}\n\n{failure.details}"
        super().__init__(message)
        self.failure = failure


@dataclass(slots=True)
class CompletedIntakeAuditFormGenerator:
    catalog: FormCatalog
    settings: Settings

    async def generate(
        self,
        request: ReviewGenerateRequest,
        canonical: AuditFormDefinition,
    ) -> GeneratedAuditResult:
        document_id = request.source_file_ids[0] if request.source_file_ids else ""
        if not document_id:
            raise ValueError("Completed intake reviews require one source document.")
        document_store = IntakeDocumentStore(self.settings)
        document_path = document_store.resolve(document_id)
        document = document_store.read_document(document_id)
        if not document.content.strip():
            raise ValueError(f"Intake document has no extractable text: {document_id}")
        form_path = self.catalog.path_for(canonical.id, canonical.version)
        output = await run_completed_intake_agent(
            document_text=document.content,
            document_name=document_path.name,
            path_to_questionnaire=str(form_path),
            instructions=request.instructions,
            knowledge_docs=canonical.knowledge_docs,
            active_settings=self.settings,
        )
        if isinstance(output, AuditIntakeFailure):
            raise AuditIntakeFailureError(output)
        updates = {
            "claim_number": output.claim_number.strip(),
            "form_metadata": output.form_metadata,
            "intake_document_id": document_id,
            "intake_document_name": document_path.name,
            "intake_document_type": document.file_type,
        }
        return GeneratedAuditResult(
            result=output.result,
            input_json_updates=updates,
        )


@dataclass(slots=True)
class ManualEntryAuditFormGenerator:
    async def generate(
        self,
        request: ReviewGenerateRequest,
        canonical: AuditFormDefinition,
    ) -> GeneratedAuditResult:
        if request.manual_result is None:
            raise ValueError("Manual entry reviews require a submitted audit form.")
        if request.manual_result.form_id != canonical.id:
            raise ValueError("Manual entry form does not match the selected batch form.")
        if request.manual_result.form_version != canonical.version:
            raise ValueError("Manual entry form version does not match the selected batch form.")
        return GeneratedAuditResult(result=request.manual_result)


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
            if generated.input_json_updates:
                await self.repository.merge_review_input_json(
                    review_id,
                    generated.input_json_updates,
                )

            reporter.in_progress("Validating generated audit output...", progress=75)
            manual_entry = request.input_mode == "manual_entry"
            aligned = self.validator.align_to_canonical(
                generated.result,
                canonical,
                require_citations=not manual_entry,
                require_yes_question_evidence=not manual_entry,
            )

            reporter.in_progress(
                "Saving immutable original and editable user version...",
                progress=90,
            )
            created_by = "user" if request.input_mode == "manual_entry" else "agent"
            review = await self.repository.complete_review_with_result(
                review_id,
                aligned,
                created_by=created_by,
            )
            reporter.completed("Audit review saved.", progress=100)
            return review
        except Exception as exc:
            reporter.error("Audit review generation failed.", progress=100)
            return await self.repository.mark_review_failed(review_id, str(exc))

    def _generator_for(self, request: ReviewGenerateRequest) -> AuditFormGenerator:
        if request.input_mode == "manual_entry":
            return ManualEntryAuditFormGenerator()
        if request.input_mode == "completed_intake":
            return CompletedIntakeAuditFormGenerator(self.catalog, self.settings)
        if request.synthetic or request.input_mode == "synthetic":
            return AgentAuditFormGenerator(self.catalog, self.settings, mode="synthetic")
        return AgentAuditFormGenerator(self.catalog, self.settings)


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
        source = self._source_for_request(request)
        batch = await self.repository.create_batch(
            total_count=len(items),
            input_json=request.model_dump(mode="json"),
            source=source,
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
                source=source,
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
            generation_prompt=template.generation_prompt,
            excel_column_map=template.excel_column_map,
            items=template.items,
        )
        self._validate_registered_forms(request)
        items = self._items_for_request(request)
        source = self._source_for_request(request)
        batch = await self.repository.create_batch(
            total_count=len(items),
            template_id=template.id,
            input_json=request.model_dump(mode="json"),
            source=source,
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
                source=source,
                batch_id=batch.id,
                input_json=input_json,
            )
        return await self.repository.refresh_batch_counts(batch.id)

    async def run_batch(self, batch_id: str) -> None:
        await self.repository.mark_batch_running(batch_id)

        while True:
            async with AsyncSessionLocal() as session:
                repository = ReviewRepository(session)
                batch = await repository.get_batch(batch_id)
                if batch.status != "running":
                    return
                review = await repository.next_queued_batch_review(batch_id)
                if not review:
                    await repository.refresh_batch_counts(batch_id)
                    return

            async with AsyncSessionLocal() as session:
                fresh_repository = ReviewRepository(session)
                fresh = await fresh_repository.get_review(review.id)
                if fresh.status != "running":
                    continue
                request = ReviewGenerateRequest.model_validate(fresh.input_json or {})
                service = AuditGenerationService(session, self.settings)
                completed = await service.generate_for_review(fresh.id, request)
                if completed.status == "failed" and request.input_mode == "completed_intake":
                    await ReviewRepository(session).pause_batch(batch_id)
                    return

    def _request_from_item(
        self,
        item: BatchReviewInput,
        batch_request: BatchCreateRequest,
    ) -> ReviewGenerateRequest:
        return ReviewGenerateRequest(
            prompt=item.prompt or item.generation_prompt or batch_request.generation_prompt,
            claim_number=item.claim_number,
            effective_date=item.effective_date,
            instructions=(
                item.instructions or item.generation_prompt or batch_request.generation_prompt
            ),
            form_id=batch_request.form_id,
            form_version=batch_request.form_version,
            source_file_ids=item.source_file_ids,
            manual_result=item.manual_result,
            synthetic=(
                batch_request.synthetic or batch_request.input_mode == "synthetic"
                if item.synthetic is None
                else item.synthetic
            ),
            input_mode=batch_request.input_mode,
            generation_prompt=item.generation_prompt or batch_request.generation_prompt,
        )

    def _items_for_request(self, request: BatchCreateRequest) -> list[BatchReviewInput]:
        if request.synthetic or request.input_mode == "synthetic":
            count = request.synthetic_count or len(request.items)
            if count <= 0:
                return request.items
            source_items = request.items or [BatchReviewInput(synthetic=True) for _ in range(count)]
            return [
                BatchReviewInput(
                    claim_number=item.claim_number or f"SYNTH_{uuid4().hex[:8].upper()}",
                    effective_date=item.effective_date,
                    instructions=item.instructions or request.generation_prompt,
                    prompt=item.prompt or request.generation_prompt,
                    generation_prompt=item.generation_prompt or request.generation_prompt,
                    source_file_ids=item.source_file_ids,
                    synthetic=item.synthetic,
                )
                for item in source_items
            ][:count]
        return request.items

    def _validate_registered_forms(self, request: BatchCreateRequest) -> None:
        catalog = FormCatalog(self.settings.form_catalog_dir)
        for index, item in enumerate(request.items, start=1):
            if item.form_id and item.form_id != request.form_id:
                raise ValueError(
                    f"Review row {index} uses {item.form_id}, but batches must use one form."
                )
            if item.form_version and item.form_version != request.form_version:
                raise ValueError(
                    f"Review row {index} uses {item.form_version}, "
                    "but batches must use one form version."
                )
            if request.input_mode == "completed_intake" and len(item.source_file_ids) != 1:
                raise ValueError("Completed intake reviews require exactly one selected document.")
            if request.input_mode == "manual_entry":
                if item.manual_result is None:
                    raise ValueError(f"Manual entry row {index} needs a completed audit form.")
                if item.manual_result.form_id != request.form_id:
                    raise ValueError(f"Manual entry row {index} uses a different form.")
                if item.manual_result.form_version != request.form_version:
                    raise ValueError(f"Manual entry row {index} uses a different form version.")
        try:
            catalog.get_form(request.form_id, request.form_version)
        except KeyError as exc:
            raise ValueError(
                f"Registered form {request.form_id}@{request.form_version} was not "
                "found in the form catalog."
            ) from exc

    def _source_for_request(self, request: BatchCreateRequest) -> str:
        if request.input_mode == "manual_entry":
            return "manual_entry"
        if request.input_mode == "completed_intake":
            return "completed_intake"
        if request.synthetic or request.input_mode == "synthetic":
            return "synthetic"
        if request.input_mode == "upload":
            return "batch_upload"
        return "batch_manual"


async def run_batch_job(batch_id: str, settings: Settings | None = None) -> None:
    async with AsyncSessionLocal() as session:
        service = BatchReviewGenerationService(session, settings or get_settings())
        await service.run_batch(batch_id)
