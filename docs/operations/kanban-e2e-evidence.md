# Kanban `e2e_evidence` requirement (Sprint 4 retro R2)

## What this is

The `done` status on the Art Kanban board **requires a non-empty
`metadata.e2e_evidence`** value on every card that moves to `done`.
The board policy is opt-in: when a board sets
`require_e2e_evidence: true` in `board.json`, the kernel rejects any
`kanban_complete` call that doesn't supply evidence.

This is the R2 half of the Sprint 4 retro: a `require_auth` change has
zero value without a way to satisfy it, and "CI green + tests pass" is
not enough signal. The post-mortem (`docs/post-mortem/sprint4-process-gap.md`
§ Q2) defined a `done` as requiring four things, and the e2e_evidence
field is the kernel's enforcement of point 3 (end-to-end smoke
evidence).

## Where the policy lives

| Piece | Path |
|---|---|
| Board policy flag | `~/.hermes/kanban/boards/<slug>/board.json` → `require_e2e_evidence` |
| Kernel gate | `hermes_cli/kanban_db.py` → `MissingE2EEvidenceError` + `complete_task` |
| Tool surface | `tools/kanban_tools.py` → `kanban_complete` (tool error) |
| CLI surface | `hermes_cli/kanban.py` → `_cmd_complete` (exit 3) |
| Test | `tests/hermes_cli/test_kanban_e2e_evidence.py` |

The Art board already has `require_e2e_evidence: true` set. New boards
opt in by adding the flag (see "Enabling on a new board" below).

## What counts as evidence

`metadata.e2e_evidence` is intentionally permissive — the goal is "stop
silent ship-broken work", not "enforce a strict schema". The validator
accepts any of:

* **non-empty string** — a URL, a log path, or a free-form note
  ("manually tested login + tasks + logout on staging 2026-07-02").
* **dict** with at least one non-empty value in the standard keys
  (`url`, `curl_log`, `screenshot`, `note`, `playwright_trace`,
  `manual_verify`, `evidence`, `transcript`).
* **list/tuple** of the above.

The string form is what most agents pass; the dict form is what humans
tend to write when they want to attach both a URL and a note. The
validator only fails when the value is empty (None, empty string, empty
dict, empty list, or zero).

## How workers attach evidence

Three patterns, in order of preference:

1. **Real automated evidence** — Playwright trace, curl log, server
   response body captured during a smoke run.
   ```python
   metadata={"e2e_evidence": "https://ci.example.com/artifacts/login-trace-2026-07-02.zip"}
   ```
2. **Manual verification note** — for changes that are not
   end-user-runnable (CI config, dead-code removal, docs):
   ```python
   metadata={"e2e_evidence": {"note": "manually verified: workflow file present + ruff passes on dry-run 2026-07-02"}}
   ```
3. **Explicit bypass with a reason** — for changes that are provably
   non-runtime and where even a manual note is overkill:
   ```python
   metadata={"e2e_evidence_override": "docs-only change, no runtime path affected"}
   ```
   Bypass uses are audited as `completion_override_no_e2e_evidence`
   events on the task's event log. PM can `kanban tail <id>` to see
   who is using the bypass and why.

## Failure mode

A worker that calls `kanban_complete` without evidence gets back a
structured error:

```
kanban_complete blocked: completion blocked on 'art' board: board
policy requires metadata.e2e_evidence on done (Sprint 4 retro R2).
Task t_xxxx did not supply one. Pass metadata={'e2e_evidence':
'https://...'} (URL/curl log/path), or a dict like {'screenshot':
'...', 'note': 'manual verify 2026-07-02'}, or set
metadata.e2e_evidence_override='<reason>' to bypass explicitly.
```

The task itself is **not mutated** — the gate runs before the write
txn, so the worker can call `kanban_complete` again with the right
metadata. This is the same retry pattern used by the
`HallucinatedCardsError` gate.

The CLI surface (`hermes kanban complete <id>`) exits 3 on this
failure so a shell script sees it as a non-zero exit.

## Enabling on a new board

The `default` board and the `art` board both have
`require_e2e_evidence: true` set. To enable on a new board:

```bash
hermes kanban boards switch <new-slug>
# Edit ~/.hermes/kanban/boards/<new-slug>/board.json to add
#   "require_e2e_evidence": true,
# Or via the read/write helper:
python -c "from hermes_cli.kanban_db import write_board_metadata; \
           write_board_metadata('<new-slug>', require_e2e_evidence=True)"
```

After enabling, every `kanban_complete` on that board requires
evidence. There is no per-task opt-out — the bypass is at the
metadata level, not the policy level.

## Why not a stricter schema

A stricter schema (require a URL, require a screenshot, require a
playwright trace) would catch more gaps in theory, but in practice it
would push workers to attach synthetic evidence to satisfy the schema
("here's a URL to the merged PR — see, it's a URL!") rather than
genuine end-to-end evidence. The permissive validator + audit trail
is the deliberate trade-off: the cost of a fake URL is one
PM-scan-rotation away; the cost of a strict schema is a flood of
low-quality evidence attached to bypass it.

The audit log (`completion_blocked_no_e2e_evidence` and
`completion_override_no_e2e_evidence` events) is the second line of
defense — PM can scan for tasks that bypassed or were blocked, and
follow up with the worker.

## Test

`tests/hermes_cli/test_kanban_e2e_evidence.py` covers the four
branches: missing metadata, empty string, dict with one good key,
override. The tests use a tmp_path HERMES_HOME so the live board is
never touched.

## Verifying the change works end-to-end

1. Create a task and complete it without evidence:
   ```bash
   hermes kanban complete t_test --summary "no evidence"
   # → exit 3: completion blocked on 'art' board
   ```
2. Complete it with a real note:
   ```bash
   hermes kanban complete t_test --summary "with note" \
     --metadata '{"e2e_evidence": "manual smoke 2026-07-02"}'
   # → exit 0: Completed t_test
   ```
3. Inspect the event log:
   ```bash
   hermes kanban tail t_test | grep -E "completed|evidence"
   ```

## Edge cases & non-goals

* **R2 only applies when the board sets `require_e2e_evidence: true`.**
  A board that hasn't opted in is unchanged — the gate is opt-in by
  design so a new board isn't suddenly broken on its first task.
* **The override (`e2e_evidence_override`) is not a hidden backdoor.**
  Every override use is logged as a
  `completion_override_no_e2e_evidence` event with the reason text,
  visible in `hermes kanban tail <id>`. PM should review override usage
  in the next retro.
* **The 5-business-day user-verify deadline (R4) sits on top of R2.**
  A `done` task that has `e2e_evidence` is still subject to
  `hermes kanban verify` and the R4 cron. R2 ensures the worker
  attached *something*; R4 ensures the operator actually looked at it.

## Acceptance sign-off

* `require_e2e_evidence: true` on `default` and `art` boards ✅
* `MissingE2EEvidenceError` raised on empty `metadata.e2e_evidence` ✅
* 4 test cases pass in `tests/hermes_cli/test_kanban_e2e_evidence.py` ✅
* CLI exits 3 on the blocked case ✅
* Manual verification: a `done` task without evidence is rejected ✅
