# CI rules — R1 commit-evidence + emergency hotfix whitelist

> **Status**: PM-drafted (Sprint 5 retro) — awaiting final PM sign-off
> **Owner**: product-manager (rules) + sre (implementation)
> **Source**: Sprint 4 retro § 5 R1 + jerry's whitelist补充 (2026-07-02)
> **Implements**: `scripts/check_commit_evidence.py` + `whitelist.json`

## TL;DR

Every commit landing on `main` MUST reference a kanban task id
(`(#t_xxxxxxxx)` form), with three documented exemptions:

1. **`hotfix/*` branches** — emergency response. PM has 24 hours to
   backfill the task id.
2. **`[skip-kanban]` commit marker** — ad-hoc bypass for one commit.
   PM has 24 hours to backfill the task id.
3. **Author on `whitelist.json`** — pre-approved by PM via PR. No
   deadline, but the entry must be explicitly justified and timestamped.

If a hotfix / `[skip-kanban]` commit is not backfilled within 24 hours,
**the author's subsequent commits are REJECTED by CI** with the
`missing_kanban_backlink` error until PM fills in the task id or
removes the exemption.

## The three exemption paths

| Path | Triggered by | Backlink deadline | Subsequent commits |
|---|---|---|---|
| `hotfix_branch` | branch name starts with `hotfix/` | 24 hours | blocked if overdue |
| `skip_marker` | commit message contains `[skip-kanban]` | 24 hours | blocked if overdue |
| `whitelist_author` | author email or git user.name matches an entry in `whitelist.json` | none | never blocked by R1 |

`hotfix_branch` and `skip_marker` both create a record in
`.kanban-exemptions.json` (per-repo, gitignored). The `sprint-monitor.py`
cron reads this file daily and sends a feishu reminder for any
overdue exemption.

## R1 base rule (unchanged)

For any commit that doesn't qualify for a whitelist exemption:

* The commit message must contain `(#t_xxxxxxxx)` (or bare `t_xxxxxxxx`).
* That task id, when looked up via `hermes kanban show <id>`:
    - MUST exist on the configured board (`HERMES_KANBAN_BOARD`, default `art`)
    - MUST have at least one parent whose title matches `/Sprint \d+/i`

The CI implementation is `scripts/check_commit_evidence.py`, wired via
`.github/workflows/parent-task-check.yml`. See
`docs/operations/ci-parent-task-check.md` for the technical reference.

## 24-hour backlink window

`hotfix_branch` and `skip_marker` exemptions create an entry in
`.kanban-exemptions.json` with `backlink_required_by = exempted_at + 24h`.

Once the deadline passes, the next commit by the same author (by git
author email) is **rejected** by `scripts/check_commit_evidence.py` with
the error:

```
missing_kanban_backlink: commit <sha> by <author> blocked: prior exempted
commit <old_sha> (hotfix_branch|skip_marker) is past its 24-hour backlink
deadline (<deadline>); PM must fill in the kanban task id or unsuspend
the exemption
```

PM backfills by:
1. Creating a kanban task for the hotfix / skipped commit.
2. Amending the commit message to include `(#t_xxxxxxxx)`.
3. Marking the exemption `resolved: true` in `.kanban-exemptions.json`
   (or deleting the entry).

A re-run of the CI check will pick up the amended commit message and
unblock the author.

## Whitelist maintenance

`whitelist.json` is the **only** surface for granting permanent
pre-approval. Schema is documented in
`docs/process/whitelist-schema.md`.

**Changes require PM review via PR.** Direct commits to `whitelist.json`
on `main` are not allowed — the operator proposing the change opens a PR
with:
- The proposed entry (author, reason, expiry).
- Justification (why does this author need standing pre-approval?).
- An expiry date, or `null` for permanent.

PM either approves the PR (the entry takes effect on merge) or
requests changes (the entry never lands). The PR review URL is
captured in the entry's `pr_review_url` field for audit.

## Cron + monitoring

The daily monitor (`scripts/sprint-monitor.py`) runs at 09:00 local
time and combines:

1. **R4 user-verify scan** — calls
   `hermes kanban user-verify-scan --board art --json`. Tasks that
   are `done` but lack `user_verified_at` after
   `user_verify_business_days` (default 5) are auto-blocked. The
   monitor forwards any new auto-blocks to feishu.

2. **Whitelist exemption check** — reads
   `.kanban-exemptions.json` and identifies any hotfix / skip_marker
   exemption past its 24h deadline. Forwards the overdue list to
   feishu so PM can backfill before the author's next commit is
   rejected.

The cron is silent on incident-free days (the "deliver on incident"
watchdog pattern). The R4 cron is also re-runnable manually with
`--dry-run` to preview the report.

## Why three paths and not one

A single "hotfix bypass" rule would conflate three very different
behaviours:

* **Hotfix branches** are the *intended* path for emergency response.
  We want to encourage their use; the 24h deadline is the trade-off
  for skipping the task-id check at commit time.
* **`[skip-kanban]` markers** are *unintended* and rare — typically a
  developer in a hurry who didn't want to create a task. We want to
  discourage their use; the 24h deadline is the same trade-off but
  with the assumption that they're a one-off, not a workflow.
* **Whitelist authors** are *standing pre-approval* — typically a
  designated on-call lead. No deadline because the pre-approval is
  the point; the audit trail is the `pr_review_url` field.

If a developer uses `[skip-kanban]` repeatedly, that's a signal to PM
that they should be added to `whitelist.json` (or that the team needs
a process for hotfix branches).

## Failure mode examples

| Scenario | Outcome |
|---|---|
| Commit message has `(#t_1234abcd)`, task exists, has Sprint parent | ✅ PASS |
| Commit message has `(#t_1234abcd)`, task does NOT exist | ❌ FAIL (`task_not_found`) |
| Commit message has `(#t_1234abcd)`, task has no Sprint parent | ❌ FAIL (`no_sprint_parent`) |
| Commit on `hotfix/foo`, no task id, no prior overdue exemption | ✅ PASS (exempt: `hotfix_branch`) |
| Commit on `main`, no task id, author NOT in whitelist | ❌ FAIL (`no_task_id`) |
| Commit on `main`, no task id, message contains `[skip-kanban]` | ✅ PASS (exempt: `skip_marker`) |
| Commit on `main`, no task id, author IS in whitelist | ✅ PASS (exempt: `whitelist_author`) |
| Author has 25h-old unbackfilled `hotfix_branch` exemption, current commit has `(#t_xxx)` | ❌ FAIL (`missing_kanban_backlink`) |
| Commit on `hotfix/foo`, no task id, but author has overdue exemption | ❌ FAIL (`missing_kanban_backlink`) |

## Edge cases

* **Squash-merge** changes the visible commit message. The check runs
  against the PR's individual commits, not the squash commit, so the
  check is robust to merge strategy.
* **Reverts** of bad commits still reference the bad id. That's
  intentional — the bad id is the smell; reverting the code doesn't
  fix the process.
* **Fork PRs** don't have access to hermes secrets. The check falls
  back to a permissive PASS with a printed warning. Fork maintainers
  should run the local pre-commit variant (`--local`).
* **Whitelist entry expiry** — if `expires_at` is set, the entry
  becomes inactive after that timestamp. PM is responsible for
  renewing or removing expired entries.

## Related

* Sprint 4 post-mortem: `docs/post-mortem/sprint4-process-gap.md`
* R1 technical reference: `docs/operations/ci-parent-task-check.md`
* R2 e2e_evidence: `docs/operations/kanban-e2e-evidence.md`
* R4 user-verify deadline: `docs/operations/user-verify-deadline.md`
* Whitelist schema: `docs/process/whitelist-schema.md`
* Sprint-monitor source: `scripts/sprint-monitor.py`
* Check-evidence source: `scripts/check_commit_evidence.py`
