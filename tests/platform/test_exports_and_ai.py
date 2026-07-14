from __future__ import annotations

import csv
import io
import json

import pytest

from fork_intelligence.adapters.ai import DisabledAIProvider, FakeAIProvider
from fork_intelligence.domain.exports import render_export


def _payload() -> dict[str, object]:
    return {
        "generated_at": "2026-07-13T00:00:00Z",
        "analysis": {
            "id": "11111111-1111-1111-1111-111111111111",
            "requested_identifier": "root/project",
            "status": "completed",
            "analysis_version": "analysis-v1",
            "sampling": {"fork_cap": 250},
        },
        "forks": [
            {
                "repository_id": "1",
                "full_name": "fork/project",
                "classification": "maintained_continuation",
                "confidence": 0.9,
                "depth": "structural",
                "stars": 10,
                "days_since_push": 2,
                "unique_patches": 4,
            }
        ],
        "known_limitations": ["Metadata is limited by accessible GitHub forks."],
    }


def test_json_export_is_stable_and_typed() -> None:
    body, content_type = render_export(_payload(), "json")

    assert content_type == "application/json"
    assert json.loads(body)["analysis"]["status"] == "completed"
    assert body == render_export(_payload(), "json")[0]


def test_csv_export_has_fixed_columns_and_neutralizes_spreadsheet_formulas() -> None:
    payload = _payload()
    payload["forks"][0]["full_name"] = '=HYPERLINK("https://attacker.invalid")'

    body, content_type = render_export(payload, "csv")
    rows = list(csv.DictReader(io.StringIO(body.decode())))

    assert content_type == "text/csv; charset=utf-8"
    assert list(rows[0]) == [
        "repository_id",
        "full_name",
        "classification",
        "confidence",
        "depth",
        "stars",
        "days_since_push",
        "unique_patches",
    ]
    assert rows[0]["full_name"].startswith("'=")


def test_markdown_export_escapes_table_delimiters_and_line_breaks() -> None:
    payload = _payload()
    payload["forks"][0]["full_name"] = "fork|project\nsecond-row"

    body, content_type = render_export(payload, "markdown")
    text = body.decode()

    assert content_type == "text/markdown; charset=utf-8"
    assert "fork\\|project<br>second-row" in text
    assert "## Known limitations" in text


def test_unsupported_export_format_fails_closed() -> None:
    with pytest.raises(ValueError, match="Unsupported export format"):
        render_export(_payload(), "xml")  # type: ignore[arg-type]


def test_fake_ai_is_deterministic_and_cites_only_supplied_evidence() -> None:
    package = {
        "evidence_ids": ["e3", "e1", "e2", "e0"],
        "representative_tokens": ["oauth", "auth"],
    }

    first = FakeAIProvider().label_cluster(package)
    second = FakeAIProvider().label_cluster(package)

    assert first == second
    assert first.model == "fake-deterministic"
    assert first.label == "auth / oauth"
    assert first.evidence_ids == ["e0", "e1", "e2"]
    assert set(first.evidence_ids) <= set(package["evidence_ids"])


def test_live_ai_provider_is_disabled_by_default() -> None:
    with pytest.raises(RuntimeError, match="disabled"):
        DisabledAIProvider().label_cluster({"evidence_ids": []})
