#!/usr/bin/env python3
"""codenotch hook - writes ~/.claude/codenotch/<session>.json on Claude Code events.

Registered by `codenotch --install-hooks`. Always exits 0 so it can never block
or slow down a Claude Code session.
"""
import sys
import re
import os
import json
import time
from pathlib import Path

STATE_DIR = Path.home() / ".claude" / "codenotch"

# session_id becomes a filename -> only a strict, separator-free charset.
_SID_RE = re.compile(r"\A[A-Za-z0-9._-]{1,128}\Z")

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
        if not isinstance(ev, dict):
            ev = {}
    except Exception:
        ev = {}

    name = str(ev.get("hook_event_name") or ev.get("hookEventName") or "")
    sid = str(ev.get("session_id") or ev.get("sessionId") or "default")
    if sid in (".", "..") or not _SID_RE.match(sid):
        sid = "default"
    state = MAP.get(name, "working")

    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            STATE_DIR.chmod(0o700)
        except OSError:
            pass

        base = STATE_DIR.resolve()
        target = (base / (sid + ".json")).resolve()
        if target.parent != base:          # never touch anything outside STATE_DIR
            return

        if state == "end":
            try:
                target.unlink()
            except FileNotFoundError:
                pass
            return

        rec = {
            "state": state,
            "ts": time.time(),
            "session_id": sid,
            "cwd": str(ev.get("cwd", ""))[:4096],
            "event": name[:64],
        }
        tmp = base / (sid + ".json.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, json.dumps(rec).encode("utf-8"))
        finally:
            os.close(fd)
        os.replace(tmp, target)
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
