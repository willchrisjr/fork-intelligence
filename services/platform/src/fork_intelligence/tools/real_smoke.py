from __future__ import annotations

import argparse
import json

from fork_intelligence.adapters.github import GitHubClient
from fork_intelligence.config import get_settings
from fork_intelligence.domain.repository_input import parse_repository_identifier


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Opt-in live GitHub metadata smoke test; does not require a token"
    )
    parser.add_argument("repository", nargs="?", default="octocat/Hello-World")
    parser.add_argument("--fork-pages", type=int, choices=range(1, 4), default=1)
    args = parser.parse_args()
    identifier = parse_repository_identifier(args.repository)
    with GitHubClient() as github:
        repository = github.get_repository(identifier.owner, identifier.name)
        forks = 0
        quota: dict[str, object] = {}
        for page in github.iter_forks(
            repository["owner"], repository["name"], max_pages=args.fork_pages
        ):
            forks += len(page.items)
            quota = page.quota
    print(
        json.dumps(
            {
                "repository": repository["full_name"],
                "github_id": repository["github_id"],
                "root": (repository.get("source") or {}).get("full_name")
                or repository["full_name"],
                "forks_observed": forks,
                "quota_remaining": quota.get("remaining"),
                "api_version": get_settings().github_api_version,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
