from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypeVar

from fork_intelligence.adapters.github import GitHubClient, GitHubPage
from fork_intelligence.config import Settings, get_settings
from fork_intelligence.errors import GitHubError

T = TypeVar("T")

# Authenticated failures a public operation may safely retry anonymously.
# 401 means the operator credential itself was rejected; the rate-limit codes
# mean the credential's quota is spent. Anonymous REST draws on a separate,
# IP-based quota pool, so both remain worth retrying without a credential.
FALLBACK_ELIGIBLE_CODES = frozenset({"github_unauthorized", "github_rate_limited"})

_FALLBACK_REASONS = {
    "github_unauthorized": "operator_credential_rejected",
    "github_rate_limited": "operator_credential_quota_exhausted",
}

COVERAGE_LIMITATION = (
    "Anonymous GitHub access applies a lower unauthenticated rate limit, "
    "which can reduce fork census depth and branch coverage."
)


@dataclass(frozen=True, slots=True)
class CredentialModeTransition:
    from_mode: str
    to_mode: str
    reason: str
    coverage_limitation: str | None
    occurred_at: str


@dataclass
class _RouterState:
    mode: str
    quota: dict[str, Any] = field(default_factory=dict)
    transitions: list[CredentialModeTransition] = field(default_factory=list)


class GitHubCredentialRouter:
    """Routes public GitHub operations through the operator credential first.

    Presents the same surface as :class:`GitHubClient` so callers stay unaware
    of which transport served a request. When the authenticated transport is
    rejected or quota-blocked, an eligible public operation is retried
    anonymously and the mode transition is recorded. After a fallback the
    router stays anonymous for the rest of its life rather than re-probing a
    credential already known to be unusable.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        authenticated: GitHubClient | None = None,
        anonymous: GitHubClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()

        # An explicitly supplied transport always wins; otherwise authenticated
        # access exists only when a credential is actually configured.
        self._owned: list[GitHubClient] = []
        if authenticated is None and self.settings.github_token is not None:
            authenticated = GitHubClient(self.settings)
            self._owned.append(authenticated)
        self._authenticated = authenticated

        if anonymous is None:
            anonymous = GitHubClient(self.anonymous_settings())
            self._owned.append(anonymous)
        self._anonymous = anonymous
        # The anonymous transport is the one place a fallback could re-send the
        # operator credential. Strip the header unconditionally rather than
        # trusting that every construction path built it from tokenless
        # settings — an injected client carries whatever headers it was given.
        if "authorization" in self._anonymous.client.headers:
            del self._anonymous.client.headers["authorization"]

        has_credential = self._authenticated is not None
        self._state = _RouterState(mode="authenticated" if has_credential else "anonymous")
        if not has_credential:
            # AC-RA-AGA-002.1: an absent credential is a starting condition
            # rather than a transition, but the reduced coverage it implies
            # still has to be disclosed like any other fallback.
            self._append_transition(
                from_mode="authenticated",
                to_mode="anonymous",
                reason="operator_credential_not_configured",
            )

    def anonymous_settings(self) -> Settings:
        """Tokenless settings, so the anonymous transport cannot send the credential."""
        return self.settings.model_copy(update={"github_token": None})

    @property
    def credential_mode(self) -> str:
        return self._state.mode

    @property
    def quota_snapshot(self) -> dict[str, Any]:
        if not self._state.quota:
            return {}
        # Stamp the mode at read time. Stamping it when the headers were
        # observed would freeze the mode in force during the *failing* request,
        # leaving a snapshot that contradicts the mode actually in effect.
        return {**self._state.quota, "credential_mode": self._state.mode}

    def drain_transitions(self) -> list[CredentialModeTransition]:
        """Hand pending transitions to the caller, which owns persisting them."""
        pending = self._state.transitions
        self._state.transitions = []
        return pending

    def get_repository(self, owner: str, name: str, *, etag: str | None = None) -> dict[str, Any]:
        return self._route(lambda client: client.get_repository(owner, name, etag=etag))

    def get_branch(self, owner: str, name: str, branch: str) -> dict[str, Any]:
        return self._route(lambda client: client.get_branch(owner, name, branch))

    def iter_forks(
        self, owner: str, name: str, *, max_pages: int | None = None
    ) -> Iterator[GitHubPage]:
        """Stream fork pages, resuming anonymously if the credential fails mid-listing.

        Pages stay lazy because the caller commits and checkpoints per page.
        A fallback therefore resumes at the page that failed rather than
        restarting: pages already yielded are already durable, and the caller
        de-duplicates by repository id, so a small ordering skew between the
        two quota pools costs at most the coverage already disclosed.
        """
        next_page = 1
        while True:
            client = self._active_client()
            authenticated = client is self._authenticated
            pages = client.iter_forks(owner, name, max_pages=max_pages, start_page=next_page)
            while True:
                try:
                    page = next(pages)
                except StopIteration:
                    return
                except GitHubError as exc:
                    if not authenticated or exc.code not in FALLBACK_ELIGIBLE_CODES:
                        self._observe_quota(exc.details.get("quota"))
                        raise
                    self._record_fallback(exc)
                    break
                self._observe_quota(page.quota)
                next_page = page.page + 1
                yield page

    def _active_client(self) -> GitHubClient:
        if self._state.mode == "authenticated" and self._authenticated is not None:
            return self._authenticated
        return self._anonymous

    def _route(self, operation: Callable[[GitHubClient], T]) -> T:
        client = self._active_client()
        if client is not self._authenticated:
            return self._invoke(client, operation)
        try:
            return self._invoke(client, operation)
        except GitHubError as exc:
            if exc.code not in FALLBACK_ELIGIBLE_CODES:
                raise
            self._record_fallback(exc)
            return self._invoke(self._anonymous, operation)

    def _invoke(self, client: GitHubClient, operation: Callable[[GitHubClient], T]) -> T:
        try:
            return operation(client)
        except GitHubError as exc:
            self._observe_quota(exc.details.get("quota"))
            raise

    def _record_fallback(self, exc: GitHubError) -> None:
        self._observe_quota(exc.details.get("quota"))
        self._append_transition(
            from_mode=self._state.mode,
            to_mode="anonymous",
            reason=_FALLBACK_REASONS[exc.code],
        )
        self._state.mode = "anonymous"

    def _append_transition(self, *, from_mode: str, to_mode: str, reason: str) -> None:
        self._state.transitions.append(
            CredentialModeTransition(
                from_mode=from_mode,
                to_mode=to_mode,
                reason=reason,
                coverage_limitation=COVERAGE_LIMITATION,
                occurred_at=datetime.now(UTC).isoformat(),
            )
        )

    def _observe_quota(self, quota: Any) -> None:
        if not isinstance(quota, dict):
            return
        # Quota headers are provider-reported integers plus a resource label.
        # Rebuilding the dict field-by-field keeps anything else the provider
        # (or an error payload) supplied out of a value that gets persisted
        # and rendered in the browser.
        self._state.quota = {
            "limit": _coerce_int(quota.get("limit")),
            "remaining": _coerce_int(quota.get("remaining")),
            "reset": _coerce_int(quota.get("reset")),
            "resource": _coerce_resource(quota.get("resource")),
        }

    def close(self) -> None:
        for client in self._owned:
            client.close()
        self._owned = []

    def __enter__(self) -> GitHubCredentialRouter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _coerce_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _coerce_resource(value: Any) -> str | None:
    """Accept only GitHub's short resource labels.

    This value is provider-controlled and ends up persisted, exported, and
    rendered in the browser, so it is matched against the shape GitHub
    documents rather than passed through as free text.
    """
    if not isinstance(value, str):
        return None
    return value if re.fullmatch(r"[a-z0-9_]{1,32}", value) else None
