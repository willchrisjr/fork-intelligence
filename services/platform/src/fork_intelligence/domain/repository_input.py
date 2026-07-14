from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from fork_intelligence.errors import PlatformError

_PART = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?$")


@dataclass(frozen=True, slots=True)
class RepositoryIdentifier:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}.git"


def parse_repository_identifier(value: str) -> RepositoryIdentifier:
    raw = value.strip()
    if not raw or any(ord(character) < 32 for character in raw):
        raise _invalid()

    if "://" in raw:
        parsed = urlsplit(raw)
        if parsed.scheme != "https" or parsed.hostname != "github.com":
            raise _invalid("Only canonical HTTPS github.com URLs are supported")
        if parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment:
            raise _invalid()
        segments = [unquote(segment) for segment in parsed.path.split("/") if segment]
    else:
        if any(token in raw for token in ("?", "#", "@", ":", "\\")):
            raise _invalid()
        segments = raw.split("/")

    if len(segments) != 2:
        raise _invalid()
    owner, name = segments
    if name.endswith(".git"):
        name = name[:-4]
    if not _PART.fullmatch(owner) or not _PART.fullmatch(name):
        raise _invalid()
    if owner.startswith("-") or name.startswith("-") or ".." in owner or ".." in name:
        raise _invalid()
    return RepositoryIdentifier(owner=owner, name=name)


def _invalid(
    message: str = "Expected owner/repository or https://github.com/owner/repository",
) -> PlatformError:
    return PlatformError("invalid_repository", message, status_code=422)
