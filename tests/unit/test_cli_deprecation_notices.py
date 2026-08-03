"""Unit tests for the deprecation notices on ``bernstein consensus`` and
``bernstein issue-to-pr`` (#3144).

Both command groups inspect state that no shipped runtime writes. They stay
registered through the 3.10 line with a deprecation warning on invocation and
are unregistered in 4.0.0. The core modules stay importable and unchanged.
"""

from __future__ import annotations

from click.testing import CliRunner

from bernstein.cli.commands.consensus_cmd import consensus_group
from bernstein.cli.commands.issue_to_pr_cmd import issue_to_pr_group


def _stderr_lines(result) -> list[str]:
    return [line for line in (result.stderr or "").splitlines() if line.strip()]


def test_consensus_emits_deprecation_notice_on_invocation() -> None:
    runner = CliRunner()
    result = runner.invoke(consensus_group, ["list"])

    assert result.exit_code == 0, result.output
    # The deprecation notice goes to stderr so stdout stays machine-parseable.
    assert any("deprecation" in line and "4.0.0" in line for line in _stderr_lines(result))
    assert "no relay entries" in result.stdout


def test_consensus_stderr_does_not_pollute_stdout() -> None:
    runner = CliRunner()
    result = runner.invoke(consensus_group, ["list"])

    assert result.exit_code == 0, result.output
    assert "deprecation" not in result.stdout


def test_consensus_help_mentions_deprecation() -> None:
    runner = CliRunner()
    result = runner.invoke(consensus_group, ["--help"])

    assert result.exit_code == 0, result.output
    assert "Deprecated" in result.stdout
    assert "4.0.0" in result.stdout


def test_issue_to_pr_emits_deprecation_notice_on_invocation() -> None:
    runner = CliRunner()
    # Missing ISSUE_ID triggers a usage error, but the group callback (where
    # the deprecation notice lives) runs first -- so no gh subprocess, no
    # network, and the notice is still emitted.
    result = runner.invoke(issue_to_pr_group, ["trace"])

    assert result.exit_code == 2
    assert any("deprecation" in line and "4.0.0" in line for line in _stderr_lines(result))


def test_issue_to_pr_stderr_does_not_pollute_stdout() -> None:
    runner = CliRunner()
    result = runner.invoke(issue_to_pr_group, ["--help"])

    assert result.exit_code == 0, result.output
    assert "Deprecated" in result.stdout
    assert "4.0.0" in result.stdout


def test_issue_to_pr_help_mentions_deprecation() -> None:
    runner = CliRunner()
    result = runner.invoke(issue_to_pr_group, ["--help"])

    assert result.exit_code == 0, result.output
    assert "Deprecated" in result.stdout
    assert "4.0.0" in result.stdout
