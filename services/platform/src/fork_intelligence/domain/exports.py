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
        ]
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for fork in payload.get("forks", []):
            writer.writerow({key: _csv_safe(value) for key, value in fork.items()})
        return output.getvalue().encode(), "text/csv; charset=utf-8"
    if format_name == "markdown":
        analysis = payload["analysis"]
        lines = [
            f"# Fork Intelligence analysis {analysis['id']}",
            "",
            f"- Repository: `{analysis['requested_identifier']}`",
            f"- Status: {analysis['status']}",
            f"- Analysis version: {analysis['analysis_version']}",
            f"- Generated at: {payload['generated_at']}",
            f"- Sampling: `{json.dumps(analysis.get('sampling', {}), sort_keys=True)}`",
            "",
            "## Forks",
            "",
            "| Repository | Classification | Confidence | Depth |",
            "| --- | --- | ---: | --- |",
        ]
        for fork in payload.get("forks", []):
            lines.append(
                f"| {_markdown_cell(fork['full_name'])} | "
                f"{_markdown_cell(fork.get('classification', 'unknown'))} | "
                f"{fork.get('confidence', 0):.2f} | {fork.get('depth', 'metadata')} |"
            )
        lines.extend(["", "## Known limitations", ""])
        limitations = payload.get("known_limitations") or ["No additional limitations recorded."]
        lines.extend(f"- {limitation}" for limitation in limitations)
        return ("\n".join(lines) + "\n").encode(), "text/markdown; charset=utf-8"
    raise ValueError(f"Unsupported export format: {format_name}")


def _csv_safe(value: Any) -> Any:
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _markdown_cell(value: Any) -> str:
    return (
        str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\r", "").replace("\n", "<br>")
    )
