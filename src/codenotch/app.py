#!/usr/bin/env python3
"""codenotch-kde - tiny always-on-top overlay showing Claude Code usage limits.

Reads the local Claude Code OAuth token (~/.claude/.credentials.json) and polls
the same endpoint `/usage` uses. Session state (working / waiting / idle) comes
from a state file written by the companion hook (see: codenotch --install-hooks).
"""
import sys
import os
import json
import time
import math
import shutil
import subprocess
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone

__version__ = "0.1.3"  # dev fallback; the installed VERSION file wins
try:
    _vf = Path(__file__).with_name("VERSION")
    if _vf.is_file():
        __version__ = _vf.read_text().strip() or __version__
except Exception:
    pass

HOME = Path.home()
CREDS = HOME / ".claude" / ".credentials.json"
STATE_DIR = HOME / ".claude" / "codenotch"
PROJECTS = HOME / ".claude" / "projects"
CFG_PATH = HOME / ".config" / "codenotch" / "config.json"
SETTINGS = HOME / ".claude" / "settings.json"

DEFAULTS = {
    "edge": "top",          # top | bottom
    "align": "center",      # left | center | right
    "margin_x": 0,
    "margin_y": 4,
    "poll_seconds": 60,
    "endpoint": "https://api.anthropic.com/api/oauth/usage",
    "opacity": 0.94,
    "scale": 1.3,
    "autohide": True,
    "peek": 5,
    "reveal_ms": 130,
    "hide_delay_ms": 700,
}

HOOK_EVENTS = ["UserPromptSubmit", "PreToolUse", "PostToolUse",
               "Stop", "SubagentStop", "Notification",
               "SessionStart", "SessionEnd"]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def load_cfg():
    cfg = dict(DEFAULTS)
    try:
        user = json.loads(CFG_PATH.read_text())
        if isinstance(user, dict):
            cfg.update(user)
    except Exception:
        pass
    return _coerce_cfg(cfg)


def _coerce_cfg(cfg):
    """Force every field to a sane type/range so a hand-edited config file
    can't crash startup or push the window off-screen."""
    def num(key, lo, hi, cast=float):
        try:
            v = cast(cfg.get(key, DEFAULTS[key]))
        except (TypeError, ValueError):
            v = cast(DEFAULTS[key])
        return max(lo, min(hi, v))

    cfg["scale"] = num("scale", 0.5, 4.0)
    cfg["opacity"] = num("opacity", 0.2, 1.0)
    cfg["poll_seconds"] = num("poll_seconds", 15, 3600, int)
    cfg["margin_x"] = num("margin_x", -4000, 4000, int)
    cfg["margin_y"] = num("margin_y", 0, 4000, int)
    cfg["peek"] = num("peek", 2, 80, int)
    cfg["reveal_ms"] = num("reveal_ms", 0, 4000, int)
    cfg["hide_delay_ms"] = num("hide_delay_ms", 0, 20000, int)
    if cfg.get("edge") not in ("top", "bottom"):
        cfg["edge"] = "top"
    if cfg.get("align") not in ("left", "center", "right"):
        cfg["align"] = "center"
    if not isinstance(cfg.get("autohide"), bool):
        cfg["autohide"] = bool(DEFAULTS["autohide"])
    if not isinstance(cfg.get("endpoint"), str):
        cfg["endpoint"] = DEFAULTS["endpoint"]
    return cfg


def human_delta(secs):
    secs = max(0, int(secs))
    h, rem = divmod(secs, 3600)
    m = rem // 60
    if h >= 1:
        return f"{h}h{m:02d}m"
    if m >= 1:
        return f"{m}m"
    return f"{secs}s"


def parse_iso(s):
    if not s:
        return None
    if isinstance(s, (int, float)):
        try:
            return datetime.fromtimestamp(float(s), tz=timezone.utc)
        except Exception:
            return None
    try:
        t = s[:-1] + "+00:00" if s.endswith("Z") else s
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# usage endpoint
# --------------------------------------------------------------------------- #
class UsageError(Exception):
    pass


def load_token():
    d = json.loads(CREDS.read_text())
    o = d.get("claudeAiOauth", d)
    return (o.get("accessToken"), int(o.get("expiresAt", 0) or 0),
            o.get("subscriptionType"), o.get("rateLimitTier"))


# The OAuth bearer token must only ever leave this machine towards Anthropic.
ALLOWED_HOSTS = ("api.anthropic.com",)


def _check_endpoint(url):
    """Return the validated URL or raise. Guards the bearer token against a
    tampered config file pointing `endpoint` at an attacker (or at plain http)."""
    try:
        u = urllib.parse.urlsplit(url)
    except Exception:
        raise UsageError("endpoint inválido")
    host = (u.hostname or "").lower()
    ok_host = host in ALLOWED_HOSTS or host.endswith(".anthropic.com")
    if u.scheme != "https" or not ok_host:
        raise UsageError("endpoint no permitido")
    return url


class _SameHostRedirect(urllib.request.HTTPRedirectHandler):
    """Follow redirects only within the same host; never carry the token off-site."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old = urllib.parse.urlsplit(req.full_url).hostname
        new = urllib.parse.urlsplit(newurl).hostname
        if new != old or not str(newurl).startswith("https://"):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_SameHostRedirect())


def fetch_usage(cfg):
    url = _check_endpoint(cfg.get("endpoint") or DEFAULTS["endpoint"])
    tok, exp, sub, tier = load_token()
    if not tok:
        raise UsageError("sin token")
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {tok}",
        "anthropic-beta": "oauth-2025-04-20",
        "anthropic-version": "2023-06-01",
        "User-Agent": f"codenotch-kde/{__version__} (KDE; X11)",
        "Accept": "application/json",
    })
    try:
        with _OPENER.open(req, timeout=15) as r:
            if urllib.parse.urlsplit(r.geturl()).hostname not in ALLOWED_HOSTS \
                    and not str(r.geturl()).startswith("https://api.anthropic.com"):
                raise UsageError("redirección rechazada")
            return json.loads(r.read(2_000_000).decode("utf-8")), sub, tier
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise UsageError("auth (abrí Claude Code)")
        raise UsageError(f"HTTP {e.code}")
    except urllib.error.URLError:
        raise UsageError("sin red")
    except UsageError:
        raise
    except Exception as e:  # noqa: BLE001
        raise UsageError(str(e)[:40])


LABEL_HINTS = [
    (("opus",), "opus"),
    (("five", "5_hour", "5hour", "5-hour", "5 hour", "fivehour", "five_hour",
      "session", "current", "rolling", "hour"), "5h"),
    (("seven", "7_day", "7day", "7-day", "7 day", "week", "weekly", "day"), "7d"),
]


def _label_for(key):
    k = str(key).lower()
    for needles, lab in LABEL_HINTS:
        if any(n in k for n in needles):
            return lab
    return str(key)[:6]


def _clamp_pct(v):
    """Value is already a 0..100 percentage; just sanitise it."""
    try:
        return max(0.0, min(100.0, float(v)))
    except Exception:
        return None


def _as_pct(v):
    """Heuristic for the fallback walk: accept a 0..1 fraction or a 0..100 value."""
    try:
        v = float(v)
    except Exception:
        return None
    if v <= 1.5:
        v *= 100.0
    return max(0.0, min(100.0, v))


# api `limits[].kind` / `.group` -> short label
KIND_LABEL = {
    "session": "5h", "five_hour": "5h",
    "weekly_all": "7d", "weekly": "7d", "seven_day": "7d",
    "weekly_opus": "opus", "opus": "opus",
    "weekly_sonnet": "sonnet", "sonnet": "sonnet",
    "weekly_cowork": "cowork",
}
# top-level buckets worth showing if `limits[]` is absent
KNOWN_KEYS = {
    "five_hour": "5h", "seven_day": "7d",
    "seven_day_opus": "opus", "seven_day_sonnet": "sonnet",
}
_ORDER = {"5h": 0, "7d": 1, "opus": 2, "sonnet": 3, "cowork": 4}


def _finish(meters):
    seen = {}
    for m in meters:
        if m and m.get("pct") is not None:
            seen.setdefault(m["label"], m)
    return sorted(seen.values(), key=lambda m: _ORDER.get(m["label"], 9))[:4]


def extract_meters(data):
    """Pull {label, pct, resets_at} meters out of the /usage response.

    Preference order: the explicit ``limits[]`` array, then known top-level
    buckets, then a generic heuristic walk for shapes we don't recognise.
    """
    if not isinstance(data, dict):
        data = {"_": data}

    # 1) explicit limits[] array (current API shape)
    lims = data.get("limits")
    if isinstance(lims, list) and lims:
        meters = []
        for it in lims:
            if not isinstance(it, dict):
                continue
            pct = _clamp_pct(it.get("percent", it.get("utilization")))
            if pct is None:
                continue
            key = str(it.get("kind") or it.get("group") or "").lower()
            meters.append({
                "label": KIND_LABEL.get(key) or _label_for(key or "uso"),
                "pct": pct,
                "resets_at": it.get("resets_at") or it.get("resetsAt"),
            })
        done = _finish(meters)
        if done:
            return done

    # 2) known named buckets
    meters = []
    for k, lab in KNOWN_KEYS.items():
        node = data.get(k)
        if isinstance(node, dict) and node.get("utilization") is not None:
            pct = _clamp_pct(node["utilization"])
            if pct is not None:
                meters.append({"label": lab, "pct": pct,
                               "resets_at": node.get("resets_at")})
    done = _finish(meters)
    if done:
        return done

    # 3) generic heuristic walk (unknown shape)
    out = []

    def visit(key, node):
        if isinstance(node, dict):
            pct = None
            for pk in ("utilization", "percent_used", "percentUsed", "used_pct",
                       "usage_pct", "usagePct", "percent", "usage", "used"):
                if pk in node and isinstance(node[pk], (int, float, str)):
                    pct = _as_pct(node[pk])
                    if pct is not None:
                        break
            resets = None
            for rk in ("resets_at", "resetsAt", "reset_at", "resetAt",
                       "next_reset", "nextReset", "expires_at", "expiresAt"):
                if rk in node:
                    resets = node[rk]
                    break
            if pct is not None:
                inner = None
                for nk in ("name", "label", "type", "title", "kind"):
                    if isinstance(node.get(nk), str):
                        inner = node[nk]
                        break
                out.append({"label": _label_for(inner or key or "uso"),
                            "pct": pct, "resets_at": resets})
            for k, v in node.items():
                if isinstance(v, (dict, list)):
                    visit(k, v)

    visit("", data)
    return _finish(out)


# --------------------------------------------------------------------------- #
# session activity
# --------------------------------------------------------------------------- #
PRIO = {"waiting": 3, "working": 2, "idle": 1, "none": 0}


def read_activity():
    now = time.time()
    best = None
    try:
        files = list(STATE_DIR.glob("*.json"))
    except Exception:
        files = []
    for p in files:
        try:
            s = json.loads(p.read_text())
        except Exception:
            continue
        if now - float(s.get("ts", 0)) > 3600:
            continue
        if best is None or PRIO.get(s.get("state"), 0) > PRIO.get(best.get("state"), 0):
            best = s
    if best:
        best["src"] = "hook"
        return best
    newest = 0.0
    try:
        for p in PROJECTS.glob("*/*.jsonl"):
            m = p.stat().st_mtime
            if m > newest:
                newest = m
    except Exception:
        pass
    if newest and now - newest < 8:
        return {"state": "working", "src": "mtime"}
    if newest and now - newest < 3600:
        return {"state": "idle", "src": "mtime"}
    return {"state": "none", "src": "none"}


# --------------------------------------------------------------------------- #
# hook install / uninstall
# --------------------------------------------------------------------------- #
def _load_settings():
    if SETTINGS.exists():
        return json.loads(SETTINGS.read_text())
    return {}


def install_hooks():
    data = _load_settings()
    if SETTINGS.exists():
        bak = SETTINGS.with_name("settings.json.codenotch-bak")
        if not bak.exists():
            bak.write_text(SETTINGS.read_text())
    hooks = data.setdefault("hooks", {})
    entry = {"type": "command", "command": "codenotch-hook"}
    for ev in HOOK_EVENTS:
        arr = hooks.setdefault(ev, [])
        grp = next((g for g in arr if g.get("matcher", "") == ""), None)
        if grp is None:
            grp = {"matcher": "", "hooks": []}
            arr.append(grp)
        if not any(h.get("command") == "codenotch-hook" for h in grp.get("hooks", [])):
            grp.setdefault("hooks", []).append(dict(entry))
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(data, indent=2))
    print(f"Hooks instalados en {SETTINGS}")
    if (SETTINGS.with_name('settings.json.codenotch-bak')).exists():
        print(f"Backup: {SETTINGS.with_name('settings.json.codenotch-bak')}")
    print("Abrí una nueva sesión de Claude Code para que los tome.")


def uninstall_hooks():
    if not SETTINGS.exists():
        print("No hay settings.json")
        return
    data = _load_settings()
    hooks = data.get("hooks", {})
    for ev in list(hooks.keys()):
        arr = hooks.get(ev, [])
        for grp in arr:
            grp["hooks"] = [h for h in grp.get("hooks", [])
                            if h.get("command") != "codenotch-hook"]
        arr = [g for g in arr if g.get("hooks")]
        if arr:
            hooks[ev] = arr
        else:
            hooks.pop(ev, None)
    if not hooks:
        data.pop("hooks", None)
    SETTINGS.write_text(json.dumps(data, indent=2))
    print("Hooks de codenotch quitados de settings.json")


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #
def run_gui(cfg):
    from PyQt6 import QtCore, QtGui, QtWidgets
    Qt = QtCore.Qt

    COL = {
        "bg": QtGui.QColor(18, 18, 20, 236),
        "text": QtGui.QColor(232, 232, 236),
        "dim": QtGui.QColor(152, 152, 160),
        "track": QtGui.QColor(255, 255, 255, 38),
        "ok": QtGui.QColor(90, 200, 120),
        "warn": QtGui.QColor(232, 184, 82),
        "crit": QtGui.QColor(232, 92, 92),
        "working": QtGui.QColor(92, 162, 240),
        "waiting": QtGui.QColor(236, 172, 72),
        "idle": QtGui.QColor(90, 200, 120),
        "none": QtGui.QColor(122, 122, 130),
    }

    def meter_color(pct):
        if pct >= 80:
            return COL["crit"]
        if pct >= 50:
            return COL["warn"]
        return COL["ok"]

    STATE_ES = {"working": "trabajando", "waiting": "esperándote",
                "idle": "libre", "none": "sin sesión"}

    class Notch(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.cfg = cfg
            self.s = float(cfg.get("scale", 1.0))
            self.meters = []
            self.sub = None
            self.tier = None
            self.err = None
            self.raw = None
            self.activity = {"state": "none"}
            self.phase = 0.0
            self._hinted = False
            self._autohide = bool(cfg.get("autohide", True))
            self._revealed = not self._autohide
            self._hovering = False
            self._menu_open = False
            self.peek = max(2, int(cfg.get("peek", 5)))
            self._geo_anim = None
            self._leave_timer = QtCore.QTimer(self)
            self._leave_timer.setSingleShot(True)
            self._leave_timer.timeout.connect(self._maybe_hide)

            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.Tool
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.WindowDoesNotAcceptFocus
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            self.setWindowOpacity(float(cfg.get("opacity", 0.93)))
            self.setWindowTitle("codenotch")

            self.h = int(30 * self.s)
            self.pad = int(13 * self.s)
            self.f_main = QtGui.QFont()
            self.f_main.setPointSizeF(10.0 * self.s)
            self.f_main.setWeight(QtGui.QFont.Weight.Medium)
            self.f_small = QtGui.QFont()
            self.f_small.setPointSizeF(8.4 * self.s)

            self.t_poll = QtCore.QTimer(self)
            self.t_poll.timeout.connect(self.refresh_usage)
            self.t_poll.start(max(15, int(cfg.get("poll_seconds", 60))) * 1000)
            self.t_tick = QtCore.QTimer(self)
            self.t_tick.timeout.connect(self.refresh_activity)
            self.t_tick.start(1000)
            self.t_anim = QtCore.QTimer(self)
            self.t_anim.timeout.connect(self._animate)
            self.t_anim.start(50)

            self.refresh_activity()
            self._apply_geo(animate=False)
            QtCore.QTimer.singleShot(0, self.refresh_usage)
            if self._autohide:
                # peek once on startup so it's discoverable, then tuck away
                QtCore.QTimer.singleShot(500, lambda: self._set_revealed(True))
                QtCore.QTimer.singleShot(3600, self._maybe_hide)

        # ---- data ----
        def refresh_usage(self):
            try:
                data, sub, tier = fetch_usage(self.cfg)
                self.raw = data
                self.meters = extract_meters(data)
                self.sub, self.tier = sub, tier
                self.err = None if self.meters else "sin datos de uso"
            except UsageError as e:
                self.err = str(e)
            except Exception as e:  # noqa: BLE001
                self.err = str(e)[:40]
            self._apply_geo(animate=False)
            self._update_tooltip()
            self.update()

        def refresh_activity(self):
            self.activity = read_activity()
            self._update_tooltip()
            if self._autohide:
                st = self.activity.get("state")
                if st == "waiting" and not self._revealed:
                    self._set_revealed(True)
                elif st != "waiting" and self._revealed and not self._hovering \
                        and not self._menu_open and not self._leave_timer.isActive():
                    self._leave_timer.start(int(self.cfg.get("hide_delay_ms", 700)))
                elif not self._revealed and not self._hovering:
                    self._check_hover_zone()
            self.update()

        def _check_hover_zone(self):
            """Fast mouse moves can skip enterEvent on the thin strip; poll a band."""
            try:
                c = QtGui.QCursor.pos()
            except Exception:
                return
            g = self.geometry()
            band = self.h + int(10 * self.s)
            if self.cfg.get("edge", "top") == "bottom":
                zone = QtCore.QRect(g.x(), g.bottom() - band, g.width(), band)
            else:
                zone = QtCore.QRect(g.x(), g.y(), g.width(), band)
            if zone.contains(c):
                self._set_revealed(True)

        def _animate(self):
            if self.activity.get("state") in ("working", "waiting"):
                self.phase = (self.phase + 0.09) % (2 * math.pi)
                self.update()

        # ---- geometry ----
        def _calc_width(self):
            s = self.s
            w = self.pad + int(16 * s)                       # status dot
            if self.err and not self.meters:
                w += int(150 * s)
            else:
                w += int(96 * s) * max(1, len(self.meters))  # meters
                w += int(74 * s)                             # reset countdown
            return max(int(150 * s), w + self.pad)

        def _target_geo(self):
            scr = self.screen() or QtWidgets.QApplication.primaryScreen()
            g = scr.availableGeometry()
            w = self._calc_width()
            h = self.h if self._revealed else self.peek
            align = self.cfg.get("align", "center")
            mx = int(self.cfg.get("margin_x", 0))
            if align == "left":
                x = g.left() + 8 + mx
            elif align == "right":
                x = g.right() - w - 8 - mx
            else:
                x = g.left() + (g.width() - w) // 2 + mx
            my = int(self.cfg.get("margin_y", 4))
            if self.cfg.get("edge", "top") == "bottom":
                y = g.bottom() - h - my
            else:
                y = g.top() + my
            return QtCore.QRect(int(x), int(y), int(w), int(h))

        def _apply_geo(self, animate=True):
            target = self._target_geo()
            if self._geo_anim is not None:
                self._geo_anim.stop()
                self._geo_anim = None
            if animate and self.isVisible() and self.geometry() != target:
                a = QtCore.QPropertyAnimation(self, b"geometry", self)
                a.setDuration(int(self.cfg.get("reveal_ms", 130)))
                a.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
                a.setStartValue(self.geometry())
                a.setEndValue(target)
                a.start()
                self._geo_anim = a
            else:
                self.setGeometry(target)

        # kept for callers that just want a static re-place
        def reposition(self):
            self._apply_geo(animate=False)

        def _set_revealed(self, val):
            if val == self._revealed:
                return
            self._revealed = val
            self._apply_geo(animate=True)
            self.update()

        def _maybe_hide(self):
            if not self._autohide or self._hovering or self._menu_open:
                return
            if self.activity.get("state") == "waiting":
                return
            self._set_revealed(False)

        def enterEvent(self, ev):
            self._hovering = True
            self._leave_timer.stop()
            if self._autohide and not self._revealed:
                self._set_revealed(True)
            super().enterEvent(ev)

        def leaveEvent(self, ev):
            self._hovering = False
            if self._autohide:
                self._leave_timer.start(int(self.cfg.get("hide_delay_ms", 700)))
            super().leaveEvent(ev)

        def showEvent(self, ev):
            super().showEvent(ev)
            if not self._hinted:
                self._hinted = True
                QtCore.QTimer.singleShot(80, self._x11_hints)

        def _x11_hints(self):
            xprop = shutil.which("xprop")
            if not xprop or QtWidgets.QApplication.platformName() != "xcb":
                return
            wid = str(int(self.winId()))
            for args in (
                ["-f", "_NET_WM_WINDOW_TYPE", "32a", "-set",
                 "_NET_WM_WINDOW_TYPE", "_NET_WM_WINDOW_TYPE_DOCK"],
                ["-f", "_NET_WM_STATE", "32a", "-set", "_NET_WM_STATE",
                 "_NET_WM_STATE_STICKY,_NET_WM_STATE_ABOVE,"
                 "_NET_WM_STATE_SKIP_TASKBAR,_NET_WM_STATE_SKIP_PAGER"],
                ["-f", "_NET_WM_DESKTOP", "32c", "-set", "_NET_WM_DESKTOP",
                 "0xFFFFFFFF"],
            ):
                try:
                    subprocess.run([xprop, "-id", wid] + args,
                                   timeout=3, capture_output=True)
                except Exception:
                    pass
            self.hide()
            self.show()
            self.reposition()

        # ---- interaction ----
        def mousePressEvent(self, ev):
            if ev.button() == Qt.MouseButton.RightButton:
                self._menu_open = True
                self._leave_timer.stop()
                m = QtWidgets.QMenu(self)
                m.addAction("Refrescar ahora", self.refresh_usage)
                ah = m.addAction("Auto-ocultar")
                ah.setCheckable(True)
                ah.setChecked(self._autohide)
                ah.triggered.connect(self._toggle_autohide)
                edge = m.addAction("Cambiar borde (arriba/abajo)")
                edge.triggered.connect(self._toggle_edge)
                m.addAction("Editar configuración",
                            lambda: subprocess.Popen(["xdg-open", str(CFG_PATH)]))
                m.addSeparator()
                m.addAction("Salir", QtWidgets.QApplication.quit)
                m.exec(ev.globalPosition().toPoint())
                self._menu_open = False
                if self._autohide and not self._hovering:
                    self._leave_timer.start(int(self.cfg.get("hide_delay_ms", 700)))
            elif ev.button() == Qt.MouseButton.LeftButton:
                QtWidgets.QToolTip.showText(ev.globalPosition().toPoint(),
                                            self.toolTip(), self)

        def _persist(self, **kv):
            try:
                CFG_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                cur = {}
                if CFG_PATH.exists():
                    loaded = json.loads(CFG_PATH.read_text())
                    if isinstance(loaded, dict):
                        cur = loaded
                cur.update(kv)
                tmp = CFG_PATH.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(cur, indent=2))
                tmp.chmod(0o600)
                tmp.replace(CFG_PATH)
            except Exception:
                pass

        def _toggle_autohide(self):
            self._autohide = not self._autohide
            self.cfg["autohide"] = self._autohide
            self._persist(autohide=self._autohide)
            self._set_revealed(True if not self._autohide else False)

        def _toggle_edge(self):
            self.cfg["edge"] = "bottom" if self.cfg.get("edge") == "top" else "top"
            self._persist(edge=self.cfg["edge"])
            self._apply_geo(animate=False)

        def _update_tooltip(self):
            lines = []
            if self.sub:
                lines.append(f"Plan: {self.sub}"
                             + (f"  ·  tier {self.tier}" if self.tier else ""))
            for mt in self.meters:
                t = f"{mt['label']}: {mt['pct']:.1f}%"
                dt = parse_iso(mt.get("resets_at"))
                if dt:
                    secs = (dt - datetime.now(timezone.utc)).total_seconds()
                    t += f"  ·  reset en {human_delta(secs)}"
                lines.append(t)
            a = self.activity
            lines.append("Sesión: " + STATE_ES.get(a.get("state"), "?")
                         + (f"  [{a.get('src')}]" if a.get("src") else ""))
            if self.err:
                lines.append(f"aviso: {self.err}")
            if not self.meters and self.raw:
                lines.append("claves: " + ", ".join(list(self.raw.keys())[:8]))
            self.setToolTip("\n".join(lines))

        # ---- paint ----
        def paintEvent(self, ev):
            s = self.s
            p = QtGui.QPainter(self)
            p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

            # collapsed: just a slim accent sliver hinting the hidden bar
            if self.height() <= self.peek + 1:
                st = self.activity.get("state", "none")
                c = QtGui.QColor(COL.get(st, COL["none"]))
                if st == "waiting":
                    c.setAlphaF(0.45 + 0.55 * (0.5 + 0.5 * math.sin(self.phase)))
                lw = min(self.width() * 0.5, 120 * s)
                x0 = (self.width() - lw) / 2.0
                hh = max(2.0, self.height() - 2.0)
                yy = 0.0 if self.cfg.get("edge", "top") != "bottom" else 2.0
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(c)
                p.drawRoundedRect(QtCore.QRectF(x0, yy, lw, hh), hh / 2, hh / 2)
                return

            rect = QtCore.QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
            rad = self.height() / 2.0
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(COL["bg"])
            p.drawRoundedRect(rect, rad, rad)

            x = float(self.pad)
            cy = self.height() / 2.0
            st = self.activity.get("state", "none")
            dot = QtGui.QColor(COL.get(st, COL["none"]))
            dr = 5.0 * s
            if st == "waiting":
                dot.setAlphaF(0.4 + 0.6 * (0.5 + 0.5 * math.sin(self.phase)))
            p.setBrush(dot)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QtCore.QPointF(x + dr, cy), dr, dr)
            if st == "working":
                pen = QtGui.QPen(COL["working"], 1.6 * s)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                rr = dr + 3.0 * s
                start = int(-self.phase * 180 / math.pi * 16)
                p.drawArc(QtCore.QRectF(x + dr - rr, cy - rr, 2 * rr, 2 * rr),
                          start, 90 * 16)
            x += 2 * dr + 9 * s

            if self.err and not self.meters:
                p.setFont(self.f_main)
                p.setPen(COL["dim"])
                p.drawText(QtCore.QRectF(x, 0, self.width() - x - self.pad, self.height()),
                           int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                           f"Claude · {self.err}")
                return

            soonest = None
            for mt in self.meters:
                x = self._meter(p, x, cy, mt)
                dt = parse_iso(mt.get("resets_at"))
                if dt and (soonest is None or dt < soonest):
                    soonest = dt

            if soonest:
                secs = (soonest - datetime.now(timezone.utc)).total_seconds()
                p.setFont(self.f_main)
                p.setPen(COL["dim"])
                p.drawText(QtCore.QRectF(x, 0, self.width() - x - self.pad, self.height()),
                           int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                           "⟳ " + human_delta(secs))

        def _meter(self, p, x, cy, mt):
            s = self.s
            p.setFont(self.f_small)
            p.setPen(COL["dim"])
            p.drawText(QtCore.QRectF(x, 0, 20 * s, self.height()),
                       int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                       mt["label"])
            x += 21 * s
            tw, th = 40 * s, 6 * s
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(COL["track"])
            p.drawRoundedRect(QtCore.QRectF(x, cy - th / 2, tw, th), th / 2, th / 2)
            fw = tw * mt["pct"] / 100.0
            if fw > 0:
                p.setBrush(meter_color(mt["pct"]))
                p.drawRoundedRect(QtCore.QRectF(x, cy - th / 2, max(th, fw), th),
                                  th / 2, th / 2)
            x += tw + 5 * s
            p.setFont(self.f_small)
            p.setPen(COL["text"])
            p.drawText(QtCore.QRectF(x, 0, 30 * s, self.height()),
                       int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                       f"{round(mt['pct'])}%")
            return x + 34 * s

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("codenotch")
    app.setQuitOnLastWindowClosed(False)
    w = Notch()
    w.show()
    return app.exec()


# --------------------------------------------------------------------------- #
def main():
    args = sys.argv[1:]
    if args and args[0] in ("--dump", "dump"):
        try:
            data, sub, tier = fetch_usage(load_cfg())
        except Exception as e:  # noqa: BLE001
            print("error:", e)
            return 1
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print("\n---- meters detectados ----")
        print(json.dumps(extract_meters(data), indent=2, ensure_ascii=False))
        print(f"\nplan={sub} tier={tier}")
        return 0
    if args and args[0] == "--install-hooks":
        install_hooks()
        return 0
    if args and args[0] == "--uninstall-hooks":
        uninstall_hooks()
        return 0
    if args and args[0] in ("-V", "--version"):
        print(f"codenotch {__version__}")
        return 0
    if args and args[0] in ("-h", "--help"):
        print("codenotch [--dump | --install-hooks | --uninstall-hooks | --version]")
        return 0
    return run_gui(load_cfg())


if __name__ == "__main__":
    sys.exit(main())
