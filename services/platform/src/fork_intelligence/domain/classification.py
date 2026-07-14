from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CLASSIFICATION_VERSION = "classification-2026.07.1"


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    label: str
    confidence: float
    reasons: list[str]
    missing_inputs: list[str]
    version: str = CLASSIFICATION_VERSION


def classify_repository(metrics: dict[str, Any]) -> ClassificationResult:
    expected = ("ahead", "behind", "unique_patches", "days_since_push", "active_months_12m")
    missing = [field for field in expected if metrics.get(field) is None]
    coverage = (len(expected) - len(missing)) / len(expected)
    if coverage < 0.6:
        return ClassificationResult(
            label="unknown",
            confidence=round(coverage * 0.5, 3),
            reasons=["Data coverage is too low for a reliable classification"],
            missing_inputs=missing,
        )
    ahead = int(metrics.get("ahead") or 0)
    behind = int(metrics.get("behind") or 0)
    patches = int(metrics.get("unique_patches") or 0)
    days = int(metrics.get("days_since_push") or 3650)
    months = int(metrics.get("active_months_12m") or 0)
    source_files = int(metrics.get("source_files_changed") or 0)
    dependency_changes = int(metrics.get("dependency_changes") or 0)

    label = "unknown"
    reasons = ["Insufficient structural evidence for a stronger classification"]
    strength = 0.45
    if ahead == 0 and patches == 0:
        label, reasons, strength = (
            "mirror",
            ["No commits or stable patches unique relative to upstream"],
            0.95,
        )
    elif patches <= 3 and days < 365 and behind < 100:
        label, reasons, strength = (
            "compatibility_patch",
            ["Small bounded unique patch set", "Recent enough to plausibly track upstream"],
            0.78,
        )
    elif months >= 6 and days <= 120 and (patches >= 10 or ahead >= 20):
        label, reasons, strength = (
            "maintained_continuation",
            ["Sustained recent activity", "Material original development"],
            0.88,
        )
    elif source_files >= 50 and dependency_changes >= 3 and patches >= 20:
        label, reasons, strength = (
            "independent_direction",
            ["Broad source and dependency divergence", "Large unique patch set"],
            0.82,
        )
    elif patches >= 10:
        label, reasons, strength = (
            "specialized",
            ["Material original patch set outside upstream"],
            0.7,
        )
    elif ahead > 0:
        if days <= 180 and behind < 50:
            label, reasons, strength = (
                "contribution",
                ["Small recent unique commit set that remains close to upstream"],
                0.62,
            )
        else:
            label, reasons, strength = (
                "experimental",
                ["Limited divergent history without sustained maintenance evidence"],
                0.56,
            )
    return ClassificationResult(
        label=label,
        confidence=round(strength * coverage, 3),
        reasons=reasons,
        missing_inputs=missing,
    )
