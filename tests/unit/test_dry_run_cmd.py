"""Tests for the ``bernstein dry-run`` failure contract (issue #3550).

A plan file that fails to load must exit non-zero and surface the loader's
message in both table and JSON modes -- never a plausible empty result
(``{"tasks": [], "total": 0}`` with exit 0).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from click.testing import CliRunner, Result

from bernstein.cli.commands.dry_run_cmd import dry_run_cmd

VALID_PLAN: dict[str, object] = {
    "name": "Dry Run Test Plan",
    "description": "Plan used by the dry-run CLI contract tests",
    "stages": [
        {
            "name": "S1",
            "steps": [{"title": "Step A", "goal": "Do the thing", "role": "backend"}],
        }
    ],
}

MALFORMED_PLAN_YAML = (
    "stages:\n"
    "  - name: S1\n"
    "    steps:\n"
    "      - title: [unclosed\n"  # invalid YAML -> PlanLoadError from the loader
)


def _write_plan(tmp_path: Path, content: str) -> Path:
    plan_file = tmp_path / "plan.yaml"
    plan_file.write_text(content)
    return plan_file


def _valid_plan_yaml() -> str:
    return yaml.dump(VALID_PLAN)


def _run_dry_run(plan_file: Path | None, as_json: bool, workdir: Path, monkeypatch: pytest.MonkeyPatch) -> Result:
    """Invoke ``dry-run`` from ``workdir`` so Path.cwd() resolves there."""
    monkeypatch.chdir(workdir)
    args = []
    if plan_file is not None:
        args += ["--plan", str(plan_file)]
    if as_json:
        args += ["--json"]
    return CliRunner().invoke(dry_run_cmd, args)


def _extract_json(output: str) -> dict[str, Any]:
    """Pull the JSON document out of CLI output.

    The router can emit ``[SPAWNER-DEBUG]`` log lines to stderr, which
    CliRunner mixes into ``result.output``; the JSON document itself starts
    at the first ``{`` and ends at the last ``}``.
    """
    start = output.index("{")
    end = output.rindex("}") + 1
    return json.loads(output[start:end])


# ---------------------------------------------------------------------------
# Malformed plan: the failure contract
# ---------------------------------------------------------------------------


def test_malformed_plan_table_mode_exits_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _write_plan(tmp_path, MALFORMED_PLAN_YAML)
    result = _run_dry_run(plan, as_json=False, workdir=tmp_path, monkeypatch=monkeypatch)

    assert result.exit_code == 1, result.output
    # The loader's message reaches the operator in table mode.
    assert "Plan load error" in result.output


def test_malformed_plan_json_mode_structured_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _write_plan(tmp_path, MALFORMED_PLAN_YAML)
    result = _run_dry_run(plan, as_json=True, workdir=tmp_path, monkeypatch=monkeypatch)

    assert result.exit_code == 1, result.output
    # A structured error payload, never the success shape.
    assert '"tasks"' not in result.output
    payload = _extract_json(result.output)
    assert payload["error"]["kind"] == "PlanLoadError"
    assert payload["error"]["message"]


# ---------------------------------------------------------------------------
# Valid plan / backlog: unchanged behavior
# ---------------------------------------------------------------------------


def test_valid_plan_table_mode_exits_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _write_plan(tmp_path, _valid_plan_yaml())
    result = _run_dry_run(plan, as_json=False, workdir=tmp_path, monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert "Step A" in result.output
    assert "Plan load error" not in result.output


def test_valid_plan_json_mode_exits_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _write_plan(tmp_path, _valid_plan_yaml())
    result = _run_dry_run(plan, as_json=True, workdir=tmp_path, monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    payload = _extract_json(result.output)
    assert payload["total"] == 1
    assert payload["tasks"][0]["title"] == "Step A"


def test_empty_backlog_remains_legitimate_empty_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Backlog path (no --plan) keeps exit 0 for an empty backlog."""
    result = _run_dry_run(plan_file=None, as_json=False, workdir=tmp_path, monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert "No open tasks found in backlog." in result.output
