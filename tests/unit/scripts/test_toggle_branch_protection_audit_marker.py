from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import toggle_branch_protection_audit_marker as marker_mod
from toggle_branch_protection_audit_marker import (
    LABEL_DRIFT,
    LABEL_UNREACHABLE,
    TITLE_DRIFT,
    TITLE_UNREACHABLE,
    close_markers,
    main,
    open_marker,
    sync_markers,
)


def test_open_marker_opens_issue_when_none_open() -> None:
    with (
        patch.object(marker_mod, "list_open_markers", return_value=[]),
        patch.object(marker_mod, "_gh") as mock_gh,
    ):
        open_marker("acme/repo", LABEL_UNREACHABLE, TITLE_UNREACHABLE, "Auth error body")

    mock_gh.assert_called_once()
    args = mock_gh.call_args[0][0]
    assert "repos/acme/repo/issues" in args[3]
    assert f"title={TITLE_UNREACHABLE}" in args
    assert f"labels[]={LABEL_UNREACHABLE}" in args


def test_open_marker_leaves_existing_open_marker_in_place() -> None:
    with (
        patch.object(marker_mod, "list_open_markers", return_value=[42]),
        patch.object(marker_mod, "_gh") as mock_gh,
    ):
        open_marker("acme/repo", LABEL_UNREACHABLE, TITLE_UNREACHABLE, "Auth error body")

    mock_gh.assert_not_called()


def test_close_markers_closes_all_matching_issues() -> None:
    with (
        patch.object(marker_mod, "list_open_markers", return_value=[42, 99]),
        patch.object(marker_mod, "_gh") as mock_gh,
    ):
        close_markers("acme/repo", LABEL_UNREACHABLE, "Resolved")

    # 2 API calls per issue (comment + patch state=closed)
    assert mock_gh.call_count == 4


def test_sync_markers_exit_code_0_closes_both_markers() -> None:
    with (
        patch.object(marker_mod, "close_markers") as mock_close,
        patch.object(marker_mod, "open_marker") as mock_open,
    ):
        sync_markers("acme/repo", exit_code=0)

    mock_open.assert_not_called()
    assert mock_close.call_count == 2
    closed_labels = [c[0][1] for c in mock_close.call_args_list]
    assert LABEL_UNREACHABLE in closed_labels
    assert LABEL_DRIFT in closed_labels


def test_sync_markers_exit_code_1_opens_drift_and_closes_unreachable() -> None:
    with (
        patch.object(marker_mod, "ensure_label") as mock_ensure,
        patch.object(marker_mod, "open_marker") as mock_open,
        patch.object(marker_mod, "close_markers") as mock_close,
    ):
        sync_markers("acme/repo", exit_code=1, detail="missing deletion rule")

    mock_ensure.assert_called_once()
    mock_open.assert_called_once()
    assert mock_open.call_args[0][1] == LABEL_DRIFT
    assert mock_open.call_args[0][2] == TITLE_DRIFT

    mock_close.assert_called_once()
    assert mock_close.call_args[0][1] == LABEL_UNREACHABLE


def test_sync_markers_exit_code_2_opens_unreachable_and_closes_drift() -> None:
    with (
        patch.object(marker_mod, "ensure_label") as mock_ensure,
        patch.object(marker_mod, "open_marker") as mock_open,
        patch.object(marker_mod, "close_markers") as mock_close,
    ):
        sync_markers("acme/repo", exit_code=2, detail="Bad credentials (HTTP 401)")

    mock_ensure.assert_called_once()
    mock_open.assert_called_once()
    assert mock_open.call_args[0][1] == LABEL_UNREACHABLE
    assert mock_open.call_args[0][2] == TITLE_UNREACHABLE

    mock_close.assert_called_once()
    assert mock_close.call_args[0][1] == LABEL_DRIFT


def test_main_with_result_file(tmp_path: Path) -> None:
    result_file = tmp_path / "result.json"
    result_file.write_text(json.dumps({"exit_code": 2, "detail": "Token expired"}), encoding="utf-8")

    with patch.object(marker_mod, "sync_markers") as mock_sync:
        code = main(["--repo", "acme/repo", "--result-file", str(result_file)])

    assert code == 2
    mock_sync.assert_called_once_with("acme/repo", 2, "Token expired")
