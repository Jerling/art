# CI parent-task check (Sprint 4 retro R1)

## What this is

A GitHub Actions check that runs on every pull request targeting `main` and
**refuses to merge any commit whose message references a `(#t_xxxxxxxx)`
task id that does not exist on the Hermes Kanban board, or whose task has
no Sprint N parent**.

This is the cheapest, most local rule that would have caught the Sprint 4
JWT gap: the offending commit `b2e30a1` referenced `t_f0d2773e`, which
`kanban_show` returns as `task_not_found`. The CI check would have blocked
the merge at PR time, not 28 days later when jerry tried the deployed
build.

> The script also implements R7's small-change threshold (hotfix
> branch exemption, `[skip-kanban]` marker, and a PM-managed
> `whitelist.json` for pre-approved authors). See
> `docs/process/ci-rules.md` for the R7 rules. This document covers
> only the R1 parent-task check; the script is the unified
> implementation of both.

## Where the code lives

| Piece | Path |
|---|---|
| Workflow YAML | `.github/workflows/parent-task-check.yml` |
| Check script | `scripts/check_commit_evidence.py` |
| Post-mortem | `docs/post-mortem/sprint4-process-gap.md` § 5 / R1 |
| Sprint 4 retro doc | `docs/post-mortem/sprint4-process-gap.md` |

The workflow is **additive** — it runs in parallel with the existing
`ci.yml` (ruff + mypy + pytest). A failure here does not skip the other
checks, and a failure in lint/tests does not skip this one.

## What gets checked

For each commit on the PR (oldest-first, with merge commits skipped):

1. The commit message must contain a `t_<8 hex>` reference, in either
   the bare form or the `(#t_xxxxxxxx)` citation form.
2. That id, when looked up via `hermes kanban show <id> --json`, must
   return a real task (not `task_not_found`).
3. That task must have at least one parent whose title matches
   `/Sprint \d+/i` — the assumption being that any new work on `main`
   belongs to a Sprint card, not a free-floating task.

If any of the three checks fail, the workflow exits 1 and emits a
`::error` annotation pointing at the offending commit SHA so the
developer sees a precise pointer in the PR's Files Changed view.

## Why `Sprint N` parent specifically

Sprint 1–4 history shows that free-floating tasks (no Sprint parent) are
exactly the ones that escape review, test-lead, and PM confirmation. The
parent lookup is a cheap proxy for "is this work on a current Sprint
plan?" — if it isn't, the developer should either:

* Link the task to a Sprint N parent before merging, or
* Ping jerry for an explicit override (added as a PR comment).

The check intentionally does **not** enforce the existence of acceptance
criteria, sub-tasks, or step 6 (user verify) — those are PM-side
controls in R3/R4/R5/R7, not CI checks. CI sees the commit; the board
sees the rest.

## Auth model

The script shells out to `hermes kanban show <id>` rather than calling
the Kanban SQLite directly. This means the runner needs:

* `hermes` on `PATH` (installed in a `Setup hermes` step)
* `HERMES_KANBAN_DB` and `HERMES_KANBAN_BOARD` env vars pointing at a
  board the runner has read access to
* The `gh` CLI authenticated to read the PR's commit list

In practice this runs on a self-hosted runner that has those
credentials. On a fully-public GitHub-hosted runner where those creds
aren't available, the script **falls back to a permissive PASS with a
printed warning** — the PR is not blocked on infra plumbing. Pass
`--strict` to fail-closed when the lookup is ambiguous (recommended for
the self-hosted runner; the workflow does this automatically).

The fallback exists so a misconfigured runner does not silently merge
broken work, but also so a misconfigured runner does not block an
otherwise-good PR. The two failure modes are different, and the
fallback message is explicit about which is which.

## Running locally

The same script is runnable as a pre-commit hook:

```bash
# Scan HEAD~1..HEAD, no GitHub calls
python scripts/check_commit_evidence.py --local

# Scan a custom range
PARENT_TASK_CHECK_RANGE=HEAD~5..HEAD python scripts/check_commit_evidence.py --local

# Run against a real PR (needs gh auth + hermes on PATH)
python scripts/check_commit_evidence.py --repo jer/data/Code/art --pr 42
```

A pre-commit hook config (`.pre-commit-config.yaml` snippet) is
**not** included in this change because:

* Most commits in this repo land via squash-merge, so the parent check
  is naturally a CI check, not a local one.
* The check needs `hermes` + the board DB, which a developer's laptop
  may not have. The CI check is the canonical gate; the local hook is
  a developer convenience.

## Test

`tests/ci/test_check_commit_evidence.py` covers the script's three
branches (no task id, task not found, task has no Sprint parent) plus
the positive case (real task with a Sprint parent). The tests use a
fake `hermes` shim and a temp git repo so they don't touch the live
board or the network.

## Verifying the change works end-to-end

1. Open a PR with a commit message that references a fake id:
   `echo "test: fake commit" | git commit --allow-empty -F-`
   The `t_deadbeef` reference is added by re-committing with
   `(#t_deadbeef)` in the message body.
2. Push the branch. The `parent-task-check` job should fail with
   `task_not_found: t_deadbeef is NOT on board 'art'`.
3. Re-commit with a real, sprint-parented task id. The job should pass.

## Edge cases & non-goals

* **Squash-merge** changes the message. The check runs against the PR's
  individual commits (oldest first), not the squash commit, so the
  check is robust to merge strategy.
* **Reverts** of `t_f0d2773e`-style commits still reference the bad id.
  That's intentional — the bad id is the smell; reverting the code
  doesn't fix the process.
* **Hotfixes** that need to bypass the rule should add a Sprint N
  parent task first, then reference it. The Sprint 5 retro added an
  explicit `e2e_evidence_override` mechanism for genuinely
  evidence-free changes (see `docs/operations/kanban-e2e-evidence.md`),
  but R1 has no override — a Sprint parent is mandatory.
* **Cross-repo commits** (commits made on a fork, then rebased) are
  scanned by reading the final PR commits, not the original fork
  history, so the check works regardless of contributor provenance.

## Acceptance sign-off

* Workflow file present at `.github/workflows/parent-task-check.yml` ✅
* Check script present at `scripts/check_commit_evidence.py` ✅
* 4 test cases pass in `tests/ci/test_check_commit_evidence.py` ✅
* Manual verification: a PR with `(#t_deadbeef)` is rejected ✅
