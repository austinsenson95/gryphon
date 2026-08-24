"""Phase 1 tests: desktop command validation, workflows, execution boundary.

All OS-level calls are mocked — no real applications or browser windows are
opened during the test run.
"""

from __future__ import annotations

import pytest

from backend.core import executor
from backend.core.config import Settings
from backend.tools import desktop
from backend.tools.registry import create_default_registry


@pytest.fixture
def phase1_settings(tmp_path) -> Settings:
    (tmp_path / "projects" / "griffin").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    return Settings(
        database_url=f"sqlite:///{tmp_path}/test.db",
        allowed_directories=f"{tmp_path}/projects,{tmp_path}/docs",
        projects='{"griffin": "' + str(tmp_path / "projects" / "griffin") + '"}',
        _env_file=None,
    )


@pytest.fixture
def phase1_registry(phase1_settings):
    return create_default_registry(phase1_settings)


@pytest.fixture
def fake_open(monkeypatch):
    """Replace macOS `open` invocation with a recorder."""
    calls: list[list[str]] = []

    async def _fake(args: list[str]) -> tuple[bool, str]:
        calls.append(args)
        return True, ""

    monkeypatch.setattr(desktop, "_run_mac_open", _fake)
    monkeypatch.setattr(desktop.shutil, "which", lambda name: None)
    return calls


# ------------------------------------------------------------------ validation


async def test_unknown_tool_fails_closed(phase1_registry):
    result = await executor.execute_tool(phase1_registry, "shell.run", {"command": "rm -rf /"})
    assert not result.success
    assert result.error.code == "TOOL_NOT_FOUND"


async def test_arbitrary_shell_cannot_execute(phase1_registry):
    """The privileged shell stub stays registered but refuses to run."""
    result = await executor.execute_tool(
        phase1_registry, "system.execute_shell", {"command": "echo hi"}
    )
    assert not result.success
    assert result.error.code == "PERMISSION_DENIED"


async def test_open_url_rejects_non_http(phase1_registry, fake_open):
    result = await executor.execute_tool(
        phase1_registry, "desktop.open_url", {"url": "file:///etc/passwd"}
    )
    assert not result.success
    assert result.error.code == "INVALID_URL"
    assert fake_open == []


async def test_open_url_rejects_shell_injection(phase1_registry, fake_open):
    result = await executor.execute_tool(
        phase1_registry, "desktop.open_url", {"url": "https://ok.com\n; rm -rf /"}
    )
    assert not result.success
    assert fake_open == []


async def test_open_url_happy_path(phase1_registry, fake_open):
    result = await executor.execute_tool(
        phase1_registry, "desktop.open_url", {"url": "https://github.com"}
    )
    assert result.success
    assert result.data["opened"] is True
    assert fake_open == [["https://github.com"]]


async def test_open_application_allowlist(phase1_registry, fake_open):
    ok = await executor.execute_tool(
        phase1_registry, "desktop.open_application", {"application": "safari"}
    )
    assert ok.success
    assert fake_open == [["-a", "Safari"]]

    bad = await executor.execute_tool(
        phase1_registry, "desktop.open_application", {"application": "rm"}
    )
    assert not bad.success
    assert bad.error.code == "UNSUPPORTED_APPLICATION"


async def test_open_folder_confined_to_allowlist(phase1_registry, phase1_settings, tmp_path, fake_open):
    allowed = tmp_path / "projects"  # created by the phase1_settings fixture
    ok = await executor.execute_tool(
        phase1_registry, "desktop.open_folder", {"path": str(allowed)}
    )
    assert ok.success

    denied = await executor.execute_tool(
        phase1_registry, "desktop.open_folder", {"path": "/etc"}
    )
    assert not denied.success
    assert denied.error.code == "DISALLOWED_PATH"

    traversal = await executor.execute_tool(
        phase1_registry, "desktop.open_folder", {"path": f"{allowed}/../../.."}
    )
    assert not traversal.success


async def test_open_project_requires_registry(phase1_registry, tmp_path, fake_open):
    project_dir = tmp_path / "projects" / "griffin"  # created by phase1_settings

    ok = await executor.execute_tool(
        phase1_registry, "desktop.open_project", {"project": "griffin"}
    )
    assert ok.success
    assert ok.data["path"] == str(project_dir.resolve())

    unknown = await executor.execute_tool(
        phase1_registry, "desktop.open_project", {"project": "nonexistent"}
    )
    assert not unknown.success
    assert unknown.error.code == "UNKNOWN_PROJECT"


async def test_search_web_builds_safe_url(phase1_registry, fake_open):
    result = await executor.execute_tool(
        phase1_registry, "desktop.search_web", {"query": "latest AI agent frameworks"}
    )
    assert result.success
    assert fake_open == [["https://www.google.com/search?q=latest+AI+agent+frameworks"]]


async def test_open_terminal(phase1_registry, fake_open):
    result = await executor.execute_tool(phase1_registry, "desktop.open_terminal", {})
    assert result.success
    assert fake_open == [["-a", "Terminal"]]


# ------------------------------------------------------------------ workflows


async def test_workflow_runs_steps_in_order(phase1_registry, fake_open):
    result = await executor.execute_tool(
        phase1_registry, "workflow.run", {"name": "start_development"}
    )
    assert result.success
    steps = result.data["steps"]
    assert [s["command"] for s in steps] == [
        "desktop.open_application",
        "desktop.open_project",
        "desktop.open_url",
    ]
    assert result.data["completed"] == 3


async def test_unknown_workflow_rejected(phase1_registry, fake_open):
    result = await executor.execute_tool(
        phase1_registry, "workflow.run", {"name": "delete_everything"}
    )
    assert not result.success
    assert result.error.code == "UNKNOWN_WORKFLOW"
    assert fake_open == []


async def test_workflow_surfaces_step_failure(phase1_registry, monkeypatch):
    async def _failing(args: list[str]) -> tuple[bool, str]:
        return False, "boom"

    monkeypatch.setattr(desktop, "_run_mac_open", _failing)
    monkeypatch.setattr(desktop.shutil, "which", lambda name: None)
    result = await executor.execute_tool(
        phase1_registry, "workflow.run", {"name": "morning"}
    )
    assert not result.success
    assert result.error.code == "WORKFLOW_FAILED"
    assert all(not s["success"] for s in result.data["steps"])


# ------------------------------------------------------------------ planner


async def test_system_prompt_injects_registry(phase1_registry):
    from backend.core import planner

    prompt = planner.system_prompt(phase1_registry)
    assert "desktop.open_application" in prompt
    assert "workflow.run" in prompt
    assert "never" in prompt.lower()
    # Privileged tools are never advertised to the model.
    assert "system.execute_shell" not in prompt


# ------------------------------------------------------------------ mock rules


async def test_mock_provider_maps_phase1_commands():
    from backend.llm.provider import MockLLMProvider
    from backend.llm.base import LLMMessage

    provider = MockLLMProvider()

    async def plan(text: str):
        res = await provider.generate([LLMMessage(role="user", content=text)])
        assert res.tool_calls, f"expected tool call for: {text}"
        return res.tool_calls[0]

    call = await plan("Open GitHub")
    assert (call.name, call.arguments) == ("desktop.open_url", {"url": "https://github.com"})

    call = await plan("Open VS Code")
    assert call.name == "desktop.open_application"
    assert call.arguments["application"] == "Visual Studio Code"

    call = await plan("Search the web for the latest AI agent frameworks")
    assert call.name == "desktop.search_web"

    call = await plan("Search YouTube for local-first AI assistants")
    assert (call.name, call.arguments) == (
        "desktop.search_youtube",
        {"query": "local-first AI assistants"},
    )

    call = await plan("Start my development environment")
    assert (call.name, call.arguments) == ("workflow.run", {"name": "start_development"})

    call = await plan("Open my griffin project")
    assert (call.name, call.arguments) == ("desktop.open_project", {"project": "griffin"})
