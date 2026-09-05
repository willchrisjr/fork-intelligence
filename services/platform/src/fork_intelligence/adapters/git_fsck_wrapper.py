"""Rewrite index-pack fsck flags so filtered fetches honor warn overrides.

Git 2.55 fetch-pack passes ``--strict=<fetch.fsck.* spec>`` on unfiltered
fetches, but once ``--filter`` is set it switches to a bare ``--fsck-objects``
because ``--strict`` also checks links that partial clones intentionally omit.
The spec never reaches index-pack. This wrapper is exec'd as ``git`` from a
GIT_EXEC_PATH overlay so the child ``git index-pack`` invocation gets the
typed ``--fsck-objects=`` form that index-pack actually honors.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

FSCK_WARN_MSG_IDS: tuple[str, ...] = ("zeroPaddedFilemode", "badTimezone")
FSCK_WARN_SPEC = ",".join(f"{msg_id}=warn" for msg_id in FSCK_WARN_MSG_IDS)


def apply_index_pack_fsck_warn_overrides(args: list[str]) -> list[str]:
    """Return argv with ``--fsck-objects`` rewritten to include warn spec.

    Other arguments are unchanged. Dangerous fsck ids are not demoted.
    """
    rewritten: list[str] = []
    for argument in args:
        if argument == "--fsck-objects":
            rewritten.append(f"--fsck-objects={FSCK_WARN_SPEC}")
        elif argument.startswith("--fsck-objects="):
            rewritten.append(_merge_fsck_objects_arg(argument))
        else:
            rewritten.append(argument)
    return rewritten


def _merge_fsck_objects_arg(argument: str) -> str:
    existing = argument.removeprefix("--fsck-objects=")
    parts = [part for part in existing.split(",") if part]
    present = {part.split("=", 1)[0].lower() for part in parts}
    for override in FSCK_WARN_SPEC.split(","):
        msg_id = override.split("=", 1)[0]
        if msg_id.lower() not in present:
            parts.append(override)
    return "--fsck-objects=" + ",".join(parts)


def main() -> None:
    real_git = os.environ.get("FORK_INTELLIGENCE_REAL_GIT", "")
    if not real_git:
        sys.stderr.write("FORK_INTELLIGENCE_REAL_GIT is not set\n")
        sys.exit(127)
    program = Path(sys.argv[0]).name
    args = sys.argv[1:]
    if program.startswith("git-") and program != "git":
        args = [program[4:], *args]
    os.execv(real_git, [real_git, *apply_index_pack_fsck_warn_overrides(args)])  # noqa: S606


if __name__ == "__main__":
    main()
