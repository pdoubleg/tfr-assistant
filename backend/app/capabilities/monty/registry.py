"""Lightweight registry and doc parsing for Monty Python repl tools."""

from __future__ import annotations

import inspect
import re
import textwrap
from abc import ABC
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, ClassVar


@dataclass(frozen=True, slots=True)
class ToolMetadata:
    """Marker metadata attached to decorated collection tools."""


@dataclass(frozen=True, slots=True)
class ToolArgument:
    name: str
    annotation: str | None
    default: str | None
    kind: str
    description: str = ""

    def render_signature_fragment(self) -> str:
        prefix = ""
        if self.kind == "var_positional":
            prefix = "*"
        elif self.kind == "var_keyword":
            prefix = "**"
        suffix = f": {self.annotation}" if self.annotation else ""
        default = f" = {self.default}" if self.default is not None else ""
        return f"{prefix}{self.name}{suffix}{default}"

    def render_argument_help(self) -> str:
        annotation = f" ({self.annotation})" if self.annotation else ""
        description = f": {self.description}" if self.description else ""
        return f"- {self.name}{annotation}{description}"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    func: Callable[..., Any]
    description: str
    detailed_description: str
    usage_example: str | None = None
    collection: str | None = None
    collection_description: str | None = None
    arguments: tuple[ToolArgument, ...] = field(default_factory=tuple)
    return_annotation: str | None = None
    return_description: str | None = None


@dataclass(slots=True)
class RegisteredFunction:
    name: str
    func: Callable[..., Any]
    description: str
    detailed_description: str
    usage_example: str | None = None
    collection: str | None = None
    collection_description: str | None = None
    arguments: tuple[ToolArgument, ...] = field(default_factory=tuple)
    return_annotation: str | None = None
    return_description: str | None = None

    def render_signature(self, *, multiline: bool = False, indent: str = "    ") -> str:
        fragments: list[str] = []
        inserted_kw_marker = False
        for argument in self.arguments:
            if argument.kind == "keyword_only" and not inserted_kw_marker:
                fragments.append("*")
                inserted_kw_marker = True
            fragments.append(argument.render_signature_fragment())
        suffix = f" -> {self.return_annotation}" if self.return_annotation else ""
        if not multiline:
            return f"{self.name}({', '.join(fragments)}){suffix}"
        rendered = ",\n".join(f"{indent}{fragment}" for fragment in fragments)
        return f"{self.name}(\n{rendered},\n){suffix}"


@dataclass(slots=True)
class RegisteredCollection:
    name: str
    description: str
    tool_names: list[str] = field(default_factory=list)

    def sorted_tool_names(self) -> list[str]:
        return sorted(self.tool_names)


_TOOL_METADATA_ATTR = "__monty_tool_metadata__"


def tool(
    func: Callable[..., Any] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]] | Callable[..., Any]:
    """Mark a collection method as available inside the Monty Python repl."""

    metadata = ToolMetadata()

    def decorator(target: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(target)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            return target(*args, **kwargs)

        setattr(target, _TOOL_METADATA_ATTR, metadata)
        setattr(wrapped, _TOOL_METADATA_ATTR, metadata)
        return wrapped

    if func is None:
        return decorator
    return decorator(func)


def _get_tool_metadata(func: Callable[..., Any]) -> ToolMetadata | None:
    raw = getattr(func, "__func__", func)
    return getattr(inspect.unwrap(raw), _TOOL_METADATA_ATTR, None)


class ToolCollection(ABC):
    name: ClassVar[str]
    description: ClassVar[str] = ""

    @property
    def collection_name(self) -> str:
        return str(getattr(type(self), "name", "") or self.__class__.__name__)

    @property
    def collection_description(self) -> str:
        return str(getattr(type(self), "description", "") or inspect.getdoc(type(self)) or "")

    def tools(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for _, member in inspect.getmembers(self, predicate=callable):
            if _get_tool_metadata(member) is None:
                continue
            specs.append(
                build_tool_spec(
                    member,
                    collection=self.collection_name,
                    collection_description=self.collection_description,
                )
            )
        return specs


class FunctionRegistry:
    """Declarative registry of Python repl-callable functions."""

    def __init__(self) -> None:
        self._functions: dict[str, RegisteredFunction] = {}
        self._collections: dict[str, RegisteredCollection] = {}

    def register_collection(self, collection: ToolCollection) -> None:
        metadata = self._collections.setdefault(
            collection.collection_name,
            RegisteredCollection(collection.collection_name, collection.collection_description),
        )
        if collection.collection_description and not metadata.description:
            metadata.description = collection.collection_description
        for spec in collection.tools():
            self.register_tool(spec)

    def register_tool(self, spec: ToolSpec) -> RegisteredFunction:
        if spec.name in self._functions:
            raise ValueError(f"Function {spec.name!r} is already registered.")
        entry = RegisteredFunction(
            name=spec.name,
            func=spec.func,
            description=spec.description,
            detailed_description=spec.detailed_description,
            usage_example=spec.usage_example,
            collection=spec.collection,
            collection_description=spec.collection_description,
            arguments=spec.arguments,
            return_annotation=spec.return_annotation,
            return_description=spec.return_description,
        )
        self._functions[entry.name] = entry
        if entry.collection:
            collection = self._collections.setdefault(
                entry.collection,
                RegisteredCollection(entry.collection, entry.collection_description or ""),
            )
            collection.tool_names.append(entry.name)
        return entry

    def get(self, name: str) -> RegisteredFunction | None:
        return self._functions.get(name)

    def get_collection(self, name: str) -> RegisteredCollection | None:
        return self._collections.get(name)

    def entries(self, *, collection: str | None = None) -> list[RegisteredFunction]:
        names = sorted(self._functions)
        if collection is not None:
            names = [name for name in names if self._functions[name].collection == collection]
        return [self._functions[name] for name in names]

    def collections(self) -> list[RegisteredCollection]:
        return [self._collections[name] for name in sorted(self._collections)]

    def exported_tools(self) -> dict[str, Callable[..., Any]]:
        return {entry.name: entry.func for entry in self.entries()}


def build_tool_spec(
    func: Callable[..., Any],
    *,
    name: str | None = None,
    collection: str | None = None,
    collection_description: str | None = None,
) -> ToolSpec:
    parsed = _parse_docstring(inspect.getdoc(func) or "")
    signature = inspect.signature(func)
    arguments: list[ToolArgument] = []
    for parameter in signature.parameters.values():
        if parameter.name == "self":
            continue
        arguments.append(
            ToolArgument(
                name=parameter.name,
                annotation=_annotation_text(parameter.annotation),
                default=_default_text(parameter.default),
                kind=_kind_text(parameter.kind),
                description=parsed["args"].get(parameter.name, ""),
            )
        )
    return ToolSpec(
        name=name or func.__name__,
        func=func,
        description=parsed["summary"] or f"Call {func.__name__}.",
        detailed_description=parsed["details"] or parsed["summary"],
        usage_example=parsed["examples"] or None,
        collection=collection,
        collection_description=collection_description,
        arguments=tuple(arguments),
        return_annotation=_annotation_text(signature.return_annotation),
        return_description=parsed["returns"] or None,
    )


def _parse_docstring(doc: str) -> dict[str, Any]:
    sections = {"args": {}, "returns": "", "examples": "", "summary": "", "details": ""}
    if not doc.strip():
        return sections
    lines = doc.splitlines()
    first_block: list[str] = []
    index = 0
    while index < len(lines) and not _is_section(lines[index]):
        first_block.append(lines[index])
        index += 1
    first_text = "\n".join(first_block).strip()
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", first_text) if part.strip()]
    sections["summary"] = paragraphs[0] if paragraphs else ""
    sections["details"] = "\n\n".join(paragraphs)

    current: str | None = None
    buffers: dict[str, list[str]] = {"args": [], "returns": [], "examples": []}
    for line in lines[index:]:
        stripped = line.strip()
        section = _section_name(stripped)
        if section:
            current = section
            continue
        if current in buffers:
            buffers[current].append(line)

    sections["args"] = _parse_args_section(buffers["args"])
    sections["returns"] = "\n".join(line.strip() for line in buffers["returns"]).strip()
    sections["examples"] = textwrap.dedent("\n".join(buffers["examples"])).strip()
    return sections


def _is_section(line: str) -> bool:
    return _section_name(line.strip()) is not None


def _section_name(stripped: str) -> str | None:
    normalized = stripped.rstrip(":").lower()
    if normalized in {"args", "arguments", "parameters"}:
        return "args"
    if normalized in {"returns", "return"}:
        return "returns"
    if normalized in {"examples", "example"}:
        return "examples"
    return None


def _parse_args_section(lines: list[str]) -> dict[str, str]:
    args: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\s*\([^)]*\))?:\s*(.*)$", stripped)
        if match:
            current = match.group(1)
            args[current] = [match.group(2).strip()]
        elif current:
            args[current].append(stripped)
    return {name: " ".join(parts).strip() for name, parts in args.items()}


def _annotation_text(annotation: Any) -> str | None:
    if annotation is inspect.Signature.empty:
        return None
    text = getattr(annotation, "__name__", None) or str(annotation)
    return (
        text.replace("typing.", "")
        .replace("collections.abc.", "")
        .replace("<class '", "")
        .replace("'>", "")
    )


def _default_text(default: Any) -> str | None:
    if default is inspect.Signature.empty:
        return None
    return repr(default)


def _kind_text(kind: inspect._ParameterKind) -> str:
    if kind is inspect.Parameter.KEYWORD_ONLY:
        return "keyword_only"
    if kind is inspect.Parameter.VAR_POSITIONAL:
        return "var_positional"
    if kind is inspect.Parameter.VAR_KEYWORD:
        return "var_keyword"
    return "positional"
