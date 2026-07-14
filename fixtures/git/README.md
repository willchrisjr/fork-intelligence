# Synthetic Git fixture

`build_fixture.py` creates a deterministic repository graph at test time. It
uses fixed identities, timestamps, messages, and file contents, then mirrors
the scenario heads into immutable `refs/analyses/...` refs in a bare store.

The graph covers:

- an exact mirror;
- a fork ahead of upstream;
- diverged upstream and fork histories;
- a cherry-picked patch with a different commit identity;
- an equivalent patch after rebasing onto a newer upstream;
- a two-commit series and its one-commit squash;
- rename detection;
- a merge commit;
- binary, generated, and vendored changes.

The fixture builder invokes Git only through fixed argument arrays. It never
executes repository content, hooks, submodules, or package commands.
