from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ANALYSIS_ID = "11111111-1111-1111-1111-111111111111"
GIT_EXECUTABLE = shutil.which("git") or "/usr/bin/git"


@dataclass(frozen=True, slots=True)
class SyntheticGitNetwork:
    worktree: Path
    bare_store: Path
    refs: dict[str, str]
    shas: dict[str, str]


class _RepositoryBuilder:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.tick = 0

    def run(self, *args: str, dated: bool = False) -> str:
        env = {
            **os.environ,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": "Fork Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Fork Fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        }
        if dated:
            self.tick += 1
            timestamp = f"2025-01-{self.tick:02d}T12:00:00+00:00"
            env["GIT_AUTHOR_DATE"] = timestamp
            env["GIT_COMMITTER_DATE"] = timestamp
        process = subprocess.run(  # noqa: S603 - fixed fixture-only Git argv
            [GIT_EXECUTABLE, *args],
            cwd=self.path,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            shell=False,
        )
        return process.stdout.strip()

    def write(self, relative: str, contents: str | bytes) -> None:
        target = self.path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(contents, bytes):
            target.write_bytes(contents)
        else:
            target.write_text(contents, encoding="utf-8")

    def commit(self, message: str) -> str:
        self.run("add", "--all")
        self.run("commit", "--no-gpg-sign", "-m", message, dated=True)
        return self.run("rev-parse", "HEAD")

    def branch(self, name: str, start: str) -> None:
        self.run("switch", "--create", name, start)


def build_synthetic_network(root: Path) -> SyntheticGitNetwork:
    worktree = root / "work"
    bare_store = root / "network.git"
    worktree.mkdir(parents=True)
    builder = _RepositoryBuilder(worktree)
    builder.run("init", "--initial-branch=main")
    builder.run("config", "commit.gpgsign", "false")
    builder.run("config", "core.autocrlf", "false")

    builder.write("README.md", "# synthetic network\n")
    builder.write("src/core.py", "def core() -> str:\n    return 'base'\n")
    base = builder.commit("base")

    builder.write("src/upstream.py", "def upstream() -> str:\n    return 'feature'\n")
    upstream_feature = builder.commit("upstream feature")
    builder.write("docs/upstream.md", "upstream documentation\n")
    main = builder.commit("upstream documentation")

    builder.branch("ahead", main)
    builder.write("src/ahead.py", "def ahead() -> bool:\n    return True\n")
    ahead = builder.commit("fork development")

    builder.branch("divergence", base)
    builder.write("src/divergent.py", "DIRECTION = 'independent'\n")
    divergence = builder.commit("independent direction")

    builder.branch("cherry-pick", base)
    builder.run("cherry-pick", upstream_feature, dated=True)
    cherry_pick = builder.run("rev-parse", "HEAD")

    builder.branch("topic-original", base)
    builder.write("src/rebased.py", "def rebased() -> str:\n    return 'same patch'\n")
    topic_original = builder.commit("portable topic")

    builder.branch("topic-rebased", main)
    builder.run("cherry-pick", topic_original, dated=True)
    topic_rebased = builder.run("rev-parse", "HEAD")

    builder.branch("series", main)
    builder.write("src/squash_a.py", "A = 1\n")
    series_first = builder.commit("squash part one")
    builder.write("src/squash_b.py", "B = 2\n")
    series = builder.commit("squash part two")

    builder.branch("squashed", main)
    builder.write("src/squash_a.py", "A = 1\n")
    builder.write("src/squash_b.py", "B = 2\n")
    squashed = builder.commit("squashed feature")

    builder.branch("rename", main)
    builder.run("mv", "src/upstream.py", "src/renamed.py")
    rename = builder.commit("rename upstream module")

    builder.branch("merge-feature", main)
    builder.write("src/merge_feature.py", "FEATURE = True\n")
    merge_feature = builder.commit("merge feature")
    builder.branch("merged", main)
    builder.write("src/merge_base.py", "BASE = True\n")
    merge_base_change = builder.commit("parallel merge work")
    builder.run(
        "merge",
        "--no-ff",
        "--no-gpg-sign",
        "-m",
        "merge feature",
        merge_feature,
        dated=True,
    )
    merged = builder.run("rev-parse", "HEAD")

    builder.branch("binary", main)
    builder.write("assets/sample.bin", bytes(range(64)))
    binary = builder.commit("binary asset")

    builder.branch("generated-vendor", main)
    builder.write("generated/client.generated.ts", "export const generated = true;\n")
    builder.write("vendor/library.c", "int vendored(void) { return 1; }\n")
    generated_vendor = builder.commit("generated and vendored content")

    builder.run("clone", "--bare", str(worktree), str(bare_store))

    shas = {
        "base": base,
        "upstream_feature": upstream_feature,
        "main": main,
        "mirror": main,
        "ahead": ahead,
        "divergence": divergence,
        "cherry_pick": cherry_pick,
        "topic_original": topic_original,
        "topic_rebased": topic_rebased,
        "series_first": series_first,
        "series": series,
        "squashed": squashed,
        "rename": rename,
        "merge_feature": merge_feature,
        "merge_base_change": merge_base_change,
        "merged": merged,
        "binary": binary,
        "generated_vendor": generated_vendor,
    }
    refs: dict[str, str] = {}
    for name, sha in shas.items():
        ref = f"refs/analyses/{ANALYSIS_ID}/scenarios/{name}"
        subprocess.run(  # noqa: S603 - fixed fixture-only Git argv
            [GIT_EXECUTABLE, "--git-dir", str(bare_store), "update-ref", ref, sha],
            check=True,
            capture_output=True,
            shell=False,
        )
        refs[name] = ref
    return SyntheticGitNetwork(worktree=worktree, bare_store=bare_store, refs=refs, shas=shas)
