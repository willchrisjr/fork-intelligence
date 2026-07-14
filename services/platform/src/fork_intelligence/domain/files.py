from __future__ import annotations

from collections import Counter
from pathlib import PurePosixPath

FILE_CATEGORIES = (
    "application_source",
    "tests",
    "documentation",
    "ci_automation",
    "build_packaging",
    "dependency_manifest",
    "lockfile",
    "configuration",
    "generated",
    "vendored",
    "assets",
    "examples",
    "unknown",
)


def classify_file(path: str) -> str:
    normalized = path.lower().strip("/")
    parts = PurePosixPath(normalized).parts
    name = parts[-1] if parts else ""
    suffix = PurePosixPath(name).suffix
    if any(part in {"vendor", "vendored", "third_party", "node_modules"} for part in parts):
        return "vendored"
    if any(part in {"generated", "gen", "dist"} for part in parts) or name.endswith(
        (".generated.ts", ".generated.go")
    ):
        return "generated"
    if name in {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "cargo.lock"}:
        return "lockfile"
    if name in {
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "cargo.toml",
        "go.mod",
        "gemfile",
        "composer.json",
    } or suffix in {".csproj", ".gradle"}:
        return "dependency_manifest"
    if any(part in {"test", "tests", "spec", "specs", "__tests__"} for part in parts):
        return "tests"
    if any(part in {"docs", "doc"} for part in parts) or suffix in {".md", ".rst", ".adoc"}:
        return "documentation"
    if ".github" in parts or any(part in {"ci", ".circleci"} for part in parts):
        return "ci_automation"
    if name in {"dockerfile", "makefile", "cmakelists.txt"} or suffix in {".nix", ".mk"}:
        return "build_packaging"
    if any(part in {"examples", "example", "samples"} for part in parts):
        return "examples"
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2"}:
        return "assets"
    if name.startswith(".") or suffix in {".toml", ".yaml", ".yml", ".json", ".ini", ".cfg"}:
        return "configuration"
    if suffix in {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".c",
        ".cc",
        ".cpp",
        ".h",
        ".swift",
        ".rb",
        ".php",
    }:
        return "application_source"
    return "unknown"


def summarize_files(paths: list[str]) -> dict[str, int]:
    counts = Counter(classify_file(path) for path in paths)
    return {category: counts.get(category, 0) for category in FILE_CATEGORIES}
