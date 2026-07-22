from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from fork_intelligence.adapters.github_graphql import (
    ACCELERATED_FIELDS,
    GitHubGraphQLClient,
)
from fork_intelligence.config import Settings
from fork_intelligence.errors import GitHubError

TOKEN = "ghp-operator-secret"  # noqa: S105 - inert fixture value.

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "github_graphql"


def _contract(name: str) -> dict[str, Any]:
    """Load a recorded GraphQL contract fixture."""
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _client(handler: Any, **overrides: Any) -> GitHubGraphQLClient:
    settings = Settings(github_token=TOKEN, **overrides)
    transport = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url=settings.github_api_url,
    )
    return GitHubGraphQLClient(settings, transport)


def _responds(payload: dict[str, Any], status: int = 200) -> Any:
    def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return handle


# --- Complete responses -------------------------------------------------------


def test_complete_response_normalizes_into_the_rest_provider_model() -> None:
    with _client(_responds(_contract("complete"))) as graphql:
        result = graphql.fetch_repository("octocat", "Hello-World")

    assert result.fields["github_id"] == 1296269
    assert result.fields["owner"] == "octocat"
    assert result.fields["full_name"] == "octocat/Hello-World"
    assert result.fields["default_branch"] == "main"
    assert result.fields["language"] == "Python"
    assert result.fields["license"] == "MIT"
    assert result.fields["watchers"] == 42
    assert result.fields["open_issues"] == 7
    assert result.fields["topics"] == ["forks", "analysis"]
    assert result.partial_errors == []
    assert result.cost == 1
    assert result.quota["resource"] == "graphql"


def test_branch_metadata_is_batched_in_the_same_request() -> None:
    with _client(_responds(_contract("complete"))) as graphql:
        result = graphql.fetch_repository("octocat", "Hello-World")

    assert result.branches == [
        {"name": "main", "head_sha": "a" * 40},
        {"name": "feature/topic", "head_sha": "b" * 40},
    ]


def test_normalized_fields_never_exceed_the_declared_accelerated_set() -> None:
    """REST stays the correctness baseline for anything outside this set."""
    with _client(_responds(_contract("complete"))) as graphql:
        result = graphql.fetch_repository("octocat", "Hello-World")

    assert set(result.fields) <= ACCELERATED_FIELDS


def test_query_is_bounded_by_the_configured_branch_limit() -> None:
    sent: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=_contract("complete"))

    with _client(handle, max_graphql_branches=25) as graphql:
        graphql.fetch_repository("octocat", "Hello-World")

    assert sent[0]["variables"]["branchLimit"] == 25


# --- Partial responses --------------------------------------------------------


def test_partial_response_keeps_present_fields_and_omits_absent_ones() -> None:
    with _client(_responds(_contract("partial"))) as graphql:
        result = graphql.fetch_repository("octocat", "Hello-World")

    # Present values survive.
    assert result.fields["github_id"] == 1296269
    assert result.fields["stars"] == 2500
    # Null values are omitted entirely rather than defaulted to zero, so the
    # caller can tell "not supplied" from "genuinely zero" and use REST.
    for absent in ("updated_at", "pushed_at", "forks", "size_kb", "language", "license"):
        assert absent not in result.fields
    assert "open_issues" not in result.fields
    assert "topics" not in result.fields


def test_partial_errors_are_reduced_to_classifications() -> None:
    with _client(_responds(_contract("partial"))) as graphql:
        result = graphql.fetch_repository("octocat", "Hello-World")

    assert result.partial_errors == ["FORBIDDEN", "RATE_LIMITED"]
    # Provider free text must not ride along into anything persisted.
    assert "withheld by the provider" not in str(result)


# --- Rate limiting and rejection ---------------------------------------------


@pytest.mark.parametrize(
    ("status", "code"),
    [(401, "github_unauthorized"), (403, "github_rate_limited"), (429, "github_rate_limited")],
)
def test_rejection_and_quota_exhaustion_raise_router_recognized_codes(
    status: int, code: str
) -> None:
    """Raised, not swallowed, so the router can record a mode transition."""

    def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers={"x-ratelimit-remaining": "0"})

    with _client(handle) as graphql, pytest.raises(GitHubError) as caught:
        graphql.fetch_repository("octocat", "Hello-World")

    assert caught.value.code == code
    assert caught.value.details["quota"]["remaining"] == 0


def test_cost_over_budget_is_refused_rather_than_normalized() -> None:
    payload = _contract("complete")
    payload["data"]["rateLimit"]["cost"] = 500

    with _client(_responds(payload), max_graphql_cost=50) as graphql:
        result = graphql.fetch_repository("octocat", "Hello-World")

    assert result.is_empty
    assert "cost_budget_exceeded" in result.partial_errors
    assert result.cost == 500


# --- Malformed and unavailable ------------------------------------------------


@pytest.mark.parametrize(
    "handler_response",
    [
        httpx.Response(200, content=b"not json at all"),
        httpx.Response(200, json=["unexpected", "shape"]),
        httpx.Response(200, json={"data": {"repository": None}}),
        httpx.Response(500, json={"message": "server error"}),
    ],
)
def test_malformed_or_unavailable_responses_degrade_instead_of_raising(
    handler_response: httpx.Response,
) -> None:
    with _client(lambda _: handler_response) as graphql:
        result = graphql.fetch_repository("octocat", "Hello-World")

    assert result.is_empty
    assert result.partial_errors  # the reason is always named


def test_transport_failure_degrades_instead_of_raising() -> None:
    def handle(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with _client(handle) as graphql:
        result = graphql.fetch_repository("octocat", "Hello-World")

    assert result.is_empty
    assert result.partial_errors == ["transport_error"]


# --- Construction guards ------------------------------------------------------


def test_graphql_requires_a_credential() -> None:
    with pytest.raises(ValueError, match="requires an operator credential"):
        GitHubGraphQLClient(Settings())


def test_graphql_refuses_a_non_canonical_origin() -> None:
    """A token may only ever be sent to the canonical GitHub origin."""
    tokenless_custom_origin = Settings(github_api_url="https://api.github.test")
    settings = tokenless_custom_origin.model_copy(update={"github_token": TOKEN})

    with pytest.raises(ValueError, match="canonical GitHub API origin"):
        GitHubGraphQLClient(settings)


def test_credential_is_sent_only_as_a_bearer_header() -> None:
    seen: list[tuple[str | None, bytes]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append((request.headers.get("authorization"), request.content))
        return httpx.Response(200, json=_contract("complete"))

    settings = Settings(github_token=TOKEN)
    graphql = GitHubGraphQLClient(settings)
    graphql.client = httpx.Client(
        transport=httpx.MockTransport(handle),
        base_url=settings.github_api_url,
        headers=graphql.client.headers,
    )
    with graphql:
        graphql.fetch_repository("octocat", "Hello-World")

    authorization, body = seen[0]
    assert authorization == f"Bearer {TOKEN}"
    # Never in the request body, where it would be logged as query variables.
    assert TOKEN.encode() not in body
