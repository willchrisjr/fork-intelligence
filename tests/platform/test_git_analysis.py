from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
from build_fixture import SyntheticGitNetwork

from fork_intelligence.adapters.git import BareNetworkStore, SafeGit, _namespace_branch
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
