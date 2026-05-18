from pathlib import Path

import pytest

from app.core.config import Settings
from app.services.intake_documents import IntakeDocumentStore


def test_intake_document_store_lists_supported_documents(tmp_path: Path) -> None:
    docs_dir = tmp_path / "intake_docs"
    docs_dir.mkdir()
    (docs_dir / "completed-audit.txt").write_text(
        "Claim Number: ABC123\nCompleted audit content",
        encoding="utf-8",
    )
    (docs_dir / "ignored.csv").write_text("not supported", encoding="utf-8")

    documents = IntakeDocumentStore(Settings(completed_intake_docs_dir=docs_dir)).list_documents()

    assert [document.id for document in documents] == ["completed-audit.txt"]
    assert documents[0].filename == "completed-audit.txt"
    assert documents[0].file_type == "txt"
    assert "ABC123" in documents[0].preview


def test_intake_document_store_rejects_path_traversal(tmp_path: Path) -> None:
    docs_dir = tmp_path / "intake_docs"
    docs_dir.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    store = IntakeDocumentStore(Settings(completed_intake_docs_dir=docs_dir))

    with pytest.raises(ValueError, match="inside the configured intake folder"):
        store.resolve("../outside.txt")
