from __future__ import annotations

from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.db.models import EvalCaseORM, EvalDatasetORM
from app.db.session import AsyncSessionLocal
from app.models.audit import AuditFormResult
from app.schemas.evaluations import EvalCaseCreate, EvalDatasetCreate
from app.schemas.forms import AuditFormRegistration
from app.schemas.optimizations import OptimizationDemoFixtureRecord
from app.schemas.prompts import PromptActivationUpdate, PromptVersionCreate
from app.services.catalog import FormCatalog
from app.services.evaluation_service import EvaluationRepository
from app.services.prompt_registry import PromptRegistryRepository

DEMO_FORM_ID = "demo_receipt_policy"
DEMO_FORM_VERSION = "v0.1"
DEMO_PROMPT = "Complete the receipt reimbursement audit from the note. Apply policy carefully."


async def ensure_demo_fixture(settings: Settings | None = None) -> OptimizationDemoFixtureRecord:
    settings = settings or get_settings()
    catalog = FormCatalog(settings.form_catalog_dir)
    try:
        definition = catalog.get_form(DEMO_FORM_ID, DEMO_FORM_VERSION)
    except KeyError:
        definition = catalog.register_form(_demo_form_registration())
    async with AsyncSessionLocal() as session:
        await _ensure_demo_prompt(session, catalog)
        existing = (
            await session.scalars(
                select(EvalDatasetORM).where(
                    EvalDatasetORM.form_id == DEMO_FORM_ID,
                    EvalDatasetORM.form_version == DEMO_FORM_VERSION,
                    EvalDatasetORM.source_kind == "optimization_demo",
                )
            )
        ).first()
        if existing:
            case_count = len(
                (
                    await session.scalars(
                        select(EvalCaseORM).where(EvalCaseORM.dataset_id == existing.id)
                    )
                ).all()
            )
            return OptimizationDemoFixtureRecord(
                dataset_id=existing.id,
                form_id=DEMO_FORM_ID,
                form_version=DEMO_FORM_VERSION,
                case_count=case_count,
                created=False,
            )
        dataset = await EvaluationRepository(session).create_dataset(
            EvalDatasetCreate(
                name="GEPA Demo - Receipt Policy",
                description=(
                    "Isolated 20-case receipt policy fixture for prompt optimization demos."
                ),
                form_id=DEMO_FORM_ID,
                form_version=DEMO_FORM_VERSION,
                source_kind="optimization_demo",
                source_metadata={"purpose": "gepa_prompt_optimization"},
                cases=_demo_cases(definition.canonical),
            )
        )
        return OptimizationDemoFixtureRecord(
            dataset_id=dataset.id,
            form_id=DEMO_FORM_ID,
            form_version=DEMO_FORM_VERSION,
            case_count=len(dataset.cases),
            created=True,
        )


def _demo_form_registration() -> AuditFormRegistration:
    payload = {
        "id": DEMO_FORM_ID,
        "version": DEMO_FORM_VERSION,
        "title": "Receipt Reimbursement Policy Audit",
        "description": "Demo form for GEPA prompt optimization using short receipt notes.",
        "canonical": {
            "form_id": DEMO_FORM_ID,
            "form_version": DEMO_FORM_VERSION,
            "title": "Receipt Reimbursement Policy Audit",
            "description": "Determine whether a reimbursement request meets policy.",
            "questions": [
                {
                    "id": "Q1",
                    "text": "Is the purchase business related and allowed by policy?",
                    "answer": "Yes",
                    "comments": "Canonical template.",
                    "citations": "Policy note.",
                    "sub_questions": None,
                },
                {
                    "id": "Q2",
                    "text": "Is the expense amount within policy limits?",
                    "answer": "Yes",
                    "comments": "Canonical template.",
                    "citations": "Policy note.",
                    "sub_questions": None,
                },
                {
                    "id": "Q3",
                    "text": "Does the request avoid prohibited or review-required drivers?",
                    "answer": "Yes",
                    "comments": None,
                    "citations": None,
                    "sub_questions": [
                        {
                            "id": "Q3.1",
                            "text": "Alcohol is present.",
                            "reasoning": "",
                            "citations": "",
                            "answer": False,
                        },
                        {
                            "id": "Q3.2",
                            "text": "Gift card or cash-equivalent purchase is present.",
                            "reasoning": "",
                            "citations": "",
                            "answer": False,
                        },
                        {
                            "id": "Q3.3",
                            "text": "Personal or non-business item is present.",
                            "reasoning": "",
                            "citations": "",
                            "answer": False,
                        },
                        {
                            "id": "Q3.4",
                            "text": "Receipt or required documentation is missing.",
                            "reasoning": "",
                            "citations": "",
                            "answer": False,
                        },
                    ],
                },
            ],
            "overall_outcome": "Meets",
            "outcome_justification": "Canonical template.",
        },
    }
    return AuditFormRegistration.model_validate(payload)


async def _ensure_demo_prompt(session, catalog: FormCatalog) -> None:
    repository = PromptRegistryRepository(session, catalog)
    active = await repository.resolve_active(
        form_id=DEMO_FORM_ID,
        form_version=DEMO_FORM_VERSION,
    )
    if active.version_id:
        return
    version = await repository.create_version(
        PromptVersionCreate(
            form_id=DEMO_FORM_ID,
            form_version=DEMO_FORM_VERSION,
            text=DEMO_PROMPT,
            source_kind="handcrafted",
            commit_message="Registered demo receipt policy prompt.",
            created_by="system",
            applicable_form_versions=[DEMO_FORM_VERSION],
            alias="production",
        )
    )
    await repository.set_activation(
        PromptActivationUpdate(
            family_id=version.family_id,
            version_id=version.id,
            form_version=DEMO_FORM_VERSION,
            activated_by="system",
            notes="Activated demo receipt policy prompt.",
        )
    )


def _demo_cases(canonical: AuditFormResult) -> list[EvalCaseCreate]:
    specs = [
        ("RCPT-001", "Client lunch $42 with itemized receipt; no alcohol.", "Meets", []),
        (
            "RCPT-002",
            "Team dinner $87 with wine listed on receipt.",
            "Does Not Meet",
            ["Q2", "Q3.1"],
        ),
        ("RCPT-003", "Office supplies $31, receipt attached.", "Meets", []),
        ("RCPT-004", "Coffee meeting $18, no receipt attached.", "Does Not Meet", ["Q3.4"]),
        ("RCPT-005", "Gift card purchase $25 for client raffle.", "Does Not Meet", ["Q3.2"]),
        ("RCPT-006", "Dinner $59 with client, itemized receipt, no alcohol.", "Meets", []),
        ("RCPT-007", "Dinner $60 with client, itemized receipt, no alcohol.", "Meets", []),
        (
            "RCPT-008",
            "Dinner $61 with client, itemized receipt, no alcohol.",
            "Does Not Meet",
            ["Q2"],
        ),
        ("RCPT-009", "Hotel minibar snacks $14 during trip.", "Does Not Meet", ["Q3.3"]),
        ("RCPT-010", "Taxi from airport to client site $38, receipt attached.", "Meets", []),
        ("RCPT-011", "Conference meal $72, no alcohol, agenda attached.", "Does Not Meet", ["Q2"]),
        ("RCPT-012", "Restaurant receipt $54 includes beer.", "Does Not Meet", ["Q3.1"]),
        ("RCPT-013", "Printer paper $22 for project room, receipt attached.", "Meets", []),
        ("RCPT-014", "Personal headphones $49 bought during travel.", "Does Not Meet", ["Q3.3"]),
        (
            "RCPT-015",
            "Client breakfast $28, receipt photo unreadable/missing details.",
            "Does Not Meet",
            ["Q3.4"],
        ),
        (
            "RCPT-016",
            "Team dinner $92 includes cocktails and dessert.",
            "Does Not Meet",
            ["Q2", "Q3.1"],
        ),
        ("RCPT-017", "Parking for client visit $16, receipt attached.", "Meets", []),
        ("RCPT-018", "Visa prepaid card $100 for vendor thank-you.", "Does Not Meet", ["Q3.2"]),
        (
            "RCPT-019",
            "Lunch $63, missing attendee list but receipt attached.",
            "Does Not Meet",
            ["Q2", "Q3.4"],
        ),
        ("RCPT-020", "Client lunch $55 with itemized receipt and attendee names.", "Meets", []),
    ]
    cases: list[EvalCaseCreate] = []
    for claim_number, note, outcome, failing in specs:
        result = _demo_result(canonical, note, outcome, failing)
        cases.append(
            EvalCaseCreate(
                claim_number=claim_number,
                effective_date="2026-05-19",
                instructions=(
                    "Policy: business meals up to $60 are allowed; over $60 needs review. "
                    "Alcohol, gift cards/cash equivalents, personal items, and missing or "
                    f"unreadable documentation need review.\nReceipt note: {note}"
                ),
                input={"prompt": f"Receipt note: {note}"},
                ground_truths=[
                    {
                        "reference_kind": "R2",
                        "result": result,
                        "reviewer": "demo-policy",
                        "source_metadata": {"demo": True},
                    }
                ],
            )
        )
    return cases


def _demo_result(
    canonical: AuditFormResult,
    note: str,
    outcome: str,
    failing: list[str],
) -> AuditFormResult:
    questions = []
    for question in canonical.questions:
        if question.id == "Q1":
            fail = "Q1" in failing
            questions.append(
                question.model_copy(
                    update={
                        "answer": "No" if fail else "Yes",
                        "comments": (
                            "The note describes a non-business or disallowed purchase."
                            if fail
                            else "The purchase appears business related."
                        ),
                    }
                )
            )
        elif question.id == "Q2":
            fail = "Q2" in failing
            questions.append(
                question.model_copy(
                    update={
                        "answer": "No" if fail else "Yes",
                        "comments": (
                            "The amount exceeds the $60 policy threshold."
                            if fail
                            else "The amount is within the $60 policy threshold."
                        ),
                    }
                )
            )
        elif question.id == "Q3":
            sub_questions = []
            for sub_question in question.sub_questions or []:
                active = sub_question.id in failing
                sub_questions.append(
                    sub_question.model_copy(
                        update={
                            "answer": active,
                            "reasoning": (
                                f"{sub_question.text} Evidence from note: {note}" if active else ""
                            ),
                            "citations": "Receipt note." if active else "",
                        }
                    )
                )
            questions.append(
                question.model_copy(
                    update={
                        "answer": "No" if any(sub.answer for sub in sub_questions) else "Yes",
                        "sub_questions": sub_questions,
                    }
                )
            )
    return canonical.model_copy(
        update={
            "questions": questions,
            "overall_outcome": outcome,
            "outcome_justification": (
                "The reimbursement needs review because one or more policy drivers apply."
                if outcome != "Meets"
                else "No policy exceptions are present in the note."
            ),
        }
    )
