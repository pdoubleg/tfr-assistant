from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.capabilities.monty.workspace_files.readers import FileReadResult, read_file_content
from app.core.config import Settings, get_settings
from app.schemas.reviews import IntakeDocumentRecord

SUPPORTED_INTAKE_EXTENSIONS = {".pdf", ".docx", ".txt"}


@dataclass(slots=True)
class IntakeDocumentStore:
    settings: Settings = field(default_factory=get_settings)

    @property
    def root(self) -> Path:
        root = self.settings.completed_intake_docs_dir
        if not root.is_absolute():
            root = Path.cwd() / root
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()

    def list_documents(self) -> list[IntakeDocumentRecord]:
        documents: list[IntakeDocumentRecord] = []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_INTAKE_EXTENSIONS:
                continue
            stat = path.stat()
            preview = ""
            try:
                preview = _truncate(read_file_content(path).content.replace("\r\n", "\n"), 500)
            except Exception:
                preview = ""
            documents.append(
                IntakeDocumentRecord(
                    id=self._id_for_path(path),
                    filename=path.name,
                    file_type=path.suffix.lower().lstrip("."),
                    size_bytes=stat.st_size,
                    modified_at=_datetime_from_timestamp(stat.st_mtime),
                    preview=preview,
                )
            )
        return documents

    def read_document(self, document_id: str) -> FileReadResult:
        path = self.resolve(document_id)
        return read_file_content(path)

    def resolve(self, document_id: str) -> Path:
        normalized = document_id.replace("\\", "/").strip("/")
        path = (self.root / normalized).resolve()
        if not _is_relative_to(path, self.root):
            raise ValueError("Intake document path must stay inside the configured intake folder.")
        if not path.is_file():
            raise FileNotFoundError(f"Intake document was not found: {document_id}")
        if path.suffix.lower() not in SUPPORTED_INTAKE_EXTENSIONS:
            raise ValueError(f"Unsupported intake document type: {path.suffix or 'extensionless'}")
        return path

    def _id_for_path(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _truncate(text: str, limit: int) -> str:
    compact = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _datetime_from_timestamp(timestamp: float):
    from datetime import UTC, datetime

    return datetime.fromtimestamp(timestamp, UTC)
