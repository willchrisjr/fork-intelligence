from __future__ import annotations

import argparse
import json
from pathlib import Path

from fork_intelligence.api.main import app


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export the deterministic FastAPI OpenAPI document"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("../../packages/contracts/openapi.json"),
        help="Output path; defaults to the monorepo contracts package",
    )
    parser.add_argument("--check", action="store_true", help="Fail if the output differs")
    args = parser.parse_args()
    rendered = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.exists() or args.output.read_text() != rendered:
            raise SystemExit("OpenAPI contract is out of date")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered)


if __name__ == "__main__":
    main()
