from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from fork_intelligence.config import Settings, get_settings
from fork_intelligence.errors import GitHubError


@dataclass(frozen=True, slots=True)
class GitHubPage:
    items: list[dict[str, Any]]
    page: int
    has_next: bool
    etag: str | None
    quota: dict[str, Any]


class GitHubClient:
    def __init__(
        self, settings: Settings | None = None, client: httpx.Client | None = None
    ) -> None:
        self.settings = settings or get_settings()
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": self.settings.github_api_version,
            "User-Agent": "fork-intelligence/0.1",
        }
        if self.settings.github_token is not None:
            headers["Authorization"] = f"Bearer {self.settings.github_token.get_secret_value()}"
        self._owns_client = client is None
        self.client = client or httpx.Client(
            base_url=self.settings.github_api_url,
            headers=headers,
            timeout=httpx.Timeout(30),
            follow_redirects=False,
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get_repository(self, owner: str, name: str, *, etag: str | None = None) -> dict[str, Any]:
        response = self._request(
            "GET", f"/repos/{_path_segment(owner)}/{_path_segment(name)}", etag=etag
        )
        if response.status_code == 304:
            raise GitHubError(
                "not_modified_without_cache",
                "GitHub returned not-modified but no cached representation was supplied",
                status_code=502,
            )
        return self.normalize_repository(response.json())

    def get_branch(self, owner: str, name: str, branch: str) -> dict[str, Any]:
        response = self._request(
            "GET",
            (
                f"/repos/{_path_segment(owner)}/{_path_segment(name)}/branches/"
                f"{_path_segment(branch)}"
            ),
        )
        data = response.json()
        commit = data.get("commit") or {}
        sha = str(commit.get("sha") or "")
        return {"name": str(data.get("name") or branch), "head_sha": sha}

    def iter_forks(
        self, owner: str, name: str, *, max_pages: int | None = None
    ) -> Iterator[GitHubPage]:
        page_limit = max_pages or self.settings.max_github_pages
        for page in range(1, page_limit + 1):
            response = self._request(
                "GET",
                f"/repos/{_path_segment(owner)}/{_path_segment(name)}/forks",
                params={"sort": "newest", "per_page": 100, "page": page},
            )
            raw = response.json()
            if not isinstance(raw, list):
                raise GitHubError(
                    "invalid_github_response", "Expected a list of forks", status_code=502
                )
            has_next = "next" in response.links
            yield GitHubPage(
                items=[self.normalize_repository(item) for item in raw],
                page=page,
                has_next=has_next,
                etag=response.headers.get("etag"),
                quota=self._quota(response),
            )
            if "next" not in response.links:
                break

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        etag: str | None = None,
    ) -> httpx.Response:
        headers = {"If-None-Match": etag} if etag else None
        for attempt in range(3):
            try:
                response = self.client.request(method, path, params=params, headers=headers)
                redirects = 0
                while response.status_code in {301, 302, 307, 308}:
                    location = response.headers.get("location")
                    if not location or redirects >= 3:
                        raise GitHubError(
                            "unsafe_github_redirect",
                            "GitHub redirect was missing or exceeded its bound",
                            status_code=502,
                        )
                    target = response.url.join(location)
                    configured = httpx.URL(self.settings.github_api_url)
                    if (
                        target.scheme != "https"
                        or target.host != configured.host
                        or target.port != configured.port
                    ):
                        raise GitHubError(
                            "unsafe_github_redirect",
                            "GitHub redirect left the configured HTTPS API origin",
                            status_code=502,
                        )
                    response = self.client.request(method, target, params=params, headers=headers)
                    redirects += 1
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise GitHubError(
                        "github_unavailable", "GitHub request failed", status_code=503
                    ) from exc
                time.sleep((2**attempt) * 0.2)
                continue
            if response.status_code in {429, 502, 503, 504} and attempt < 2:
                retry_after = min(float(response.headers.get("retry-after", "0") or 0), 5)
                time.sleep(max(retry_after, (2**attempt) * 0.2))
                continue
            if response.status_code == 404:
                raise GitHubError(
                    "repository_not_found", "Repository is unavailable", status_code=404
                )
            if response.status_code in {401, 403, 429}:
                raise GitHubError(
                    "github_rate_limited" if response.status_code != 401 else "github_unauthorized",
                    "GitHub denied the request or its API quota is exhausted",
                    status_code=503,
                    details={"quota": self._quota(response)},
                )
            if response.is_error:
                raise GitHubError(
                    "github_error",
                    "GitHub returned an unexpected response",
                    status_code=502,
                    details={"status": response.status_code},
                )
            return response
        raise AssertionError("retry loop exhausted")

    @staticmethod
    def _quota(response: httpx.Response) -> dict[str, Any]:
        return {
            "limit": _optional_int(response.headers.get("x-ratelimit-limit")),
            "remaining": _optional_int(response.headers.get("x-ratelimit-remaining")),
            "reset": _optional_int(response.headers.get("x-ratelimit-reset")),
            "resource": response.headers.get("x-ratelimit-resource"),
        }

    @staticmethod
    def normalize_repository(data: dict[str, Any]) -> dict[str, Any]:
        owner = data.get("owner") or {}
        license_data = data.get("license") or {}
        return {
            "github_id": int(data["id"]),
            "owner": str(owner.get("login") or data["full_name"].split("/", 1)[0]),
            "name": str(data["name"]),
            "full_name": str(data["full_name"]),
            "html_url": str(data["html_url"]),
            "clone_url": str(data["clone_url"]),
            "default_branch": str(data.get("default_branch") or "main"),
            "is_fork": bool(data.get("fork", False)),
            "archived": bool(data.get("archived", False)),
            "disabled": bool(data.get("disabled", False)),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
            "pushed_at": data.get("pushed_at"),
            "stars": int(data.get("stargazers_count") or 0),
            "watchers": int(data.get("subscribers_count") or data.get("watchers_count") or 0),
            "forks": int(data.get("forks_count") or 0),
            "open_issues": int(data.get("open_issues_count") or 0),
            "size_kb": int(data.get("size") or 0),
            "language": data.get("language"),
            "license": license_data.get("spdx_id"),
            "topics": list(data.get("topics") or []),
            "parent": _relationship(data.get("parent")),
            "source": _relationship(data.get("source")),
        }


def _relationship(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "github_id": int(value["id"]),
        "full_name": str(value["full_name"]),
        "html_url": str(value["html_url"]),
        "clone_url": str(value["clone_url"]),
        "default_branch": str(value.get("default_branch") or "main"),
    }


def _optional_int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _path_segment(value: str) -> str:
    return quote(value, safe="")
