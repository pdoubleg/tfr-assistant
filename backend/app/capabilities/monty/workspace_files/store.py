"""Workspace-scoped file operations for the chat agent."""

from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.capabilities.monty.workspace_files.readers import read_file_content
from app.core.config import Settings, get_settings


class WorkspaceFileError(ValueError):
    """Raised when a workspace file operation is invalid or unsafe."""


_SKIPPED_DIRECTORY_NAMES = {
    ".git",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
}

_WRITABLE_EXTENSIONS = {
    "",
    ".bash",
    ".bat",
    ".c",
    ".cfg",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".csv",
    ".dockerfile",
    ".env",
    ".go",
    ".graphql",
    ".h",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsonl",
    ".jsx",
    ".log",
    ".md",
    ".mermaid",
    ".mjs",
    ".mmd",
    ".py",
    ".rb",
    ".rs",
    ".scss",
    ".sh",
    ".sql",
    ".svg",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

_READABLE_EXTENSIONS = {
    "",
    ".bash",
    ".bat",
    ".c",
    ".cfg",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".csv",
    ".dockerfile",
    ".docx",
    ".env",
    ".go",
    ".graphql",
    ".h",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsonl",
    ".jsx",
    ".log",
    ".md",
    ".mermaid",
    ".mjs",
    ".mmd",
    ".pdf",
    ".py",
    ".rb",
    ".rs",
    ".scss",
    ".sh",
    ".sql",
    ".svg",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xlsx",
    ".xml",
    ".yaml",
    ".yml",
}


@dataclass(slots=True)
class WorkspaceFileStore:
    """Read and write files inside the configured agent workspace only."""

    settings: Settings | None = None
    root: Path = field(init=False)

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()
        self.root = _resolve_config_path(self.settings.agent_workspace_dir, self.settings)
        self.root.mkdir(parents=True, exist_ok=True)
        self.root = self.root.resolve()

    def inspect_directory(
        self,
        directory: str = ".",
        *,
        max_depth: int = 2,
        max_entries: int = 300,
        include_hidden: bool = False,
    ) -> str:
        path = self.resolve_path(directory)
        if not path.exists():
            raise WorkspaceFileError(f"Directory does not exist: {directory}")
        if not path.is_dir():
            raise WorkspaceFileError(f"Path is not a directory: {directory}")

        max_depth = max(0, min(max_depth, 8))
        max_entries = max(1, min(max_entries, 2000))
        entry_count = 0
        truncated = False
        header = [f"Directory: {self.display_path(path)}/"]
        lines: list[str] = []

        def walk(current: Path, depth: int, prefix: str) -> None:
            nonlocal entry_count, truncated
            if depth > max_depth or truncated:
                return

            children = self._visible_children(current, include_hidden=include_hidden)
            for index, child in enumerate(children):
                if entry_count >= max_entries:
                    truncated = True
                    lines.append(f"{prefix}... output truncated after {max_entries} entries")
                    return
                entry_count += 1

                connector = "`-- " if index == len(children) - 1 else "|-- "
                next_prefix = prefix + ("    " if index == len(children) - 1 else "|   ")
                lines.append(f"{prefix}{connector}{self._format_entry(child)}")

                if child.is_dir() and not child.is_symlink() and depth < max_depth:
                    walk(child, depth + 1, next_prefix)
                elif child.is_dir() and depth >= max_depth:
                    lines.append(f"{next_prefix}... max_depth reached")

        walk(path, 0, "")
        if entry_count == 0:
            lines.append("(empty)")
        if truncated:
            lines.append("Increase max_entries or inspect a narrower directory to continue.")
        body = "\n".join(lines)
        header.append(f"Characters: {len(body)}")
        return "\n".join(header + [body])

    def inspect_file(self, file_path: str) -> str:
        path = self.resolve_path(file_path)
        if not path.exists():
            raise WorkspaceFileError(f"File does not exist: {file_path}")
        if not path.is_file():
            raise WorkspaceFileError(f"Path is not a file: {file_path}")

        stat = path.stat()
        suffix = path.suffix.lower()
        mime_type, _ = mimetypes.guess_type(path.name)
        rows = [
            f"Path: {self.display_path(path)}",
            f"Name: {path.name}",
            f"Extension: {suffix or '(none)'}",
            f"MIME type: {mime_type or '(unknown)'}",
            f"Size: {_format_size(stat.st_size)} ({stat.st_size} bytes)",
            "Readable by read_file: " + ("yes" if suffix in _READABLE_EXTENSIONS else "maybe"),
            "Writable by write_file: " + ("yes" if suffix in _WRITABLE_EXTENSIONS else "no"),
            "Modified: "
            + datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(timespec="seconds"),
        ]
        return "\n".join(rows)

    def read_file(self, file_path: str, *, max_chars: int | None = 100_000) -> str:
        path = self.resolve_path(file_path)
        if not path.exists():
            raise WorkspaceFileError(f"File does not exist: {file_path}")
        if not path.is_file():
            raise WorkspaceFileError(f"Path is not a file: {file_path}")

        result = read_file_content(path)
        if max_chars is None:
            return result.content
        max_chars = max(0, min(max_chars, 1_000_000))
        content = result.content
        truncated = len(content) > max_chars
        if truncated:
            content = content[:max_chars]
        if truncated:
            content += (
                f"\n\n[read_file truncated at max_chars={max_chars}; "
                f"original_chars={len(result.content)}]"
            )
        return content

    def write_file(
        self,
        file_path: str,
        content: str,
        *,
        overwrite: bool = True,
    ) -> str:
        path = self.resolve_path(file_path)
        suffix = path.suffix.lower()
        if suffix not in _WRITABLE_EXTENSIONS:
            raise WorkspaceFileError(
                f"Writing {suffix or 'extensionless'} files is not supported by this tool."
            )
        if path.exists() and not path.is_file():
            raise WorkspaceFileError(f"Path exists and is not a file: {file_path}")
        if path.exists() and not overwrite:
            raise WorkspaceFileError(f"File already exists and overwrite=false: {file_path}")

        self._validate_content_for_extension(path, content)
        parent = self.resolve_path(str(path.parent))
        parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="")
        return f"Wrote {len(content.encode('utf-8'))} byte(s) to {self.display_path(path)}."

    def resolve_path(self, path_input: str | Path) -> Path:
        candidate = Path(path_input)
        _validate_visible_path(candidate)
        path = candidate if candidate.is_absolute() else self.root / candidate
        resolved = path.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceFileError(
                f"Path is outside the workspace: {path_input}. Use paths relative to '.' only."
            ) from exc
        return resolved

    def display_path(self, path: Path) -> str:
        return str(path.resolve().relative_to(self.root)).replace("\\", "/") or "."

    def _visible_children(self, directory: Path, *, include_hidden: bool) -> list[Path]:
        children = []
        for child in directory.iterdir():
            if not include_hidden and child.name.startswith("."):
                continue
            if child.is_dir() and child.name in _SKIPPED_DIRECTORY_NAMES:
                continue
            children.append(child)
        return sorted(children, key=lambda item: (not item.is_dir(), item.name.lower()))

    def _format_entry(self, path: Path) -> str:
        if path.is_symlink():
            try:
                target = path.resolve()
                target.relative_to(self.root)
                target_text = f" -> {self.display_path(target)}"
            except ValueError:
                target_text = " -> outside workspace (blocked)"
            return f"{path.name}@{target_text}"

        if path.is_dir():
            try:
                count = len(self._visible_children(path, include_hidden=False))
                return f"{path.name}/ ({count} item{'s' if count != 1 else ''})"
            except OSError:
                return f"{path.name}/ (unreadable)"

        try:
            size = path.stat().st_size
            size_text = _format_size(size)
        except OSError:
            size_text = "unknown size"
        mime_type, _ = mimetypes.guess_type(path.name)
        type_text = mime_type or path.suffix.lower().lstrip(".") or "file"
        return f"{path.name} ({size_text}, {type_text})"

    def _validate_content_for_extension(self, path: Path, content: str) -> None:
        suffix = path.suffix.lower()
        if suffix in {".json"}:
            try:
                json.loads(content)
            except json.JSONDecodeError as exc:
                raise WorkspaceFileError(f"Invalid JSON for {path.name}: {exc}") from exc
        if "\x00" in content:
            raise WorkspaceFileError("Refusing to write content containing NUL bytes.")


def _resolve_config_path(path: Path, settings: Settings) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (settings.data_dir.parent / path).resolve()


def _validate_visible_path(path: Path) -> None:
    if any(part.startswith(".") and part not in {".", ".."} for part in path.parts):
        raise WorkspaceFileError(
            f"Hidden dot files and directories are not available: {path}. "
            "Use non-hidden workspace paths."
        )


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"
