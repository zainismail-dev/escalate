"""Playbook validator CLI (full checks arrive in task 1.5)."""

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    root = Path(args[0] if args else "playbooks")
    files = sorted(root.rglob("*.yaml"))
    print(f"{len(files)} playbook file(s) found under {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
