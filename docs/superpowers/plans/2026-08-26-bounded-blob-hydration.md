# Bounded Explicit Blob Hydration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `fetch_branch`'s blind whole-history blob fetch with an explicit, budgeted, deterministic hydration step that retrieves only the blobs the bounded analysis shortlist actually needs.

**Architecture:** A local planning call enumerates exactly which Git objects are absent for the analysis endpoints and the bounded commit shortlist. A separate network call hydrates them in a deterministic order under a per-fork byte ceiling, returning reason-coded outcomes. `compare` stays free of network I/O and receives the completed outcome for disclosure.

**Tech Stack:** Python 3.13, pytest, Git plumbing via the existing `SafeGit` sterile argv runner, Pydantic settings.

## Global Constraints

Copied verbatim from `docs/superpowers/specs/2026-08-26-bounded-blob-hydration-design.md`. Every task's requirements implicitly include this section.

- **Analyzed repository content is never executed.** Fetching Git objects is not execution. Never check out, build, or run analyzed code, hooks, or package managers.
- **`GIT_NO_LAZY_FETCH=1`** is set in `SafeGit.run`. Configuring a promisor remote is unavailable by design. Every network operation must be an explicit, argv-visible fetch.
- **`protocol.file.allow=never`** is set in `SafeGit.run`. Tests therefore **cannot** fetch from a local fixture path. `hydrate_blobs` network behaviour is tested by spying on `store.git.run` via `monkeypatch.setattr(store.git, "run", ...)`, following the existing pattern in `tests/platform/test_git_analysis.py:325`.
- **All Git invocations use fixed, validated argument arrays.** No shell, no interpolation of untrusted values.
- **Remotes must be the allowlisted HTTPS GitHub origin** produced by `parse_repository_identifier(...).clone_url`.
- Existing settings and their bounds: `max_blob_bytes` default `2_000_000`, `max_git_store_bytes` default `5_000_000_000`, `max_git_commits` default `2000`, `max_analysis_seconds` default `2700`, `git_timeout_seconds` default `120.0`.
- **Patch evidence is never fabricated.** A commit whose blobs did not arrive is recorded as missing.
- Every cap or incomplete stage is disclosed (D005).
- Add tests with every behaviour change. Run `uv run --directory services/platform pytest` from the repository root.

---

### Task 0: Mechanism measurement spike

Throwaway measurement. No production code is committed. It answers the two questions the budget defaults depend on, and it is the only task that touches the network against a real repository.

**Files:**
- Create: `/private/tmp/hydration-spike/` (scratch, outside the repository — never committed)
- Modify: `docs/superpowers/specs/2026-08-26-bounded-blob-hydration-design.md` (record the finding)

**Interfaces:**
- Consumes: nothing.
- Produces: a recorded answer to "does GitHub honour `--filter=blob:limit` on explicit commit-SHA wants", and a measured transfer size that Task 1 uses to pick the `max_hydration_bytes` default.

- [ ] **Step 1: Create a scratch bare store and fetch ancestry only**

```bash
mkdir -p /private/tmp/hydration-spike && cd /private/tmp/hydration-spike
rm -rf probe.git && git init --bare probe.git
git --git-dir=probe.git fetch --no-tags --no-recurse-submodules \
  --filter=blob:none https://github.com/octocat/Hello-World.git \
  '+refs/heads/master:refs/probe/master'
du -sh probe.git
```

Expected: fetch succeeds; `du -sh` shows a small store (tens of KB) because no blobs were transferred.

- [ ] **Step 2: Confirm blobs are genuinely absent**

```bash
cd /private/tmp/hydration-spike
git --git-dir=probe.git ls-tree -r refs/probe/master \
  | awk '{print $3}' \
  | git --git-dir=probe.git cat-file --batch-check
```

Expected: at least one line ending in `missing`. This is the same absence-detection mechanism Task 3 relies on, so a result with zero `missing` lines invalidates the plan and must be reported before continuing.

- [ ] **Step 3: Fetch explicit commit SHAs with a blob-size filter**

```bash
cd /private/tmp/hydration-spike
SHA=$(git --git-dir=probe.git rev-parse refs/probe/master)
git --git-dir=probe.git fetch --no-tags --no-recurse-submodules \
  --filter=blob:limit=2000000 https://github.com/octocat/Hello-World.git "$SHA"
du -sh probe.git
git --git-dir=probe.git ls-tree -r refs/probe/master \
  | awk '{print $3}' \
  | git --git-dir=probe.git cat-file --batch-check
```

Expected: the fetch succeeds and the previously-`missing` lines now report a type and size. Record the `du -sh` delta.

- [ ] **Step 4: Record the finding in the spec**

Append to the "Implementation step zero" section of the spec, replacing nothing:

```markdown
**Measured 2026-08-26.** GitHub [does / does not] honour `--filter=blob:limit`
on explicit commit-SHA wants. Store size after `blob:none`: [X]. After
hydrating one commit SHA under `blob:limit=2000000`: [Y]. Delta: [Y-X].
```

If GitHub does **not** honour the filter, stop and report before starting Task 1; the spec's fallback applies and this plan needs revision.

- [ ] **Step 5: Clean up and commit the recorded finding**

```bash
rm -rf /private/tmp/hydration-spike
git add docs/superpowers/specs/2026-08-26-bounded-blob-hydration-design.md
git commit -m "docs: record WO-12 hydration mechanism measurement"
```

---

### Task 1: Add the `max_hydration_bytes` setting

**Files:**
- Modify: `services/platform/src/fork_intelligence/config.py:53` (add after `max_blob_bytes`)
- Test: `tests/platform/test_config.py`

**Interfaces:**
- Consumes: the measured delta from Task 0.
- Produces: `Settings.max_hydration_bytes: int` — the per-fork hydration byte ceiling, consumed by `hydrate_blobs` in Task 4.

- [ ] **Step 1: Write the failing test**

Add to `tests/platform/test_config.py`:

```python
def test_max_hydration_bytes_has_a_bounded_per_fork_default() -> None:
    settings = Settings()

    assert settings.max_hydration_bytes == 250_000_000
    assert settings.max_hydration_bytes < settings.max_git_store_bytes


def test_max_hydration_bytes_rejects_values_outside_its_bounds() -> None:
    with pytest.raises(ValidationError):
        Settings(max_hydration_bytes=1023)
    with pytest.raises(ValidationError):
        Settings(max_hydration_bytes=100_000_000_001)
```

Ensure the file imports `ValidationError`:

```python
from pydantic import ValidationError
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory services/platform pytest tests/platform/test_config.py -k max_hydration_bytes -v`

Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'max_hydration_bytes'`.

- [ ] **Step 3: Write minimal implementation**

In `services/platform/src/fork_intelligence/config.py`, directly after the `max_blob_bytes` field:

```python
    max_hydration_bytes: int = Field(default=250_000_000, ge=1024, le=100_000_000_000)
```

The default is deliberately far below `max_git_store_bytes` (5 GB). The store cap is per-network and shared across every fork in an analysis; without a per-fork ceiling the first fork can consume the whole budget and starve the rest.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory services/platform pytest tests/platform/test_config.py -k max_hydration_bytes -v`

Expected: PASS, 2 passed.

- [ ] **Step 5: Commit**

```bash
git add services/platform/src/fork_intelligence/config.py tests/platform/test_config.py
git commit -m "feat(config): add max_hydration_bytes per-fork ceiling"
```

---

### Task 2: Add a blobless fixture variant

Every later task needs a store where blobs are genuinely absent. The existing `synthetic_git_network` fixture has all objects present, so it cannot exercise hydration at all.

**Files:**
- Modify: `fixtures/git/build_fixture.py:180` (extend the returned dataclass and builder)
- Modify: `tests/platform/conftest.py`
- Test: `tests/platform/test_git_analysis.py`

**Interfaces:**
- Consumes: `SyntheticGitNetwork` from Task 0's untouched fixture module.
- Produces: `SyntheticGitNetwork.blobless_store: Path` — a bare store holding every commit and tree from `bare_store` but no blob objects, plus `build_blobless_store(source: Path, destination: Path) -> Path`.

- [ ] **Step 1: Write the failing test**

Add to `tests/platform/test_git_analysis.py`:

```python
def test_blobless_fixture_store_has_trees_but_no_blobs(
    synthetic_git_network: SyntheticGitNetwork,
) -> None:
    store = BareNetworkStore("blobless-network", Settings())
    store.path = synthetic_git_network.blobless_store

    listing = store.git.run(
        ["ls-tree", "-r", synthetic_git_network.refs["ahead"]], git_dir=store.path
    ).text.splitlines()
    assert listing, "trees must still be present"

    oids = "\n".join(line.split()[2] for line in listing).encode()
    check = store.git.run(
        ["cat-file", "--batch-check"], git_dir=store.path, stdin=oids
    ).text

    assert "missing" in check
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory services/platform pytest tests/platform/test_git_analysis.py -k blobless_fixture -v`

Expected: FAIL with `AttributeError: 'SyntheticGitNetwork' object has no attribute 'blobless_store'`.

- [ ] **Step 3: Write minimal implementation**

In `fixtures/git/build_fixture.py`, add the field to the dataclass:

```python
@dataclass(frozen=True, slots=True)
class SyntheticGitNetwork:
    worktree: Path
    bare_store: Path
    refs: dict[str, str]
    shas: dict[str, str]
    blobless_store: Path
```

Add the builder function above `build_synthetic_network`:

```python
def build_blobless_store(source: Path, destination: Path) -> Path:
    """Copy every commit and tree from source, deliberately omitting blobs."""
    subprocess.run(  # noqa: S603 - fixed fixture-only Git argv
        [GIT_EXECUTABLE, "init", "--bare", str(destination)],
        check=True,
        capture_output=True,
        shell=False,
    )
    refs = subprocess.run(  # noqa: S603 - fixed fixture-only Git argv
        [GIT_EXECUTABLE, "--git-dir", str(source), "for-each-ref", "--format=%(refname)"],
        check=True,
        capture_output=True,
        shell=False,
    ).stdout.decode()
    for ref in refs.splitlines():
        subprocess.run(  # noqa: S603 - fixed fixture-only Git argv
            [
                GIT_EXECUTABLE,
                "--git-dir",
                str(destination),
                "fetch",
                "--no-tags",
                "--filter=blob:none",
                str(source),
                f"+{ref}:{ref}",
            ],
            check=True,
            capture_output=True,
            shell=False,
        )
    return destination
```

At the end of `build_synthetic_network`, before the return, build it and pass it through:

```python
    blobless_store = build_blobless_store(bare_store, root / "blobless.git")
    return SyntheticGitNetwork(
        worktree=worktree,
        bare_store=bare_store,
        refs=refs,
        shas=shas,
        blobless_store=blobless_store,
    )
```

Note: this fixture builder runs Git directly rather than through `SafeGit`, so `protocol.file.allow=never` does not apply to it. That is why the fixture may fetch from a local path while production code may not.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory services/platform pytest tests/platform/test_git_analysis.py -k blobless_fixture -v`

Expected: PASS.

- [ ] **Step 5: Verify no existing test regressed**

Run: `uv run --directory services/platform pytest tests/platform/test_git_analysis.py -v`

Expected: all previously-passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add fixtures/git/build_fixture.py tests/platform/test_git_analysis.py
git commit -m "test(fixtures): add blobless synthetic store variant"
```

---

### Task 3: `BlobHydrationPlan` and `plan_blob_hydration`

Pure local. No network.

**Files:**
- Modify: `services/platform/src/fork_intelligence/adapters/git.py` (add dataclass near `HistoryComparison:37`, add method to `BareNetworkStore`)
- Test: `tests/platform/test_git_analysis.py`

**Interfaces:**
- Consumes: `Settings.max_git_commits`, the blobless fixture from Task 2.
- Produces:
  - `BlobHydrationPlan` — frozen dataclass with `merge_base: str`, `endpoint_refs: tuple[str, str, str]`, `commits: list[str]`, `absent_objects: dict[str, list[str]]` (key `"endpoints"` plus one key per commit SHA).
  - `BareNetworkStore.plan_blob_hydration(upstream_ref: str, fork_ref: str, *, deadline: float | None = None) -> BlobHydrationPlan`

- [ ] **Step 1: Write the failing test**

```python
def test_hydration_plan_lists_absent_objects_for_endpoints_and_shortlist(
    synthetic_git_network: SyntheticGitNetwork,
) -> None:
    store = BareNetworkStore("plan-network", Settings())
    store.path = synthetic_git_network.blobless_store
    refs = synthetic_git_network.refs

    plan = store.plan_blob_hydration(refs["main"], refs["ahead"])

    assert plan.merge_base
    assert plan.endpoint_refs == (plan.merge_base, refs["ahead"], refs["main"])
    assert plan.commits, "the ahead branch has unique commits"
    assert "endpoints" in plan.absent_objects
    assert any(plan.absent_objects[commit] for commit in plan.commits)


def test_hydration_plan_is_empty_when_every_blob_is_already_present(
    synthetic_git_network: SyntheticGitNetwork, tmp_path: Path
) -> None:
    store = _store(synthetic_git_network, tmp_path)
    refs = synthetic_git_network.refs

    plan = store.plan_blob_hydration(refs["main"], refs["ahead"])

    assert plan.commits, "the shortlist is still computed"
    assert all(not objects for objects in plan.absent_objects.values())


def test_hydration_plan_performs_no_network_access(
    synthetic_git_network: SyntheticGitNetwork, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = BareNetworkStore("plan-network", Settings())
    store.path = synthetic_git_network.blobless_store
    real_run = store.git.run
    commands: list[list[str]] = []

    def recording_run(args: list[str], **kwargs: Any) -> object:
        commands.append(args)
        return real_run(args, **kwargs)

    monkeypatch.setattr(store.git, "run", recording_run)

    store.plan_blob_hydration(
        synthetic_git_network.refs["main"], synthetic_git_network.refs["ahead"]
    )

    assert not any(args[0] == "fetch" for args in commands)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --directory services/platform pytest tests/platform/test_git_analysis.py -k hydration_plan -v`

Expected: FAIL with `AttributeError: 'BareNetworkStore' object has no attribute 'plan_blob_hydration'`.

- [ ] **Step 3: Write minimal implementation**

Add the dataclass after `HistoryComparison` in `git.py`:

```python
@dataclass(frozen=True, slots=True)
class BlobHydrationPlan:
    merge_base: str
    endpoint_refs: tuple[str, str, str]
    commits: list[str]
    absent_objects: dict[str, list[str]]

    @property
    def total_absent(self) -> int:
        return sum(len(objects) for objects in self.absent_objects.values())
```

Add to `BareNetworkStore`:

```python
    def plan_blob_hydration(
        self, upstream_ref: str, fork_ref: str, *, deadline: float | None = None
    ) -> BlobHydrationPlan:
        _validate_full_ref(upstream_ref)
        _validate_full_ref(fork_ref)
        self._assert_not_quarantined()
        merge_base = self._run_with_optional_deadline(
            ["merge-base", upstream_ref, fork_ref], deadline
        ).text.strip()
        commits = self._run_with_optional_deadline(
            [
                "rev-list",
                "--reverse",
                f"--max-count={self.settings.max_git_commits}",
                f"{upstream_ref}..{fork_ref}",
            ],
            deadline,
        ).text.splitlines()
        endpoint_refs = (merge_base, fork_ref, upstream_ref)
        absent: dict[str, list[str]] = {}
        endpoint_oids: list[str] = []
        for ref in endpoint_refs:
            endpoint_oids.extend(self._tree_blob_oids(ref, deadline))
        absent["endpoints"] = self._absent_oids(endpoint_oids, deadline)
        for commit in commits:
            absent[commit] = self._absent_oids(
                self._commit_blob_oids(commit, deadline), deadline
            )
        return BlobHydrationPlan(
            merge_base=merge_base,
            endpoint_refs=endpoint_refs,
            commits=commits,
            absent_objects=absent,
        )

    def _tree_blob_oids(self, ref: str, deadline: float | None) -> list[str]:
        listing = self._run_with_optional_deadline(
            ["ls-tree", "-r", ref], deadline
        ).text.splitlines()
        return [line.split()[2] for line in listing if line]

    def _commit_blob_oids(self, commit: str, deadline: float | None) -> list[str]:
        raw = self._run_with_optional_deadline(
            ["diff-tree", "-r", "--root", "--no-commit-id", commit], deadline
        ).text.splitlines()
        oids: list[str] = []
        for line in raw:
            if not line.startswith(":"):
                continue
            fields = line[1:].split()
            if len(fields) < 4:
                continue
            for oid in (fields[2], fields[3]):
                if _SHA.fullmatch(oid) and oid != _EMPTY_OID:
                    oids.append(oid)
        return oids

    def _absent_oids(self, oids: list[str], deadline: float | None) -> list[str]:
        unique = sorted(set(oids))
        if not unique:
            return []
        check = self._run_with_optional_deadline(
            ["cat-file", "--batch-check"],
            deadline,
            stdin=("\n".join(unique) + "\n").encode("utf-8"),
        ).text
        missing: list[str] = []
        for line in check.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "missing":
                missing.append(parts[0])
        return missing
```

Add the module constant near `_SHA`:

```python
_EMPTY_OID = "0" * 40
```

`cat-file --batch-check` is used rather than `rev-list --missing=print` because the store has no `extensions.partialClone` configured, and `--batch-check` reports absence as data rather than failing.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --directory services/platform pytest tests/platform/test_git_analysis.py -k hydration_plan -v`

Expected: PASS, 3 passed.

- [ ] **Step 5: Commit**

```bash
git add services/platform/src/fork_intelligence/adapters/git.py tests/platform/test_git_analysis.py
git commit -m "feat(git): add local bounded blob hydration planning"
```

---

### Task 4: `HydrationOutcome` and `hydrate_blobs`

The only network step. Tested by spying on `store.git.run`, because `protocol.file.allow=never` forbids fetching a local fixture.

**Files:**
- Modify: `services/platform/src/fork_intelligence/adapters/git.py`
- Test: `tests/platform/test_git_analysis.py`

**Interfaces:**
- Consumes: `BlobHydrationPlan` from Task 3, `Settings.max_hydration_bytes` from Task 1, `parse_repository_identifier`.
- Produces:
  - `HydrationOutcome` — frozen dataclass with `planned: int`, `hydrated: int`, `cutoff_index: int | None`, `missing: dict[str, int]` (keys `oversized`, `absent_upstream`, `budget_exhausted`, `fetch_failed`), `hydrated_commits: list[str]`.
  - `BareNetworkStore.hydrate_blobs(plan: BlobHydrationPlan, owner: str, repository: str, *, deadline: float | None = None) -> HydrationOutcome`

- [ ] **Step 1: Write the failing test**

```python
def _spy_store(network: SyntheticGitNetwork, settings: Settings) -> tuple[BareNetworkStore, list[list[str]]]:
    store = BareNetworkStore("hydrate-network", settings)
    store.path = network.blobless_store
    return store, []


def test_hydration_fetches_endpoints_before_shortlist_commits(
    synthetic_git_network: SyntheticGitNetwork, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, commands = _spy_store(synthetic_git_network, Settings())
    plan = store.plan_blob_hydration(
        synthetic_git_network.refs["main"], synthetic_git_network.refs["ahead"]
    )
    real_run = store.git.run

    def recording_run(args: list[str], **kwargs: Any) -> object:
        commands.append(args)
        if args and args[0] == "fetch":
            return GitResult(stdout=b"", stderr=b"")
        return real_run(args, **kwargs)

    monkeypatch.setattr(store.git, "run", recording_run)

    outcome = store.hydrate_blobs(plan, "octocat", "Hello-World")

    fetches = [args for args in commands if args and args[0] == "fetch"]
    assert fetches, "hydration must issue at least one fetch"
    first = fetches[0]
    assert "--filter=blob:limit=2000000" in first
    assert "https://github.com/octocat/Hello-World.git" in first
    assert plan.merge_base in first
    assert first[0] == "fetch"
    assert outcome.planned == len(plan.commits)


def test_hydration_stops_at_the_byte_ceiling_and_reports_a_cutoff(
    synthetic_git_network: SyntheticGitNetwork, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, commands = _spy_store(synthetic_git_network, Settings(max_hydration_bytes=1024))
    plan = store.plan_blob_hydration(
        synthetic_git_network.refs["main"], synthetic_git_network.refs["ahead"]
    )
    real_run = store.git.run

    def recording_run(args: list[str], **kwargs: Any) -> object:
        commands.append(args)
        if args and args[0] == "fetch":
            return GitResult(stdout=b"", stderr=b"")
        return real_run(args, **kwargs)

    monkeypatch.setattr(store.git, "run", recording_run)
    monkeypatch.setattr(store, "_store_size_bytes", lambda: 2048)

    outcome = store.hydrate_blobs(plan, "octocat", "Hello-World")

    assert outcome.cutoff_index is not None
    assert outcome.missing["budget_exhausted"] > 0


def test_hydration_records_fetch_failure_without_raising(
    synthetic_git_network: SyntheticGitNetwork, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, commands = _spy_store(synthetic_git_network, Settings())
    plan = store.plan_blob_hydration(
        synthetic_git_network.refs["main"], synthetic_git_network.refs["ahead"]
    )
    real_run = store.git.run

    def recording_run(args: list[str], **kwargs: Any) -> object:
        if args and args[0] == "fetch":
            raise GitCommandError("git_failed", "simulated transport failure")
        return real_run(args, **kwargs)

    monkeypatch.setattr(store.git, "run", recording_run)

    outcome = store.hydrate_blobs(plan, "octocat", "Hello-World")

    assert outcome.hydrated == 0
    assert outcome.missing["fetch_failed"] > 0
```

Ensure the test module imports `GitResult`:

```python
from fork_intelligence.adapters.git import BareNetworkStore, GitResult, SafeGit, _namespace_branch
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --directory services/platform pytest tests/platform/test_git_analysis.py -k hydration_ -v`

Expected: FAIL with `AttributeError: 'BareNetworkStore' object has no attribute 'hydrate_blobs'`.

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass(frozen=True, slots=True)
class HydrationOutcome:
    planned: int
    hydrated: int
    cutoff_index: int | None
    missing: dict[str, int]
    hydrated_commits: list[str]
```

```python
    def hydrate_blobs(
        self,
        plan: BlobHydrationPlan,
        owner: str,
        repository: str,
        *,
        deadline: float | None = None,
    ) -> HydrationOutcome:
        self._assert_not_quarantined()
        identifier = parse_repository_identifier(f"{owner}/{repository}")
        missing = {
            "oversized": 0,
            "absent_upstream": 0,
            "budget_exhausted": 0,
            "fetch_failed": 0,
        }
        baseline = self._store_size_bytes()
        hydrated_commits: list[str] = []
        cutoff_index: int | None = None

        if plan.absent_objects.get("endpoints"):
            if not self._hydrate_wants(identifier, list(plan.endpoint_refs), deadline):
                missing["fetch_failed"] += 1

        for index, commit in enumerate(plan.commits):
            if not plan.absent_objects.get(commit):
                hydrated_commits.append(commit)
                continue
            if self._store_size_bytes() - baseline >= self.settings.max_hydration_bytes:
                cutoff_index = index
                missing["budget_exhausted"] = len(plan.commits) - index
                break
            if self._hydrate_wants(identifier, [commit], deadline):
                remaining = self._absent_oids(plan.absent_objects[commit], deadline)
                if remaining:
                    missing["oversized"] += 1
                else:
                    hydrated_commits.append(commit)
            else:
                missing["fetch_failed"] += 1

        self._enforce_store_limit()
        return HydrationOutcome(
            planned=len(plan.commits),
            hydrated=len(hydrated_commits),
            cutoff_index=cutoff_index,
            missing=missing,
            hydrated_commits=hydrated_commits,
        )

    def _hydrate_wants(
        self, identifier: Any, wants: list[str], deadline: float | None
    ) -> bool:
        args = [
            "fetch",
            "--no-tags",
            "--no-recurse-submodules",
            f"--filter=blob:limit={self.settings.max_blob_bytes}",
            identifier.clone_url,
            *wants,
        ]
        try:
            self._run_with_optional_deadline(args, deadline)
        except GitCommandError as exc:
            if exc.code in {"git_resource_limit", "git_store_limit", "git_timeout"}:
                raise
            return False
        return True
```

Reason codes are assigned as follows. A fetch that raises a non-escalating error is `fetch_failed`. A fetch that succeeds but leaves objects still absent means the remote declined to serve them under the size filter, which is `oversized`. Reaching the byte ceiling before processing a commit is `budget_exhausted`. `absent_upstream` is reserved for Task 8's fixture, where the remote reports the object does not exist.

`git_store_limit`, `git_resource_limit`, and `git_timeout` deliberately propagate, preserving the existing escalation and quarantine behaviour.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --directory services/platform pytest tests/platform/test_git_analysis.py -k hydration_ -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/platform/src/fork_intelligence/adapters/git.py tests/platform/test_git_analysis.py
git commit -m "feat(git): add bounded explicit blob hydration"
```

---

### Task 5: Remove the blanket blob fetch from `fetch_branch`

**Files:**
- Modify: `services/platform/src/fork_intelligence/adapters/git.py:275-288`
- Test: `tests/platform/test_git_analysis.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `fetch_branch` issues exactly one `fetch`, with `--filter=blob:none`.

- [ ] **Step 1: Write the failing test**

```python
def test_fetch_branch_issues_only_the_blobless_ancestry_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = BareNetworkStore("single-fetch-network", Settings(git_store_root=tmp_path))
    fetches: list[list[str]] = []

    def recording_run(args: list[str], **kwargs: Any) -> object:
        if args and args[0] == "fetch":
            fetches.append(args)
            return GitResult(stdout=b"", stderr=b"")
        if args and args[0] == "rev-parse":
            return GitResult(stdout=b"a" * 40 + b"\n", stderr=b"")
        return GitResult(stdout=b"", stderr=b"")

    monkeypatch.setattr(store.git, "run", recording_run)

    store.fetch_branch(
        "00000000-0000-4000-8000-000000000000", 1, "octocat", "Hello-World", "main", "a" * 40
    )

    assert len(fetches) == 1
    assert "--filter=blob:none" in fetches[0]
    assert not any(arg.startswith("--filter=blob:limit") for arg in fetches[0])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory services/platform pytest tests/platform/test_git_analysis.py -k only_the_blobless -v`

Expected: FAIL, `assert 2 == 1`.

- [ ] **Step 3: Write minimal implementation**

In `fetch_branch`, delete the entire second fetch block — the `try:` containing `--filter=blob:limit=...` through its `except GitCommandError` clause (currently `git.py:275-288`), leaving the first fetch, its `_enforce_store_limit()`, and the `rev-parse` head verification intact. The next statement after the head-change check becomes:

```python
            self.git.run(["update-ref", cached, head_sha], git_dir=self.path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory services/platform pytest tests/platform/test_git_analysis.py -k only_the_blobless -v`

Expected: PASS.

- [ ] **Step 5: Run the whole Git suite for regressions**

Run: `uv run --directory services/platform pytest tests/platform/test_git_analysis.py -v`

Expected: all pass. Any failure here is a blob requirement not captured in the spec's working-set table and must be reported.

- [ ] **Step 6: Commit**

```bash
git add services/platform/src/fork_intelligence/adapters/git.py tests/platform/test_git_analysis.py
git commit -m "refactor(git): drop the blanket blob fetch from fetch_branch"
```

---

### Task 6: Disclose hydration through `compare`

**Files:**
- Modify: `services/platform/src/fork_intelligence/adapters/git.py:370` (signature) and the `patch_overlap` construction at `git.py:462-478`
- Test: `tests/platform/test_git_analysis.py`

**Interfaces:**
- Consumes: `HydrationOutcome` from Task 4.
- Produces: `compare(..., hydration: HydrationOutcome | None = None)`; `patch_overlap["coverage"]["hydration"]` present only when `hydration` is not `None`.

- [ ] **Step 1: Write the failing test**

```python
def test_compare_omits_hydration_disclosure_when_none_was_performed(
    synthetic_git_network: SyntheticGitNetwork, tmp_path: Path
) -> None:
    store = _store(synthetic_git_network, tmp_path)

    comparison = store.compare(
        synthetic_git_network.refs["main"], synthetic_git_network.refs["ahead"]
    )

    coverage = comparison.patch_overlap["coverage"]
    assert "hydration" not in coverage


def test_compare_discloses_hydration_outcome_when_supplied(
    synthetic_git_network: SyntheticGitNetwork, tmp_path: Path
) -> None:
    store = _store(synthetic_git_network, tmp_path)
    outcome = HydrationOutcome(
        planned=5,
        hydrated=3,
        cutoff_index=3,
        missing={
            "oversized": 1,
            "absent_upstream": 0,
            "budget_exhausted": 2,
            "fetch_failed": 0,
        },
        hydrated_commits=[],
    )

    comparison = store.compare(
        synthetic_git_network.refs["main"],
        synthetic_git_network.refs["ahead"],
        hydration=outcome,
    )

    disclosure = comparison.patch_overlap["coverage"]["hydration"]
    assert disclosure["method"] == "bounded-explicit-hydration-v1"
    assert disclosure["planned"] == 5
    assert disclosure["hydrated"] == 3
    assert disclosure["cutoff_index"] == 3
    assert disclosure["missing"]["budget_exhausted"] == 2
```

Import `HydrationOutcome` in the test module.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --directory services/platform pytest tests/platform/test_git_analysis.py -k hydration_disclosure -v`

Expected: FAIL with `TypeError: compare() got an unexpected keyword argument 'hydration'`.

- [ ] **Step 3: Write minimal implementation**

Change the signature:

```python
    def compare(
        self,
        upstream_ref: str,
        fork_ref: str,
        *,
        timeout: float | None = None,
        hydration: HydrationOutcome | None = None,
    ) -> HistoryComparison:
```

Immediately before the `return HistoryComparison(...)`, build the coverage object:

```python
        coverage: dict[str, object] = {
            "commit_patches_available": len(patch_ids) + len(upstream_patch_ids),
            "commit_patches_missing": len(missing_blob_commits),
        }
        if hydration is not None:
            coverage["hydration"] = {
                "method": "bounded-explicit-hydration-v1",
                "planned": hydration.planned,
                "hydrated": hydration.hydrated,
                "cutoff_index": hydration.cutoff_index,
                "missing": dict(hydration.missing),
            }
```

Then replace the inline `"coverage": {...}` literal inside `patch_overlap` with `"coverage": coverage`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --directory services/platform pytest tests/platform/test_git_analysis.py -k hydration_disclosure -v`

Expected: PASS, 2 passed.

- [ ] **Step 5: Commit**

```bash
git add services/platform/src/fork_intelligence/adapters/git.py tests/platform/test_git_analysis.py
git commit -m "feat(git): disclose hydration coverage in patch overlap"
```

---

### Task 7: Wire hydration into the pipeline

**Files:**
- Modify: `services/platform/src/fork_intelligence/services/pipeline.py:521-529`, and the metrics block at `pipeline.py:555`
- Test: `tests/platform/test_pipeline.py`

**Interfaces:**
- Consumes: `plan_blob_hydration`, `hydrate_blobs`, `compare(hydration=...)`.
- Produces: the fork analysis snapshot's `patch_coverage` metrics gain `hydration_planned` and `hydration_hydrated`.

- [ ] **Step 1: Write the failing test**

Add to `tests/platform/test_pipeline.py`:

```python
def test_fork_analysis_plans_and_hydrates_before_comparing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_plan(self: Any, upstream_ref: str, fork_ref: str, **kwargs: Any) -> Any:
        calls.append("plan")
        return BlobHydrationPlan(
            merge_base="b" * 40,
            endpoint_refs=("b" * 40, fork_ref, upstream_ref),
            commits=[],
            absent_objects={"endpoints": []},
        )

    def fake_hydrate(self: Any, plan: Any, owner: str, repository: str, **kwargs: Any) -> Any:
        calls.append("hydrate")
        return HydrationOutcome(
            planned=0,
            hydrated=0,
            cutoff_index=None,
            missing={
                "oversized": 0,
                "absent_upstream": 0,
                "budget_exhausted": 0,
                "fetch_failed": 0,
            },
            hydrated_commits=[],
        )

    real_compare = BareNetworkStore.compare

    def recording_compare(self: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append("compare")
        assert "hydration" in kwargs
        return real_compare(self, *args, **kwargs)

    monkeypatch.setattr(BareNetworkStore, "plan_blob_hydration", fake_plan)
    monkeypatch.setattr(BareNetworkStore, "hydrate_blobs", fake_hydrate)
    monkeypatch.setattr(BareNetworkStore, "compare", recording_compare)

    # Exercise the fork-analysis path using the module's existing pipeline
    # harness helper; see the neighbouring tests in this file for the setup
    # they share.
    _run_single_fork_analysis()

    assert calls == ["plan", "hydrate", "compare"]
```

If `_run_single_fork_analysis` does not already exist in the test module, extract it from whichever neighbouring test currently drives `_analyze_fork`, so the ordering assertion reuses the established harness rather than inventing a second one.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory services/platform pytest tests/platform/test_pipeline.py -k plans_and_hydrates -v`

Expected: FAIL — `calls == ["compare"]`, since planning and hydration are not wired in yet.

- [ ] **Step 3: Write minimal implementation**

In `pipeline.py`, between the `fork_ref = store.fetch_branch(...)` call and the `comparison = store.compare(...)` call:

```python
        hydration_plan = store.plan_blob_hydration(root_ref, fork_ref)
        hydration = store.hydrate_blobs(
            hydration_plan,
            fork.owner,
            fork.name,
        )
        comparison = store.compare(
            root_ref,
            fork_ref,
            hydration=hydration,
        )
```

Use whatever owner/name attributes the surrounding code already uses for this fork; do not introduce new lookups.

Extend the metrics block at `pipeline.py:555`:

```python
                    "missing_blobs": len(comparison.missing_blob_commits),
                    "hydration_planned": hydration.planned,
                    "hydration_hydrated": hydration.hydrated,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory services/platform pytest tests/platform/test_pipeline.py -k plans_and_hydrates -v`

Expected: PASS.

- [ ] **Step 5: Run the full platform suite**

Run: `uv run --directory services/platform pytest`

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add services/platform/src/fork_intelligence/services/pipeline.py tests/platform/test_pipeline.py
git commit -m "feat(pipeline): hydrate bounded blobs before comparing forks"
```

---

### Task 8: Edge-case fixtures and the determinism guarantee

**Files:**
- Modify: `fixtures/git/build_fixture.py`
- Test: `tests/platform/test_git_analysis.py`

**Interfaces:**
- Consumes: everything from Tasks 2 through 6.
- Produces: fixture scenarios `oversized_blob`, `absent_blob`, `corrupt_object`; no new production interfaces.

- [ ] **Step 1: Write the failing tests**

```python
def test_oversized_blobs_are_reported_as_missing_not_fabricated(
    synthetic_git_network: SyntheticGitNetwork, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = BareNetworkStore("oversized-hydration", Settings(max_blob_bytes=1024))
    store.path = synthetic_git_network.blobless_store
    plan = store.plan_blob_hydration(
        synthetic_git_network.refs["main"], synthetic_git_network.refs["binary"]
    )
    real_run = store.git.run

    def recording_run(args: list[str], **kwargs: Any) -> object:
        if args and args[0] == "fetch":
            return GitResult(stdout=b"", stderr=b"")
        return real_run(args, **kwargs)

    monkeypatch.setattr(store.git, "run", recording_run)

    outcome = store.hydrate_blobs(plan, "octocat", "Hello-World")

    assert outcome.missing["oversized"] > 0
    assert outcome.hydrated < outcome.planned


def test_hydration_is_reproducible_under_identical_caps(
    synthetic_git_network: SyntheticGitNetwork, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run_once() -> HydrationOutcome:
        store = BareNetworkStore("determinism", Settings(max_hydration_bytes=4096))
        store.path = synthetic_git_network.blobless_store
        plan = store.plan_blob_hydration(
            synthetic_git_network.refs["main"], synthetic_git_network.refs["series"]
        )
        real_run = store.git.run

        def recording_run(args: list[str], **kwargs: Any) -> object:
            if args and args[0] == "fetch":
                return GitResult(stdout=b"", stderr=b"")
            return real_run(args, **kwargs)

        monkeypatch.setattr(store.git, "run", recording_run)
        monkeypatch.setattr(store, "_store_size_bytes", lambda: 8192)
        return store.hydrate_blobs(plan, "octocat", "Hello-World")

    first = run_once()
    second = run_once()

    assert first.cutoff_index == second.cutoff_index
    assert first.hydrated_commits == second.hydrated_commits
    assert first.missing == second.missing


def test_renames_still_resolve_after_the_blanket_fetch_removal(
    synthetic_git_network: SyntheticGitNetwork, tmp_path: Path
) -> None:
    store = _store(synthetic_git_network, tmp_path)

    comparison = store.compare(
        synthetic_git_network.refs["main"], synthetic_git_network.refs["rename"]
    )

    statuses = {entry["status"][0] for entry in comparison.changed_files}
    assert "R" in statuses
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --directory services/platform pytest tests/platform/test_git_analysis.py -k "oversized_blobs or reproducible or renames_still" -v`

Expected: the oversized and reproducibility tests fail; the rename test may already pass, which is correct — it exists as a regression guard for Task 5.

- [ ] **Step 3: Add the oversized fixture scenario**

In `build_synthetic_network`, after the existing `binary` scenario:

```python
    builder.branch("oversized", base)
    builder.write("assets/large.bin", b"\x00" * 3_000_000)
    oversized = builder.commit("add an oversized binary asset")
```

Add `"oversized": oversized,` to the `shas` dict.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --directory services/platform pytest tests/platform/test_git_analysis.py -k "oversized_blobs or reproducible or renames_still" -v`

Expected: PASS.

- [ ] **Step 5: Run the complete check suite**

Run: `pnpm check:ci`

Expected: format, lint, strict mypy, all platform tests, frontend tests, contract generation, and build all pass.

- [ ] **Step 6: Commit**

```bash
git add fixtures/git/build_fixture.py tests/platform/test_git_analysis.py
git commit -m "test: cover oversized blobs, determinism, and rename regression"
```

---

### Task 9: Update documentation and open the pull request

**Files:**
- Modify: `docs/STATUS.md`, `docs/ROADMAP.md`, `docs/HANDOFF.md`

**Interfaces:**
- Consumes: the completed implementation.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Record the delivered behaviour in STATUS**

Under "Completed", add:

```markdown
- Bounded explicit blob hydration plans and retrieves only the blobs needed by
  the analysis endpoints and the capped commit shortlist, in a deterministic
  order under a per-fork byte ceiling, with reason-coded disclosure of anything
  not hydrated.
```

- [ ] **Step 2: Mark the roadmap item delivered**

In `docs/ROADMAP.md`, Priority 1 item 3, append: `Delivered 2026-08-26 (WO-12).`

- [ ] **Step 3: Mark the HANDOFF section resolved**

In `docs/HANDOFF.md` § "3. Bounded explicit blob hydration", add a `**Resolved**` marker line following the pattern used by the two P0 sections.

- [ ] **Step 4: Run the full check suite one final time**

Run: `pnpm check:ci`

Expected: all pass.

- [ ] **Step 5: Commit and open the pull request**

```bash
git add docs/STATUS.md docs/ROADMAP.md docs/HANDOFF.md
git commit -m "docs: record WO-12 bounded blob hydration as delivered"
git push -u origin agent/wo-12-blob-hydration
gh pr create --base main --title "WO-12: bounded explicit blob hydration" --body-file -
```

Fill the repository pull request template. State honestly which checks were run, and note in "Known limitations" that web presentation and export provenance for hydration disclosures remain follow-on work.

---

## Self-Review

**Spec coverage.** Every spec section maps to a task: the working-set table drives Task 3's endpoint and commit enumeration; the fetch mechanism is Tasks 0 and 4; ordering and determinism are Tasks 4 and 8; blanket-fetch removal is Task 5; disclosure is Task 6; budgets are Tasks 1 and 4; testing is Tasks 2 and 8; acceptance criteria are covered across Tasks 3 through 8.

**Known gap, deliberately left.** The spec lists `absent_upstream` as a reason code, but no task produces it — it requires a remote that reports an object as nonexistent, which the spy-based test strategy cannot simulate and `protocol.file.allow=never` prevents testing locally. Task 4 initialises the counter to `0` and never increments it. The implementer should either wire it where a fetch fails with a "not our ref" style error, or drop the code from the disclosure and the spec. Flag this rather than fabricating coverage for it.

**Type consistency.** `BlobHydrationPlan`, `HydrationOutcome`, `plan_blob_hydration`, `hydrate_blobs`, and `compare(hydration=...)` use identical names and signatures across Tasks 3, 4, 6, and 7. `missing` keys are the same four strings throughout. `cutoff_index` is `int | None` everywhere.
