# codenotch-kde

Tiny always-on-top overlay for **KDE Plasma on X11** showing Claude Code usage
limits and session state. A Linux / `.deb` take on macOS
[`vinzdg/codenotch`](https://github.com/vinzdg/codenotch) (not affiliated).

```
●  5h ▓▓▓▓░░ 42%   7d ▓░░░░░ 13%   ⟳ 1h20m
```

- **dot** — session state: green = libre, blue spinner = trabajando,
  amber pulse = esperándote, grey = sin sesión
- **5h / 7d / opus** — utilisation of each Claude limit window
- **⟳** — time until the soonest window resets
- left-click = tooltip with exact numbers + plan; right-click = menu
  (refrescar, auto-ocultar, cambiar borde, editar config, salir)
- **auto-hide**: collapses to a thin accent sliver at the screen edge, reveals
  on hover; stays visible while a session is waiting on you

## Data sources

| what | where |
|---|---|
| OAuth token | `~/.claude/.credentials.json` — no keychain on Linux |
| usage numbers | `GET https://api.anthropic.com/api/oauth/usage` (same call as `/usage`) |
| session state | `~/.claude/codenotch/<session>.json`, written by `codenotch-hook` |

The endpoint is **unofficial** and may change; see
[`docs/usage-endpoint.md`](docs/usage-endpoint.md). `codenotch --dump` prints the
raw response and the meters detected.

## Install (from a release `.deb`)

```sh
sudo apt install ./codenotch_<version>_all.deb   # pulls python3-pyqt6, x11-utils
systemctl --user daemon-reload
systemctl --user enable --now codenotch.service
codenotch --install-hooks                        # optional: live session dot
```

`--install-hooks` merges command hooks into `~/.claude/settings.json`
(backup: `settings.json.codenotch-bak`); undo with `codenotch --uninstall-hooks`.

## Build from source

```sh
make deb            # -> dist/codenotch_<version>_all.deb
make run            # run from src/ without installing (dev)
make dump           # inspect the /usage response
make install-local  # copy src+packaging into /usr (sudo), no packaging round-trip
make lint
```

Requires `dpkg-dev`; runtime needs `python3-pyqt6`, `x11-utils`.

## Layout

```
src/codenotch/       app.py (overlay) + hook.py (Claude Code hook)
packaging/           debian/ (control.in, maintainer scripts), bin/, systemd/, applications/
build-deb.sh         assembles a staging tree from src/ + packaging/ + VERSION
VERSION              single source of truth for the version
docs/                usage-endpoint.md
```

Install mapping (`.deb` and `make install-local` agree):

| repo | system |
|---|---|
| `src/codenotch/*.py` | `/usr/lib/codenotch/` |
| `packaging/bin/*` | `/usr/bin/` |
| `packaging/systemd/*` | `/usr/lib/systemd/user/` |
| `packaging/applications/*` | `/usr/share/applications/` |

## Config — `~/.config/codenotch/config.json`

```json
{
  "edge": "top",
  "align": "center",
  "scale": 1.3,
  "opacity": 0.94,
  "poll_seconds": 60,
  "margin_x": 0,
  "margin_y": 4,
  "autohide": true,
  "peek": 5,
  "reveal_ms": 130,
  "hide_delay_ms": 700
}
```

- `scale` — overall size multiplier (fonts + bar). Bump for readability.
- `autohide` / `peek` / `hide_delay_ms` — the reveal-on-hover behaviour.
- `edge` / `align` — which screen edge and where along it.

## Notes / limits

- **X11 only.** On Wayland the DOCK/sticky hints (set via `xprop`) are skipped;
  the bar still shows but behaves like a normal tool window.
- Token refresh is left to Claude Code. While the token is stale the bar shows
  `auth (abrí Claude Code)` until the CLI rewrites `.credentials.json`.
- Without hooks the dot falls back to transcript mtime — working / idle only,
  no "waiting".

## License

MIT — see [LICENSE](LICENSE).
