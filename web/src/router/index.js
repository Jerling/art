import { createRouter, createWebHistory } from 'vue-router'
import { useRoleStore } from '../stores/role.js'
import { isAdmin } from '../utils/permissions.js'
import { isAuthenticated, AUTH_EXPIRED_EVENT } from '../utils/auth.js'

const FLASH_KEY = 'art_route_flash'

/** Persist a one-shot toast for the next page to display. */
function setFlash(message, type = 'info') {
  try {
    localStorage.setItem(FLASH_KEY, JSON.stringify({ message, type, ts: Date.now() }))
  } catch (_) {
    /* ignore quota / privacy errors */
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/tasks',
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { requiresAuth: false },
    },
    {
      path: '/roles',
      name: 'roles',
      component: () => import('../views/RolesView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/tasks',
      name: 'tasks',
      component: () => import('../views/TasksView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/tasks/kanban',
      name: 'kanban',
      component: () => import('../views/KanbanBoard.vue'),
      meta: { requiresAuth: true },
    },
  ],
})

/**
 * Global auth guard.
 *
 *  - If the route requires auth and we have no token → /login (with
 *    a ``?next=`` so the user lands back where they tried to go).
 *  - If the route is /login and we *are* authenticated → bounce to
 *    /tasks so the user doesn't see the login form when already in.
 *  - For admin-only routes the existing role check still applies.
 *
 * The admin check is skipped when there's no token, because the
 * role store will fail to fetch and we'd rather send the user to
 * /login than to show a confusing "Admin only" flash.
 */
router.beforeEach((to) => {
  const authenticated = isAuthenticated()

  // Already-logged-in user hitting /login → home
  if (to.path === '/login' && authenticated) {
    return { path: '/tasks' }
  }

  // Unauthenticated user hitting a protected route → /login
  if (to.meta?.requiresAuth && !authenticated) {
    return { path: '/login', query: { next: to.fullPath } }
  }

  // Admin-only check — only relevant when authenticated
  if (to.meta?.requiresAdmin) {
    const roleStore = useRoleStore()
    // We don't await here because beforeEach is synchronous; the
    // role store hydrates from localStorage instantly, and the
    // Kanban/Tasks views also call ensureLoaded() for the actual
    // server fetch.
    if (!isAdmin(roleStore.currentRole)) {
      setFlash('Admin only — role management is restricted to administrators.', 'error')
      return { path: '/tasks' }
    }
  }

  return true
})

/**
 * Global 401 listener.
 *
 * The ``authFetch`` wrapper dispatches this event when it sees a 401
 * and clears the token.  We translate that into a route push to
 * /login with a flash message, but only when the user wasn't already
 * on the login page (so a wrong-password attempt doesn't loop).
 */
if (typeof window !== 'undefined') {
  window.addEventListener(AUTH_EXPIRED_EVENT, () => {
    const current = router.currentRoute.value
    if (current.path === '/login') return
    setFlash('Your session has expired. Please sign in again.', 'error')
    router.replace({
      path: '/login',
      query: { next: current.fullPath },
    })
  })
}

export { FLASH_KEY }
export default router
