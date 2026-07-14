from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

CLUSTER_VERSION = "complete-link-agglomerative-2026.07.1"
_TOKEN = re.compile(r"[a-z0-9][a-z0-9_+-]{1,40}")
_BORING = {"src", "lib", "app", "test", "tests", "docs", "main", "index", "readme"}


@dataclass(frozen=True, slots=True)
class ForkVector:
    repository_id: str
    tokens: frozenset[str]
    weights: dict[str, float]


@dataclass(frozen=True, slots=True)
class ClusterResult:
    members: list[str]
    label: str
    shared_tokens: list[str]
    confidence: float
    algorithm: str = CLUSTER_VERSION
    labeling_method: str = "representative-token-heuristic"


def build_vector(repository_id: str, evidence: dict[str, Any]) -> ForkVector:
    tokens: set[str] = set()
    for path in evidence.get("changed_paths", []):
        tokens.update(_TOKEN.findall(str(path).lower()))
    for dependency in evidence.get("dependencies_added", []):
        tokens.add(str(dependency).lower())
    for term in evidence.get("commit_terms", []):
        tokens.add(str(term).lower())
    tokens -= _BORING
    weights = {token: 1.0 for token in sorted(tokens)}
    return ForkVector(repository_id=repository_id, tokens=frozenset(tokens), weights=weights)


def similarity(left: ForkVector, right: ForkVector) -> float:
    union = left.tokens | right.tokens
    if not union:
        return 0.0
    return len(left.tokens & right.tokens) / len(union)


def cluster_vectors(vectors: list[ForkVector], threshold: float = 0.25) -> list[ClusterResult]:
    by_id = {
        vector.repository_id: vector
        for vector in sorted(vectors, key=lambda item: item.repository_id)
    }
    groups: list[frozenset[str]] = [frozenset({identifier}) for identifier in sorted(by_id)]
    while True:
        candidates: list[tuple[float, tuple[str, ...], int, int]] = []
        for left_index, left in enumerate(groups):
            for right_index in range(left_index + 1, len(groups)):
                right = groups[right_index]
                score = min(
                    similarity(by_id[left_id], by_id[right_id])
                    for left_id in left
                    for right_id in right
                )
                if score >= threshold:
                    candidates.append((score, tuple(sorted(left | right)), left_index, right_index))
        if not candidates:
            break
        _, _, left_index, right_index = min(candidates, key=lambda item: (-item[0], item[1]))
        merged = groups[left_index] | groups[right_index]
        groups = [
            group for index, group in enumerate(groups) if index not in {left_index, right_index}
        ]
        groups.append(merged)
        groups.sort(key=lambda group: tuple(sorted(group)))
    clusters: list[ClusterResult] = []
    for group in groups:
        member_vectors = [by_id[identifier] for identifier in sorted(group)]
        frequencies: dict[str, int] = {}
        for vector in member_vectors:
            for token in vector.tokens:
                frequencies[token] = frequencies.get(token, 0) + 1
        shared = sorted(frequencies, key=lambda token: (-frequencies[token], token))[:5]
        label = " / ".join(shared[:2]) if shared else "uncategorized direction"
        pair_scores = [
            similarity(member_vectors[index], member_vectors[other])
            for index in range(len(member_vectors))
            for other in range(index + 1, len(member_vectors))
        ]
        confidence = sum(pair_scores) / len(pair_scores) if pair_scores else 0.5
        clusters.append(
            ClusterResult(
                members=sorted(group),
                label=label,
                shared_tokens=shared,
                confidence=round(confidence, 3),
            )
        )
    return clusters
