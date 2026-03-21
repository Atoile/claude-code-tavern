"""
PreToolUse hook: enforce TAVERN_MODE=run write restrictions.
Reads stdin JSON from Claude Code hook, checks env config, and outputs
a deny decision if the target file is outside permitted paths.
"""
import json
import sys
import os


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    file_path = data.get("tool_input", {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    # Determine env file (prefer .env.local, fall back to .env.example)
    if os.path.exists(".env.local"):
        env_file = ".env.local"
    elif os.path.exists(".env.example"):
        env_file = ".env.example"
    else:
        sys.exit(0)

    # Parse TAVERN_MODE
    mode = "dev"
    try:
        with open(env_file) as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("TAVERN_MODE="):
                    mode = stripped.split("=", 1)[1].strip()
                    break
    except Exception:
        sys.exit(0)

    if mode != "run":
        sys.exit(0)

    # Normalize to forward slashes
    fp = file_path.replace("\\", "/")
    cwd = os.getcwd().replace("\\", "/").rstrip("/")

    # Convert to relative path
    if fp.startswith(cwd + "/"):
        rel = fp[len(cwd) + 1:]
    elif fp.startswith(cwd):
        rel = fp[len(cwd):].lstrip("/")
    else:
        rel = fp.lstrip("/")

    # Check permitted paths
    allowed = (
        rel.startswith("infrastructure/characters/")
        or rel.startswith("infrastructure/dialogues/")
        or rel == "infrastructure/queue/queue.json"
    )

    if not allowed:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f'TAVERN_MODE=run — write to "{rel}" is not permitted. Queue stopped.'
                ),
            }
        }))


if __name__ == "__main__":
    main()
