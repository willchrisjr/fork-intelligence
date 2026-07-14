from __future__ import annotations

import hashlib
import os
import re
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from fork_intelligence.config import Settings, get_settings
from fork_intelligence.domain.files import summarize_files
from fork_intelligence.domain.repository_input import parse_repository_identifier
from fork_intelligence.errors import GitCommandError, PlatformError

_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,250}$")
_SHA = re.compile(r"^[0-9a-f]{40,64}$")


@dataclass(frozen=True, slots=True)
class GitResult:
    stdout: bytes
    stderr: bytes

    @property
    def text(self) -> str:
        return self.stdout.decode("utf-8", errors="replace")


@dataclass(frozen=True, slots=True)
class HistoryComparison:
    merge_base: str
    ahead: int
    behind: int
    shared_commits: int
    unique_commits: list[str]
    changed_files: list[dict[str, str]]
    file_composition: dict[str, int]
    directory_summary: dict[str, int]
    patch_ids: dict[str, str]
    patch_overlap: dict[str, object]
    missing_blob_commits: list[str]
    conflict_estimate: dict[str, object]


class SafeGit:
    """Runs fixed Git argv under sterile configuration; never invokes a shell."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def run(
        self,
        args: list[str],
        *,
        git_dir: Path | None = None,
        stdin: bytes | None = None,
        timeout: float | None = None,
        abort_check: Callable[[], bool] | None = None,
    ) -> GitResult:
        if not args or any("\x00" in arg for arg in args):
            raise PlatformError("invalid_git_arguments", "Invalid Git argument array")
        command = [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "protocol.file.allow=never",
            "-c",
            "protocol.ext.allow=never",
            "-c",
            "fetch.fsckObjects=true",
        ]
        if git_dir is not None:
            command.extend(["--git-dir", str(git_dir.resolve())])
        command.extend(args)
        with tempfile.TemporaryDirectory(prefix="fork-intelligence-git-home-") as home:
            env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": home,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_PROTOCOL_FROM_USER": "0",
                "GIT_NO_LAZY_FETCH": "1",
                "LC_ALL": "C",
            }
            effective_timeout = self.settings.git_timeout_seconds if timeout is None else timeout
            if effective_timeout <= 0:
                raise GitCommandError(
                    "git_timeout", "Git operation exceeded its configured timeout", status_code=504
                )
            process = subprocess.Popen(  # noqa: S603
                command,
                stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                env=env,
                start_new_session=True,
            )
            stdout = bytearray()
            stderr = bytearray()
            output_exceeded = threading.Event()

            def read_bounded(stream: BinaryIO, destination: bytearray) -> None:
                with stream:
                    while chunk := stream.read(64 * 1024):
                        remaining = self.settings.git_max_output_bytes - len(destination)
                        if len(chunk) > remaining:
                            if remaining > 0:
                                destination.extend(chunk[:remaining])
                            output_exceeded.set()
                            _terminate_process_group(process)
                            return
                        destination.extend(chunk)

            def write_input(stream: BinaryIO, payload: bytes) -> None:
                with stream, suppress(BrokenPipeError, OSError):
                    stream.write(payload)

            assert process.stdout is not None
            assert process.stderr is not None
            readers = [
                threading.Thread(target=read_bounded, args=(process.stdout, stdout), daemon=True),
                threading.Thread(target=read_bounded, args=(process.stderr, stderr), daemon=True),
            ]
            for reader in readers:
                reader.start()
            writer: threading.Thread | None = None
            if stdin is not None:
                assert process.stdin is not None
                writer = threading.Thread(
                    target=write_input, args=(process.stdin, stdin), daemon=True
                )
                writer.start()

            deadline = time.monotonic() + effective_timeout
            timed_out = False
            resource_exceeded = False
            try:
                while process.poll() is None:
                    if output_exceeded.is_set():
                        _terminate_process_group(process)
                        break
                    if abort_check is not None and abort_check():
                        resource_exceeded = True
                        _terminate_process_group(process)
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        timed_out = True
                        _terminate_process_group(process)
                        break
                    try:
                        process.wait(timeout=min(0.05, remaining))
                    except subprocess.TimeoutExpired:
                        continue
                process.wait()
            except BaseException:
                _terminate_process_group(process)
                process.wait()
                raise
            finally:
                if writer is not None:
                    writer.join()
                for reader in readers:
                    reader.join()
        if output_exceeded.is_set():
            raise GitCommandError(
                "git_output_limit", "Git operation exceeded its output limit", status_code=413
            )
        if resource_exceeded:
            raise GitCommandError(
                "git_resource_limit", "Git operation exceeded a resource limit", status_code=413
            )
        if timed_out:
            raise GitCommandError(
                "git_timeout", "Git operation exceeded its configured timeout", status_code=504
            )
        if process.returncode != 0:
            raise GitCommandError(
                "git_failed",
                "Git operation failed",
                status_code=422,
                details={
                    "exit_code": process.returncode,
                    "stderr": bytes(stderr).decode("utf-8", errors="replace")[:1000],
                },
            )
        return GitResult(bytes(stdout), bytes(stderr))


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError:
        with suppress(ProcessLookupError):
            process.kill()


class BareNetworkStore:
    def __init__(self, network_id: str, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        safe_network_id = re.sub(r"[^A-Za-z0-9-]", "", network_id)
        if not safe_network_id or safe_network_id != network_id:
            raise PlatformError("invalid_network_id", "Unsafe network storage identifier")
        self.path = (self.settings.git_store_root / f"{safe_network_id}.git").resolve()
        self.quarantine_path = self.path / "fork-intelligence.quarantine"
        self.git = SafeGit(self.settings)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._assert_not_quarantined()
        if not self.path.exists():
            self.git.run(["init", "--bare", str(self.path)])

    def fetch_branch(
        self,
        analysis_id: str,
        github_repository_id: int,
        owner: str,
        repository: str,
        branch: str,
        head_sha: str,
    ) -> str:
        identifier = parse_repository_identifier(f"{owner}/{repository}")
        if not re.fullmatch(r"[0-9a-f-]{36}", analysis_id):
            raise PlatformError("invalid_analysis_id", "Unsafe analysis reference identifier")
        if github_repository_id <= 0:
            raise PlatformError("invalid_repository_id", "GitHub repository ID must be positive")
        _validate_ref_component(branch)
        if not _SHA.fullmatch(head_sha):
            raise PlatformError("invalid_commit_sha", "GitHub branch head is not a full commit SHA")
        self.initialize()
        self._enforce_store_limit()
        branch_namespace = _namespace_branch(branch)
        staging = f"refs/staging/{analysis_id}/{github_repository_id}/{branch_namespace}"
        cached = f"refs/cache/repositories/{github_repository_id}/heads/{branch_namespace}"
        pinned = f"refs/analyses/{analysis_id}/repositories/{github_repository_id}/{head_sha}"
        refspec = f"+refs/heads/{branch}:{staging}"
        try:
            self.git.run(
                [
                    "fetch",
                    "--no-tags",
                    "--no-recurse-submodules",
                    "--filter=blob:none",
                    identifier.clone_url,
                    refspec,
                ],
                git_dir=self.path,
                abort_check=self._store_limit_exceeded,
            )
            self._enforce_store_limit()
            fetched = self.git.run(
                ["rev-parse", "--verify", staging], git_dir=self.path
            ).text.strip()
            if fetched != head_sha:
                raise GitCommandError(
                    "git_head_changed",
                    "Branch moved between GitHub census and Git fetch; retry from a fresh snapshot",
                    status_code=409,
                )
            try:
                self.git.run(
                    [
                        "fetch",
                        "--no-tags",
                        "--no-recurse-submodules",
                        f"--filter=blob:limit={self.settings.max_blob_bytes}",
                        identifier.clone_url,
                        refspec,
                    ],
                    git_dir=self.path,
                    abort_check=self._store_limit_exceeded,
                )
                self._enforce_store_limit()
            except GitCommandError as exc:
                if exc.code in {"git_resource_limit", "git_store_limit"}:
                    raise
            self.git.run(["update-ref", cached, head_sha], git_dir=self.path)
            if self._ref_exists(pinned):
                existing = self.git.run(
                    ["show-ref", "--verify", "--hash", pinned], git_dir=self.path
                ).text.strip()
                if existing != head_sha:
                    raise GitCommandError(
                        "immutable_ref_conflict",
                        "An immutable analysis ref already points elsewhere",
                        status_code=409,
                    )
            self.git.run(["update-ref", pinned, head_sha], git_dir=self.path)
            return pinned
        except GitCommandError as exc:
            if exc.code == "git_resource_limit" or self._store_limit_exceeded():
                self._quarantine_store()
                raise GitCommandError(
                    "git_store_limit",
                    "Git network store exceeded its configured hard size cap",
                    status_code=413,
                ) from exc
            raise
        finally:
            if self.path.exists():
                with suppress(GitCommandError):
                    self.git.run(["update-ref", "-d", staging], git_dir=self.path)

    def _ref_exists(self, ref: str) -> bool:
        try:
            self.git.run(["show-ref", "--verify", "--quiet", ref], git_dir=self.path)
        except GitCommandError:
            return False
        return True

    def _store_size_bytes(self) -> int:
        size = 0
        for file in self.path.rglob("*"):
            try:
                if file.is_file() and not file.is_symlink():
                    size += file.stat().st_size
            except FileNotFoundError:
                continue
        return size

    def _store_limit_exceeded(self) -> bool:
        return self._store_size_bytes() > self.settings.max_git_store_bytes

    def _enforce_store_limit(self) -> None:
        if self._store_limit_exceeded():
            self._quarantine_store()
            raise GitCommandError(
                "git_store_limit",
                "Git network store exceeded its configured hard size cap",
                status_code=413,
            )

    def _quarantine_store(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        with suppress(OSError):
            self.quarantine_path.write_text(
                "store exceeded configured size limit\n", encoding="utf-8"
            )
        for pattern in ("objects/pack/tmp_*", "objects/tmp_*"):
            for temporary in self.path.glob(pattern):
                with suppress(FileNotFoundError, OSError):
                    if temporary.is_file() and not temporary.is_symlink():
                        temporary.unlink()

    def _assert_not_quarantined(self) -> None:
        if self.path.exists() and self._store_limit_exceeded():
            self._quarantine_store()
        if self.quarantine_path.exists():
            raise GitCommandError(
                "git_store_quarantined",
                "Git network store is quarantined pending operator cleanup",
                status_code=503,
            )

    def compare(
        self, upstream_ref: str, fork_ref: str, *, timeout: float | None = None
    ) -> HistoryComparison:
        _validate_full_ref(upstream_ref)
        _validate_full_ref(fork_ref)
        self._assert_not_quarantined()
        deadline = time.monotonic() + (
            self.settings.max_analysis_seconds if timeout is None else timeout
        )
        merge_base = self._run_before_deadline(
            ["merge-base", upstream_ref, fork_ref], deadline
        ).text.strip()
        behind, ahead = (
            int(value)
            for value in self._run_before_deadline(
                ["rev-list", "--left-right", "--count", f"{upstream_ref}...{fork_ref}"],
                deadline,
            )
            .text.strip()
            .split()
        )
        unique = self._run_before_deadline(
            [
                "rev-list",
                "--reverse",
                f"--max-count={self.settings.max_git_commits}",
                f"{upstream_ref}..{fork_ref}",
            ],
            deadline,
        ).text.splitlines()
        upstream_unique = self._run_before_deadline(
            [
                "rev-list",
                "--reverse",
                f"--max-count={self.settings.max_git_commits}",
                f"{fork_ref}..{upstream_ref}",
            ],
            deadline,
        ).text.splitlines()
        shared = int(
            self._run_before_deadline(["rev-list", "--count", merge_base], deadline).text.strip()
        )
        changed = _parse_name_status(
            self._run_before_deadline(
                ["diff", "--name-status", "-z", "--find-renames", merge_base, fork_ref],
                deadline,
            ).stdout
        )
        paths = [item["path"] for item in changed]
        directories: dict[str, int] = {}
        for path in paths:
            first = PurePosixPath(path).parts[0] if PurePosixPath(path).parts else "."
            directories[first] = directories.get(first, 0) + 1
        patch_ids: dict[str, str] = {}
        upstream_patch_ids: dict[str, str] = {}
        missing_blob_commits: list[str] = []
        for commit in unique:
            try:
                patch_ids[commit] = self.patch_id(commit, deadline=deadline)
            except GitCommandError as exc:
                if exc.code != "git_failed":
                    raise
                missing_blob_commits.append(commit)
        for commit in upstream_unique:
            try:
                upstream_patch_ids[commit] = self.patch_id(commit, deadline=deadline)
            except GitCommandError as exc:
                if exc.code != "git_failed":
                    raise
                missing_blob_commits.append(commit)
        shared_patch_ids = sorted(set(patch_ids.values()) & set(upstream_patch_ids.values()))
        fork_aggregate = self.range_patch_id(merge_base, fork_ref, deadline=deadline)
        upstream_aggregate = self.range_patch_id(merge_base, upstream_ref, deadline=deadline)
        upstream_paths = set(
            self._run_before_deadline(
                ["diff", "--name-only", merge_base, upstream_ref], deadline
            ).text.splitlines()
        )
        fork_paths = set(paths)
        overlap = len(upstream_paths & fork_paths)
        denominator = len(upstream_paths | fork_paths) or 1
        return HistoryComparison(
            merge_base=merge_base,
            ahead=ahead,
            behind=behind,
            shared_commits=shared,
            unique_commits=unique,
            changed_files=changed,
            file_composition=summarize_files(paths),
            directory_summary=dict(sorted(directories.items())),
            patch_ids=patch_ids,
            patch_overlap={
                "method": "stable-patch-id-and-range-patch-id-v1",
                "bounded_at_commits": self.settings.max_git_commits,
                "shared_patch_ids": shared_patch_ids,
                "shared_patch_count": len(shared_patch_ids),
                "fork_aggregate_patch_id": fork_aggregate,
                "upstream_aggregate_patch_id": upstream_aggregate,
                "aggregate_match": bool(fork_aggregate and fork_aggregate == upstream_aggregate),
                "coverage": {
                    "commit_patches_available": len(patch_ids) + len(upstream_patch_ids),
                    "commit_patches_missing": len(missing_blob_commits),
                },
            },
            missing_blob_commits=missing_blob_commits,
            conflict_estimate={
                "value": round(overlap / denominator, 3),
                "method": "changed-path-overlap-v1",
                "label": "approximation_not_merge_simulation",
            },
        )

    def patch_id(self, commit_sha: str, *, deadline: float | None = None) -> str:
        if not _SHA.fullmatch(commit_sha):
            raise PlatformError("invalid_commit_sha", "Commit SHA is invalid")
        patch = self._run_with_optional_deadline(
            ["show", "--pretty=format:", "--no-ext-diff", "--binary", commit_sha], deadline
        ).stdout
        result = self._run_with_optional_deadline(
            ["patch-id", "--stable"], deadline, stdin=patch
        ).text.strip()
        if not result:
            return f"empty:{hashlib.sha256(patch).hexdigest()}"
        return result.split()[0]

    def range_patch_id(
        self, base_ref: str, tip_ref: str, *, deadline: float | None = None
    ) -> str | None:
        _validate_analysis_ref(base_ref, allow_sha=True)
        _validate_analysis_ref(tip_ref, allow_sha=True)
        try:
            patch = self._run_with_optional_deadline(
                ["diff", "--no-ext-diff", "--binary", base_ref, tip_ref], deadline
            ).stdout
        except GitCommandError as exc:
            if exc.code != "git_failed":
                raise
            return None
        if not patch:
            return None
        result = self._run_with_optional_deadline(
            ["patch-id", "--stable"], deadline, stdin=patch
        ).text.strip()
        return result.split()[0] if result else hashlib.sha256(patch).hexdigest()

    def _run_before_deadline(
        self, args: list[str], deadline: float, *, stdin: bytes | None = None
    ) -> GitResult:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise GitCommandError(
                "git_timeout", "Git operation exceeded its configured timeout", status_code=504
            )
        return self.git.run(
            args,
            git_dir=self.path,
            stdin=stdin,
            timeout=min(self.settings.git_timeout_seconds, remaining),
        )

    def _run_with_optional_deadline(
        self, args: list[str], deadline: float | None, *, stdin: bytes | None = None
    ) -> GitResult:
        if deadline is None:
            return self.git.run(args, git_dir=self.path, stdin=stdin)
        return self._run_before_deadline(args, deadline, stdin=stdin)


def _validate_ref_component(value: str) -> None:
    if (
        not _REF.fullmatch(value)
        or value.startswith("-")
        or ".." in value
        or "@{" in value
        or "//" in value
        or value.endswith(("/", ".", ".lock"))
    ):
        raise PlatformError("invalid_git_ref", "Git reference is unsafe")


def _validate_full_ref(value: str) -> None:
    _validate_analysis_ref(value)


def _validate_analysis_ref(value: str, *, allow_sha: bool = False) -> None:
    if allow_sha and _SHA.fullmatch(value):
        return
    if not value.startswith("refs/analyses/"):
        raise PlatformError("invalid_git_ref", "Only immutable analysis refs may be analyzed")
    _validate_ref_component(value.removeprefix("refs/analyses/"))


def _namespace_branch(branch: str) -> str:
    return branch


def _parse_name_status(output: bytes) -> list[dict[str, str]]:
    fields = output.decode("utf-8", errors="surrogateescape").split("\0")
    fields = [field for field in fields if field]
    result: list[dict[str, str]] = []
    index = 0
    while index < len(fields):
        status = fields[index]
        index += 1
        if status.startswith(("R", "C")):
            old_path, path = fields[index : index + 2]
            index += 2
            result.append({"status": status[0], "old_path": old_path, "path": path})
        else:
            path = fields[index]
            index += 1
            result.append({"status": status[0], "path": path})
    return result
