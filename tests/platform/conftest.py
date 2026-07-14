from __future__ import annotations

import sys
from pathlib import Path

import pytest

FIXTURE_MODULES = Path(__file__).resolve().parents[2] / "fixtures" / "git"
if str(FIXTURE_MODULES) not in sys.path:
    sys.path.insert(0, str(FIXTURE_MODULES))

from build_fixture import SyntheticGitNetwork, build_synthetic_network  # noqa: E402


@pytest.fixture(scope="session")
def synthetic_git_network(tmp_path_factory: pytest.TempPathFactory) -> SyntheticGitNetwork:
    return build_synthetic_network(tmp_path_factory.mktemp("synthetic-git-network"))
