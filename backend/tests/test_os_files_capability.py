import os

import pytest
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from app.agents.chat_agent import build_chat_agent
from app.capabilities.deps import TFRChatDeps
from app.capabilities.monty.runtime import MontyPythonRuntime
from app.capabilities.monty.workspace_files import WorkspaceFileError, WorkspaceFileStore
from app.core.config import Settings
from app.models.chat_state import TFRChatState


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_workspace_store_blocks_parent_path_escape(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        agent_workspace_dir=tmp_path / "data" / "workspace",
    )
    store = WorkspaceFileStore(settings)

    with pytest.raises(WorkspaceFileError, match="outside the workspace"):
        store.read_file("../secret.txt")


def test_workspace_store_blocks_absolute_path_escape(tmp_path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    settings = Settings(
        data_dir=tmp_path / "data",
        agent_workspace_dir=tmp_path / "data" / "workspace",
    )
    store = WorkspaceFileStore(settings)

    with pytest.raises(WorkspaceFileError, match="outside the workspace"):
        store.read_file(str(outside))


@pytest.mark.skipif(os.name == "nt", reason="Windows symlink creation needs elevated privileges")
def test_workspace_store_blocks_symlink_escape(tmp_path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    settings = Settings(
        data_dir=tmp_path / "data",
        agent_workspace_dir=tmp_path / "data" / "workspace",
    )
    store = WorkspaceFileStore(settings)
    (store.root / "linked").symlink_to(outside, target_is_directory=True)

    with pytest.raises(WorkspaceFileError, match="outside the workspace"):
        store.read_file("linked/secret.txt")


def test_workspace_store_writes_reads_and_truncates_text(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        agent_workspace_dir=tmp_path / "data" / "workspace",
    )
    store = WorkspaceFileStore(settings)

    message = store.write_file("notes/summary.md", "# Hello\n\nabcdef")
    output = store.read_file("notes/summary.md", max_chars=9)

    assert "Wrote" in message
    assert "notes/summary.md" in message
    assert str(store.root) not in message
    assert "# Hello\n\n" in output
    assert "[read_file truncated at max_chars=9; original_chars=15]" in output


def test_workspace_store_validates_json_before_write(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        agent_workspace_dir=tmp_path / "data" / "workspace",
    )
    store = WorkspaceFileStore(settings)

    with pytest.raises(WorkspaceFileError, match="Invalid JSON"):
        store.write_file("bad.json", "{")


def test_workspace_store_blocks_hidden_dot_paths(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        agent_workspace_dir=tmp_path / "data" / "workspace",
    )
    store = WorkspaceFileStore(settings)

    with pytest.raises(WorkspaceFileError, match="Hidden dot files"):
        store.write_file(".env", "SECRET=value")

    with pytest.raises(WorkspaceFileError, match="Hidden dot files"):
        store.write_file("nested/.env", "SECRET=value")

    with pytest.raises(WorkspaceFileError, match="Hidden dot files"):
        store.read_file(".env")


def test_workspace_store_inspects_directory_tree(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        agent_workspace_dir=tmp_path / "data" / "workspace",
    )
    store = WorkspaceFileStore(settings)
    store.write_file("alpha/readme.md", "hello")
    store.write_file("beta.txt", "world")

    tree = store.inspect_directory(".", max_depth=1)

    assert "Directory: ./" in tree
    assert "Characters:" in tree
    assert "alpha/" in tree
    assert "readme.md" in tree
    assert "beta.txt" in tree
    assert str(store.root) not in tree


def test_workspace_store_creates_parent_directories_on_write(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        agent_workspace_dir=tmp_path / "data" / "workspace",
    )
    store = WorkspaceFileStore(settings)

    message = store.write_file("generated/reports/summary.md", "hello")

    assert message == "Wrote 5 byte(s) to generated/reports/summary.md."
    assert (store.root / "generated" / "reports" / "summary.md").exists()


def test_workspace_store_inspects_file(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        agent_workspace_dir=tmp_path / "data" / "workspace",
    )
    store = WorkspaceFileStore(settings)
    store.write_file("alpha/readme.md", "hello")

    info = store.inspect_file("alpha/readme.md")

    assert "Path: alpha/readme.md" in info
    assert "Extension: .md" in info
    assert "Readable by read_file: yes" in info
    assert "Writable by write_file: yes" in info


def test_workspace_store_reads_docx_when_available(tmp_path) -> None:
    docx = pytest.importorskip("docx")
    settings = Settings(
        data_dir=tmp_path / "data",
        agent_workspace_dir=tmp_path / "data" / "workspace",
    )
    store = WorkspaceFileStore(settings)
    document = docx.Document()
    document.add_paragraph("Insurance review note")
    document.save(store.root / "sample.docx")

    output = store.read_file("sample.docx")

    assert "Insurance review note" in output


@pytest.mark.anyio
async def test_monty_files_collection_reads_and_writes_workspace_files(tmp_path) -> None:
    settings = Settings(
        chat_model="test",
        data_dir=tmp_path / "data",
        agent_workspace_dir=tmp_path / "data" / "workspace",
    )
    runtime = MontyPythonRuntime(TFRChatState(), settings)

    result = await runtime.execute(
        """
write_file("notes/example.md", "# Example\\n\\nhello workspace")
text = read_file("notes/example.md")
print(len(text))
print(text[:9])
"""
    )

    assert result["status"] == "success"
    assert result["stdout"] == "26\n# Example\n"


def test_monty_files_help_includes_shallow_workspace_tree(tmp_path) -> None:
    settings = Settings(
        chat_model="test",
        data_dir=tmp_path / "data",
        agent_workspace_dir=tmp_path / "data" / "workspace",
    )
    store = WorkspaceFileStore(settings)
    store.write_file("notes/example.md", "hello")
    runtime = MontyPythonRuntime(TFRChatState(), settings)

    help_text = runtime.help("files")

    assert "Collection: files" in help_text
    assert "Current shallow workspace tree:" in help_text
    assert "notes/" in help_text
    assert "inspect_file" in help_text
    assert "read_file" in help_text


@pytest.mark.anyio
async def test_monty_files_collection_blocks_workspace_escape(tmp_path) -> None:
    settings = Settings(
        chat_model="test",
        data_dir=tmp_path / "data",
        agent_workspace_dir=tmp_path / "data" / "workspace",
    )
    runtime = MontyPythonRuntime(TFRChatState(), settings)

    result = await runtime.execute('read_file("../secret.txt")')

    assert result["status"] == "error"
    assert "Path is outside the workspace" in result["error"]
    assert str(settings.agent_workspace_dir) not in result["error"]


@pytest.mark.anyio
async def test_chat_agent_exposes_file_access_through_python_repl(tmp_path) -> None:
    settings = Settings(
        chat_model="test",
        data_dir=tmp_path / "data",
        agent_workspace_dir=tmp_path / "data" / "workspace",
    )
    state = TFRChatState()
    agent = build_chat_agent(settings)
    ctx = RunContext(
        deps=TFRChatDeps(state, settings=settings),
        model=TestModel(),
        usage=RunUsage(),
    )

    tool_names: list[str] = []
    for toolset in agent.toolsets:
        tool_names.extend((await toolset.get_tools(ctx)).keys())

    assert "python_repl_execute" in tool_names
    assert "inspect_directory" not in tool_names
    assert "read_file" not in tool_names
