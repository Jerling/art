# User-verify 5-business-day deadline (Sprint 4 retro R4)

## What this is

After a task moves to `done`, the operator has **5 business days** to
mark it user-verified via `hermes kanban verify <id> --by <user>`. If
no verification lands in that window, a daily cron auto-blocks the
task and posts a comment naming the deadline. **Push (step 7) is
gated on user verification** — a `done` task that hasn't been
user-verified cannot move to "deployed and done" status.

This is the R4 half of the Sprint 4 retro. Sprint 4 was unverified for
**33 days** before the bug surfaced; the missing forcing function is a
deadline, not a stronger review process.

## Where the deadline lives

| Piece | Path |
|---|---|
| Board policy | `~/.hermes/kanban/boards/<slug>/board.json` → `user_verify_business_days` |
| Schema columns | `hermes_cli/kanban_db.py` → `tasks.user_verified_at`, `user_verified_by` |
| Manual verify CLI | `hermes kanban verify <id> --by <user> [--note ...]` |
| Cron scan | `hermes kanban user-verify-scan --board <slug> --json` |
| Cron wrapper | `~/.hermes/scripts/r4_user_verify_scan.sh` |
| Cron job | `hermes cron list` → id `800c23baf001` |
| Test | `tests/hermes_cli/test_kanban_user_verify.py` |

The Art board has `user_verify_business_days: 5` set. The default
board has the same.

## Why business days, not calendar days

A 5-calendar-day deadline that lands on a Friday effectively becomes
a 3-business-day deadline for the operator, or a 7-business-day
deadline if it crosses a long weekend. A 5-business-day deadline is
predictable: 5 working days from completion, regardless of where the
weekends fall.

The math is in `hermes_cli/kanban_db.py` →
`_business_days_between(start, end)`. It:

* counts days in the half-open interval `[start, end)`,
* skips Saturdays and Sundays (no public-holiday table — see "Why no
  holiday calendar" below),
* is implemented in UTC so the cron and the board stay aligned across
  deploys.

## How the cron is wired

The cron runs **once per day at 09:00 local time** (operator's
timezone). The job is `r4_user_verify_scan.sh`, registered as
cron job id `800c23baf001`. The job is configured with
`no_agent=true` so the script runs without a worker — the
script's stdout is the message the operator sees on each tick.

The script:

1. Discovers boards via `hermes kanban boards list --json` (falls
   back to scanning the on-disk layout if hermes is broken).
2. For each board, calls `hermes kanban user-verify-scan --board
   <slug> --json`.
3. Aggregates the blocked counts + ids per board.
4. Exits 0 on a no-op day (silent — operator doesn't see anything).
5. Exits 1 on a day with auto-blocks (operator sees a structured
   report in their home chat).

The exit-1-on-incident pattern means the operator's chat is silent on
quiet days and only surfaces when something actually happened — the
"deliver on incident" watchdog pattern. The full stdout is
also captured in the cron log file
(`~/.hermes/cron/output/800c23baf001.log` on a default install)
for audit.

## What auto-block looks like

When the cron blocks a task, three things land in the task's event
log:

1. `user_verify_deadline_exceeded` — audit event with
   `elapsed_business_days`, `configured_deadline_days`, and
   `completed_at`.
2. `blocked` — workflow event with `reason: "Sprint 4 retro R4:
   user-verify deadline exceeded (N business days without
   user_verified_at; configured limit 5)"` and
   `source: "auto_block_unverified_tasks"`.
3. A comment on the task naming the deadline and pointing at this
   doc.

The task transitions to `blocked` status. The `claim_lock` is
cleared so a worker can re-claim it once the operator verifies (or
the operator can `unblock` after fixing the underlying issue).

The auto-block uses a CAS on `status = 'done' AND
user_verified_at IS NULL` to avoid racing a manual `verify` or
`unblock` that landed between the candidate SELECT and the
UPDATE.

## Manual verification

The operator (jerry, or whoever is named in the task's `assignee`)
runs:

```bash
hermes kanban verify t_xxxx --by jerry \
  --note "manually tested login + tasks + logout on staging 2026-07-02"
```

This sets `user_verified_at = now` and `user_verified_by = "jerry"`
on the task, and emits a `user_verified` event. Re-verifying a task
is idempotent — the latest verification wins, so a re-check after a
bug fix overwrites the older one.

To reverse a verify (e.g. you tested the wrong branch):

```bash
hermes kanban verify t_xxxx --by jerry --unverify
```

This clears `user_verified_at` / `user_verified_by` and emits a
`user_unverified` event. The R4 cron will re-block the task at the
next deadline check if the operator doesn't re-verify.

## Why no public-holiday calendar

A holiday table would be brittle:

* The team spans at least two timezones (UTC + China), and
  Chinese vs. US holidays rarely align.
* Public-holiday calendars change yearly and the kanban board would
  need a yearly update.
* A wrong holiday table silently shifts deadlines, which is
  worse than no table at all.

Operators who need to extend a deadline (e.g. the team is on a
two-week break) can:

* `hermes kanban unblock t_xxxx --reason "holiday break"`, then
  re-`complete` it after the break (resets `completed_at` to the
  post-break date).
* raise `user_verify_business_days` on the board temporarily
  (`write_board_metadata(board, user_verify_business_days=14)`).

## Edge cases & non-goals

* **R4 only fires on boards that have opted in to R2** (`require_e2e_evidence: true`).
  The kernel checks this in `auto_block_unverified_tasks` and
  returns an empty list on a board that hasn't opted in. The cron
  scans every board anyway, but it's a no-op on non-R2 boards.
* **The cron is idempotent and safe to re-run.** It uses a CAS on
  `status = 'done' AND user_verified_at IS NULL`, so a manual
  verify or unblock between SELECT and UPDATE is not raced.
* **`--force` flag on `user-verify-scan`** bypasses the
  `require_e2e_evidence` check. This is **for testing only** — the
  real cron never passes `--force`. Misuse would auto-block tasks
  on boards that haven't opted in, which is the opposite of what
  the cron should do.
* **The deadline is per-board, not per-task.** A high-priority
  task can't be given a shorter deadline; the operator can
  `unblock` + re-`complete` to reset `completed_at`, but the
  configured window is shared.

## Test

`tests/hermes_cli/test_kanban_user_verify.py` covers:

* `_business_days_between` math: weekend skipping, negative
  intervals, same-day returns 0.
* `mark_user_verified`: idempotent, refuses non-`done` tasks,
  requires `by_user`.
* `auto_block_unverified_tasks`: blocks a 6-business-days-old task,
  leaves a 4-day-old task alone, no-op on boards that haven't
  opted in (without `--force`).

The tests use `monkeypatch` + tmp_path HERMES_HOME so the live board
is never touched. A separate test (`test_r4_cron.sh`) force-ages a
task via `user-verify-scan --business-days 0 --force` and verifies
the auto-block path.

## Verifying the change works end-to-end

1. Pick a recent `done` task that has no `user_verified_at`. If
   none exist, create one and complete it (with `e2e_evidence` so
   R2 doesn't reject).
2. Run the scan with a forced deadline to bypass the real clock:
   ```bash
   hermes kanban user-verify-scan --board art --business-days 0 --force --json
   ```
   Expected: the task appears in `blocked`, with
   `count` ≥ 1.
3. `hermes kanban show t_xxxx` should now report `status: blocked`
   and the event log should contain both
   `user_verify_deadline_exceeded` and a `blocked` event with the
   auto-block reason.
4. Re-`complete` the task with a real `e2e_evidence` and
   `hermes kanban verify t_xxxx --by jerry` to restore it to
   `done` + verified.

## Acceptance sign-off

* `user_verify_business_days: 5` on `default` and `art` boards ✅
* Cron job `800c23baf001` registered, schedule `0 9 * * *`,
  script `r4_user_verify_scan.sh` ✅
* Daily scan runs; auto-block path tested ✅
* 6 test cases pass in `tests/hermes_cli/test_kanban_user_verify.py` ✅
* Manual verification: force-age one task → cron auto-blocks it ✅
