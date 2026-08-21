"""Derive a run's read-path set from its Merkle-chained journal (#4180).

Merge admission needs to know which repository paths a task's run actually
read. The authoritative source is the run's journal: a declaration can be
stale, but a journal row cannot be inserted after the fact without breaking
the chain head. This module composes the pieces that already exist:

* journal rows and chain verification live in
  :mod:`bernstein.core.replay.journal` (:func:`~.journal.verify_events`);
* the closed set of journal payload fields that name an accessed filesystem
  path is :data:`~.journal.PATH_FIELDS` (shared with clean-run attestation).

The derivation is a pure function: same journal bytes, same worktree root,
same result. It refuses on a broken chain or an unusable journal rather
than returning a partial set -- a trimmed set would silently weaken the
merge-admission check this feeds.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bernstein.core.replay.journal import (
    PATH_FIELDS,
    JournalParseError,
    load_events,
    verify_events,
)


class ReadPathDerivationError(ValueError):
    """The read-path set could not be derived from the journal.

    ``reason`` distinguishes the failure classes so a caller can report or
    test each distinctly:

    * :attr:`REASON_MISSING` - the journal file does not exist;
    * :attr:`REASON_EMPTY` - the journal exists but holds no rows;
    * :attr:`REASON_BROKEN_CHAIN` - rows do not recompute from genesis
      (mutation, torn write, or any unparsable line under strict reading).
    """

    REASON_MISSING = "journal_missing"
    REASON_EMPTY = "journal_empty"
    REASON_BROKEN_CHAIN = "broken_chain"

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ReadPathSet:
    """Derived read-path classification for one run.

    Attributes:
        read_paths: Worktree-relative POSIX paths (``/`` separators) inside
            the worktree root, in no particular order.
        out_of_tree: Absolute POSIX paths outside the worktree root. These
            are returned, not dropped: out-of-tree reads are exactly what a
            merge-admission caller will want to see.
    """

    read_paths: frozenset[str]
    out_of_tree: frozenset[str]


def derive_read_paths(journal_path: Path, worktree_root: Path) -> ReadPathSet:
    """Derive the paths a run read from its journal.

    Args:
        journal_path: Path to the run's ``journal.jsonl``.
        worktree_root: Repository root the run was scoped to. Paths inside
            it are normalized to worktree-relative POSIX form; paths outside
            it are returned separately in :attr:`ReadPathSet.out_of_tree`.

    Returns:
        The classified read-path set.

    Raises:
        ReadPathDerivationError: The journal is missing, empty, or its
            chain does not verify. The reason attribute distinguishes the
            three cases. Never returns a partial set.
    """
    if not journal_path.exists():
        raise ReadPathDerivationError(
            ReadPathDerivationError.REASON_MISSING,
            f"journal does not exist: {journal_path}",
        )

    try:
        loaded = load_events(journal_path, strict=True)
    except JournalParseError as exc:
        raise ReadPathDerivationError(
            ReadPathDerivationError.REASON_BROKEN_CHAIN,
            f"journal contains an unparsable row: {exc}",
        ) from exc

    if not loaded.events:
        raise ReadPathDerivationError(
            ReadPathDerivationError.REASON_EMPTY,
            f"journal holds no rows: {journal_path}",
        )

    chain = verify_events(loaded.events)
    if not chain.chain_consistent:
        detail = "; ".join(chain.errors) or "chain verification failed"
        raise ReadPathDerivationError(
            ReadPathDerivationError.REASON_BROKEN_CHAIN,
            f"journal chain does not verify: {detail}",
        )

    root = worktree_root.resolve()
    read_paths: set[str] = set()
    out_of_tree: set[str] = set()
    for row in loaded.events:
        for field in PATH_FIELDS:
            raw = row.get(field)
            if not isinstance(raw, str) or not raw:
                continue
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = root / candidate
            resolved = candidate.resolve()
            try:
                relative = resolved.relative_to(root)
            except ValueError:
                out_of_tree.add(resolved.as_posix())
            else:
                read_paths.add(relative.as_posix())
    return ReadPathSet(
        read_paths=frozenset(read_paths),
        out_of_tree=frozenset(out_of_tree),
    )
