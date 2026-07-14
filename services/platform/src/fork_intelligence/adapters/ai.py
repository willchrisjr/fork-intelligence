from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class AIResult:
    label: str
    summary: str
    evidence_ids: list[str]
    model: str
    prompt_version: str


class AIProvider(Protocol):
    def label_cluster(self, evidence_package: dict[str, Any]) -> AIResult: ...


class DisabledAIProvider:
    def label_cluster(self, evidence_package: dict[str, Any]) -> AIResult:
        del evidence_package
        raise RuntimeError("AI enrichment is disabled")


class FakeAIProvider:
    """Deterministic test provider that can only cite supplied evidence IDs."""

    def label_cluster(self, evidence_package: dict[str, Any]) -> AIResult:
        evidence_ids = sorted(str(item) for item in evidence_package.get("evidence_ids", []))[:3]
        tokens = sorted(str(item) for item in evidence_package.get("representative_tokens", []))
        label = " / ".join(tokens[:2]) if tokens else "unlabeled direction"
        return AIResult(
            label=label,
            summary=f"Evidence-backed direction involving {label}.",
            evidence_ids=evidence_ids,
            model="fake-deterministic",
            prompt_version="cluster-label-v1",
        )
