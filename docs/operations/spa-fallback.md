# SPA fallback — manual smoke test & SRE runbook

## Problem

Art's FastAPI backend (port `8000`) serves both the REST API (`/api/v1/*`)
and the Vue SPA built artifact (`web/dist/`).  Vue Router uses HTML5 history
mode, so a browser hard-refresh on a deep path like `/login`, `/tasks`,
`/roles`, `/tasks/kanban` lands on the backend as a **request for that
exact path** — but no router matches it.  What happens next depends on the
path:

| Path shape                         | Matches                            | Backend response         | SPA boots? |
|------------------------------------|------------------------------------|--------------------------|------------|
| `/login` (no API route)            | nothing → `StaticFiles` 404        | JSON `{"detail":...}`   | ❌         |
| `/tasks`, `/roles`, `/messages/*`  | Sprint-1 router prefix + `require_auth` | JSON 401              | ❌         |
| `/some-random-spa-path`            | nothing → `StaticFiles` 404        | JSON `{"detail":...}`   | ❌         |

In all three cases the browser receives a JSON error body, vue-router
can't bootstrap (the SPA shell never arrives), and the user sees a blank
page.  This was the root cause of Jerry's report "Failed to list task
错误"—the Web UI was completely unusable.

Why this wasn't caught at Sprint 4 close-out (`t_0e04abde`, commit `6588dcd`):
the decision log flagged the limitation that
`StaticFiles(directory="web/dist", html=True)` only handles **directory**
fallback (`/tasks/` → `index.html`), NOT extensionless deep paths
(`/tasks` → 404).  But the flag wasn't promoted to a blocker, so the
follow-up was never created.

## Fix (task `t_a6893d76`)

`main.py` now registers **two** Starlette exception handlers in addition
to the existing `StaticFiles` mount:

1. `@app.exception_handler(404)` — converts unmatched SPA paths to
   `web/dist/index.html` (`200 OK`, `text/html`).
2. `@app.exception_handler(401)` — converts auth-required SPA paths to
   `web/dist/index.html` so vue-router can run its own client-side
   `isAuthenticated()` guard and redirect to `/login`.

Both handlers share a helper `_is_spa_path(request, require_no_auth_header=...)`
that returns `True` ONLY when the path is **not**:

- `/api/*`, `/docs/*`, `/redoc/*`, `/openapi.json`, `/metrics`, `/health/*`
- a static asset (last URL segment contains a dot, e.g. `/favicon.ico`)
- (for 401 only) carrying an `Authorization` header — which means it's an
  authenticated API call from `authFetch` and **must** see JSON so
  `auth.js` can dispatch `AUTH_EXPIRED_EVENT` and bounce to `/login`.

Without that `Authorization` check, the SPA's own `authFetch('/tasks')`
calls (which carry the JWT) would be silently rewritten to HTML and the
auth-expired redirect handler in `web/src/utils/auth.js` would never
fire.  See the comment block above the handlers in `main.py` for the
full rationale.

## Verification (re-run after every change to `main.py`)

Prereq: uvicorn running with the current `main.py`:

```bash
cd /home/jer/data/Code/art
source .venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 8000
```

Prereq: seeded admin user (one-time):

```bash
python -m scripts.seed_admin   # creates admin/admin if missing
```

### 1. w3m dump — response must be HTML

`w3m -dump` is intentionally used because it doesn't run JavaScript, so
the only way to confirm the SPA shell is being served is to inspect the
**raw response body**.  The expected body is `web/dist/index.html` —
14 lines, no visible text content (the SPA mounts into `<div id="app">`
at runtime).  `w3m -dump` may render empty for this reason, even when
the fix is correct.  Verify via `curl`:

```bash
$ curl -s -o /tmp/login_body -w "HTTP %{http_code} | %{content_type}\n" \
    http://127.0.0.1:8000/login
HTTP 200 | text/html; charset=utf-8

$ head -1 /tmp/login_body
<!doctype html>
```

Required w3m/curl checks (all four must return `200 + text/html`):

```bash
w3m -dump http://127.0.0.1:8000/login     # ✓ returns index.html
w3m -dump http://127.0.0.1:8000/tasks     # ✓ returns index.html (was 401 pre-fix)
w3m -dump http://127.0.0.1:8000/          # ✓ returns index.html
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
     -H 'Content-Type: application/json' \
     -d '{"username":"admin","password":"admin"}' \
     -w 'HTTP %{http_code}\n'
# ✓ HTTP 200 + {"access_token": "..."}
```

### 2. Negative checks — real errors MUST keep their JSON

```bash
curl -s -w "\nHTTP %{http_code}\n" \
  http://127.0.0.1:8000/api/v1/auth/me
# ✓ HTTP 401 | application/json | {"detail":"Authentication required"}

curl -s -w "\nHTTP %{http_code}\n" \
  http://127.0.0.1:8000/api/v1/tasks
# ✓ HTTP 404 | application/json | {"detail":"Not Found"}

curl -s -w "\nHTTP %{http_code}\n" \
  http://127.0.0.1:8000/favicon.ico
# ✓ HTTP 404 | application/json | {"detail":"Not Found"}

curl -s -w "\nHTTP %{http_code}\n" \
  http://127.0.0.1:8000/missing.png
# ✓ HTTP 404 | application/json | {"detail":"Not Found"}
```

### 3. authFetch / API shape — JWT-bearing calls keep JSON

This is the critical distinguisher.  With the JWT attached, the SPA's
own fetch calls must NOT be rewritten to HTML:

```bash
TOK=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
        -H 'Content-Type: application/json' \
        -d '{"username":"admin","password":"admin"}' \
      | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

curl -s -H "Authorization: Bearer $TOK" \
     -w "\nHTTP %{http_code} | %{content_type}\n" \
     http://127.0.0.1:8000/tasks?page=1\&page_size=10
# ✓ HTTP 200 | application/json   (NOT text/html)
```

With a bad token, the response must still be JSON 401:

```bash
curl -s -H "Authorization: Bearer *** 'http://127.0.0.1:8000/tasks?page=1&page_size=10'
# ✓ HTTP 401 | application/json
```

### 4. End-to-end browser flow

1. Open `http://127.0.0.1:8000/login` in a fresh browser (no token in
   `localStorage`).  You should see the Art Board login form with a
   "Use default admin credentials" button.
2. Open `http://127.0.0.1:8000/tasks` directly.  URL should change to
   `/login?next=/tasks` (vue-router auth guard ran).  Login form visible.
3. Click "Use default admin credentials" then "Sign in".  URL should
   change to `/tasks`, header should read "Tasks 0" with empty-state
   message "No tasks yet. Create one!".

## Out of scope, but observed

After login, the `/tasks` page renders with a transient pink `[object
Object]` banner.  Tracing shows this is a **pre-existing frontend
bug**, unrelated to the SPA fallback:

- `web/src/views/TasksView.vue:143` calls `listTasks({ page: 1, page_size: 200 })`
  — but `task_router.list_tasks` has `page_size: int = Query(100, le=100)`,
  so the backend returns `HTTP 422` with `detail` as a validation-error
  list, not a string.
- `web/src/api/tasks.js:31` does
  `throw new Error(await _err(res, ...))` where `_err` returns
  `data.detail` verbatim.
- `TasksView.vue:147` does `error.value = e.message`, so the array
  ends up in `error.value`.
- Vue's `{{ error }}` interpolation tostringifies the array to
  `[object Object]`.

Fix: clamp `page_size` to `100` in `listTasks()` callers, and have `_err`
`String(data.detail)` before returning.  Should be tracked as a separate
task (out of scope for `t_a6893d76` per the PM's "不动前端代码" guard).

## Decision log update (Sprint 4 retro R3)

The Sprint 4 retro comment on `t_0e04abde` decision #4 read:

> "Acceptable for now; flag as follow-up."

Going forward, R3 says: if a Sprint close-out declares something
"acceptable for now" but the follow-up never gets created, treat it as
a blocker at the next Integration Verification step.  This fallback
could have shipped with the Web UI in Sprint 4 if the follow-up had been
queued — instead it became P0 a day later.  Use `w3m -dump` against SPA
paths in every Web UI integration verification run; if the response
isn't HTML, the SPA can't boot.

## File map

- `main.py` lines ~104–220 — exception handlers (`spa_fallback_404`,
  `spa_fallback_401`) + shared helpers (`_is_spa_path`, `_serve_index_html`).
- `docs/operations/spa-fallback.md` — this file.
- `web/src/router/index.js` — vue-router guard that consumes the SPA
  shell and redirects to `/login` when `isAuthenticated()` is false.
- `web/src/utils/auth.js` — `authFetch` wrapper that dispatches
  `AUTH_EXPIRED_EVENT` on 401 (relies on JSON 401 responses, preserved
  by the `Authorization`-header check in the 401 handler).
