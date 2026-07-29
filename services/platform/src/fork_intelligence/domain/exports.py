from __future__ import annotations

import csv
import io
import json
from typing import Any, Literal

ExportFormat = Literal["json", "csv", "markdown"]


def render_export(payload: dict[str, Any], format_name: ExportFormat) -> tuple[bytes, str]:
    if format_name == "json":
        return (
            json.dumps(payload, sort_keys=True, indent=2, default=str).encode(),
            "application/json",
        )
    if format_name == "csv":
        output = io.StringIO(newline="")
        fields = [
            "repository_id",
            "full_name",
            "classification",
            "confidence",
            "depth",
            "stars",
            "days_since_push",
            "unique_patches",
            # Branch coverage stays one fork per row: counts plus a joined list
            # rather than extra rows, so the row grain never changes.
            "branches_considered",
            "branches_selected",
            "branches_excluded_by_cap",
            "branches_unevaluated",
            "selected_branches",
            "branch_limitations",
        ]
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for fork in payload.get("forks", []):
            writer.writerow({key: _csv_safe(value) for key, value in fork.items()})
        return output.getvalue().encode(), "text/csv; charset=utf-8"
    if format_name == "markdown":
        analysis = payload["analysis"]
        access = analysis.get("access") or {}
        lines = [
            f"# Fork Intelligence analysis {analysis['id']}",
            "",
            f"- Repository: `{analysis['requested_identifier']}`",
            f"- Status: {analysis['status']}",
            f"- Analysis version: {analysis['analysis_version']}",
            f"- Generated at: {payload['generated_at']}",
            f"- Credential mode: {access.get('credential_mode', 'unknown')}",
            f"- Sampling: `{json.dumps(analysis.get('sampling', {}), sort_keys=True)}`",
        ]
        lines.extend(_markdown_provider_access(access))
        lines.extend(_markdown_branch_plan(analysis.get("branch_plan") or {}))
        lines.extend(
            [
                "",
                "## Forks",
                "",
                "| Repository | Classification | Confidence | Depth | Branches selected |",
                "| --- | --- | ---: | --- | ---: |",
            ]
        )
        for fork in payload.get("forks", []):
            selected = fork.get("branches_selected")
            considered = fork.get("branches_considered")
            coverage = (
                f"{selected}/{considered}"
                if selected is not None and considered is not None
                else "n/a"
            )
            lines.append(
                f"| {_markdown_cell(fork['full_name'])} | "
                f"{_markdown_cell(fork.get('classification', 'unknown'))} | "
                f"{fork.get('confidence', 0):.2f} | {fork.get('depth', 'metadata')} | "
                f"{_markdown_cell(coverage)} |"
            )
        lines.extend(["", "## Known limitations", ""])
        limitations = payload.get("known_limitations") or ["No additional limitations recorded."]
        lines.extend(f"- {_markdown_cell(limitation)}" for limitation in limitations)
        return ("\n".join(lines) + "\n").encode(), "text/markdown; charset=utf-8"
    raise ValueError(f"Unsupported export format: {format_name}")


def _markdown_provider_access(access: dict[str, Any]) -> list[str]:
    """Readable provider-access section (AC-AE-004.1).

    Renders nothing when no access provenance was recorded, rather than an
    empty section that would imply the analysis had none.
    """
    if not access:
        return []
    lines = ["", "## Provider access", ""]
    quota = access.get("quota") or {}
    lines.append(f"- Effective credential mode: {access.get('credential_mode', 'unknown')}")
    if quota.get("remaining") is not None or quota.get("limit") is not None:
        lines.append(
            f"- Provider quota at completion: {quota.get('remaining', 'unknown')} "
            f"of {quota.get('limit', 'unknown')} ({quota.get('resource', 'unknown')})"
        )
    condition = access.get("access_condition")
    if condition:
        # AC-AE-004.2: a partial analysis says so, and says what it is waiting on.
        lines.append(
            f"- Provider condition: {condition.get('code', 'unknown')} — "
            f"{condition.get('message', 'no detail recorded')}"
        )
    transitions = access.get("transitions") or []
    if transitions:
        lines.extend(["", "### Access mode changes", ""])
        for transition in transitions:
            lines.append(
                f"- {transition.get('from_mode', '?')} → {transition.get('to_mode', '?')}: "
                f"{transition.get('reason', 'no reason recorded')}"
            )
    limitations = access.get("coverage_limitations") or []
    if limitations:
        lines.extend(["", "### Coverage limitations", ""])
        lines.extend(f"- {_markdown_cell(item)}" for item in limitations)
    return lines


def _markdown_branch_plan(plan: dict[str, Any]) -> list[str]:
    """Readable branch-selection section (AC-RA-RBP-002.4)."""
    if not plan:
        return []
    counts = plan.get("counts") or {}
    lines = ["", "## Branch selection", ""]
    lines.append(f"- Method version: {plan.get('planner_version', 'unknown')}")
    lines.append(f"- Effective branch cap per fork: {plan.get('effective_cap', 'unknown')}")
    lines.append(
        f"- Candidates considered: {counts.get('considered', 0)}; "
        f"selected: {counts.get('selected', 0)}; "
        # Cap exclusions and unevaluable candidates stay separate so a sampling
        # choice is never read as missing data (AC-RA-RBP-004.2).
        f"excluded by cap: {counts.get('excluded_by_cap', 0)}; "
        f"could not be evaluated: {counts.get('unevaluated', 0)}"
    )
    lines.append(f"- Branches structurally analyzed: {counts.get('structurally_analyzed', 0)}")
    if plan.get("structural_coverage_default_only"):
        # AC-RA-RBP-004.3
        lines.append("- Structural branch coverage did not extend beyond the default branch.")
    reasons = plan.get("selection_reasons") or {}
    if reasons:
        lines.extend(["", "### Selection reasons", ""])
        lines.extend(
            f"- {_markdown_cell(reason)}: {count}" for reason, count in sorted(reasons.items())
        )
    return lines


def _csv_safe(value: Any) -> Any:
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _markdown_cell(value: Any) -> str:
    return (
        str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\r", "").replace("\n", "<br>")
    )
