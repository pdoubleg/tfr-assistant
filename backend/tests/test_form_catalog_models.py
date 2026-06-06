from app.models.audit import AuditFormResult, FormQuestion
from app.schemas.forms import AuditFormRegistration, ReviewAgentToolName
from app.services.catalog import FormCatalog


def test_form_catalog_preserves_generation_model_metadata(tmp_path) -> None:
    catalog = FormCatalog(tmp_path)
    registration = AuditFormRegistration(
        id="demo_review",
        version="v0.1",
        title="Demo Review",
        model_name="gpt-5.4-mini",
        description="Demo form.",
        tools=["Documents", "Policy Docs", "Notes"],
        include_state_compliance=True,
        canonical=AuditFormResult(
            form_id="demo_review",
            form_version="v0.1",
            title="Demo Review",
            description="Demo form.",
            questions=[
                FormQuestion(
                    id="Q1",
                    text="Is the file complete?",
                    answer="Yes",
                    comments="Canonical placeholder.",
                    citations="Canonical placeholder.",
                )
            ],
            overall_outcome="Meets",
            outcome_justification="Canonical placeholder.",
        ),
    )

    saved = catalog.register_form(registration)
    summary = catalog.list_forms()[0]

    assert saved.model_name == "gpt-5.4-mini"
    assert saved.catalog_key == "demo_review@v0.1-gpt-5.4-mini"
    assert saved.tools == [
        ReviewAgentToolName.GET_CLAIM_DOCUMENTS_METADATA,
        ReviewAgentToolName.GET_CLAIM_DOCUMENT_CONTENT,
        ReviewAgentToolName.GET_POLICY_DOCUMENTS_METADATA,
        ReviewAgentToolName.GET_POLICY_DOCUMENT_CONTENT,
        ReviewAgentToolName.GET_CLAIM_NOTES,
    ]
    assert saved.include_state_compliance is True
    assert summary.model_name == "gpt-5.4-mini"
    assert summary.tools == saved.tools
    assert summary.include_state_compliance is True
