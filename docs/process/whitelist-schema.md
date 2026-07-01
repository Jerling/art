# `whitelist.json` schema

The file is a JSON array of PM-approved whitelist entries. An empty
array (`[]`) means no authors have permanent pre-approval — the only
exemption paths are `hotfix/*` branches and the `[skip-kanban]` commit
marker, both of which require a kanban backlink within 24 hours.

## Entry shape

```json
{
  "author": "jerry@art.local",
  "name_match": "jerry",
  "reason": "PM-approved: emergency hotfix response lead",
  "approved_by": "PM",
  "approved_at": "2026-07-02T00:00:00Z",
  "expires_at": null,
  "pr_review_url": "https://github.com/Jerling/art/pull/123"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `author` | string | one of `author` / `name_match` | Git author email (case-insensitive match). |
| `name_match` | string | one of `author` / `name_match` | Git `user.name` substring match. Fallback for teams with rotating emails. |
| `reason` | string | yes | Human-readable justification, surfaces in CI logs. |
| `approved_by` | string | yes | Who approved this entry (`PM`, `jerry`, ...). |
| `approved_at` | string (ISO 8601) | yes | When this entry was added. |
| `expires_at` | string (ISO 8601) or `null` | yes | When this entry stops being effective. `null` = permanent until PM removes. |
| `pr_review_url` | string (URL) | yes | Link to the PR that added this entry. Required for audit. |

## Maintenance

Adding or removing an entry MUST go through a PR with PM review
(captured by the `approved_by` + `pr_review_url` fields). Direct commits
to `whitelist.json` on `main` are not allowed — the Sprint 5 retro
ratified this as a PM-controlled surface.

## Initial state

The file ships as `[]` (no permanent pre-approval). Operators use the
`hotfix/*` branch or `[skip-kanban]` marker for emergency work; PM adds
an entry only when an operator needs standing pre-approval (e.g. a
designated on-call lead who lands hotfixes out of band).
