#!/usr/bin/env python3
"""codenotch hook - writes ~/.claude/codenotch/<session>.json on Claude Code events.

Registered by `codenotch --install-hooks`. Always exits 0 so it can never block
or slow down a Claude Code session.
"""
import sys
import json
import time
from pathlib import Path

STATE_DIR = Path.home() / ".claude" / "codenotch"

MAP = {
    "UserPromptSubmit": "working",
    "PreToolUse": "working",
    "PostToolUse": "working",
    "Stop": "idle",
    "SubagentStop": "idle",
    "SessionStart": "idle",
    "Notification": "waiting",
    "SessionEnd": "end",
}


def main():
    try:
        raw = sys.stdin.read() or "{}"
    except Exception:
        raw = "{}"
    try:
        ev = json.loads(raw)
    except Exception:
        ev = {}

    name = ev.get("hook_event_name") or ev.get("hookEventName") or ""
    sid = ev.get("session_id") or ev.get("sessionId") or "default"
    state = MAP.get(name, "working")

    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        target = STATE_DIR / f"{sid}.json"
        if state == "end":
            target.unlink(missing_ok=True)
            return
        rec = {
            "state": state,
            "ts": time.time(),
            "session_id": sid,
            "cwd": ev.get("cwd", ""),
            "event": name,
        }
        if name == "Notification":
            rec["message"] = ev.get("message", "")
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec))
        tmp.replace(target)
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
