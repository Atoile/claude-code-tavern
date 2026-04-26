"""Lint all tracked Python files with ruff and pyright."""
import os
import subprocess
import sys


def repo_root() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def main() -> None:
    os.chdir(repo_root())

    files = subprocess.run(
        ["git", "ls-files", "--", "*.py"],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()

    if not files:
        print("No tracked Python files found.")
        sys.exit(0)

    print(f"Linting {len(files)} tracked Python file(s)...\n")

    rc_ruff = subprocess.run(["ruff", "check"] + files).returncode
    print()
    rc_pyright = subprocess.run(["pyright"] + files).returncode

    sys.exit(0 if rc_ruff == 0 and rc_pyright == 0 else 1)


if __name__ == "__main__":
    main()
