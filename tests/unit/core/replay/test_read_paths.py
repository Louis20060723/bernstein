"""Derive a run's read-path set from its journal (#4180).

Merge admission needs to know which repository paths a task's run actually
read, and that set must come from the Merkle-chained journal rather than
from anything the agent declares. These tests pin the derivation contract:

* known rows yield exactly the expected worktree-relative POSIX path set;
* a mutated row (byte flip in the file) raises the dedicated error instead
  of returning a smaller set;
* an absent or empty journal raises the dedicated error with a distinct
  reason;
* a row naming a path outside the worktree root lands in the out-of-tree
  set, absent from the main set;
* two calls over the same journal yield identical results (iteration-
  independent equality).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bernstein.core.replay.journal import EventJournal
from bernstein.core.replay.read_paths import (
    ReadPathDerivationError,
    ReadPathSet,
    derive_read_paths,
)


def _journal(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    """Append ``rows`` into a fresh Merkle-chained journal; return its path.

    Each row dict is passed to ``EventJournal.record`` verbatim, so a row
    like ``{"event": "read", "path": "src/foo.py"}`` writes a journal line
    carrying the ``path`` payload field.
    """
    journal = EventJournal("read-paths-run", tmp_path / ".sdd")
    for row in rows:
        event = str(row["event"])
        data = {k: v for k, v in row.items() if k != "event"}
        journal.record(event, **data)
    return journal.path


def _flip_byte(path: Path, needle: bytes, index: int) -> None:
    """Flip one byte inside the first occurrence of ``needle``."""
    data = path.read_bytes()
    pos = data.index(needle) + index
    flipped = bytearray(data)
    flipped[pos] = ord("x") if flipped[pos] != ord("x") else ord("y")
    path.write_bytes(bytes(flipped))


def test_known_rows_yield_expected_relative_path_set(tmp_path: Path) -> None:
    path = _journal(
        tmp_path,
        [
            {"event": "read", "path": "src/foo.py"},
            {"event": "read", "path": "docs/bar.md"},
            {"event": "write", "file_path": "tests/test_foo.py"},
            {"event": "step", "value": 1},  # no path field: ignored
        ],
    )

    result = derive_read_paths(path, tmp_path)

    assert isinstance(result, ReadPathSet)
    assert result.read_paths == frozenset({"src/foo.py", "docs/bar.md", "tests/test_foo.py"})
    assert result.out_of_tree == frozenset()


def test_absolute_in_tree_path_is_normalized_to_relative(tmp_path: Path) -> None:
    in_tree = tmp_path / "src" / "baz.py"
    path = _journal(tmp_path, [{"event": "read", "path": str(in_tree)}])

    result = derive_read_paths(path, tmp_path)

    assert result.read_paths == frozenset({"src/baz.py"})
    assert result.out_of_tree == frozenset()


def test_duplicate_paths_are_collected_once(tmp_path: Path) -> None:
    path = _journal(
        tmp_path,
        [
            {"event": "read", "path": "src/foo.py"},
            {"event": "read", "path": "src/foo.py"},
            {"event": "read", "file_path": "src/foo.py"},
        ],
    )

    result = derive_read_paths(path, tmp_path)

    assert result.read_paths == frozenset({"src/foo.py"})


def test_mutated_row_raises_dedicated_error_not_smaller_set(tmp_path: Path) -> None:
    path = _journal(tmp_path, [{"event": "read", "path": "src/foo.py"}])
    _flip_byte(path, b"src/foo.py", 4)  # corrupt the payload -> chain breaks

    with pytest.raises(ReadPathDerivationError) as exc_info:
        derive_read_paths(path, tmp_path)

    assert exc_info.value.reason == ReadPathDerivationError.REASON_BROKEN_CHAIN


def test_absent_journal_raises_with_distinct_reason(tmp_path: Path) -> None:
    missing = tmp_path / "no" / "journal.jsonl"

    with pytest.raises(ReadPathDerivationError) as exc_info:
        derive_read_paths(missing, tmp_path)

    assert exc_info.value.reason == ReadPathDerivationError.REASON_MISSING


def test_empty_journal_raises_with_distinct_reason(tmp_path: Path) -> None:
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")

    with pytest.raises(ReadPathDerivationError) as exc_info:
        derive_read_paths(empty, tmp_path)

    assert exc_info.value.reason == ReadPathDerivationError.REASON_EMPTY


def test_out_of_tree_path_lands_in_separate_set(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside" / "secret.py"
    path = _journal(
        tmp_path,
        [
            {"event": "read", "path": "src/foo.py"},
            {"event": "read", "path": str(outside)},
        ],
    )

    result = derive_read_paths(path, tmp_path)

    assert result.read_paths == frozenset({"src/foo.py"})
    assert result.out_of_tree == frozenset({str(outside)})


def test_determinism_two_calls_identical_results(tmp_path: Path) -> None:
    path = _journal(
        tmp_path,
        [
            {"event": "read", "path": "src/foo.py"},
            {"event": "read", "path": "docs/bar.md"},
        ],
    )

    first = derive_read_paths(path, tmp_path)
    second = derive_read_paths(path, tmp_path)

    assert first == second
    assert first.read_paths == second.read_paths
    assert first.out_of_tree == second.out_of_tree
