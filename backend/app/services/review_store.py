from datetime import UTC, datetime
from uuid import uuid4

from app.models.audit import AuditFormResult
from app.schemas.reviews import ReviewRecord, ReviewUpdate


class ReviewStore:
    """Temporary in-memory review repository.

    The original agent output is only written at creation time. User edits are
    stored in the separate user_version copy so evaluation can compare them.
    """

    def __init__(self) -> None:
        self._records: dict[str, ReviewRecord] = {}

    def list_reviews(self) -> list[ReviewRecord]:
        return sorted(self._records.values(), key=lambda record: record.updated_at, reverse=True)

    def create_from_agent_output(self, result: AuditFormResult) -> ReviewRecord:
        review_id = str(uuid4())
        now = datetime.now(UTC)
        original = result.model_copy(deep=True, update={"id": review_id})
        user_version = original.model_copy(deep=True)
        record = ReviewRecord(
            id=review_id,
            form_id=result.form_id,
            form_version=result.form_version,
            original=original,
            user_version=user_version,
            created_at=now,
            updated_at=now,
        )
        self._records[review_id] = record
        return record

    def get_review(self, review_id: str) -> ReviewRecord:
        try:
            return self._records[review_id]
        except KeyError as exc:
            raise KeyError(f"Unknown review: {review_id}") from exc

    def update_user_version(self, review_id: str, update: ReviewUpdate) -> ReviewRecord:
        record = self.get_review(review_id)
        updated = record.model_copy(
            update={
                "user_version": update.user_version.model_copy(deep=True),
                "updated_at": datetime.now(UTC),
            }
        )
        self._records[review_id] = updated
        return updated


review_store = ReviewStore()

