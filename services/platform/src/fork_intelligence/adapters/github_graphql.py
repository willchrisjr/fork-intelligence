from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

from fork_intelligence.adapters.github import GitHubPage
from fork_intelligence.config import Settings, get_settings
from fork_intelligence.domain.repository_input import parse_repository_identifier
from fork_intelligence.errors import GitHubError, PlatformError

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

# Direct forks of one repository. Nested forks are a later census step, not a
# nested connection, so cost stays proportional to one page. ``first`` is at
# most 100. Identity fields are required; counts and topics may be absent.
FORKS_QUERY = """
query RepositoryForks($owner: String!, $name: String!, $pageSize: Int!, $after: String) {
  rateLimit { limit cost remaining nodeCount resetAt }
  repository(owner: $owner, name: $name) {
    databaseId
    forks(first: $pageSize, after: $after, orderBy: {field: CREATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
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
        defaultBranchRef { name }
        primaryLanguage { name }
        licenseInfo { spdxId }
        watchers(first: 1) { totalCount }
        issues(states: OPEN, first: 1) { totalCount }
        repositoryTopics(first: 20) { nodes { topic { name } } }
        parent { databaseId nameWithOwner }
      }
    }
  }
}
"""

# GitHub connection arguments are 1 through 100. One page matches REST's
# fork-list page so a fallback does not shrink the census.
FORK_PAGE_SIZE = 100
_MAX_GITHUB_ID = 2**63 - 1
_CURSOR = re.compile(r"^[A-Za-z0-9+/=_-]{1,512}$")
_FIELD_LABELS = frozenset(
    {
        "github_graphql",
        "derived_canonical_https",
        "not_supplied",
        "default_assumed",
    }
)
DEGRADATION_REASONS = frozenset(
    {
        "transport_error",
        "timeout",
        "http_error",
        "malformed_response",
        "partial_error",
        "rate_limited",
        "repository_unavailable",
        "schema_drift",
        "cost_budget_exceeded",
        "invalid_locator",
    }
)

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


class GraphQLDegraded(Exception):
    """The fork listing cannot continue on GraphQL.

    Pages already yielded stay valid. Callers fall back to REST. This is not a
    credential rejection: HTTP 401/403/429 still raise :class:`GitHubError` so
    the router can change mode.
    """

    def __init__(
        self,
        reason: str,
        *,
        partial_errors: list[str] | None = None,
        quota: dict[str, Any] | None = None,
        cost: int | None = None,
    ) -> None:
        if reason not in DEGRADATION_REASONS:
            reason = "schema_drift"
        super().__init__(reason)
        self.reason = reason
        self.partial_errors = list(partial_errors or [])
        self.quota = quota or {}
        self.cost = cost


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
        self._spent = 0
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

    @property
    def points_spent(self) -> int:
        """Server-reported GraphQL points charged to this client."""
        return self._spent

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

        if self._charge(cost):
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

    def iter_forks(
        self,
        owner: str,
        name: str,
        *,
        max_pages: int | None = None,
        start_page: int = 1,
        after: str | None = None,
    ) -> Iterator[GitHubPage]:
        """Yield direct forks, one GraphQL page at a time.

        Stops by raising :class:`GraphQLDegraded` when the connection cannot be
        trusted. Pages already yielded are complete and de-duplicated by GitHub
        repository id. ``after`` is the cursor of the last committed page.
        """
        if _locator(owner, name) is None:
            raise GraphQLDegraded("invalid_locator")
        if after is not None and _valid_cursor(after) is None:
            raise GraphQLDegraded("schema_drift")
        page_limit = max_pages if max_pages is not None else self.settings.max_github_pages
        if start_page > page_limit:
            return

        cursor = after
        seen: set[int] = set()
        page_number = start_page
        while page_number <= page_limit:
            if self._spent >= self.settings.max_graphql_cost:
                raise GraphQLDegraded("cost_budget_exceeded", cost=self._spent)
            page = self._fork_page(owner, name, cursor, seen)
            yield GitHubPage(
                items=page.items,
                page=page_number,
                has_next=page.has_next,
                etag=None,
                quota=page.quota,
                cursor=page.cursor,
                transport="github_graphql",
                graphql_cost=page.cost,
                inaccessible_count=page.inaccessible_count,
            )
            if not page.has_next:
                return
            if page.cursor is None or page.cursor == cursor:
                raise GraphQLDegraded("schema_drift", quota=page.quota, cost=page.cost)
            cursor = page.cursor
            page_number += 1

    def _charge(self, cost: int | None) -> bool:
        """Record a server-reported cost. True when the budget is exceeded."""
        if cost is None:
            return False
        self._spent += cost
        return cost > self.settings.max_graphql_cost or self._spent > self.settings.max_graphql_cost

    def _fork_page(
        self,
        owner: str,
        name: str,
        cursor: str | None,
        seen: set[int],
    ) -> _ForkPage:
        payload = {
            "query": FORKS_QUERY,
            "variables": {
                "owner": owner,
                "name": name,
                "pageSize": FORK_PAGE_SIZE,
                "after": cursor,
            },
        }
        try:
            response = self.client.post("/graphql", json=payload)
        except httpx.TimeoutException as exc:
            raise GraphQLDegraded("timeout") from exc
        except httpx.HTTPError as exc:
            raise GraphQLDegraded("transport_error") from exc

        if response.status_code in {401, 403, 429}:
            raise GitHubError(
                "github_unauthorized" if response.status_code == 401 else "github_rate_limited",
                "GitHub denied the GraphQL request or its API quota is exhausted",
                status_code=503,
                details={"quota": _rest_quota(response)},
            )
        if response.status_code in {502, 504}:
            raise GraphQLDegraded("timeout")
        if response.is_error:
            raise GraphQLDegraded("http_error")

        try:
            body = response.json()
        except ValueError as exc:
            raise GraphQLDegraded("malformed_response") from exc
        if not isinstance(body, dict):
            raise GraphQLDegraded("malformed_response")

        data = body.get("data")
        data = data if isinstance(data, dict) else {}
        errors = _error_classifications(body.get("errors"))
        quota, cost = _rate_limit(data.get("rateLimit"))
        if cost is None:
            raise GraphQLDegraded("schema_drift", partial_errors=errors, quota=quota)
        over_budget = self._charge(cost)
        if "RATE_LIMITED" in errors:
            raise GraphQLDegraded("rate_limited", partial_errors=errors, quota=quota, cost=cost)
        if over_budget:
            raise GraphQLDegraded("cost_budget_exceeded", quota=quota, cost=cost)

        repository = data.get("repository")
        if not isinstance(repository, dict):
            raise GraphQLDegraded(
                "repository_unavailable", partial_errors=errors, quota=quota, cost=cost
            )
        if errors:
            raise GraphQLDegraded("partial_error", partial_errors=errors, quota=quota, cost=cost)
        parent_id = _as_int(repository.get("databaseId"))
        if parent_id is None or not 1 <= parent_id <= _MAX_GITHUB_ID:
            raise GraphQLDegraded("schema_drift", quota=quota, cost=cost)

        forks = repository.get("forks")
        if not isinstance(forks, dict):
            raise GraphQLDegraded("schema_drift", quota=quota, cost=cost)
        page_info = forks.get("pageInfo")
        nodes = forks.get("nodes")
        if not isinstance(page_info, dict) or not isinstance(nodes, list):
            raise GraphQLDegraded("schema_drift", quota=quota, cost=cost)
        has_next = page_info.get("hasNextPage")
        if not isinstance(has_next, bool):
            raise GraphQLDegraded("schema_drift", quota=quota, cost=cost)
        end_cursor = _valid_cursor(page_info.get("endCursor"))
        if has_next and end_cursor is None:
            raise GraphQLDegraded("schema_drift", quota=quota, cost=cost)

        items: list[dict[str, Any]] = []
        inaccessible = 0
        for node in nodes:
            if not isinstance(node, dict):
                inaccessible += 1
                continue
            item = _normalize_fork_node(node, parent_id)
            if item is None:
                inaccessible += 1
                continue
            github_id = item["github_id"]
            if github_id in seen:
                continue
            seen.add(github_id)
            items.append(item)
        return _ForkPage(
            items=items,
            has_next=has_next,
            cursor=end_cursor,
            quota=quota,
            cost=cost,
            inaccessible_count=inaccessible,
        )


@dataclass(frozen=True, slots=True)
class _ForkPage:
    items: list[dict[str, Any]]
    has_next: bool
    cursor: str | None
    quota: dict[str, Any]
    cost: int
    inaccessible_count: int


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
    quota: dict[str, Any] = {
        "limit": _as_int(raw.get("limit")),
        "remaining": _as_int(raw.get("remaining")),
        "resource": "graphql",
        "node_count": _as_int(raw.get("nodeCount")),
    }
    reset = _reset_epoch(raw.get("resetAt"))
    if reset is None:
        reset = _as_int(raw.get("reset"))
    if reset is not None:
        quota["reset"] = reset
    return quota, cost


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


def _reset_epoch(value: Any) -> int | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int(parsed.timestamp())


def _valid_cursor(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or _CURSOR.fullmatch(value) is None:
        return None
    return value


def _locator(owner: str, name: str) -> str | None:
    try:
        return parse_repository_identifier(f"{owner}/{name}").full_name
    except PlatformError:
        return None


def _normalize_fork_node(node: dict[str, Any], parent_github_id: int) -> dict[str, Any] | None:
    """Map one fork node onto the REST repository shape, or skip it.

    ``html_url`` and ``clone_url`` are derived from a validated owner/name.
    A provider URL that is not that canonical HTTPS locator is rejected, so a
    GraphQL payload cannot redirect the later Git fetch.
    """
    full_name = _as_str(node.get("nameWithOwner"))
    github_id = _as_int(node.get("databaseId"))
    if full_name is None or github_id is None or not 1 <= github_id <= _MAX_GITHUB_ID:
        return None
    try:
        identifier = parse_repository_identifier(full_name)
    except PlatformError:
        return None
    reported_name = _as_str(node.get("name"))
    if reported_name is not None and reported_name != identifier.name:
        return None
    owner = node.get("owner")
    login = _as_str(owner.get("login")) if isinstance(owner, dict) else None
    if login is not None and login != identifier.owner:
        return None
    html_url = f"https://github.com/{identifier.owner}/{identifier.name}"
    reported_url = _as_str(node.get("url"))
    if reported_url is not None and reported_url.rstrip("/") != html_url:
        return None

    parent = _normalize_parent(node.get("parent"))
    if parent is not None and parent["github_id"] != parent_github_id:
        return None

    sources: dict[str, str] = {
        "github_id": "github_graphql",
        "owner": "github_graphql",
        "name": "github_graphql",
        "full_name": "github_graphql",
        "html_url": "derived_canonical_https",
        "clone_url": "derived_canonical_https",
    }
    default_ref = node.get("defaultBranchRef")
    default_name = _as_str(default_ref.get("name")) if isinstance(default_ref, dict) else None
    if default_name is None:
        default_name = "main"
        sources["default_branch"] = "default_assumed"
    elif any(ord(char) < 32 for char in default_name) or len(default_name) > 255:
        return None
    else:
        sources["default_branch"] = "github_graphql"

    def flag(value: bool | None, key: str) -> bool:
        if value is None:
            sources[key] = "not_supplied"
            return False
        sources[key] = "github_graphql"
        return value

    item: dict[str, Any] = {
        "github_id": github_id,
        "owner": identifier.owner,
        "name": identifier.name,
        "full_name": identifier.full_name,
        "html_url": html_url,
        "clone_url": identifier.clone_url,
        "default_branch": default_name,
        "is_fork": flag(_as_bool(node.get("isFork")), "is_fork"),
        "archived": flag(_as_bool(node.get("isArchived")), "archived"),
        "disabled": flag(_as_bool(node.get("isDisabled")), "disabled"),
    }

    def optional_str(graphql_key: str, field: str) -> None:
        value = _as_str(node.get(graphql_key))
        item[field] = value
        sources[field] = "github_graphql" if value is not None else "not_supplied"

    optional_str("createdAt", "created_at")
    optional_str("updatedAt", "updated_at")
    optional_str("pushedAt", "pushed_at")

    def count(raw: Any, field: str) -> None:
        value = _as_int(raw)
        if value is None or value < 0:
            item[field] = 0
            sources[field] = "not_supplied"
            return
        item[field] = value
        sources[field] = "github_graphql"

    count(node.get("stargazerCount"), "stars")
    count(node.get("forkCount"), "forks")
    count(node.get("diskUsage"), "size_kb")
    watchers = node.get("watchers")
    count(watchers.get("totalCount") if isinstance(watchers, dict) else None, "watchers")
    issues = node.get("issues")
    count(issues.get("totalCount") if isinstance(issues, dict) else None, "open_issues")

    language = node.get("primaryLanguage")
    language_name = _as_str(language.get("name")) if isinstance(language, dict) else None
    item["language"] = language_name
    sources["language"] = "github_graphql" if language_name is not None else "not_supplied"

    license_info = node.get("licenseInfo")
    license_name = _as_str(license_info.get("spdxId")) if isinstance(license_info, dict) else None
    item["license"] = license_name
    sources["license"] = "github_graphql" if license_name is not None else "not_supplied"

    topics_raw = node.get("repositoryTopics")
    if isinstance(topics_raw, dict):
        names: list[str] = []
        for topic_node in topics_raw.get("nodes") or []:
            if not isinstance(topic_node, dict):
                continue
            topic = topic_node.get("topic")
            topic_name = _as_str(topic.get("name")) if isinstance(topic, dict) else None
            if topic_name is not None and topic_name not in names:
                names.append(topic_name)
            if len(names) >= 20:
                break
        item["topics"] = names
        sources["topics"] = "github_graphql"
    else:
        item["topics"] = []
        sources["topics"] = "not_supplied"

    item["parent"] = parent
    sources["parent"] = "github_graphql" if parent is not None else "not_supplied"
    item["source"] = None
    sources["source"] = "not_supplied"
    if any(label not in _FIELD_LABELS for label in sources.values()):
        return None
    item["field_provenance"] = sources
    return item


def _normalize_parent(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    github_id = _as_int(value.get("databaseId"))
    full_name = _as_str(value.get("nameWithOwner"))
    if github_id is None or not 1 <= github_id <= _MAX_GITHUB_ID or full_name is None:
        return None
    try:
        identifier = parse_repository_identifier(full_name)
    except PlatformError:
        return None
    return {
        "github_id": github_id,
        "full_name": identifier.full_name,
        "html_url": f"https://github.com/{identifier.owner}/{identifier.name}",
        "clone_url": identifier.clone_url,
    }
