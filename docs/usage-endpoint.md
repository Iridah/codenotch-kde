# The usage endpoint

> **Unofficial.** `GET https://api.anthropic.com/api/oauth/usage` is the call
> Claude Code's `/usage` view makes. It is not a documented public API and its
> shape can change without notice. codenotch parses it defensively and degrades
> to a `sin datos de uso` state rather than crashing when a field moves.

## Auth

Bearer token from `~/.claude/.credentials.json`:

```json
{ "claudeAiOauth": { "accessToken": "...", "expiresAt": 0,
                     "refreshToken": "...", "subscriptionType": "pro",
                     "rateLimitTier": "default_claude_ai" } }
```

Headers sent:

```
Authorization: Bearer <accessToken>
anthropic-beta: oauth-2025-04-20
anthropic-version: 2023-06-01
```

Token refresh is left entirely to Claude Code. If `expiresAt` is in the past
codenotch still tries the call; on `401/403` it shows `auth (abrí Claude Code)`
until the CLI rewrites the credentials file, which codenotch re-reads each poll.

## Response shape (observed 2026-09, Pro plan)

```json
{
  "five_hour":  { "utilization": 10.0, "resets_at": "2026-09-07T22:59:59.879132+00:00" },
  "seven_day":  { "utilization": 6.0,  "resets_at": "2026-09-14T04:59:59.879155+00:00" },
  "seven_day_opus": null,
  "seven_day_sonnet": null,
  "nimbus_quill": { "utilization": 0.0, "resets_at": null },
  "tangelo": null, "iguana_necktie": null, "cinder_cove": null,
  "extra_usage": { "is_enabled": false, ... },
  "limits": [
    { "kind": "session",    "group": "session", "percent": 10, "severity": "normal",
      "resets_at": "2026-09-07T22:59:59.879132+00:00", "is_active": true },
    { "kind": "weekly_all", "group": "weekly",  "percent": 6,  "severity": "normal",
      "resets_at": "2026-09-14T04:59:59.879155+00:00", "is_active": false }
  ],
  "spend": { "used": { "amount_minor": 0, "currency": "USD", "exponent": 2 }, ... }
}
```

Notes:

- `*.utilization` and `limits[].percent` are **0-100**, not 0-1.
- The top level carries a set of internal codename buckets
  (`nimbus_quill`, `tangelo`, `iguana_necktie`, `cinder_cove`, ...) that are
  almost always `null` or `0.0`. They are **not** meters to display.
- `limits[]` is the stable, self-describing list. codenotch prefers it.

## How codenotch reads it (`extract_meters`)

1. If `limits[]` is a non-empty list, build meters from it and stop.
   `kind`/`group` maps: `session -> 5h`, `weekly_all -> 7d`,
   `weekly_opus -> opus`, `weekly_sonnet -> sonnet`.
2. Else try known top-level buckets: `five_hour`, `seven_day`,
   `seven_day_opus`, `seven_day_sonnet`.
3. Else fall back to a generic recursive walk for any
   `utilization` / `percent` / `*_pct` field (this last mode may rescale a
   `<= 1.5` value as a fraction).

`codenotch --dump` prints the raw JSON plus the meters it detected — the way to
diagnose a shape change.
