"""The gate must block on the finding types the configured reviewer emits.

``scripts/review_bot_ack.py`` splits review-bot comments into must-address and
informational, and only must-address findings hold the required
``review-bot-ack`` context. That split was written against severity headings
embedded in prose (``**Potential issue**``, ``**bug:**``, ``nit:``). The
reviewer this repository configures does not write those headings: it states
its category in a machine-readable marker instead, e.g.::

    <!--
    _Finding type:_ `Logical Bugs`
    -->

so every finding it files fell through to the informational bucket. The gate
counted the findings, rendered them in the sticky summary, and exited 0 - a
correctness defect and a typo were graded identically.

These tests pin the taxonomy against bodies captured verbatim from findings the
reviewer filed on this repository. They assert both directions: a correctness
category blocks, and a cosmetic category stays informational, so the fix cannot
degenerate into "block on any finding" - that would make the ack marker
mandatory on every typo and train operators to rubber-stamp it.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Generator
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "review_bot_ack.py"


@pytest.fixture
def ack() -> Generator[ModuleType, None, None]:
    """Load scripts/review_bot_ack.py as an importable module."""
    spec = importlib.util.spec_from_file_location("review_bot_ack_taxonomy_under_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


def _body(prose: str, marker: str, badge_content: str, severity: str) -> str:
    """Assemble a finding in the shape the configured reviewer posts them.

    The trailing "Prompt for AI Agents" block is reproduced because it is the
    bulk of a real body and it is dense with words the prose heuristics look
    for; a classifier that reads it instead of the marker misgrades findings.
    """
    return (
        f"{prose}\n"
        f"<!--\n{marker}\n-->\n\n"
        f'<picture><img src="https://baz.co/api/v2/badges?type=reviewer'
        f'&content={badge_content}&severity={severity}" alt="Severity" height="24" /></picture>\n\n'
        "**Baz can fix this** - reply `apply commit` / `apply pr` to fix without changes, "
        "or comment to modify the plan.\n\n"
        "<details>\n<summary>Prompt for AI Agents</summary>\n\n"
        "```text\nBefore applying, verify this suggestion against the current code. "
        "Two related issues need fixing in this style of block.\n```\n\n"
        "</details>\n"
    )


# --- bodies captured from findings filed on this repository -----------------

# A release workflow creates its GitHub Release with GITHUB_TOKEN, which does
# not start follow-up workflows, so Docker/Homebrew/SBOM publication silently
# never runs. Graded `high` by the reviewer.
LOGICAL_BUG = _body(
    "### Major/minor release follow-ups undocumented\n\n"
    "`docs/operations/release.md` says the Docker/Homebrew/SBOM follow-ups run from either\n"
    "`publish.yml` or the `release` event, but `release-major-minor.yml` creates the release\n"
    "with `GITHUB_TOKEN`, which doesn't start new workflows, so those follow-ups never run.\n",
    "_Finding type:_ `Logical Bugs`",
    "Logical%20Bugs",
    "high",
)

# A watcher documents that a reconcile workflow checks the published version,
# but the workflow reads a local file, so a republished tag misses a gap.
BREAKING_CHANGE = _body(
    "### Handoff notice checks wrong version\n\n"
    "`copr_build_watch.py` says `reconcile-release.yml` checks the published Copr version,\n"
    "but the workflow reads `pj_version` from the checked-out `pyproject.toml`.\n",
    "_Finding type:_ `Breaking Changes`",
    "Breaking%20Changes",
    "medium",
)

# A polling loop starts another fetch with a fixed timeout even when less time
# remains, so it can run past its configured deadline.
DESIGN_REVIEW = _body(
    "### Watcher exceeds configured deadline\n\n"
    "`watch` starts another `fetch` with `fetch_state`'s fixed 30-second timeout even when\n"
    "less time remains, so a late poll can run past `deadline_seconds`.\n",
    "_Finding type:_ `Verifiable Architecture & Design Review`",
    "Verifiable%20Architecture%20%26%20Design%20Review",
    "low",
)

# A missing relative pronoun in a release note.
NAMING_AND_TYPOS = _body(
    "### Release note contains grammatical error\n\n"
    "Could we change ``on a workspace `bernstein init` has just created`` to\n"
    "``on a workspace that `bernstein init` has just created``?\n",
    "_Finding type:_ `Naming and Typos`",
    "Naming%20and%20Typos",
    "low",
)

# A checklist in an operations doc fetches two comment endpoints but not the
# reviews endpoint. A documentation-completeness point, graded `low`.
GUIDELINES_LOW = _body(
    "### Shepherd checklist misses review endpoint\n\n"
    "In the Shepherds checklist, step 2 only fetches `pulls/<n>/comments` and\n"
    "`issues/<n>/comments`, so the human workflow misses the review artifacts.\n",
    "_Finding type:_ `AI Coding Guidelines`",
    "AI%20Coding%20Guidelines",
    "low",
)

# Same category, but the finding is a path-traversal hole: a user-controlled
# pattern reaches `unlink()` with no resolved-path containment check. Graded
# `high`. This is why the category alone cannot decide the split.
GUIDELINES_HIGH = _body(
    "### Overstated file-delete safety in docs\n\n"
    '`file_remove()` feeds user-controlled `--pattern` into `wt.glob(f"src/**/{pattern}")`\n'
    "and then calls `target.unlink()` without a resolved-path containment check, so the\n"
    "promise that `file-remove` won't delete outside the worktree isn't enforced.\n",
    "_Finding type:_ `AI Coding Guidelines`",
    "AI%20Coding%20Guidelines",
    "high",
)

# The reviewer files one finding under two categories, with a plural marker.
MULTI_TYPE = _body(
    "### Shepherds step 3 misstates where severity comes from\n\n"
    "`Shepherds` step 3 tells operators to classify `pulls/<n>/reviews` into must-address vs\n"
    "informational, but the gate derives that split from the comment endpoints only.\n",
    "_Finding types:_ `Logical Bugs` `AI Coding Guidelines`",
    "Logical%20Bugs%20%C2%B7%20AI%20Coding%20Guidelines",
    "low",
)

# The reviewer's own follow-up confirming an earlier finding was applied. It
# carries no marker and must not be graded as a fresh blocking finding.
RESOLUTION_REPLY = (
    "Commit 9a71f38 **addressed** this comment by separating comment severity "
    "classification from review coverage, explicitly stating that `pulls/<n>/reviews` "
    "carries no severity and only supplies per-bot head-commit coverage.\n"
)


# --- correctness categories block ------------------------------------------


def test_a_logical_bug_finding_is_must_address(ack: ModuleType) -> None:
    """The reviewer's bug category is what the gate exists to hold PRs on."""
    assert ack.classify(LOGICAL_BUG) == "must-address"


def test_a_breaking_change_finding_is_must_address(ack: ModuleType) -> None:
    """A compatibility break is a correctness defect, not a suggestion."""
    assert ack.classify(BREAKING_CHANGE) == "must-address"


def test_a_design_review_finding_is_must_address(ack: ModuleType) -> None:
    """The design category files correctness defects, e.g. a blown deadline."""
    assert ack.classify(DESIGN_REVIEW) == "must-address"


def test_a_multi_type_finding_blocks_when_any_type_blocks(ack: ModuleType) -> None:
    """A finding filed under several categories takes the strictest one.

    The marker is plural (``_Finding types:_``) with one backticked name per
    category, so the parser must read all of them, not just the first.
    """
    assert ack.classify(MULTI_TYPE) == "must-address"


# --- cosmetic categories stay informational --------------------------------


def test_a_typo_finding_stays_informational(ack: ModuleType) -> None:
    """A missing relative pronoun must not require an ack marker to merge.

    If cosmetic findings block, the ack marker becomes routine and stops
    carrying the signal that a real defect was consciously accepted.
    """
    assert ack.classify(NAMING_AND_TYPOS) == "informational"


def test_a_low_severity_guidelines_finding_stays_informational(ack: ModuleType) -> None:
    """Convention adherence is advisory at the severity the reviewer assigns."""
    assert ack.classify(GUIDELINES_LOW) == "informational"


def test_a_resolution_reply_is_not_a_blocking_finding(ack: ModuleType) -> None:
    """The reviewer's "addressed by commit X" follow-up carries no marker."""
    assert ack.classify(RESOLUTION_REPLY) == "informational"


# --- severity escalates across categories -----------------------------------


def test_high_severity_escalates_an_informational_category(ack: ModuleType) -> None:
    """Category alone under-reads: this one is a path-traversal delete.

    The reviewer filed a user-controlled path reaching ``unlink()`` under its
    conventions category and graded it `high`. Trusting the category would let
    it through, so the assigned severity escalates independently.
    """
    assert ack.classify(GUIDELINES_HIGH) == "must-address"


# --- unmapped categories fail closed ---------------------------------------


def test_an_unmapped_finding_type_is_must_address(ack: ModuleType) -> None:
    """A category nobody has triaged yet blocks rather than passing silently.

    This bug was invisible precisely because unrecognised findings defaulted to
    informational. Failing closed makes the next new category announce itself
    on a PR instead of being waved through; the ack marker is the escape hatch
    while the taxonomy is updated.
    """
    unmapped = _body(
        "### Some newly introduced category\n\nA finding of a kind not yet mapped.\n",
        "_Finding type:_ `Concurrency Hazards`",
        "Concurrency%20Hazards",
        "low",
    )
    assert ack.classify(unmapped) == "must-address"


def test_every_mapped_category_is_classified_exactly_once(ack: ModuleType) -> None:
    """No category may be listed as both blocking and informational."""
    overlap = ack.MUST_ADDRESS_FINDING_TYPES & ack.INFORMATIONAL_FINDING_TYPES
    assert overlap == frozenset()


def test_finding_type_markers_are_read_from_the_whole_body(ack: ModuleType) -> None:
    """The marker parser returns every category the body names, lowercased."""
    assert ack.finding_types(MULTI_TYPE) == ["logical bugs", "ai coding guidelines"]
    assert ack.finding_types(LOGICAL_BUG) == ["logical bugs"]
    assert ack.finding_types(RESOLUTION_REPLY) == []


# --- the prose heuristics still serve bodies with no marker -----------------


def test_prose_severity_headings_still_classify(ack: ModuleType) -> None:
    """Bodies with no marker keep falling back to the heading heuristics.

    The marker path is additive: a reviewer that writes ``**Potential issue**``
    in prose rather than a structured marker must keep grading as before.
    """
    assert ack.classify("**Potential issue**\n\nThis dereferences a null.") == "must-address"
    assert ack.classify("nit: spacing here") == "informational"
