import json
from pathlib import Path

from app.schemas.forms import AuditFormDefinition, AuditFormRegistration, AuditFormSummary


class FormCatalog:
    def __init__(self, catalog_dir: Path) -> None:
        self.catalog_dir = catalog_dir
        self.catalog_dir.mkdir(parents=True, exist_ok=True)

    def list_forms(self, *, published_only: bool = False) -> list[AuditFormSummary]:
        return [
            AuditFormSummary(
                id=form.id,
                version=form.version,
                title=form.title,
                published=form.published,
                form_kind=form.form_kind,
                model_name=form.model_name,
                description=form.description,
                tools=form.tools,
                knowledge_docs=form.knowledge_docs,
                include_state_compliance=form.include_state_compliance,
                question_count=len(form.canonical.questions),
                sub_question_count=sum(
                    len(getattr(question, "sub_questions", None) or [])
                    for question in form.canonical.questions
                ),
                created_at=form.created_at,
            )
            for form in self._load_all()
            if not published_only or form.published
        ]

    def get_form(self, form_id: str, version: str) -> AuditFormDefinition:
        path = self.path_for(form_id, version)
        if not path.exists():
            raise KeyError(f"Unknown audit form: {form_id}@{version}")
        return AuditFormDefinition.model_validate_json(path.read_text(encoding="utf-8"))

    def get_published_form(self, form_id: str, version: str) -> AuditFormDefinition:
        definition = self.get_form(form_id, version)
        if not definition.published:
            raise PermissionError(f"Audit form {form_id}@{version} is not published.")
        return definition

    def register_form(self, registration: AuditFormRegistration) -> AuditFormDefinition:
        definition = AuditFormDefinition(**registration.model_dump())
        path = self.path_for(definition.id, definition.version)
        if path.exists():
            raise ValueError(f"Audit form {definition.id}@{definition.version} already exists.")
        self._write_form(definition)
        return definition

    def set_published(self, form_id: str, version: str, published: bool) -> AuditFormDefinition:
        definition = self.get_form(form_id, version).model_copy(update={"published": published})
        self._write_form(definition)
        return definition

    def _load_all(self) -> list[AuditFormDefinition]:
        forms: list[AuditFormDefinition] = []
        for path in sorted(self.catalog_dir.glob("*.json")):
            forms.append(AuditFormDefinition.model_validate_json(path.read_text(encoding="utf-8")))
        return forms

    def path_for(self, form_id: str, version: str) -> Path:
        safe_name = f"{form_id}__{version}".replace("/", "_")
        return self.catalog_dir / f"{safe_name}.json"

    def _write_form(self, definition: AuditFormDefinition) -> None:
        self.path_for(definition.id, definition.version).write_text(
            json.dumps(definition.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
