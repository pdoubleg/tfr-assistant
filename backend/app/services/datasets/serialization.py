import json

from app.db.models import DatasetCandidateORM
from app.models.audit import AuditResult, compact_audit_result_text, parse_audit_result


def result_text(result: AuditResult) -> str:
    return compact_audit_result_text(result)


def candidate_text(candidate: DatasetCandidateORM) -> str:
    parts = [
        candidate.claim_number,
        candidate.instructions,
        json.dumps(candidate.input_json or {}, ensure_ascii=False, default=str),
    ]
    for reference in candidate.references_json or []:
        try:
            result = parse_audit_result(reference.get("result"))
        except Exception:
            continue
        parts.append(result_text(result))
    return "\n".join(part for part in parts if part)
