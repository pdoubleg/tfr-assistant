from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, fields


@dataclass(frozen=True, slots=True)
class AuditObservationContext:
    audit_run_id: str | None = None
    review_id: str | None = None
    source: str = ""
    source_run_id: str | None = None
    batch_id: str | None = None
    eval_run_id: str | None = None
    eval_dataset_id: str | None = None
    optimization_run_id: str | None = None
    case_id: str | None = None
    claim_number: str = ""
    form_id: str = ""
    form_version: str = ""
    form_kind: str = ""
    model_name: str = ""
    tenant_id: str | None = None
    user_id: str | None = None

    def normalized(self) -> AuditObservationContext:
        source_run_id = self.source_run_id
        if not source_run_id:
            source_run_id = self.optimization_run_id or self.eval_run_id or self.batch_id
        review_id = self.review_id or self.audit_run_id
        audit_run_id = self.audit_run_id or review_id
        return AuditObservationContext(
            audit_run_id=audit_run_id,
            review_id=review_id,
            source=self.source,
            source_run_id=source_run_id,
            batch_id=self.batch_id,
            eval_run_id=self.eval_run_id,
            eval_dataset_id=self.eval_dataset_id,
            optimization_run_id=self.optimization_run_id,
            case_id=self.case_id,
            claim_number=self.claim_number,
            form_id=self.form_id,
            form_version=self.form_version,
            form_kind=self.form_kind,
            model_name=self.model_name,
            tenant_id=self.tenant_id,
            user_id=self.user_id,
        )

    def otel_attributes(self) -> dict[str, str | bool]:
        ctx = self.normalized()
        pairs = {
            "audit.observed": True,
            "audit.run_id": ctx.audit_run_id,
            "audit.review_id": ctx.review_id,
            "audit.source": ctx.source,
            "audit.source_run_id": ctx.source_run_id,
            "audit.batch_id": ctx.batch_id,
            "audit.eval_run_id": ctx.eval_run_id,
            "audit.eval_dataset_id": ctx.eval_dataset_id,
            "audit.optimization_run_id": ctx.optimization_run_id,
            "audit.case_id": ctx.case_id,
            "audit.claim_number": ctx.claim_number,
            "audit.form_id": ctx.form_id,
            "audit.form_version": ctx.form_version,
            "audit.form_kind": ctx.form_kind,
            "audit.model_name": ctx.model_name,
            "audit.tenant_id": ctx.tenant_id,
            "audit.user_id": ctx.user_id,
        }
        return {
            key: value if isinstance(value, bool) else str(value)
            for key, value in pairs.items()
            if value not in {None, ""}
        }


_current_context: ContextVar[AuditObservationContext | None] = ContextVar(
    "audit_observation_context",
    default=None,
)


def current_audit_context() -> AuditObservationContext | None:
    return _current_context.get()


@contextmanager
def audit_observation_context(
    context: AuditObservationContext | None = None,
    **updates: object,
) -> Iterator[AuditObservationContext]:
    base = context or current_audit_context() or AuditObservationContext()
    values = {field.name: getattr(base, field.name) for field in fields(base)}
    values.update({key: value for key, value in updates.items() if value is not None})
    next_context = AuditObservationContext(**values).normalized()
    token = _current_context.set(next_context)
    try:
        yield next_context
    finally:
        _current_context.reset(token)


@contextmanager
def observed_audit_generation(
    *,
    name: str = "audit_generation",
    context: AuditObservationContext | None = None,
    **updates: object,
) -> Iterator[AuditObservationContext]:
    with audit_observation_context(context, **updates) as active_context:
        try:
            from opentelemetry import trace
        except Exception:
            yield active_context
            return

        tracer = trace.get_tracer("tfr_assistant.audit_generation")
        with tracer.start_as_current_span(
            name, attributes=active_context.otel_attributes()
        ) as span:
            span.set_attribute("audit.observed", True)
            yield active_context


def apply_context_to_span(span: object, context: AuditObservationContext | None = None) -> None:
    active_context = context or current_audit_context()
    if active_context is None:
        return
    for key, value in active_context.otel_attributes().items():
        try:
            span.set_attribute(key, value)
        except Exception:
            continue
