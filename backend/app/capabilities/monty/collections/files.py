"""Workspace file tools for the Monty Python repl."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.capabilities.monty.registry import ToolCollection, tool
from app.capabilities.monty.workspace_files import WorkspaceFileStore

if TYPE_CHECKING:
    from app.capabilities.monty.collections.base import MontyRuntimeContext


class FilesCollection(ToolCollection):
    """Inspect, read, and write files in the workspace."""

    name = "files"
    description = "Inspect, read, and write files in the workspace."

    def __init__(self, context: MontyRuntimeContext) -> None:
        self.context = context

    @property
    def collection_description(self) -> str:
        try:
            tree = self._store().inspect_directory(".", max_depth=1, max_entries=80)
        except Exception as exc:  # pragma: no cover - defensive help fallback
            tree = f"Unable to inspect workspace during help generation: {exc}"
        return (
            "Inspect, read, and write files in the workspace. Treat '.' as the "
            "workspace root; use filenames like 'notes.md' or paths like "
            "'folder/notes.md'. Parent folders are created automatically by "
            "write_file(). Escape attempts are blocked. "
            "read_file() returns plain extracted text, so store it in variables, "
            "inspect it with print(len(text)) or slices, and chunk it in Python before "
            "calling llm_query_batched(). Current shallow workspace tree:\n\n"
            f"{tree}"
        )

    @tool
    def inspect_directory(
        self,
        directory: str = ".",
        *,
        max_depth: int = 2,
        max_entries: int = 300,
        include_hidden: bool = False,
    ) -> str:
        """Inspect a workspace directory as a formatted file tree.

        Use this before reading unknown paths. Treat "." as the workspace root.
        The output includes the workspace-relative directory, approximate tree
        character count, file sizes, MIME/extension hints, and truncation notes
        when a directory is too large for one response.

        Args:
            directory: Workspace-relative directory to inspect.
            max_depth: Maximum child directory depth to include.
            max_entries: Maximum number of entries to include before truncating.
            include_hidden: Whether to include dotfiles and dot-directories.

        Returns:
            str: Formatted directory tree.

        Examples:
            ```python
            tree = inspect_directory(".", max_depth=1)
            print(tree)
            # Prints
            # Directory: ./
            # Characters: 128
            # |-- reports/ (2 items)
            # `-- notes.md (42 B, text/markdown)
            ```
        """
        return self._store().inspect_directory(
            directory,
            max_depth=max_depth,
            max_entries=max_entries,
            include_hidden=include_hidden,
        )

    @tool
    def inspect_file(self, file_path: str) -> str:
        """Inspect one workspace file without reading its full contents.

        Use this when you need file size, type, modified timestamp, or whether a
        file can be read or written by the registered file tools before deciding
        how much content to load.

        Args:
            file_path: Workspace-relative file path to inspect.

        Returns:
            str: File metadata summary.

        Examples:
            ```python
            info = inspect_file("reports/claim-summary.pdf")
            print(info)
            # Prints
            # Path: reports/claim-summary.pdf
            # Extension: .pdf
            # Size: 318.4 KB (326041 bytes)
            # Readable by read_file: yes
            ```
        """
        return self._store().inspect_file(file_path)

    @tool
    def read_file(self, file_path: str, *, max_chars: int | None = 100_000) -> str:
        """Read a workspace file and return extracted text.

        Text, Markdown, JSON, CSV, source-code files, PDF, DOCX, and XLSX are
        supported. The return value is plain text, so assign it to a variable and
        use normal Python operations before printing or sending chunks to an
        async RLM tool. Pass max_chars=None only when you intentionally need the
        full extracted text in the repl state.

        Args:
            file_path: Workspace-relative file path to read.
            max_chars: Maximum characters to return. Defaults to 100000. Use
                None to return all extracted text.

        Returns:
            str: Extracted file text.

        Examples:
            ```python
            pdf_text = read_file("reports/claim-summary.pdf")
            print(len(pdf_text))
            print(pdf_text[:2000])
            # Prints
            # 18472
            # Claim Summary ...
            ```
        """
        return self._store().read_file(file_path, max_chars=max_chars)

    @tool
    def write_file(self, file_path: str, content: str, *, overwrite: bool = True) -> str:
        """Write text content to a workspace file.

        Use this for LLM-generated text artifacts such as Markdown, JSON, CSV,
        source code, Mermaid, HTML, CSS, SQL, and plain text. Parent folders are
        created automatically. PDF writing is not supported. JSON files are
        validated before writing.

        Args:
            file_path: Workspace-relative file path to create or update.
            content: Text content to write.
            overwrite: Whether to replace an existing file.

        Returns:
            str: Success message with workspace-relative path and bytes written.

        Examples:
            ```python
            summary = "# Claim Summary\\n\\nNo roof exclusions were identified."
            result = write_file("outputs/summary.md", summary)
            print(result)
            # Prints
            # Wrote 54 byte(s) to outputs/summary.md.
            ```
        """
        return self._store().write_file(file_path, content, overwrite=overwrite)

    def _store(self) -> WorkspaceFileStore:
        return WorkspaceFileStore(self.context.settings)
