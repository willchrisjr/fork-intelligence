from __future__ import annotations

import pytest

from fork_intelligence.domain.repository_input import parse_repository_identifier
from fork_intelligence.errors import PlatformError


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("octocat/Hello-World", "octocat/Hello-World"),
        ("  octocat/Hello-World  ", "octocat/Hello-World"),
        ("https://github.com/octocat/Hello-World", "octocat/Hello-World"),
        ("https://github.com/octocat/Hello-World.git", "octocat/Hello-World"),
    ],
)
def test_parse_repository_identifier_accepts_only_supported_forms(
    value: str, expected: str
) -> None:
    identifier = parse_repository_identifier(value)

    assert identifier.full_name == expected
    assert identifier.clone_url == f"https://github.com/{expected}.git"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "owner",
        "owner/repo/extra",
        "owner/repo?tab=readme",
        "owner/repo#fragment",
        "owner@repo",
        "owner:repo",
        "owner\\repo",
        "-owner/repo",
        "owner/-repo",
        "owner/../repo",
        "owner/repo\x00tail",
        "git@github.com:owner/repo.git",
        "http://github.com/owner/repo",
        "https://example.com/owner/repo",
        "https://user:password@github.com/owner/repo",
        "https://github.com:443/owner/repo",
        "https://github.com/owner/repo?x=1",
        "https://github.com/owner/repo#readme",
        "https://github.com/owner/%2e%2e",
        "https://github.com/owner/repo%2Fextra",
    ],
)
def test_parse_repository_identifier_rejects_ambiguous_or_hostile_values(value: str) -> None:
    with pytest.raises(PlatformError) as caught:
        parse_repository_identifier(value)

    assert caught.value.code == "invalid_repository"
    assert caught.value.status_code == 422


def test_repository_components_are_length_bounded() -> None:
    with pytest.raises(PlatformError):
        parse_repository_identifier(f"{'a' * 101}/repository")
