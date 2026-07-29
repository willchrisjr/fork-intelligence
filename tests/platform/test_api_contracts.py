from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fork_intelligence.api.main import app

CONTRACT = Path(__file__).resolve().parents[2] / "packages" / "contracts" / "openapi.json"


def _live_schema() -> dict[str, Any]:
    return app.openapi()


def _committed_schema() -> dict[str, Any]:
    return json.loads(CONTRACT.read_text())


def test_committed_openapi_matches_the_application() -> None:
    """The generated contract is committed, so drift must fail here, not in CI."""
    live = json.dumps(_live_schema(), indent=2, sort_keys=True) + "\n"

    assert CONTRACT.exists(), "packages/contracts/openapi.json is missing"
    assert CONTRACT.read_text() == live, (
        "OpenAPI contract is stale. Run `pnpm contracts` and commit the result."
    )


def test_analysis_read_exposes_access_and_branch_plan() -> None:
    schemas = _committed_schema()["components"]["schemas"]
    properties = schemas["AnalysisRead"]["properties"]

    assert "access" in properties
    assert "branch_plan" in properties


def test_provider_access_contract_carries_no_credential_field() -> None:
    """AC-RA-AGA-001.3: nothing credential-shaped may exist in the transport."""
    schemas = _committed_schema()["components"]["schemas"]
    access = schemas["ProviderAccessRead"]["properties"]

    assert set(access) == {
        "credential_mode",
        "quota",
        "transitions",
        "coverage_limitations",
        "access_condition",
    }
    forbidden = ("token", "secret", "credential_value", "authorization", "password")
    serialized = json.dumps(schemas["ProviderAccessRead"]).lower()
    for term in forbidden:
        assert term not in serialized


def test_quota_contract_is_a_closed_set_of_known_fields() -> None:
    quota = _committed_schema()["components"]["schemas"]["ProviderQuotaRead"]["properties"]

    assert set(quota) == {
        "limit",
        "remaining",
        "reset",
        "resource",
        "credential_mode",
        "node_count",
    }


def test_branch_plan_contract_distinguishes_cap_from_unavailable() -> None:
    """AC-RA-RBP-004.2 has to be visible in the shape, not just the values."""
    counts = _committed_schema()["components"]["schemas"]["BranchPlanCounts"]["properties"]

    assert "excluded_by_cap" in counts
    assert "unevaluated" in counts
    assert "structurally_analyzed" in counts


def test_branch_plan_entry_contract_covers_the_disclosure_fields() -> None:
    entry = _committed_schema()["components"]["schemas"]["BranchPlanEntryRead"]["properties"]

    for field in (
        "repository_id",
        "branch_name",
        "head_sha",
        "is_default",
        "priority",
        "decision",
        "selection_reason",
        "planner_version",
    ):
        assert field in entry, f"BranchPlanEntryRead is missing {field}"


def test_repository_read_exposes_its_branch_plan() -> None:
    properties = _committed_schema()["components"]["schemas"]["RepositoryRead"]["properties"]

    assert "branch_plan" in properties


def test_existing_analysis_fields_are_preserved_for_current_clients() -> None:
    """New disclosure must be additive; removing a field would break the web app."""
    properties = _committed_schema()["components"]["schemas"]["AnalysisRead"]["properties"]

    for field in (
        "id",
        "requested_identifier",
        "mode",
        "status",
        "stage",
        "progress",
        "configuration",
        "sampling",
        "quota_snapshot",
        "warnings",
        "error",
        "analysis_version",
        "cancel_requested",
        "created_at",
        "updated_at",
    ):
        assert field in properties, f"AnalysisRead lost the pre-existing field {field}"


def test_error_and_pagination_contracts_are_unchanged() -> None:
    schemas = _committed_schema()["components"]["schemas"]

    assert set(schemas["ProblemDetails"]["properties"]) >= {
        "type",
        "title",
        "status",
        "detail",
        "instance",
        "code",
    }
    assert set(schemas["PaginatedForks"]["properties"]) == {
        "items",
        "limit",
        "total",
        "next_cursor",
    }
