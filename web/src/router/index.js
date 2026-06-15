import { createRouter, createWebHistory } from 'vue-router'
import { useRoleStore } from '../stores/role.js'
import { isAdmin } from '../utils/permissions.js'

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
      path: '/roles',
      name: 'roles',
      component: () => import('../views/RolesView.vue'),
      meta: { requiresAdmin: true },
    },
    {
      path: '/tasks',
      name: 'tasks',
      component: () => import('../views/TasksView.vue'),
    },
    {
      path: '/tasks/kanban',
      name: 'kanban',
      component: () => import('../views/KanbanBoard.vue'),
    },
  ],
})

/**
 * Admin-only guard for /roles: a non-admin (or no-role) user is redirected
 * back to /tasks with a flash message. The NavBar reads `art_route_flash`
 * from localStorage on mount and renders it as a toast.
 */
router.beforeEach(async (to) => {
  if (!to.meta?.requiresAdmin) return true

  const roleStore = useRoleStore()
  try {
    await roleStore.ensureLoaded()
  } catch (_) {
    /* fall through; currentRole will be null and we deny */
  }

  if (isAdmin(roleStore.currentRole)) return true

  setFlash('Admin only — role management is restricted to administrators.', 'error')
  return { path: '/tasks' }
})

export { FLASH_KEY }
export default router
