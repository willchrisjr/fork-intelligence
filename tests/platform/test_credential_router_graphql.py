from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from fork_intelligence.adapters.credential_router import GitHubCredentialRouter
from fork_intelligence.adapters.github import GitHubClient
from fork_intelligence.adapters.github_graphql import GitHubGraphQLClient
from fork_intelligence.config import Settings

TOKEN = "ghp-operator-secret"  # noqa: S105 - inert fixture value.

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "github_graphql"


def _contract(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _rest_repository(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": 1296269,
        "name": "Hello-World",
        "full_name": "octocat/Hello-World",
        "html_url": "https://github.com/octocat/Hello-World",
        "clone_url": "https://github.com/octocat/Hello-World.git",
        "owner": {"login": "octocat"},
        "default_branch": "main",
        "fork": False,
        "archived": False,
        "disabled": False,
        "stargazers_count": 2500,
        "subscribers_count": 42,
        "forks_count": 1300,
        "open_issues_count": 7,
        "size": 108,
        "language": "Python",
        "license": {"spdx_id": "MIT"},
        "topics": ["forks", "analysis"],
        "created_at": "2011-01-26T19:01:12Z",
        "updated_at": "2026-07-01T10:00:00Z",
        "pushed_at": "2026-06-30T09:30:00Z",
    }
    data.update(overrides)
    return data


def _router(
    *,
    graphql_response: Any,
    rest_response: Any = None,
    token: str | None = TOKEN,
) -> tuple[GitHubCredentialRouter, list[str]]:
    """Router over mock REST and GraphQL transports, recording which was hit."""
    calls: list[str] = []
    settings = Settings(github_token=token)

    def wrap(label: str, handler: Any) -> Any:
        def handle(request: httpx.Request) -> httpx.Response:
            calls.append(label)
            return handler(request) if callable(handler) else handler

        return handle

    rest_handler = rest_response or (
        lambda _: httpx.Response(200, json=_rest_repository())
    )

    def rest_client(label: str) -> GitHubClient:
        return GitHubClient(
            settings,
            httpx.Client(
                transport=httpx.MockTransport(wrap(label, rest_handler)),
                base_url=settings.github_api_url,
            ),
        )

    graphql_client = None
    if token is not None:
        graphql_client = GitHubGraphQLClient(
            settings,
            httpx.Client(
                transport=httpx.MockTransport(wrap("graphql", graphql_response)),
                base_url=settings.github_api_url,
            ),
        )

    router = GitHubCredentialRouter(
        settings,
        authenticated=rest_client("rest_authenticated") if token else None,
        anonymous=rest_client("rest_anonymous"),
        graphql=graphql_client,
    )
    return router, calls


def _ok_graphql(name: str = "complete") -> Any:
    return lambda _: httpx.Response(200, json=_contract(name))


def test_graphql_is_attempted_while_authenticated_and_attributed_per_field() -> None:
    router, calls = _router(graphql_response=_ok_graphql())

    with router:
        repository = router.get_repository("octocat", "Hello-World")
        provenance = router.last_repository_provenance

    assert calls == ["graphql", "rest_authenticated"]
    assert repository["github_id"] == 1296269
    assert provenance["source"] == "github_graphql+github_rest"
    # Fields GraphQL supplied and agreed on are credited to it.
    assert provenance["fields"]["stars"] == "github_graphql"
    assert provenance["fields"]["default_branch"] == "github_graphql"
    # clone_url is outside the accelerated set, so REST remains its source.
    assert provenance["fields"]["clone_url"] == "github_rest"
    assert provenance["graphql_cost"] == 1
    assert provenance["branches_observed"] == 2


def test_graphql_is_skipped_entirely_without_a_credential() -> None:
    router, calls = _router(graphql_response=_ok_graphql(), token=None)

    with router:
        router.get_repository("octocat", "Hello-World")
        provenance = router.last_repository_provenance

    assert "graphql" not in calls
    assert provenance["source"] == "github_rest"
    assert provenance["graphql_attempted"] is False


def test_graphql_is_skipped_once_the_router_has_fallen_back() -> None:
    """AC: the accelerator runs only while the router is in authenticated mode."""
    rest_states = iter([httpx.Response(403, headers={"x-ratelimit-remaining": "0"})])

    def rest(_: httpx.Request) -> httpx.Response:
        return next(rest_states, httpx.Response(200, json=_rest_repository()))

    router, calls = _router(graphql_response=_ok_graphql(), rest_response=rest)

    with router:
        router.get_repository("octocat", "Hello-World")  # falls back to anonymous
        calls.clear()
        router.get_repository("octocat", "Hello-World")

    assert router.credential_mode == "anonymous"
    assert "graphql" not in calls


def test_graphql_rejection_records_a_transition_through_the_existing_router_path() -> None:
    """The accelerator reuses WO-2's fallback machinery rather than its own."""

    def graphql(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, headers={"x-ratelimit-remaining": "0"})

    router, calls = _router(graphql_response=graphql)

    with router:
        router.get_repository("octocat", "Hello-World")

    assert router.credential_mode == "anonymous"
    transitions = router.drain_transitions()
    assert [transition.reason for transition in transitions] == ["operator_credential_rejected"]
    # Having learned the credential is bad, REST goes straight to anonymous.
    assert calls == ["graphql", "rest_anonymous"]


@pytest.mark.parametrize("fixture", ["partial"])
def test_partial_graphql_never_overwrites_valid_rest_data(fixture: str) -> None:
    router, _ = _router(graphql_response=_ok_graphql(fixture))

    with router:
        repository = router.get_repository("octocat", "Hello-World")
        provenance = router.last_repository_provenance

    # The fixture nulls these; REST values must survive untouched.
    assert repository["forks"] == 1300
    assert repository["language"] == "Python"
    assert repository["license"] == "MIT"
    assert provenance["fields"]["forks"] == "github_rest"
    assert provenance["fields"]["language"] == "github_rest"
    assert provenance["partial_errors"] == ["FORBIDDEN", "RATE_LIMITED"]


def test_malformed_graphql_degrades_to_a_pure_rest_result() -> None:
    router, calls = _router(
        graphql_response=lambda _: httpx.Response(200, content=b"not json")
    )

    with router:
        repository = router.get_repository("octocat", "Hello-World")
        provenance = router.last_repository_provenance

    assert repository["github_id"] == 1296269
    assert calls == ["graphql", "rest_authenticated"]
    assert provenance["source"] == "github_rest"
    assert provenance["partial_errors"] == ["malformed_response"]
    # A failed acceleration is not a credential problem.
    assert router.credential_mode == "authenticated"


def test_disagreement_prefers_rest_and_is_recorded() -> None:
    """A silent divergence would make accelerated coverage untrustworthy."""
    router, _ = _router(
        graphql_response=_ok_graphql(),
        rest_response=lambda _: httpx.Response(
            200, json=_rest_repository(stargazers_count=999)
        ),
    )

    with router:
        repository = router.get_repository("octocat", "Hello-World")
        provenance = router.last_repository_provenance

    assert repository["stars"] == 999
    assert provenance["fields"]["stars"] == "github_rest"
    assert "stars" in provenance["divergent_fields"]
