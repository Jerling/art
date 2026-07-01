/**
 * Auth utility for the Art web UI.
 *
 * Responsibilities:
 *  - Persist the JWT bearer token in localStorage (key: ``art_auth_token``)
 *  - Provide ``authFetch`` — a thin wrapper around ``fetch`` that
 *    auto-injects ``Authorization: Bearer <token>`` on every request
 *  - Convert 401 responses into a single ``auth:expired`` window event
 *    so the router can react and bounce the user to /login
 *  - Expose ``login`` / ``logout`` / ``getCurrentUser`` helpers that
 *    hit ``/api/v1/auth/login`` and ``/api/v1/auth/me``
 *
 * The window event pattern avoids a circular import between this
 * module and the router: this file does not import the router, the
 * router subscribes to the event.
 */

export const TOKEN_KEY = 'art_auth_token'
export const USER_KEY = 'art_auth_user'
export const AUTH_EXPIRED_EVENT = 'art:auth:expired'

/* ── Token storage ────────────────────────────────────────────────── */

/** @returns {string|null} */
export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch (_) {
    return null
  }
}

/** @param {string} token */
export function setToken(token) {
  try {
    localStorage.setItem(TOKEN_KEY, token)
  } catch (_) {
    /* ignore quota / privacy errors */
  }
}

export function clearToken() {
  try {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  } catch (_) {
    /* ignore */
  }
}

/** @returns {boolean} */
export function isAuthenticated() {
  return !!getToken()
}

/* ── User info cache (for navbar) ────────────────────────────────── */

/** @returns {{ id: number, username: string, is_admin: boolean }|null} */
export function getCachedUser() {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch (_) {
    return null
  }
}

/** @param {{ id: number, username: string, is_admin: boolean }|null} user */
export function setCachedUser(user) {
  try {
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user))
    else localStorage.removeItem(USER_KEY)
  } catch (_) {
    /* ignore */
  }
}

/* ── authFetch: fetch with auto-injected Authorization header ────── */

/**
 * Drop-in replacement for ``fetch`` that:
 *   - prepends ``Authorization: Bearer <token>`` when a token is stored
 *   - propagates any custom headers passed in
 *   - on a 401 response, clears the token and dispatches an
 *     ``AUTH_EXPIRED_EVENT`` so the router can navigate to /login
 *
 * @param {string} url
 * @param {RequestInit} [init]
 * @returns {Promise<Response>}
 */
export async function authFetch(url, init = {}) {
  const headers = new Headers(init.headers || {})
  const token = getToken()
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  const res = await fetch(url, { ...init, headers })

  if (res.status === 401) {
    // Only treat as expired if we actually had a token — a 401 on the
    // unauthenticated login endpoint is a normal "wrong password" case.
    if (token) {
      clearToken()
      try {
        window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT))
      } catch (_) {
        /* SSR / non-DOM */
      }
    }
  }
  return res
}

/* ── High-level auth helpers ─────────────────────────────────────── */

/**
 * @param {string} username
 * @param {string} password
 * @returns {Promise<{ access_token: string, token_type: string, expires_in: number }>}
 */
export async function login(username, password) {
  const res = await fetch('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) {
    let detail = `Login failed: ${res.status}`
    try {
      const err = await res.json()
      if (err?.detail) detail = err.detail
    } catch (_) {
      /* not JSON */
    }
    throw new Error(detail)
  }
  const data = await res.json()
  setToken(data.access_token)
  return data
}

/**
 * Fetch the currently authenticated user from the introspection
 * endpoint.  Uses the cached value as a quick first-paint source
 * when the network call fails (e.g. offline).
 *
 * @returns {Promise<{ id: number, username: string, is_admin: boolean }|null>}
 */
export async function getCurrentUser() {
  try {
    const res = await authFetch('/api/v1/auth/me')
    if (!res.ok) {
      // 401 was already handled by authFetch (token cleared + event fired)
      return getCachedUser()
    }
    const user = await res.json()
    setCachedUser(user)
    return user
  } catch (_) {
    return getCachedUser()
  }
}

/** Clear local auth state and notify the router. */
export function logout() {
  clearToken()
  try {
    window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT))
  } catch (_) {
    /* ignore */
  }
}
