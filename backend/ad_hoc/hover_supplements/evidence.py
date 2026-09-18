"""A pass owns only the evidence it is allowed to read."""

from dataclasses import dataclass

from .contracts import Evidence, EvidenceReference
from .dataframes import feature_dictionary


@dataclass(frozen=True)
class EvidenceStore:
    records: tuple[Evidence, ...]

    def list_evidence(self) -> list[dict]:
        return [e.model_dump(mode="json", exclude={"text"}) for e in self.records]

    def get_evidence(self, evidence_id: str) -> Evidence:
        for record in self.records:
            if record.id == evidence_id:
                return record
        raise ValueError("Evidence ID is unavailable in this extraction pass")

    def read_kind(self, kind: str) -> list[dict]:
        return [e.model_dump(mode="json") for e in self.records if e.kind == kind]

    def validate_references(self, features, references: list[EvidenceReference]):
        paths = set(feature_dictionary(type(features)).field.str.replace("__", ".", regex=False))
        ids = {e.id for e in self.records}
        for ref in references:
            if ref.field_path not in paths:
                raise ValueError(f"Invalid feature path: {ref.field_path}")
            if not set(ref.evidence_ids).issubset(ids):
                raise ValueError("Citation points outside accessible evidence")
        cited = {ref.field_path for ref in references}
        for field in feature_dictionary(type(features)).to_dict("records"):
            path = field["field"].replace("__", ".")
            if field["pandas_kind"] in {"text", "date"} or path.endswith(
                "supplement_pct_of_initial_estimate"
            ):
                continue
            value = features
            for name in path.split("."):
                value = getattr(value, name)
            if value is not None and value not in {"unknown", "unclear", "not_applicable"}:
                if path not in cited:
                    raise ValueError(f"Factual finding requires evidence: {path}")
