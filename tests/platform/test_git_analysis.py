from __future__ import annotations

import hashlib
import socket
import subprocess
import time
import zlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from build_fixture import SyntheticGitNetwork

from fork_intelligence.adapters.git import (
    BareNetworkStore,
    GitResult,
    SafeGit,
    _namespace_branch,
)
from fork_intelligence.adapters.git_fsck_wrapper import (
    FSCK_WARN_SPEC,
    apply_index_pack_fsck_warn_overrides,
)
from fork_intelligence.config import Settings
from fork_intelligence.errors import GitCommandError, PlatformError


def _store(network: SyntheticGitNetwork, tmp_path: Path) -> BareNetworkStore:
    store = BareNetworkStore("synthetic-network", Settings(git_store_root=tmp_path))
    store.path = network.bare_store
    return store


def test_exact_mirror_has_no_unique_history(
    synthetic_git_network: SyntheticGitNetwork, tmp_path: Path
) -> None:
    store = _store(synthetic_git_network, tmp_path)
    refs = synthetic_git_network.refs

    comparison = store.compare(refs["main"], refs["mirror"])

    assert comparison.ahead == 0
    assert comparison.behind == 0
    assert comparison.unique_commits == []
    assert comparison.changed_files == []
    assert comparison.patch_overlap["aggregate_match"] is False


def test_ahead_and_divergent_histories_are_counted_from_merge_base(
    synthetic_git_network: SyntheticGitNetwork, tmp_path: Path
) -> None:
    store = _store(synthetic_git_network, tmp_path)
    refs = synthetic_git_network.refs

    ahead = store.compare(refs["main"], refs["ahead"])
    diverged = store.compare(refs["main"], refs["divergence"])

    assert (ahead.behind, ahead.ahead) == (0, 1)
    assert ahead.merge_base == synthetic_git_network.shas["main"]
    assert (diverged.behind, diverged.ahead) == (2, 1)
    assert diverged.merge_base == synthetic_git_network.shas["base"]


def test_cherry_pick_is_labeled_as_same_stable_patch_not_same_commit(
    synthetic_git_network: SyntheticGitNetwork, tmp_path: Path
) -> None:
    store = _store(synthetic_git_network, tmp_path)
    refs = synthetic_git_network.refs
    shas = synthetic_git_network.shas

    comparison = store.compare(refs["main"], refs["cherry_pick"])

    assert shas["upstream_feature"] != shas["cherry_pick"]
    assert comparison.patch_overlap["shared_patch_count"] == 1
    assert store.patch_id(shas["upstream_feature"]) == store.patch_id(shas["cherry_pick"])


def test_rebased_equivalent_patch_is_detected_across_distinct_histories(
    synthetic_git_network: SyntheticGitNetwork, tmp_path: Path
) -> None:
    store = _store(synthetic_git_network, tmp_path)
    refs = synthetic_git_network.refs
    shas = synthetic_git_network.shas

    comparison = store.compare(refs["topic_original"], refs["topic_rebased"])

    assert shas["topic_original"] != shas["topic_rebased"]
    assert comparison.patch_overlap["shared_patch_count"] == 1
    assert store.patch_id(shas["topic_original"]) == store.patch_id(shas["topic_rebased"])


def test_bounded_aggregate_patch_match_detects_squash(
    synthetic_git_network: SyntheticGitNetwork, tmp_path: Path
) -> None:
    store = _store(synthetic_git_network, tmp_path)
    refs = synthetic_git_network.refs

    comparison = store.compare(refs["series"], refs["squashed"])

    assert comparison.patch_overlap["shared_patch_count"] == 0
    assert comparison.patch_overlap["aggregate_match"] is True
    assert comparison.patch_overlap["fork_aggregate_patch_id"]
    assert (
        comparison.patch_overlap["fork_aggregate_patch_id"]
        == comparison.patch_overlap["upstream_aggregate_patch_id"]
    )


def test_rename_detection_preserves_old_and_new_paths(
    synthetic_git_network: SyntheticGitNetwork, tmp_path: Path
) -> None:
    store = _store(synthetic_git_network, tmp_path)
    refs = synthetic_git_network.refs

    comparison = store.compare(refs["main"], refs["rename"])

    assert comparison.changed_files == [
        {"status": "R", "old_path": "src/upstream.py", "path": "src/renamed.py"}
    ]
    assert comparison.file_composition["application_source"] == 1


def test_merge_history_is_counted_without_checking_out_or_executing_code(
    synthetic_git_network: SyntheticGitNetwork, tmp_path: Path
) -> None:
    store = _store(synthetic_git_network, tmp_path)
    refs = synthetic_git_network.refs
    marker = tmp_path / "hook-executed"
    hook = synthetic_git_network.bare_store / "hooks" / "post-commit"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    hook.chmod(0o755)

    comparison = store.compare(refs["main"], refs["merged"])

    assert comparison.ahead == 3
    assert comparison.behind == 0
    assert {item["path"] for item in comparison.changed_files} == {
        "src/merge_base.py",
        "src/merge_feature.py",
    }
    assert not marker.exists()


def test_binary_generated_and_vendored_changes_are_analyzed_as_data(
    synthetic_git_network: SyntheticGitNetwork, tmp_path: Path
) -> None:
    store = _store(synthetic_git_network, tmp_path)
    refs = synthetic_git_network.refs

    binary = store.compare(refs["main"], refs["binary"])
    generated = store.compare(refs["main"], refs["generated_vendor"])

    assert binary.changed_files == [{"status": "A", "path": "assets/sample.bin"}]
    assert binary.patch_ids
    assert generated.file_composition["generated"] == 1
    assert generated.file_composition["vendored"] == 1


@pytest.mark.parametrize(
    "branch",
    [
        "-c",
        "../main",
        "main..other",
        "main@{1}",
        "main//other",
        "main.lock",
        "main:refs/heads/evil",
        "main\x00evil",
    ],
)
def test_fetch_rejects_malicious_branch_refs_before_network_access(
    branch: str, tmp_path: Path
) -> None:
    store = BareNetworkStore("safe-network", Settings(git_store_root=tmp_path))

    with pytest.raises(PlatformError) as caught:
        store.fetch_branch(
            "11111111-1111-1111-1111-111111111111",
            1,
            "owner",
            "repository",
            branch,
            "a" * 40,
        )

    assert caught.value.code == "invalid_git_ref"
    assert not store.path.exists()


@pytest.mark.parametrize("network_id", ["", "../escape", "network/name", "network_name"])
def test_network_storage_identifier_cannot_escape_store(network_id: str, tmp_path: Path) -> None:
    with pytest.raises(PlatformError, match="Unsafe network"):
        BareNetworkStore(network_id, Settings(git_store_root=tmp_path))


def test_analysis_only_accepts_immutable_analysis_refs(
    synthetic_git_network: SyntheticGitNetwork, tmp_path: Path
) -> None:
    store = _store(synthetic_git_network, tmp_path)

    with pytest.raises(PlatformError) as caught:
        store.compare("refs/heads/main", synthetic_git_network.refs["ahead"])

    assert caught.value.code == "invalid_git_ref"


def test_safe_git_does_not_interpolate_shell_metacharacters(tmp_path: Path) -> None:
    marker = tmp_path / "shell-was-executed"
    safe_git = SafeGit(Settings(git_store_root=tmp_path))

    with pytest.raises(GitCommandError):
        safe_git.run([f"--version;touch {marker}"])

    assert not marker.exists()


def test_safe_git_uses_sterile_environment_and_no_shell(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}
    real_popen = subprocess.Popen

    def recording_popen(command: list[str], **kwargs: Any) -> subprocess.Popen[bytes]:
        captured["command"] = command
        captured.update(kwargs)
        return real_popen(command, **kwargs)

    monkeypatch.setattr("fork_intelligence.adapters.git.subprocess.Popen", recording_popen)

    result = SafeGit(Settings(git_store_root=tmp_path)).run(["version"])

    command = captured["command"]
    environment = captured["env"]
    assert result.text.startswith("git version ")
    assert captured["shell"] is False
    assert captured["start_new_session"] is True
    assert "core.hooksPath=/dev/null" in command
    assert "protocol.file.allow=never" in command
    assert "protocol.ext.allow=never" in command
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert environment["GIT_TERMINAL_PROMPT"] == "0"
    assert environment["GIT_NO_LAZY_FETCH"] == "1"
    assert "GIT_CONFIG_GLOBAL" not in environment
    assert "fetch.fsckObjects=true" in command
    assert "fetch.fsck.zeroPaddedFilemode=warn" in command
    assert "fetch.fsck.badTimezone=warn" in command
    assert not any("skipList" in arg for arg in command)
    assert "skipList" not in " ".join(str(value) for value in environment.values())
    assert environment.get("GIT_EXEC_PATH")
    assert environment.get("FORK_INTELLIGENCE_REAL_GIT")


def test_safe_git_enforces_output_limit(tmp_path: Path) -> None:
    safe_git = SafeGit(Settings(git_store_root=tmp_path, git_max_output_bytes=1024))

    with pytest.raises(GitCommandError) as caught:
        safe_git.run(["help", "-a"])

    assert caught.value.code == "git_output_limit"


def test_safe_git_turns_timeout_into_typed_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_git = tmp_path / "git"
    marker = tmp_path / "descendant-survived"
    fake_git.write_text(
        "#!/bin/sh\n(/bin/sleep 0.2; /usr/bin/touch '" + str(marker) + "') &\nwait\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")

    with pytest.raises(GitCommandError) as caught:
        SafeGit(Settings(git_store_root=tmp_path)).run(["version"], timeout=0.05)

    assert caught.value.code == "git_timeout"
    assert caught.value.status_code == 504
    time.sleep(0.3)
    assert not marker.exists()


def test_safe_git_preserves_binary_stdin_and_stdout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_git = tmp_path / "git"
    fake_git.write_text("#!/bin/sh\n/bin/cat\n", encoding="utf-8")
    fake_git.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    payload = b"binary\x00payload\xff\n"

    result = SafeGit(Settings(git_store_root=tmp_path)).run(["ignored"], stdin=payload)

    assert result.stdout == payload


def test_safe_git_supports_external_resource_abort(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_git = tmp_path / "git"
    fake_git.write_text("#!/bin/sh\n/bin/sleep 5\n", encoding="utf-8")
    fake_git.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")

    with pytest.raises(GitCommandError) as caught:
        SafeGit(Settings(git_store_root=tmp_path)).run(["ignored"], abort_check=lambda: True)

    assert caught.value.code == "git_resource_limit"


def test_branch_namespace_preserves_valid_slash_refs() -> None:
    branch = _namespace_branch("release/1.x")
    reference = f"refs/staging/11111111-1111-1111-1111-111111111111/1/{branch}"

    assert branch == "release/1.x"
    assert (
        subprocess.run(  # noqa: S603 - fixed test-only Git argv.
            ["git", "check-ref-format", reference],  # noqa: S607 - intentional Git lookup.
            check=False,
            capture_output=True,
        ).returncode
        == 0
    )


def test_compare_rejects_an_exhausted_shared_deadline(
    synthetic_git_network: SyntheticGitNetwork, tmp_path: Path
) -> None:
    store = _store(synthetic_git_network, tmp_path)

    with pytest.raises(GitCommandError) as caught:
        store.compare(
            synthetic_git_network.refs["main"],
            synthetic_git_network.refs["ahead"],
            timeout=0,
        )

    assert caught.value.code == "git_timeout"


def test_compare_passes_remaining_shared_deadline_to_every_git_command(
    synthetic_git_network: SyntheticGitNetwork,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(synthetic_git_network, tmp_path)
    real_run = store.git.run
    observed_timeouts: list[float | None] = []

    def recording_run(args: list[str], **kwargs: Any) -> object:
        observed_timeouts.append(kwargs.get("timeout"))
        return real_run(args, **kwargs)

    monkeypatch.setattr(store.git, "run", recording_run)

    store.compare(
        synthetic_git_network.refs["main"], synthetic_git_network.refs["ahead"], timeout=30
    )

    assert observed_timeouts
    assert all(timeout is not None and 0 < timeout <= 30 for timeout in observed_timeouts)


def test_oversized_store_is_quarantined_and_partial_temp_files_are_removed(
    tmp_path: Path,
) -> None:
    settings = Settings(git_store_root=tmp_path, max_git_store_bytes=1_000_000)
    store = BareNetworkStore("oversized-network", settings)
    temporary = store.path / "objects" / "pack" / "tmp_partial"
    temporary.parent.mkdir(parents=True)
    temporary.write_bytes(b"x" * 1_000_001)

    with pytest.raises(GitCommandError) as caught:
        store._enforce_store_limit()

    assert caught.value.code == "git_store_limit"
    assert store.quarantine_path.exists()
    assert not temporary.exists()
    with pytest.raises(GitCommandError, match="quarantined"):
        store.initialize()


def test_fetch_branch_retrieves_blobs_in_a_single_filtered_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A blob:none fetch followed by a blob:limit fetch of the same commits is a
    no-op: Git negotiation is commit-based, so once the commits are present the
    second fetch transfers no blobs. Measured against pallets/flask on
    2026-08-26 - 332 KB of bookkeeping and zero of 236 head-tree blobs. The
    branch fetch must therefore request the blobs it needs the first time."""
    settings = Settings(git_store_root=tmp_path)
    store = BareNetworkStore("single-fetch-network", settings)
    head = "a" * 40
    fetches: list[list[str]] = []

    def recording_run(args: list[str], **kwargs: Any) -> object:
        if args and args[0] == "fetch":
            fetches.append(args)
            return GitResult(stdout=b"", stderr=b"")
        if args and args[0] in {"rev-parse", "show-ref"}:
            return GitResult(stdout=head.encode() + b"\n", stderr=b"")
        return GitResult(stdout=b"", stderr=b"")

    monkeypatch.setattr(store.git, "run", recording_run)

    store.fetch_branch(
        "00000000-0000-4000-8000-000000000000", 1, "octocat", "Hello-World", "main", head
    )

    assert len(fetches) == 1, "a second fetch of the same commits cannot backfill blobs"
    assert f"--filter=blob:limit={settings.max_blob_bytes}" in fetches[0]
    assert not any(arg == "--filter=blob:none" for arg in fetches[0])


def test_fetch_branch_reports_object_validation_rejection_distinctly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dangerous object-validation failures stay classified, not opaque git_failed.

    Legacy flask/requests-class artifacts are demoted to warnings on the
    filtered fetch path. Remaining fsck errors still surface as
    git_object_validation_failed (issue #51) rather than a generic Git failure.
    """
    store = BareNetworkStore("fsck-network", Settings(git_store_root=tmp_path))

    def failing_run(args: list[str], **kwargs: Any) -> object:
        if args and args[0] == "fetch":
            raise GitCommandError(
                "git_failed",
                "Git operation failed",
                details={
                    "exit_code": 128,
                    "stderr": (
                        "error: object 0b404df8c030cdeaca7b373956c3a697efd32f78: "
                        "missingEmail: invalid author/committer line - missing email\n"
                        "fatal: fsck error in packed object\n"
                    ),
                },
            )
        return GitResult(stdout=b"", stderr=b"")

    monkeypatch.setattr(store.git, "run", failing_run)

    with pytest.raises(GitCommandError) as caught:
        store.fetch_branch(
            "00000000-0000-4000-8000-000000000000", 1, "pallets", "flask", "main", "a" * 40
        )

    assert caught.value.code == "git_object_validation_failed"
    assert caught.value.status_code == 422
    findings = caught.value.details["fsck_findings"]
    assert any("missingEmail" in finding for finding in findings)


def test_index_pack_fsck_warn_overrides_rewrite_bare_fsck_objects_flag() -> None:
    rewritten = apply_index_pack_fsck_warn_overrides(
        ["index-pack", "--stdin", "--promisor", "--fsck-objects"]
    )

    assert rewritten == [
        "index-pack",
        "--stdin",
        "--promisor",
        f"--fsck-objects={FSCK_WARN_SPEC}",
    ]
    assert "zeroPaddedFilemode=warn" in FSCK_WARN_SPEC
    assert "badTimezone=warn" in FSCK_WARN_SPEC
    assert "skipList" not in " ".join(rewritten)


def test_index_pack_fsck_warn_overrides_preserve_unrelated_arguments() -> None:
    args = ["fetch", "--no-tags", "--filter=blob:limit=2000000", "https://github.com/x/y.git"]

    assert apply_index_pack_fsck_warn_overrides(args) == args


def test_index_pack_fsck_warn_overrides_merge_into_existing_typed_flag() -> None:
    rewritten = apply_index_pack_fsck_warn_overrides(
        ["index-pack", "--fsck-objects=missingEmail=error"]
    )

    assert rewritten[1].startswith("--fsck-objects=")
    assert "missingEmail=error" in rewritten[1]
    assert "zeroPaddedFilemode=warn" in rewritten[1]
    assert "badTimezone=warn" in rewritten[1]


def _index_pack_accepts_typed_fsck_objects() -> bool:
    result = subprocess.run(
        ["git", "index-pack", "-h"],  # noqa: S607 - intentional Git lookup.
        check=False,
        capture_output=True,
        text=True,
    )
    return "fsck-objects[=" in f"{result.stdout}{result.stderr}"


def _store_git_object(git_dir: Path, object_type: str, body: bytes) -> str:
    payload = f"{object_type} {len(body)}\0".encode() + body
    digest = hashlib.sha1(payload).hexdigest()  # noqa: S324 - Git object ID
    path = git_dir / "objects" / digest[:2] / digest[2:]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(zlib.compress(payload))
    return digest


def _build_legacy_artifact_repo(root: Path) -> Path:
    """Bare repo with flask/requests-class trees plus a still-fatal missingEmail commit."""
    source = root / "legacy.git"
    subprocess.run(  # noqa: S603 - fixed test-only Git argv.
        ["git", "init", "--bare", str(source)],  # noqa: S607 - intentional Git lookup.
        check=True,
        capture_output=True,
    )
    blob_sha = _store_git_object(source, "blob", b"hello\n")
    padded_tree = _store_git_object(
        source, "tree", b"0100644 hello.txt\0" + bytes.fromhex(blob_sha)
    )
    normal_tree = _store_git_object(source, "tree", b"100644 hello.txt\0" + bytes.fromhex(blob_sha))

    def commit(tree: str, *, author: str, message: str) -> str:
        body = (f"tree {tree}\nauthor {author}\ncommitter {author}\n\n{message}\n").encode()
        return _store_git_object(source, "commit", body)

    padded = commit(
        padded_tree,
        author="Fixture <fixture@example.invalid> 1577836800 +0000",
        message="zero padded",
    )
    timezone = commit(
        normal_tree,
        author="Fixture <fixture@example.invalid> 1577836800 UTC",
        message="bad timezone",
    )
    missing_email = commit(
        normal_tree,
        author="NoEmail 1577836800 +0000",
        message="missing email",
    )
    git_dir = ["git", "--git-dir", str(source)]
    subprocess.run(  # noqa: S603 - fixed test-only Git argv.
        [*git_dir, "update-ref", "refs/heads/padded", padded],
        check=True,
    )
    subprocess.run(  # noqa: S603 - fixed test-only Git argv.
        [*git_dir, "update-ref", "refs/heads/timezone", timezone],
        check=True,
    )
    subprocess.run(  # noqa: S603 - fixed test-only Git argv.
        [*git_dir, "update-ref", "refs/heads/missing-email", missing_email],
        check=True,
    )
    subprocess.run(  # noqa: S603 - fixed test-only Git argv.
        [*git_dir, "config", "uploadpack.allowFilter", "true"],
        check=True,
    )
    return source


def _serve_git_repo(source: Path) -> Iterator[str]:
    parent = source.parent
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    log_path = parent / "git-daemon.log"
    daemon = subprocess.Popen(  # noqa: S603 - fixed test-only Git argv.
        [  # noqa: S607 - intentional Git lookup.
            "git",
            "daemon",
            "daemon",
            "--reuseaddr",
            "--listen=127.0.0.1",
            f"--port={port}",
            f"--base-path={parent}",
            "--export-all",
            "--informative-errors",
            str(source),
        ],
        stdout=log_path.open("w"),
        stderr=subprocess.STDOUT,
    )
    url = f"git://127.0.0.1:{port}/{source.name}"
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if daemon.poll() is not None:
                raise RuntimeError(f"git daemon exited: {log_path.read_text()[-500:]}")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
                client.settimeout(0.1)
                if client.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.05)
        else:
            raise RuntimeError("git daemon did not accept connections")
        yield url
    finally:
        daemon.terminate()
        try:
            daemon.wait(timeout=2)
        except subprocess.TimeoutExpired:
            daemon.kill()
            daemon.wait(timeout=2)


def _filtered_fetch(tmp_path: Path, url: str, refspec: str) -> GitResult:
    settings = Settings(git_store_root=tmp_path, git_timeout_seconds=30)
    dest = tmp_path / "dest.git"
    safe_git = SafeGit(settings)
    safe_git.run(["init", "--bare", str(dest)])
    return safe_git.run(
        [
            "fetch",
            "--no-tags",
            "--no-recurse-submodules",
            f"--filter=blob:limit={settings.max_blob_bytes}",
            url,
            refspec,
        ],
        git_dir=dest,
    )


def test_filtered_fetch_demotes_zero_padded_filemode_to_a_warning(tmp_path: Path) -> None:
    if not _index_pack_accepts_typed_fsck_objects():
        pytest.skip("git index-pack does not accept --fsck-objects=<msg-id>=<severity>")
    source = _build_legacy_artifact_repo(tmp_path)
    for url in _serve_git_repo(source):
        result = _filtered_fetch(tmp_path, url, "+refs/heads/padded:refs/heads/padded")

    assert "zeroPaddedFilemode" in result.stderr.decode("utf-8", errors="replace")
    assert b"fatal: fsck error" not in result.stderr


def test_filtered_fetch_demotes_bad_timezone_to_a_warning(tmp_path: Path) -> None:
    if not _index_pack_accepts_typed_fsck_objects():
        pytest.skip("git index-pack does not accept --fsck-objects=<msg-id>=<severity>")
    source = _build_legacy_artifact_repo(tmp_path)
    for url in _serve_git_repo(source):
        result = _filtered_fetch(tmp_path, url, "+refs/heads/timezone:refs/heads/timezone")

    stderr = result.stderr.decode("utf-8", errors="replace")
    assert "badTimezone" in stderr
    assert "fatal: fsck error" not in stderr


def test_filtered_fetch_keeps_dangerous_fsck_checks_fatal(tmp_path: Path) -> None:
    if not _index_pack_accepts_typed_fsck_objects():
        pytest.skip("git index-pack does not accept --fsck-objects=<msg-id>=<severity>")
    source = _build_legacy_artifact_repo(tmp_path)
    with pytest.raises(GitCommandError) as caught:
        for url in _serve_git_repo(source):
            _filtered_fetch(tmp_path, url, "+refs/heads/missing-email:refs/heads/missing-email")

    assert caught.value.code == "git_failed"
    assert "missingEmail" in str(caught.value.details.get("stderr", ""))
    assert "skipList" not in str(caught.value.details.get("stderr", ""))
