"""Lint git-changed Python files (staged + unstaged + untracked) with ruff and pyright."""
import os
import subprocess
import sys


def repo_root() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def changed_files() -> list[str]:
    def lines(cmd: list[str]) -> list[str]:
        return subprocess.run(cmd, capture_output=True, text=True).stdout.splitlines()

    staged    = lines(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "--", "*.py"])
    unstaged  = lines(["git", "diff",             "--name-only", "--diff-filter=ACMR", "--", "*.py"])
    untracked = lines(["git", "ls-files", "--others", "--exclude-standard", "--", "*.py"])

    seen: set[str] = set()
    result: list[str] = []
    for f in staged + unstaged + untracked:
        if f and f not in seen and os.path.isfile(f):
            seen.add(f)
            result.append(f)
    return result


def main() -> None:
    os.chdir(repo_root())

    files = changed_files()
    if not files:
        print("No changed Python files to lint.")
        sys.exit(0)

    print(f"Linting {len(files)} changed Python file(s):")
    for f in files:
        print(f"  {f}")
    print()

    rc_ruff = subprocess.run(["ruff", "check"] + files).returncode
    print()
    rc_pyright = subprocess.run(["pyright"] + files).returncode

    sys.exit(0 if rc_ruff == 0 and rc_pyright == 0 else 1)


if __name__ == "__main__":
    main()
