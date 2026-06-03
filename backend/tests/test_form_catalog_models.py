from app.models.audit import AuditFormResult, FormQuestion
from app.schemas.forms import AuditFormRegistration
from app.services.catalog import FormCatalog


def test_form_catalog_preserves_generation_model_metadata(tmp_path) -> None:
    catalog = FormCatalog(tmp_path)
    registration = AuditFormRegistration(
        id="demo_review",
        version="v0.1",
        title="Demo Review",
        model_name="gpt-5.4-mini",
        description="Demo form.",
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
    assert summary.model_name == "gpt-5.4-mini"
