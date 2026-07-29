from __future__ import annotations

import csv
import io
import json
from typing import Any

from fork_intelligence.domain.exports import render_export

TOKEN = "ghp-operator-secret"  # noqa: S105 - inert fixture value.


def _payload(**overrides: Any) -> dict[str, Any]:
    """A sealed-snapshot payload shaped like the export route produces."""
    payload: dict[str, Any] = {
        "analysis": {
            "id": "11111111-1111-1111-1111-111111111111",
            "requested_identifier": "root/project",
            "status": "completed",
            "analysis_version": "2026.07.1",
            "sampling": {
                "branch_cap": 2,
                "branch_planner_version": "2026.07.2",
                "branches_structurally_analyzed": 3,
            },
            "access": {
                "credential_mode": "anonymous",
                "quota": {"limit": 60, "remaining": 4, "resource": "core"},
                "transitions": [
                    {
                        "from_mode": "authenticated",
                        "to_mode": "anonymous",
                        "reason": "operator_credential_quota_exhausted",
                        "coverage_limitation": "Anonymous access lowers the rate limit.",
                    }
                ],
                "coverage_limitations": ["Anonymous access lowers the rate limit."],
                "access_condition": None,
            },
            "branch_plan": {
                "planner_version": "2026.07.2",
                "effective_cap": 2,
                "counts": {
                    "considered": 5,
                    "selected": 3,
                    "excluded_by_cap": 1,
                    "unevaluated": 1,
                    "structurally_analyzed": 3,
                },
                "selection_reasons": {"default_branch": 2, "branch_cap_exceeded": 1},
                "structural_coverage_default_only": False,
            },
        },
        "generated_at": "2026-07-29T00:00:00+00:00",
        "forks": [
            {
                "repository_id": "22222222-2222-2222-2222-222222222222",
                "full_name": "someone/fork",
                "classification": "active",
                "confidence": 0.9,
                "depth": "structural",
                "stars": 5,
                "days_since_push": 2,
                "unique_patches": 3,
                "branches_considered": 3,
                "branches_selected": 2,
                "branches_excluded_by_cap": 1,
                "branches_unevaluated": 0,
                "selected_branches": "main; feature",
                "branch_limitations": "branch_cap_exceeded",
            }
        ],
        "known_limitations": ["Fork census reached its configured cap"],
    }
    payload.update(overrides)
    return payload


# --- JSON ---------------------------------------------------------------------


def test_json_export_preserves_complete_machine_readable_provenance() -> None:
    body, content_type = render_export(_payload(), "json")
    document = json.loads(body)

    assert content_type == "application/json"
    analysis = document["analysis"]
    assert analysis["access"]["credential_mode"] == "anonymous"
    assert analysis["access"]["transitions"][0]["reason"] == "operator_credential_quota_exhausted"
    assert analysis["branch_plan"]["counts"]["excluded_by_cap"] == 1
    assert analysis["branch_plan"]["planner_version"] == "2026.07.2"


def test_json_export_is_deterministic() -> None:
    first, _ = render_export(_payload(), "json")
    second, _ = render_export(_payload(), "json")

    assert first == second


# --- CSV ----------------------------------------------------------------------


def test_csv_keeps_one_fork_per_row_with_branch_coverage() -> None:
    body, _ = render_export(_payload(), "csv")
    rows = list(csv.DictReader(io.StringIO(body.decode())))

    assert len(rows) == 1
    row = rows[0]
    assert row["full_name"] == "someone/fork"
    assert row["branches_considered"] == "3"
    assert row["branches_selected"] == "2"
    assert row["branches_excluded_by_cap"] == "1"
    assert row["selected_branches"] == "main; feature"
    assert row["branch_limitations"] == "branch_cap_exceeded"


def test_csv_neutralizes_formulas_in_the_new_columns() -> None:
    """Spreadsheet safety has to cover the added columns, not just the old ones."""
    payload = _payload()
    payload["forks"][0]["selected_branches"] = '=cmd|/c calc'
    payload["forks"][0]["branch_limitations"] = "+SUM(A1)"

    body, _ = render_export(payload, "csv")
    row = next(iter(csv.DictReader(io.StringIO(body.decode()))))

    assert row["selected_branches"].startswith("'=")
    assert row["branch_limitations"].startswith("'+")


# --- Markdown -----------------------------------------------------------------


def test_markdown_renders_provider_access_and_branch_selection() -> None:
    body, content_type = render_export(_payload(), "markdown")
    text = body.decode()

    assert content_type == "text/markdown; charset=utf-8"
    assert "## Provider access" in text
    assert "Effective credential mode: anonymous" in text
    assert "### Access mode changes" in text
    assert "authenticated → anonymous" in text
    assert "## Branch selection" in text
    assert "Method version: 2026.07.2" in text
    assert "Effective branch cap per fork: 2" in text
    # Cap exclusions and unevaluable candidates must read as different things.
    assert "excluded by cap: 1" in text
    assert "could not be evaluated: 1" in text
    assert "### Selection reasons" in text


def test_markdown_reports_default_only_coverage() -> None:
    payload = _payload()
    payload["analysis"]["branch_plan"]["structural_coverage_default_only"] = True

    text = render_export(payload, "markdown")[0].decode()

    assert "did not extend beyond the default branch" in text


def test_markdown_identifies_a_partial_analysis_condition() -> None:
    """AC-AE-004.2: a partial export says what it is waiting on."""
    payload = _payload()
    payload["analysis"]["status"] = "partial"
    payload["analysis"]["access"]["access_condition"] = {
        "code": "github_rate_limited",
        "message": "GitHub access could not continue. Resume after the documented quota reset",
        "resumable": True,
    }

    text = render_export(payload, "markdown")[0].decode()

    assert "Status: partial" in text
    assert "Provider condition: github_rate_limited" in text
    assert "Resume after the documented quota reset" in text


def test_markdown_omits_sections_when_no_provenance_was_recorded() -> None:
    """An empty section would imply the analysis had no access provenance."""
    payload = _payload()
    payload["analysis"]["access"] = {}
    payload["analysis"]["branch_plan"] = {}

    text = render_export(payload, "markdown")[0].decode()

    assert "## Provider access" not in text
    assert "## Branch selection" not in text
    # The rest of the document still renders.
    assert "## Forks" in text
    assert "## Known limitations" in text


def test_markdown_escapes_untrusted_values_in_new_sections() -> None:
    payload = _payload()
    payload["analysis"]["access"]["coverage_limitations"] = ["pipe | injection\nnewline"]
    payload["known_limitations"] = ["table | breaker"]

    text = render_export(payload, "markdown")[0].decode()

    assert "pipe \\| injection<br>newline" in text
    assert "table \\| breaker" in text


# --- Provenance completeness --------------------------------------------------


def test_every_format_identifies_the_credential_mode() -> None:
    """AC-AE-004.1: credential mode is part of every export's provenance."""
    payload = _payload()

    document = json.loads(render_export(payload, "json")[0])
    assert document["analysis"]["access"]["credential_mode"] == "anonymous"

    markdown = render_export(payload, "markdown")[0].decode()
    assert "Credential mode: anonymous" in markdown

    # CSV is one row per fork, so run-level mode belongs to the other two
    # formats; per-fork coverage is what CSV carries.
    csv_body = render_export(payload, "csv")[0].decode()
    assert "branches_selected" in csv_body


def test_renderers_carry_only_what_the_projection_supplies() -> None:
    """Sanitation lives in the projection, not the renderer.

    The renderer faithfully renders its input; adding a third scrubbing layer
    here would risk mangling legitimate values. The real guarantee is tested
    end to end against the export endpoint in test_api_disclosure_endpoints,
    and at the projection in test_api_projections.
    """
    payload = _payload()
    markdown = render_export(payload, "markdown")[0].decode()

    # Only the known quota fields reach the document.
    assert "4 of 60 (core)" in markdown
