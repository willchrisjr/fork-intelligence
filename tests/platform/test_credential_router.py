from __future__ import annotations

from typing import Any

import httpx
import pytest

from fork_intelligence.adapters.credential_router import GitHubCredentialRouter
from fork_intelligence.adapters.github import GitHubClient
from fork_intelligence.config import Settings
from fork_intelligence.errors import GitHubError

TOKEN = "ghp-operator-secret"  # noqa: S105 - inert fixture value.

RATE_LIMIT_HEADERS = {
    "x-ratelimit-limit": "5000",
    "x-ratelimit-remaining": "0",
    "x-ratelimit-reset": "1234567890",
    "x-ratelimit-resource": "core",
}


def _repository(repository_id: int, full_name: str) -> dict[str, Any]:
    owner, name = full_name.split("/", 1)
    return {
        "id": repository_id,
        "name": name,
        "full_name": full_name,
        "html_url": f"https://github.com/{full_name}",
        "clone_url": f"https://github.com/{full_name}.git",
        "owner": {"login": owner},
        "default_branch": "main",
        "fork": False,
        "archived": False,
        "disabled": False,
    }


def _transport_client(handler: Any, settings: Settings) -> GitHubClient:
    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url=settings.github_api_url,
        headers={"X-GitHub-Api-Version": settings.github_api_version},
    )
    return GitHubClient(settings, client)


def _router(
    *,
    authenticated: Any | None,
    anonymous: Any,
    token: str | None = TOKEN,
) -> tuple[GitHubCredentialRouter, list[str]]:
    """Build a router over two mock transports, recording which one served each call."""
    calls: list[str] = []
    settings = Settings(github_token=token, github_graphql_enabled=False)

    def wrap(label: str, handler: Any) -> Any:
        def handle(request: httpx.Request) -> httpx.Response:
            calls.append(label)
            return handler(request)

        return handle

    auth_client = (
        _transport_client(wrap("authenticated", authenticated), settings)
        if authenticated is not None
        else None
    )
    anon_client = _transport_client(wrap("anonymous", anonymous), settings)
    router = GitHubCredentialRouter(settings, authenticated=auth_client, anonymous=anon_client)
    return router, calls


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=_repository(1, "root/project"))


def _rate_limited(request: httpx.Request) -> httpx.Response:
    return httpx.Response(403, headers=RATE_LIMIT_HEADERS)


def _unauthorized(request: httpx.Request) -> httpx.Response:
    return httpx.Response(401, headers=RATE_LIMIT_HEADERS)


# --- Credential configuration -------------------------------------------------


def test_configured_credential_is_used_by_default() -> None:
    router, calls = _router(authenticated=_ok, anonymous=_ok)

    with router:
        repository = router.get_repository("root", "project")

    assert repository["github_id"] == 1
    assert calls == ["authenticated"]
    assert router.credential_mode == "authenticated"
    assert router.drain_transitions() == []


def test_absent_credential_starts_anonymous_and_discloses_coverage() -> None:
    router, calls = _router(authenticated=None, anonymous=_ok, token=None)

    with router:
        router.get_repository("root", "project")

    assert calls == ["anonymous"]
    assert router.credential_mode == "anonymous"
    transitions = router.drain_transitions()
    assert len(transitions) == 1
    assert transitions[0].reason == "operator_credential_not_configured"
    assert transitions[0].to_mode == "anonymous"
    assert transitions[0].coverage_limitation is not None


def test_router_sends_the_credential_only_on_the_authenticated_transport() -> None:
    """Assert on the requests the router actually issues, not on client construction."""
    settings = Settings(github_token=TOKEN, github_graphql_enabled=False)
    sent: list[tuple[str, str | None]] = []

    def record(label: str, response: httpx.Response) -> Any:
        def handle(request: httpx.Request) -> httpx.Response:
            sent.append((label, request.headers.get("authorization")))
            return response

        return handle

    # Both transports are built the production way, from settings, so the
    # Authorization header is whatever GitHubClient decided to attach.
    authenticated = GitHubClient(settings)
    authenticated.client = httpx.Client(
        transport=httpx.MockTransport(record("authenticated", httpx.Response(403))),
        base_url=settings.github_api_url,
        headers=authenticated.client.headers,
    )
    anonymous = GitHubClient(settings)  # deliberately still carrying the token
    anonymous.client = httpx.Client(
        transport=httpx.MockTransport(
            record("anonymous", httpx.Response(200, json=_repository(1, "root/project")))
        ),
        base_url=settings.github_api_url,
        headers=anonymous.client.headers,
    )

    router = GitHubCredentialRouter(settings, authenticated=authenticated, anonymous=anonymous)
    with router:
        router.get_repository("root", "project")

    assert [label for label, _ in sent] == ["authenticated", "anonymous"]
    assert sent[0][1] == f"Bearer {TOKEN}"
    # Even though this anonymous transport was handed a token-bearing header
    # set, the router must have stripped it before falling back.
    assert sent[1][1] is None


def test_anonymous_settings_are_tokenless() -> None:
    router = GitHubCredentialRouter(Settings(github_token=TOKEN, github_graphql_enabled=False))

    with router:
        assert router.anonymous_settings().github_token is None


# --- Fallback -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("handler", "reason"),
    [
        (_unauthorized, "operator_credential_rejected"),
        (_rate_limited, "operator_credential_quota_exhausted"),
    ],
)
def test_rejected_or_exhausted_credential_falls_back_to_anonymous(
    handler: Any, reason: str
) -> None:
    router, calls = _router(authenticated=handler, anonymous=_ok)

    with router:
        repository = router.get_repository("root", "project")

    assert repository["github_id"] == 1
    assert calls == ["authenticated", "anonymous"]
    assert router.credential_mode == "anonymous"
    transitions = router.drain_transitions()
    assert [transition.reason for transition in transitions] == [reason]
    assert transitions[0].from_mode == "authenticated"
    assert transitions[0].to_mode == "anonymous"


def test_fallback_is_sticky_and_skips_the_spent_credential() -> None:
    router, calls = _router(authenticated=_rate_limited, anonymous=_ok)

    with router:
        router.get_repository("root", "project")
        router.get_repository("root", "project")

    assert calls == ["authenticated", "anonymous", "anonymous"]
    assert len(router.drain_transitions()) == 1


def test_non_eligible_failures_do_not_fall_back() -> None:
    def missing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    router, calls = _router(authenticated=missing, anonymous=_ok)

    with router, pytest.raises(GitHubError) as caught:
        router.get_repository("root", "project")

    assert caught.value.code == "repository_not_found"
    assert calls == ["authenticated"]
    assert router.credential_mode == "authenticated"


def test_total_failure_raises_after_every_mode_is_blocked() -> None:
    router, calls = _router(authenticated=_rate_limited, anonymous=_rate_limited)

    with router, pytest.raises(GitHubError) as caught:
        router.get_repository("root", "project")

    assert caught.value.code == "github_rate_limited"
    assert calls == ["authenticated", "anonymous"]
    assert router.credential_mode == "anonymous"
    assert router.quota_snapshot["remaining"] == 0


# --- Streaming ----------------------------------------------------------------


def test_iter_forks_resumes_anonymously_at_the_page_that_failed() -> None:
    def authenticated(request: httpx.Request) -> httpx.Response:
        if int(request.url.params["page"]) == 1:
            return httpx.Response(
                200,
                json=[_repository(2, "fork/one")],
                headers={"link": '<https://api.github.com/x?page=2>; rel="next"'},
            )
        return httpx.Response(403, headers=RATE_LIMIT_HEADERS)

    seen_pages: list[int] = []

    def anonymous(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        seen_pages.append(page)
        return httpx.Response(200, json=[_repository(3, "fork/two")])

    router, calls = _router(authenticated=authenticated, anonymous=anonymous)

    with router:
        pages = list(router.iter_forks("root", "project", max_pages=3))

    # Page 1 came from the credential, page 2 failed, and the anonymous
    # transport picked the listing back up at page 2 rather than restarting.
    assert seen_pages == [2]
    assert [page.page for page in pages] == [1, 2]
    assert [page.items[0]["github_id"] for page in pages] == [2, 3]
    assert calls == ["authenticated", "authenticated", "anonymous"]
    assert router.credential_mode == "anonymous"


def test_iter_forks_stays_lazy_so_callers_can_stop_early() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[_repository(int(request.url.params["page"]) + 1, "fork/x")],
            headers={"link": '<https://api.github.com/x?page=9>; rel="next"'},
        )

    router, calls = _router(authenticated=handler, anonymous=handler)

    with router:
        pages = router.iter_forks("root", "project", max_pages=5)
        next(pages)
        pages.close()

    assert calls == ["authenticated"]


# --- Provenance sanitation ----------------------------------------------------


def test_quota_snapshot_is_rebuilt_from_known_fields_only() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[_repository(2, "fork/one")],
            headers={**RATE_LIMIT_HEADERS, "x-ratelimit-remaining": "17"},
        )

    router, _ = _router(authenticated=handler, anonymous=handler)

    with router:
        list(router.iter_forks("root", "project", max_pages=1))

    assert router.quota_snapshot == {
        "limit": 5000,
        "remaining": 17,
        "reset": 1234567890,
        "resource": "core",
        "credential_mode": "authenticated",
    }


def test_quota_snapshot_mode_never_contradicts_the_active_mode() -> None:
    router, _ = _router(authenticated=_rate_limited, anonymous=_ok)

    with router:
        router.get_repository("root", "project")

    # The snapshot's headers came from the failing authenticated request, but
    # the mode it reports must be the one now actually serving traffic.
    assert router.credential_mode == "anonymous"
    assert router.quota_snapshot["credential_mode"] == "anonymous"


def test_quota_resource_label_rejects_free_text() -> None:
    router, _ = _router(authenticated=_ok, anonymous=_ok)

    with router:
        router._observe_quota({"resource": f"Bearer {TOKEN}"})
        smuggled = router.quota_snapshot
        router._observe_quota({"resource": "graphql"})
        legitimate = router.quota_snapshot

    assert smuggled["resource"] is None
    assert legitimate["resource"] == "graphql"


def test_quota_snapshot_drops_unexpected_provider_fields() -> None:
    router, _ = _router(authenticated=_ok, anonymous=_ok)

    with router:
        router._observe_quota(
            {"limit": 10, "remaining": "many", "smuggled": TOKEN, "resource": ["core"]}
        )
        snapshot = router.quota_snapshot

    assert snapshot == {
        "limit": 10,
        "remaining": None,
        "reset": None,
        "resource": None,
        "credential_mode": "authenticated",
    }
    assert TOKEN not in str(snapshot)
    assert "smuggled" not in snapshot
