# Sprint 4 Process Gap — Post-Mortem

> **Status**: Draft v1.0 — awaiting jerry review
> **Author**: product-manager
> **Date**: 2026-07-01
> **Scope**: Sprint 3 close-out (5/26–5/31) → Sprint 4 JWT commit (6/3) → Sprint 3 merge (6/15) → main HEAD 6/17 → production trial (7/1)
> **Severity**: P1 — deployed code is non-functional for end users (all authenticated APIs 401, UI 404)

---

## TL;DR

Sprint 4 added a JWT auth gate in front of every business API but shipped **no login endpoint** and **no static-file mount** for the Vue web app. When jerry tried the deployed build on 2026-07-01, every request 401/404'd. Root cause is not a coding bug — it is that **Sprint 4 bypassed the kanban process entirely**: no parent task, no sub-tasks, no reviewer/test-lead/user-validation sign-off. The git-only evidence trail points to `t_f0d2773e`, which does not exist on the board. We merged feature work into `sprint3/mvp-launch` twelve days after Sprint 3 declared "MVP final deliverables", with no user-verification step in between.

---

## 1. Timeline (5/22 → 7/1)

| Date | Commit | Event | Process Step |
|---|---|---|---|
| 5/22 | `ed28d14` | Sprint 1 — FastAPI + Vue3 CRUD skeleton merged | dev → review → test → PM → user ✅ |
| 5/22–5/26 | `273aefe` | Sprint 2 — WeChat + AI + MCP | dev → review (B1–B4 fixed) → test → PM |
| 5/26 | — | Sprint 2 done, `t_bbb97d79` ✅ | step 6 (user verify) skipped |
| 5/27 | `c6733af`, `b2b30fe`, `c659109`, `16f09a2`, `a9a76a7`, `8d425db`, `f55defd`, `23c5e3e`, `397b2ed`, `44e591f`, `efaec02`, `980b462`, `5f6bde9`, `14f145f`, `e77689b` | Sprint 3 web UI + push enhancements + backup + health/metrics + S1–S5 suggestions + docker-compose | 15 commits in one day, mostly bundled under Sprint 3 parent |
| 5/28 | `5c06c55`, `03ae969`, `ed9218e` | Web UI — kanban board + role perspective switching + NavBar cleanup | |
| 5/29 | `662ea27` | **Sprint 3 "MVP final deliverables"** — Beta test report + integration test report | `t_6e244f46` ✅ done, sub-tasks `t_700d0665`/`t_77adfba2`/`t_93a4c98f` ✅ done |
| 5/29 | `7419f56` | Merge `sprint3/mvp-launch` → main | step 7 (push) ✅ |
| 5/31 | `9fa60dd`, `4dfab60`, `325b582` | Sprint 3 final fixes — Docker DB path, B1/B2 rate-limiter sleep | **post-merge fixes on main, no Sprint task parent** |
| **6/1–6/2** | — | **5-day silent gap — no commits, no board activity** | step 6 (user verify) still not triggered |
| **6/3** | **`b2e30a1`** | **Sprint 4 JWT middleware on /tasks, /roles, /role_tasks, /wechat_message, /admin** | references `t_f0d2773e` (does **not** exist on board) |
| **6/3–6/14** | — | **11-day silent gap — no commits on main, no board activity** | step 2 (review), step 3 (test), step 4 (PM), step 6 (user verify) all skipped |
| 6/14 | — | OpenCode 对比评审 `t_93a4c98f` "通过" — **only reviewed code delta** | reviews code, not feature completeness |
| 6/15 | `416164c` | Web UI fix — 4 blockers + 3 major from RBAC code review (`t_92fd6e88`) | addresses **web UI permission gates**, unrelated to JWT auth wiring |
| 6/15 | `60e6236` | Merge `sprint3/mvp-launch` (containing b2e30a1 + 416164c) → main | Sprint 4 lands in production 12 days after its commit |
| 6/16 | `4c9cba1`, `c78165c`, `8e77c96`, `4ff38b2`, `5715b85`, `4d460df`, `b45fcfc`, `727d631`, `515db86` | 9 PR fixes — ruff/mypy/datetime/test-fixture (PR #4–#13) | CI green |
| 6/17 | `8bd2911` | main HEAD = `8bd2911`, `.project-memory.md` updated to "Sprint 1-4 全部 ✅ 完成" | declared complete without end-to-end verification |
| 6/17–6/30 | — | **14-day silent gap — no board activity, no deployment** | step 6 (user verify) **still** not triggered |
| **7/1** | — | **jerry trials production deployment → all business APIs 401/403, `GET /` 404** | bug surfaces **after** Sprint 4 declared ✅ |

> **Visual gap**: a red bar from **5/29 to 6/17** spans three distinct process holes — (a) Sprint 4 commit on 6/3 with no parent task; (b) 11 days of no review/test/PM activity; (c) 14 days between "declared done" and first user trial. Total elapsed from Sprint 3 close to user verification: **33 days**.

---

## 2. Evidence (verified from git / codebase / commit messages)

### 2.1 Sprint 4 has no board parent

- `b2e30a1` commit message references `(#t_f0d2773e)` — `kanban_show t_f0d2773e` returns `task_not_found`.
- No `Sprint 4` parent task exists on the board.
- No sub-tasks exist for the three obvious work items a JWT auth change requires:
  1. Login endpoint (e.g. `POST /auth/login` → returns JWT)
  2. Static file mount for `web/dist` so the Vue UI loads
  3. End-to-end test covering login → call protected endpoint

### 2.2 The shipped code is structurally incomplete

```
$ grep -rn "login\|/auth" src/api/   # → no matches
$ grep -rn "app.mount\|StaticFiles" main.py src/   # → no matches
$ ls web/dist/                        # → index.html + assets/ exist (built)
$ cat main.py                         # → no app.mount("/") anywhere
```

- `src/utils/security.py` defines `require_auth` (added in `b2e30a1`) and uses `HTTPBearer` to reject unauthenticated requests with 401.
- `src/api/handlers/{admin,role,role_task,task,wechat_message}.py` all gained the `dependencies=[Depends(require_auth)]` router-level gate.
- **But no handler anywhere in `src/api/` accepts credentials and mints a token.**
- **`main.py` has no `StaticFiles` mount.** `web/dist/index.html` is built (npm run build, 45 modules) and shipped in the repo, but FastAPI never serves it.

### 2.3 The test suite caught it — and was patched around instead of fixed

`tests/integration_tests/test_wechat_task_flow.py::TestTaskCreationPush` went from passing (Sprint 3) to **0/4 → 4/4 only after** commit `4d460df` (2026-06-16, by jerry himself, PR #8) added:

```python
app.dependency_overrides[require_auth] = lambda: {"sub": "test-user"}
```

The commit message is candid: *"Sprint 4 added require_auth as a router-level dependency on /tasks. The TestTaskCreationPush fixture mocked only get_task_service, so the auth dependency short-circuited with 401 before the mock service was ever called."*

The fix unblocks the test by **bypassing auth entirely in the test fixture**. Nothing in the codebase provides a real way to authenticate.

### 2.4 The reviews that did happen could not have caught this

| Review layer | What it reviewed | Why it missed the gap |
|---|---|---|
| **OpenCode 对比评审** `t_93a4c98f` (6/14, 11 days after commit) | The code **delta** in `b2e30a1` (security.py + handler dependency lines) | Did not check whether `require_auth` is satisfiable in production, i.e. whether a login endpoint exists |
| **CI (ruff + mypy + pytest)** (6/16–6/17, PR #4–#13) | Static analysis + unit tests | `pytest` does not exercise the deployed HTTP path; CI green after `4d460df` overrides auth in fixtures |
| **code-reviewer `t_92fd6e88`** (6/15) | Web UI RBAC permission gates in Vue components | Different layer entirely — frontend button gating, not backend auth wiring |
| **test-lead** | Unit + golden dataset + integration suite | After `4d460df`, all tests pass; nothing tests the "user gets a token" flow because no such flow exists |
| **product-manager (PM)** | Roadmap/PRD-level acceptance | No PRD was written for Sprint 4 (no parent task to attach it to) |

### 2.5 The process definition already says step 6 must run

From `.project-memory.md` ("团队通用流程 / 开发阶段"):

> 1. developer / mobile-developer 开发
> 2. code-reviewer code review
> 3. test-lead 测试验证
> 4. product-manager 确认
> 5. developer 编译部署安装本地 commit
> 6. **用户验证通过**
> 7. developer push 远程

Steps 2–6 were skipped for Sprint 4. Step 7 (push to remote) is the only one that ran — and it ran as part of the Sprint 3 merge.

### 2.6 "done" in practice means "commit + CI green"

The current operational definition of `done` on the board is **commit landed on main + CI green + summary written**. This is a code-level definition; it does not include:

- A working entry path (login endpoint for auth-gated APIs)
- A serving path (static files for the Web UI)
- A user-verified end-to-end smoke

That is why "Sprint 1-4 全部 ✅ 完成" was committed to `.project-memory.md` on 6/17 with the system actually broken.

---

## 3. Root Cause Analysis (5 Whys)

| # | Why | Answer |
|---|---|---|
| 1 | Why does production 401/404? | No login endpoint + no static file mount |
| 2 | Why was it shipped without those? | Sprint 4 was scoped to "add JWT dependency" only — the **entry path was not part of the commit** |
| 3 | Why was the scope cut that way? | No parent task / no PRD / no review — the developer chose scope unilaterally on 6/3 |
| 4 | Why did no parent task exist? | Sprint 4 was not formally planned. `.project-memory.md` on 6/3 lists no Sprint 4 entry. Sprint 3 declared itself "MVP final deliverables" on 5/29; Sprint 4 appeared as a 12-day-later addition to `sprint3/mvp-launch` |
| 5 | Why was no one tracking this? | **The process defines 7 steps but has no enforcement mechanism**: no required fields on the board card, no deadline on step 6 (user verify), no rule that "Sprint X+1 commit must have a parent task or it doesn't land" |

**True root cause**: the team treats "the process" as a checklist of who reviews what, but the **gate between step 5 (local commit) and step 7 (push)** is unenforced. The implicit assumption is "if there's a commit, there must have been a parent task"; the Sprint 4 commit disproves that assumption.

---

## 4. Answers to the Six Questions

### Q1 — Why did Sprint 4 bypass kanban?

Three plausible causes, in order of likelihood:

1. **Sprint 4 was never formally planned.** Sprint 3 declared "MVP final deliverables" on 5/29; Sprint 4 was added to `sprint3/mvp-launch` on 6/3 as a post-hoc addition. No Sprint 4 parent task was ever created on the board.
2. **The developer added a "small change" without raising a task.** A `require_auth` dependency looks like a 1-line router change per handler; from the developer's perspective it was a tightening of existing Sprint 3 work, not new scope.
3. **No rule explicitly requires a parent task for every commit.** `.project-memory.md` defines steps for development, not for change-intake. Sprint 4 fell into a gap between "MVP done" and "Sprint 5 planning".

### Q2 — What is the right definition of "done"?

**Today**: commit on main + CI green + summary written. **Insufficient**, because it can't see semantic gaps like "no entry path".

**Proposed**: `done` requires **all four** of:
1. Code commits + CI green
2. Acceptance criteria explicitly satisfied (linked to PRD or task body)
3. **End-to-end smoke evidence**: a curl/playwright/manual screenshot showing the user can actually do the thing the feature claims to enable
4. **User verification (step 6)**: confirmed by jerry in the task thread, not by the developer self-declaring

### Q3 — Why did step 6 (user verification) never trigger?

- The process defines step 6 but **no one is named responsible** for reminding jerry to verify.
- "Done" was set automatically by commit-merge, not by step 6 completion.
- The developer never asked jerry to verify; jerry didn't check because the board said "Sprint 1-4 全部 ✅ 完成" (on 6/17).

### Q4 — Task granularity

Sprint 4 was a single 9-file commit touching every API surface. It should have been at minimum three sub-tasks:

1. **`Sprint 4.1` — Login endpoint**: `POST /auth/login`, token mint, password verify (uses existing `pwd_context`), test coverage.
2. **`Sprint 4.2` — Auth gate on protected routes**: `require_auth` as FastAPI dependency, applied router-by-router with **per-router rollout** (start with `/admin` only, then expand).
3. **`Sprint 4.3` — Static mount + Web UI token flow**: `app.mount("/", StaticFiles(...))`, frontend `Authorization: Bearer` header, refresh logic, E2E test.

Splitting forces each sub-task to define its own acceptance criteria — login can't pass without a login endpoint, etc. The bundle-as-one-commit approach hid the gaps.

### Q5 — Which review layer should have caught it?

| Layer | Could have caught it? | Why it didn't |
|---|---|---|
| **OpenCode 对比评审** | **Yes** — strongest candidate | Reviewed the code delta but not the surrounding context. Should have asked: "Where does a user get a token?" |
| **code-reviewer** | Possibly — if asked to review "JWT auth implementation", not "this commit" | Review was scoped to PRs in a narrow window and didn't include the whole auth surface |
| **test-lead** | No — tests passed with `4d460df` fixture override; nothing tested "user can authenticate" because no login endpoint existed | Test scope followed code scope; both were too narrow |
| **PM** | **Yes** — PRD-level review should have asked: "What is the user's journey from login to using a protected endpoint?" | No PRD existed for Sprint 4 |
| **CI** | No — linters don't see semantic gaps | Static analysis has a floor |

**Conclusion**: The gap was at the **PM layer**. A PRD written before the commit would have made "no login endpoint" a blocker at planning time, not 28 days later at deployment time. The OpenCode review could have been second-line defense.

### Q6 — Process improvement recommendations (next section)

---

## 5. Process Improvement Recommendations

> Each recommendation includes: **what to change**, **why**, **owner** (who decides + who implements), **deadline**, and **how to verify**. Recommendations are ordered by impact / cost ratio.

### R1 — Enforce "no parent task → no commit lands on main"

- **What**: Add a CI check (or pre-merge hook) that scans commit messages on PRs targeting `main` and rejects commits whose message contains `(#t_*)` where the task ID does not exist on the board, **or** whose task has no `parent` of type "Sprint N".
- **Why**: This is the cheapest, most local rule that would have caught Sprint 4. The reference `t_f0d2773e` literally did not exist.
- **Owner**: product-manager (decision) + sre (implementation: pre-merge hook in `.github/workflows/`)
- **Deadline**: 2026-07-15 (2 weeks)
- **Verify**: A test PR with a fictional task ID is rejected by CI; a PR with a real task ID passes.

### R2 — `done` requires explicit end-to-end evidence field

- **What**: Extend the board schema with a required field `e2e_evidence` (URL to screenshot / curl log / Playwright trace / manual note) on every card that moves to `done`. PM cannot mark `done` without it being filled.
- **Why**: A `require_auth` change has zero value without a way to satisfy it; "CI green + tests pass" is not enough signal.
- **Owner**: product-manager (process) + sre (board schema migration, if board is custom) or `hermes kanban` config
- **Deadline**: 2026-07-22 (3 weeks)
- **Verify**: Try to mark any task `done` without `e2e_evidence` — board refuses.

### R3 — Every Sprint requires an "Integration Verification" sub-task before done

- **What**: As part of sprint planning (Sprint N+1 onwards), create a Sprint N integration task whose acceptance criterion is: "user can complete the entire happy path of Sprint N in a deployed environment, with evidence attached". This task blocks Sprint N+1 from starting.
- **Why**: Sprint 3 declared "MVP final deliverables" but never verified that the UI could talk to the API after Sprint 4 added the gate. An explicit integration task is the forcing function.
- **Owner**: product-manager (creates task during sprint planning) + jerry (executes the verification)
- **Deadline**: 2026-07-08 (next Sprint 5 kickoff) — first integration task created for Sprint 5
- **Verify**: Sprint 5 plan on the board contains `t_<...> — Sprint 5 integration verification` with `parents=[all sprint 5 sub-tasks]`.

### R4 — "User verification" step gets a deadline and an auto-block

- **What**: After step 5 (developer commits locally), the system starts a 5-business-day timer. If jerry has not marked "user verified" in the task thread by then, the task is auto-blocked and a reminder is sent. Push (step 7) is gated on step 6.
- **Why**: Sprint 4 was unverified for 33 days; the missing forcing function is a deadline.
- **Owner**: product-manager (rule) + sre (cron + Hermes Kanban integration)
- **Deadline**: 2026-08-01 (4 weeks)
- **Verify**: A task that is `done` on the board but has no "user verified" comment older than 5 business days → auto-blocked; manually verify by force-aging one task.

### R5 — PM owns a "feature completeness" pre-merge checklist

- **What**: Before any commit that adds a runtime gate (auth, rate limit, middleware, dependency injection), PM reviews: (a) what is the entry path? (b) what is the verification path? (c) what existing flows does this break and how are they updated? Check is recorded as a PR comment.
- **Why**: The OpenCode review can catch code-level issues; PM-level review catches product-level issues (e.g. "this blocks the login flow that doesn't exist yet").
- **Owner**: product-manager
- **Deadline**: Effective immediately (no code change needed; PM behavior change for the next PR that touches a middleware)
- **Verify**: The next PR that adds a FastAPI dependency includes a PM comment with the three answers; absence is flagged in retro.

### R6 — Retro cadence: every Sprint close writes a post-mortem into `docs/post-mortem/`

- **What**: At Sprint close, product-manager writes a `sprint<N>-retro.md` (or `sprint<N>-process-gap.md` if a gap occurred) covering: what worked, what didn't, what to change next Sprint. This file is committed in the same merge that closes the Sprint.
- **Why**: This post-mortem exists because we shipped a broken system; the practice should be normalized. Without a written retro, lessons stay in chat and don't compound.
- **Owner**: product-manager
- **Deadline**: 2026-07-08 (next Sprint 5 kickoff)
- **Verify**: `docs/post-mortem/` contains at least one file per closed Sprint going forward.

### R7 — Surface "small change" threshold for tasks

- **What**: Any PR/commit that touches > 3 files OR modifies any middleware/auth/dependency/router requires a board task, regardless of perceived size. Code-reviewer flags PRs that lack a `(#t_*)` reference and rejects them.
- **Why**: Sprint 4 was 9 files but felt "small" because the change was a 1-line router attribute per file. The file count is the better proxy for review surface area.
- **Owner**: product-manager (rule) + code-reviewer (enforcement in PR review)
- **Deadline**: 2026-07-15
- **Verify**: A PR without a task ID touching > 3 files is rejected at review.

---

## 6. Acceptance & Sign-off

This document answers jerry's six questions with evidence and proposes seven concrete improvements. **The improvements are recommendations only** — implementing them requires jerry's decision and likely updates to `.project-memory.md`, which is explicitly out of scope for this task. The follow-up task `t_62fcab87` will handle that update once jerry approves which R-items to adopt.

## 7. Appendix — Quick Reference

### Files referenced

| File | Relevance |
|---|---|
| `main.py` | No `StaticFiles` mount; no auth router |
| `src/utils/security.py` | Added `require_auth` (Sprint 4) — no login mint |
| `src/api/handlers/*.py` | All gained `require_auth` dependency (Sprint 4) |
| `tests/integration_tests/test_wechat_task_flow.py` | `TestTaskCreationPush` fixture override added 6/16 |
| `web/dist/index.html` | Built but not served |
| `.project-memory.md` | Defines the 7-step dev process (step 6 = user verify) |
| `docs/mvp-integration-test-report.md` | Sprint 3 close evidence (predates Sprint 4) |

### Commits referenced

| Commit | Date | Role |
|---|---|---|
| `662ea27` | 5/29 | Sprint 3 "MVP final deliverables" — last good state |
| **`b2e30a1`** | **6/3** | **Sprint 4 JWT auth gate (referenced missing `t_f0d2773e`)** |
| `416164c` | 6/15 | Web UI RBAC fix (separate concern) |
| `60e6236` | 6/15 | Sprint 3/4 merge into main |
| `4d460df` | 6/16 | Test fixture auth override (papering over) |
| `8bd2911` | 6/17 | main HEAD — CI green, system broken |