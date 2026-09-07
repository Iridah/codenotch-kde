# Security

## Threat model

codenotch-kde is a local, single-user desktop overlay. It runs as your user in
your graphical session.

- It **reads** your Claude Code OAuth token from `~/.claude/.credentials.json`.
- It sends that token **only** to `https://*.anthropic.com` (default
  `https://api.anthropic.com/api/oauth/usage`), as a `Bearer` header, to read
  your own usage numbers — the same call the `/usage` command makes.
- The token is never written to disk, logged, printed, or included in an error
  message. `codenotch --dump` prints the usage JSON response only (no token).
- Session state is read from small JSON files in `~/.claude/codenotch/`, written
  by `codenotch-hook` from Claude Code hook events.

Anyone who can already write arbitrary files in your `$HOME` can read the token
directly; the hardening below exists to limit what a *constrained* write
primitive (a rogue dependency touching one file, a crafted hook payload) can
achieve.

## Hardening in place

- **Endpoint pinning.** `fetch_usage` rejects any `endpoint` that is not HTTPS
  on an `*.anthropic.com` host, and uses a URL opener that refuses cross-host
  and non-HTTPS redirects, so a tampered `~/.config/codenotch/config.json`
  cannot redirect the token. Response body capped at 2 MB.
- **Hook input.** `session_id` is constrained to `[A-Za-z0-9._-]{1,128}` and the
  resolved output path is verified to stay inside `~/.claude/codenotch/`.
  State files are `0600`, the directory `0700`.
- **systemd sandbox.** The `--user` service runs with `NoNewPrivileges`,
  `ProtectSystem=strict`, `ProtectHome=read-only` (+ explicit `ReadWritePaths`),
  `SystemCallFilter=@system-service`, restricted address families and
  namespaces, a private cache dir, and `UMask=0077`.
- **Config parsing.** Every config field is coerced to a sane type/range; a
  malformed file cannot crash startup.
- **No shell.** All subprocess calls are list-form with fixed or integer
  arguments (`xprop -id <int>`, `xdg-open <fixed path>`). No `shell=True`,
  `eval`, `pickle`, or YAML anywhere.

## The usage endpoint is unofficial

`https://api.anthropic.com/api/oauth/usage` is not a documented public API. It
can change or disappear without notice. codenotch degrades to a "no data" state
rather than failing loudly. See [`docs/usage-endpoint.md`](docs/usage-endpoint.md).

## Reporting

Open a private security advisory on the GitHub repository, or email the
maintainer listed in `packaging/debian/control.in`. Please do not file a public
issue for anything exploitable.
