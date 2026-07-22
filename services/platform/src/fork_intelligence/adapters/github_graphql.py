from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from fork_intelligence.config import Settings, get_settings
from fork_intelligence.errors import GitHubError

CANONICAL_GRAPHQL_ORIGIN = "https://api.github.com"

# One bounded document. Branch pagination is capped by `max_graphql_branches`
# and there is no nested connection beyond refs, so node count stays linear in
# the branch limit rather than multiplying across levels.
REPOSITORY_QUERY = """
query RepositoryMetadata($owner: String!, $name: String!, $branchLimit: Int!) {
  rateLimit { limit cost remaining nodeCount }
  repository(owner: $owner, name: $name) {
    databaseId
    name
    nameWithOwner
    url
    isFork
    isArchived
    isDisabled
    createdAt
    updatedAt
    pushedAt
    stargazerCount
    forkCount
    diskUsage
    owner { login }
    defaultBranchRef { name target { oid } }
    primaryLanguage { name }
    licenseInfo { spdxId }
    watchers { totalCount }
    issues(states: OPEN) { totalCount }
    repositoryTopics(first: 20) { nodes { topic { name } } }
    refs(refPrefix: "refs/heads/", first: $branchLimit) {
      totalCount
      nodes { name target { oid } }
    }
  }
}
"""

# Fields this transport is allowed to contribute. REST remains the correctness
# baseline, so anything absent here is never sourced from GraphQL.
ACCELERATED_FIELDS = frozenset(
    {
        "github_id",
        "owner",
        "name",
        "full_name",
        "html_url",
        "default_branch",
        "is_fork",
        "archived",
        "disabled",
        "created_at",
        "updated_at",
        "pushed_at",
        "stars",
        "watchers",
        "forks",
        "open_issues",
        "size_kb",
        "language",
        "license",
        "topics",
    }
)


@dataclass(frozen=True, slots=True)
class GraphQLResult:
    """Whatever GraphQL could supply, with everything it could not left absent."""

    fields: dict[str, Any] = field(default_factory=dict)
    branches: list[dict[str, Any]] = field(default_factory=list)
    quota: dict[str, Any] = field(default_factory=dict)
    cost: int | None = None
    #: Sanitized GraphQL error classifications, never raw provider messages.
    partial_errors: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.fields


class GitHubGraphQLClient:
    """Authenticated-only batch transport for public repository metadata.

    This is an accelerator, never an authority: it returns what it managed to
    read and reports the rest as partial errors. Callers fill gaps from REST.
    Any condition that makes the response untrustworthy yields an empty result
    rather than a partially-invented one.
    """

    def __init__(
        self, settings: Settings | None = None, client: httpx.Client | None = None
    ) -> None:
        self.settings = settings or get_settings()
        if self.settings.github_token is None:
            raise ValueError("GraphQL acceleration requires an operator credential")
        # Belt and braces: Settings already refuses to pair a token with a
        # non-canonical origin, but the credential is about to be put on the
        # wire so the destination is checked at the point of use too.
        if self.settings.github_api_url != CANONICAL_GRAPHQL_ORIGIN:
            raise ValueError("GraphQL may only be sent to the canonical GitHub API origin")
        self._owns_client = client is None
        self.client = client or httpx.Client(
            base_url=self.settings.github_api_url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.settings.github_token.get_secret_value()}",
                "User-Agent": "fork-intelligence/0.1",
            },
            timeout=httpx.Timeout(self.settings.graphql_timeout_seconds),
            follow_redirects=False,
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> GitHubGraphQLClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fetch_repository(self, owner: str, name: str) -> GraphQLResult:
        """Batch repository and branch metadata. Never raises for provider faults.

        Returning an empty result instead of raising is deliberate: a failed
        acceleration must degrade to REST, not fail the analysis. The one
        exception is credential rejection or quota exhaustion, which the caller
        needs in order to route subsequent traffic, so those are raised as the
        same GitHubError codes the REST client uses.
        """
        payload = {
            "query": REPOSITORY_QUERY,
            "variables": {
                "owner": owner,
                "name": name,
                "branchLimit": self.settings.max_graphql_branches,
            },
        }
        try:
            response = self.client.post("/graphql", json=payload)
        except httpx.HTTPError:
            return GraphQLResult(partial_errors=["transport_error"])

        if response.status_code in {401, 403, 429}:
            # Surfaced so the router can record a credential-mode transition
            # through its existing machinery rather than silently degrading.
            raise GitHubError(
                "github_unauthorized" if response.status_code == 401 else "github_rate_limited",
                "GitHub denied the GraphQL request or its API quota is exhausted",
                status_code=503,
                details={"quota": _rest_quota(response)},
            )
        if response.is_error:
            return GraphQLResult(partial_errors=["http_error"])

        try:
            body = response.json()
        except ValueError:
            return GraphQLResult(partial_errors=["malformed_response"])
        if not isinstance(body, dict):
            return GraphQLResult(partial_errors=["malformed_response"])

        data = body.get("data")
        data = data if isinstance(data, dict) else {}
        errors = _error_classifications(body.get("errors"))
        quota, cost = _rate_limit(data.get("rateLimit"))

        if cost is not None and cost > self.settings.max_graphql_cost:
            # Refuse to normalize a document that cost more than the budget:
            # accepting it would make the budget advisory rather than enforced.
            return GraphQLResult(
                quota=quota, cost=cost, partial_errors=[*errors, "cost_budget_exceeded"]
            )

        repository = data.get("repository")
        if not isinstance(repository, dict):
            return GraphQLResult(
                quota=quota,
                cost=cost,
                partial_errors=errors or ["repository_unavailable"],
            )

        return GraphQLResult(
            fields=_normalize(repository),
            branches=_branches(repository),
            quota=quota,
            cost=cost,
            partial_errors=errors,
        )


def _normalize(repository: dict[str, Any]) -> dict[str, Any]:
    """Map GraphQL shapes onto the REST provider model, omitting anything absent.

    A field that is missing or null is left out entirely rather than defaulted,
    so the caller can tell "GraphQL did not supply this" from "the value is
    zero" and fill the gap from REST instead of persisting a fabricated value.
    """
    normalized: dict[str, Any] = {}

    def put(key: str, value: Any) -> None:
        if value is not None and key in ACCELERATED_FIELDS:
            normalized[key] = value

    owner = repository.get("owner")
    full_name = repository.get("nameWithOwner")

    put("github_id", _as_int(repository.get("databaseId")))
    put("name", _as_str(repository.get("name")))
    put("full_name", _as_str(full_name))
    put("html_url", _as_str(repository.get("url")))
    put("owner", _as_str(owner.get("login")) if isinstance(owner, dict) else None)
    put("is_fork", _as_bool(repository.get("isFork")))
    put("archived", _as_bool(repository.get("isArchived")))
    put("disabled", _as_bool(repository.get("isDisabled")))
    put("created_at", _as_str(repository.get("createdAt")))
    put("updated_at", _as_str(repository.get("updatedAt")))
    put("pushed_at", _as_str(repository.get("pushedAt")))
    put("stars", _as_int(repository.get("stargazerCount")))
    put("forks", _as_int(repository.get("forkCount")))
    put("size_kb", _as_int(repository.get("diskUsage")))

    default_ref = repository.get("defaultBranchRef")
    if isinstance(default_ref, dict):
        put("default_branch", _as_str(default_ref.get("name")))

    language = repository.get("primaryLanguage")
    if isinstance(language, dict):
        put("language", _as_str(language.get("name")))

    license_info = repository.get("licenseInfo")
    if isinstance(license_info, dict):
        put("license", _as_str(license_info.get("spdxId")))

    watchers = repository.get("watchers")
    if isinstance(watchers, dict):
        put("watchers", _as_int(watchers.get("totalCount")))

    issues = repository.get("issues")
    if isinstance(issues, dict):
        put("open_issues", _as_int(issues.get("totalCount")))

    topics = repository.get("repositoryTopics")
    if isinstance(topics, dict):
        names = [
            name
            for node in topics.get("nodes") or []
            if isinstance(node, dict)
            and isinstance(node.get("topic"), dict)
            and (name := _as_str(node["topic"].get("name"))) is not None
        ]
        if names:
            put("topics", names)

    return normalized


def _branches(repository: dict[str, Any]) -> list[dict[str, Any]]:
    refs = repository.get("refs")
    if not isinstance(refs, dict):
        return []
    branches: list[dict[str, Any]] = []
    for node in refs.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        target = node.get("target")
        name = _as_str(node.get("name"))
        head = _as_str(target.get("oid")) if isinstance(target, dict) else None
        if name is not None and head is not None:
            branches.append({"name": name, "head_sha": head})
    return branches


def _error_classifications(errors: Any) -> list[str]:
    """Reduce provider errors to their type only.

    GraphQL error messages are provider-controlled free text that would end up
    persisted and rendered, so only the classification survives.
    """
    if not isinstance(errors, list):
        return []
    classifications: list[str] = []
    for item in errors:
        if not isinstance(item, dict):
            classifications.append("unknown_error")
            continue
        raw = item.get("type")
        classifications.append(_as_slug(raw) or "unknown_error")
    return classifications


def _rate_limit(raw: Any) -> tuple[dict[str, Any], int | None]:
    if not isinstance(raw, dict):
        return {}, None
    cost = _as_int(raw.get("cost"))
    return (
        {
            "limit": _as_int(raw.get("limit")),
            "remaining": _as_int(raw.get("remaining")),
            "resource": "graphql",
            "node_count": _as_int(raw.get("nodeCount")),
        },
        cost,
    )


def _rest_quota(response: httpx.Response) -> dict[str, Any]:
    return {
        "limit": _header_int(response, "x-ratelimit-limit"),
        "remaining": _header_int(response, "x-ratelimit-remaining"),
        "reset": _header_int(response, "x-ratelimit-reset"),
        "resource": "graphql",
    }


def _header_int(response: httpx.Response, header: str) -> int | None:
    try:
        raw = response.headers.get(header)
        return int(raw) if raw is not None else None
    except ValueError:
        return None


def _as_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _as_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _as_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _as_slug(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    slug = "".join(char for char in value.strip().upper() if char.isalnum() or char == "_")
    return slug[:48] or None
