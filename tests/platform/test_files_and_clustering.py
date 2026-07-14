from __future__ import annotations

import pytest

from fork_intelligence.domain.clustering import (
    ForkVector,
    build_vector,
    cluster_vectors,
    similarity,
)
from fork_intelligence.domain.files import classify_file, summarize_files


@pytest.mark.parametrize(
    ("path", "category"),
    [
        ("src/server.py", "application_source"),
        ("tests/test_server.py", "tests"),
        ("docs/design.md", "documentation"),
        (".github/workflows/ci.yml", "ci_automation"),
        ("Dockerfile", "build_packaging"),
        ("pyproject.toml", "dependency_manifest"),
        ("pnpm-lock.yaml", "lockfile"),
        ("config/settings.yaml", "configuration"),
        ("generated/api.generated.ts", "generated"),
        ("third_party/library.cc", "vendored"),
        ("assets/logo.svg", "assets"),
        ("examples/demo.ts", "examples"),
        ("NOTICE", "unknown"),
    ],
)
def test_file_categories(path: str, category: str) -> None:
    assert classify_file(path) == category


def test_file_summary_includes_zero_counts_for_reproducible_schema() -> None:
    summary = summarize_files(["src/app.py", "tests/test_app.py", "vendor/library.py"])

    assert summary["application_source"] == 1
    assert summary["tests"] == 1
    assert summary["vendored"] == 1
    assert summary["assets"] == 0
    assert len(summary) == 13


def test_vector_tokenization_removes_boring_tokens_and_is_order_independent() -> None:
    left = build_vector(
        "2",
        {
            "changed_paths": ["src/auth/oauth_handler.py", "tests/auth/test_oauth.py"],
            "dependencies_added": ["Authlib"],
            "commit_terms": ["OAuth", "Hardening"],
        },
    )
    right = build_vector(
        "2",
        {
            "commit_terms": ["Hardening", "OAuth"],
            "dependencies_added": ["Authlib"],
            "changed_paths": ["tests/auth/test_oauth.py", "src/auth/oauth_handler.py"],
        },
    )

    assert left == right
    assert "src" not in left.tokens
    assert "tests" not in left.tokens
    assert {"auth", "oauth", "oauth_handler", "authlib", "hardening"} <= left.tokens


def test_similarity_is_symmetric_and_bounded() -> None:
    left = ForkVector("left", frozenset({"auth", "oauth"}), {})
    right = ForkVector("right", frozenset({"auth", "cli"}), {})

    assert similarity(left, right) == similarity(right, left) == pytest.approx(1 / 3)
    assert similarity(left, left) == 1


def test_cluster_order_is_deterministic_including_singletons() -> None:
    vectors = [
        ForkVector("z", frozenset({"cli", "terminal"}), {}),
        ForkVector("a", frozenset({"auth", "oauth"}), {}),
        ForkVector("b", frozenset({"auth", "oidc"}), {}),
    ]

    forward = cluster_vectors(vectors, threshold=0.3)
    reverse = cluster_vectors(list(reversed(vectors)), threshold=0.3)

    assert forward == reverse
    assert [cluster.members for cluster in forward] == [["a", "b"], ["z"]]
    assert forward[0].label.startswith("auth")
    assert forward[1].confidence == 0.5


def test_clustering_uses_complete_link_not_transitive_chaining() -> None:
    vectors = [
        ForkVector("a", frozenset({"one", "two"}), {}),
        ForkVector("b", frozenset({"one", "two", "three"}), {}),
        ForkVector("c", frozenset({"two", "three"}), {}),
    ]

    clusters = cluster_vectors(vectors, threshold=0.5)

    assert max(len(cluster.members) for cluster in clusters) == 2
