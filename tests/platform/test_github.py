from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

from fork_intelligence.adapters.github import GitHubClient
from fork_intelligence.config import Settings
from fork_intelligence.errors import GitHubError


def _repository(repository_id: int, full_name: str, **overrides: object) -> dict[str, object]:
    owner, name = full_name.split("/", 1)
    data: dict[str, object] = {
        "id": repository_id,
        "name": name,
        "full_name": full_name,
        "html_url": f"https://github.com/{full_name}",
        "clone_url": f"https://github.com/{full_name}.git",
        "owner": {"login": owner},
        "default_branch": "main",
        "fork": repository_id != 1,
        "archived": False,
        "disabled": False,
        "stargazers_count": 3,
        "subscribers_count": 2,
        "watchers_count": 99,
        "forks_count": 4,
        "open_issues_count": 5,
        "size": 6,
        "topics": ["forks"],
        "license": {"spdx_id": "MIT"},
    }
    data.update(overrides)
    return data


def _client(handler: httpx.MockTransport) -> GitHubClient:
    settings = Settings(github_api_url="https://api.github.test", max_github_pages=4)
    client = httpx.Client(
        transport=handler,
        base_url=settings.github_api_url,
        headers={"X-GitHub-Api-Version": settings.github_api_version},
    )
    return GitHubClient(settings, client)


def test_get_repository_normalizes_relationships_and_metadata() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/child/fork"
        assert request.headers["X-GitHub-Api-Version"] == "2026-03-10"
        return httpx.Response(
            200,
            json=_repository(
                2,
                "child/fork",
                parent=_repository(1, "root/project"),
                source=_repository(1, "root/project"),
            ),
            headers={"etag": '"repo-v1"'},
        )

    with _client(httpx.MockTransport(handle)) as github:
        repository = github.get_repository("child", "fork")

    assert repository["github_id"] == 2
    assert repository["watchers"] == 2
    assert repository["license"] == "MIT"
    assert repository["parent"]["github_id"] == 1
    assert repository["source"]["full_name"] == "root/project"


def test_iter_forks_follows_link_pagination_and_reports_quota() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page = int(request.url.params["page"])
        headers = {
            "x-ratelimit-limit": "60",
            "x-ratelimit-remaining": str(60 - page),
            "x-ratelimit-reset": "1234567890",
            "x-ratelimit-resource": "core",
            "etag": f'"page-{page}"',
        }
        if page == 1:
            headers["link"] = (
                '<https://api.github.test/repos/root/project/forks?page=2>; rel="next"'
            )
            return httpx.Response(200, json=[_repository(2, "fork/one")], headers=headers)
        return httpx.Response(200, json=[_repository(3, "fork/two")], headers=headers)

    with _client(httpx.MockTransport(handle)) as github:
        pages = list(github.iter_forks("root", "project"))

    assert [page.page for page in pages] == [1, 2]
    assert [page.items[0]["github_id"] for page in pages] == [2, 3]
    assert pages[0].has_next is True
    assert pages[1].has_next is False
    assert pages[1].quota == {
        "limit": 60,
        "remaining": 58,
        "reset": 1234567890,
        "resource": "core",
    }
    assert all(request.url.params["per_page"] == "100" for request in requests)


def test_iter_forks_obeys_explicit_page_cap() -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        page = request.url.params["page"]
        return httpx.Response(
            200,
            json=[_repository(int(page) + 1, f"fork/page-{page}")],
            headers={"link": f'<https://api.github.test/next?page={int(page) + 1}>; rel="next"'},
        )

    with _client(httpx.MockTransport(handle)) as github:
        pages = list(github.iter_forks("root", "project", max_pages=2))

    assert calls == 2
    assert len(pages) == 2
    assert pages[-1].has_next is True


def test_branch_path_segments_are_percent_encoded() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.raw_path == b"/repos/root/project/branches/feature%2Ftopic"
        return httpx.Response(200, json={"name": "feature/topic", "commit": {"sha": "a" * 40}})

    with _client(httpx.MockTransport(handle)) as github:
        branch = github.get_branch("root", "project", "feature/topic")

    assert branch == {"name": "feature/topic", "head_sha": "a" * 40}


def test_custom_github_origin_must_be_tokenless_and_non_production() -> None:
    with pytest.raises(ValueError, match="tokens may only"):
        Settings(
            github_api_url="https://api.github.test",
            github_token="secret",  # noqa: S106 - inert test value.
        )

    with pytest.raises(ValueError, match="Production must use"):
        Settings(environment="production", github_api_url="https://api.github.test")


@pytest.mark.parametrize(
    "url",
    [
        "http://api.github.test",
        "https://user@api.github.test",
        "https://api.github.test/path",
        "https://api.github.test?query=1",
    ],
)
def test_custom_github_origin_rejects_unsafe_url_parts(url: str) -> None:
    with pytest.raises(ValueError, match="tokenless HTTPS origins"):
        Settings(github_api_url=url)


def test_blank_github_token_is_treated_as_unset() -> None:
    settings = Settings(
        github_api_url="https://api.github.test",
        github_token="  ",  # noqa: S106 - normalization fixture.
    )

    assert settings.github_token is None


def test_analysis_deadline_cannot_exceed_actor_safety_cap() -> None:
    with pytest.raises(ValueError):
        Settings(max_analysis_seconds=2701)


def test_transient_response_is_retried_without_network_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statuses: Iterator[int] = iter([503, 200])
    sleeps: list[float] = []
    monkeypatch.setattr("fork_intelligence.adapters.github.time.sleep", sleeps.append)

    def handle(_: httpx.Request) -> httpx.Response:
        status = next(statuses)
        return httpx.Response(status, json=_repository(1, "root/project"))

    with _client(httpx.MockTransport(handle)) as github:
        result = github.get_repository("root", "project")

    assert result["github_id"] == 1
    assert sleeps == [0.2]


def test_rate_limit_error_preserves_quota_without_response_body() -> None:
    def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={
                "x-ratelimit-limit": "60",
                "x-ratelimit-remaining": "0",
                "x-ratelimit-reset": "123",
                "x-ratelimit-resource": "core",
            },
        )

    with (
        _client(httpx.MockTransport(handle)) as github,
        pytest.raises(GitHubError) as caught,
    ):
        github.get_repository("root", "project")

    assert caught.value.code == "github_rate_limited"
    assert caught.value.status_code == 503
    assert caught.value.details["quota"]["remaining"] == 0


def test_not_modified_without_cache_is_explicit() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.headers["if-none-match"] == '"cached"'
        return httpx.Response(304)

    with (
        _client(httpx.MockTransport(handle)) as github,
        pytest.raises(GitHubError) as caught,
    ):
        github.get_repository("root", "project", etag='"cached"')

    assert caught.value.code == "not_modified_without_cache"
