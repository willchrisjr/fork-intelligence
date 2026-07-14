# Git Analysis Research

Status: architecture baseline
Accessed: 2026-07-13
Primary sources: Git manuals listed in [SOURCE_REGISTER.md](SOURCE_REGISTER.md)

## Chosen storage model

Create one bare Git repository per GitHub fork network. It has no working tree
and stores fetched branch heads under exact, analyzer-owned references:

```text
data/git/networks/<network-id>.git/
refs/forks/<repository-id>/<encoded-branch>
```

The stable numeric repository ID prevents owner/name collisions after transfer.
The display owner/name is metadata, never part of command construction. Reference
components are encoded by a strict function and validated with
`git check-ref-format`; untrusted text is never interpolated into a shell.

Use explicit fetch refspecs and `--no-tags` by default. Tags and additional
branches are fetched only when the branch-selection stage includes them. A
network store shares identical objects naturally, avoiding a full clone per fork.
Alternates are not used in the MVP because lifecycle coupling can make objects
disappear when the alternate is pruned.

## Fetch strategy

1. Initialize a bare network store owned by the service account.
2. Validate an HTTPS `github.com/{owner}/{repo}.git` URL produced from normalized
   API data; never accept an arbitrary clone URL from user input.
3. Fetch the root default branch to its namespaced reference.
4. Fetch shortlisted fork heads one at a time using exact positive refspecs.
5. Start with `--filter=blob:none` when the server supports partial clone.
6. Materialize bounded blobs only for deep file/dependency analysis.
7. Record requested ref, observed SHA, fetch result, bytes/time where available,
   and object-filter depth.

Do not use shallow history for structural conclusions: shallow boundaries can
invalidate merge-base, reachability, ahead/behind, first divergence, and patch
coverage. If a bounded preview starts shallow, mark it metadata/preview depth and
deepen before publishing structural results.

## Deterministic calculations

For upstream `U` and fork `F`:

- merge base: `git merge-base U F`;
- ahead/behind: `git rev-list --left-right --count U...F`;
- fork-unique commits: `git rev-list U..F`;
- upstream-unique commits: `git rev-list F..U`;
- shared/reachable history: calculated from the merge base and commit graph;
- first divergence: oldest fork-unique boundary following the selected merge
  base, with criss-cross ambiguity disclosed;
- file status/composition: `git diff --name-status` and `--numstat` between the
  selected endpoints, with rename detection explicitly configured;
- patch fingerprint: patch output piped to `git patch-id --stable`.

Git documents stable patch IDs as reasonably stable and unique and intended for
likely duplicate commits. They ignore line numbers and whitespace, and stable
mode is insensitive to file-diff order. Therefore:

- equal stable patch ID => deterministic patch-equivalent evidence;
- unequal ID does not prove different intent;
- squashes require comparing a bounded combined normalized diff;
- similar paths or terms are similarity evidence, not equivalence;
- an LLM may never declare deterministic equivalence.

Store the Git version, diff options, hash algorithm, and patch-method version
with every fingerprint. Merge commits require an explicit parent policy and are
not silently reduced to a single-parent patch.

## Rename and composition handling

Rename detection is heuristic. Record the configured similarity threshold and
retain the raw add/delete view so results can be reproduced. File classification
separates source, tests, documentation, CI, build/packaging, manifests, lockfiles,
configuration, generated, vendored, assets, examples, and unknown. Show both raw
and adjusted divergence; adjusted results never delete the raw evidence.

## Safety configuration

All Git invocations use an argument array, a fixed executable, a fixed working
directory, a minimal environment, captured output limits, and a wall-clock
timeout. Required controls include:

- `GIT_CONFIG_NOSYSTEM=1` and a controlled `HOME`;
- command-scoped configuration such as `protocol.file.allow=never`, disabled
  credential prompts, and no recursive submodules;
- an empty service-owned hooks path; never run repository hooks;
- HTTPS GitHub remotes only, no `ext::`, file, SSH, or custom protocols;
- no checkout, worktree, package manager, build, test, filter, or executable;
- separate process concurrency, disk, object-count, blob-size, and output caps;
- redaction of credentials and remote query data from logs.

Do not bypass dubious-ownership checks by setting global `safe.directory=*`.
Stores are created and owned by the worker account. Any ownership failure is an
operational error requiring quarantine, not a configuration override.

## Maintenance, cleanup, and recovery

Ref updates are staged to temporary analyzer refs, verified, then atomically
promoted. On failure, leave the prior evidence refs intact. A per-network lock
serializes fetch/ref mutation; read-only calculations may run concurrently after
the snapshot is sealed.

Run bounded `git fsck` after suspicious failures. Schedule `git maintenance` or
`git gc` only when no analysis uses the store, and retain refs needed by active
or retained analyses before pruning. Eviction deletes the entire network store
only after database retention state marks it unreferenced. Recovery attempts to
recreate an unsealed store from persisted GitHub identity and recorded heads,
but this is best effort because force-pushed or deleted objects may no longer be
reachable. Refs and objects cited by retained evidence are preservation data,
not disposable cache; analysis/provenance state still lives in PostgreSQL.

## Performance guidance

- Reuse objects across forks inside the network bare store.
- Enable commit-graph maintenance after fetch-heavy phases.
- Bound fetch and analysis concurrency per host and per network.
- Delay blobs and large-path statistics until a fork is shortlisted.
- Cache calculations by `(left_sha, right_sha, algorithm_version, options)`.
- Measure mirror-heavy, many-branch, rebased, squashed, generated-heavy, and
  vendored-heavy fixtures before increasing defaults.

## Validation requirements

Use actual synthetic repositories, not mocked command output, to cover identical,
ahead, behind, divergent, cherry-picked, rebased, squashed, merge, rename,
generated-only, vendor-only, multiple-branch, and similar-area histories. Fuzz
repository names and branch names through the ref encoder. Tests must prove no
fixture hook or repository program is executed.
