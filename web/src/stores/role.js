import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const STORAGE_KEY = 'art_current_role_id'

/** Built-in permission groups based on role name conventions */
const BUILTIN_ROLE_PERMISSIONS = {
  admin: {
    name: 'Admin',
    canCreate: true,
    canEdit: true,
    canDelete: true,
    canAssign: true,
    canManageRoles: true,
  },
  member: {
    name: 'Member',
    canCreate: true,
    canEdit: true,
    canDelete: false,
    canAssign: true,
    canManageRoles: false,
  },
  visitor: {
    name: 'Visitor',
    canCreate: false,
    canEdit: false,
    canDelete: false,
    canAssign: false,
    canManageRoles: false,
  },
}

export const useRoleStore = defineStore('role', () => {
  /** @type {import('vue').Ref<number|null>} */
  const currentRoleId = ref(
    JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null')
  )

  /** Full role object of the currently selected role (populated after listRoles call) */
  /** @type {import('vue').Ref<object|null>} */
  const currentRole = ref(null)

  /** All roles loaded from the server */
  /** @type {import('vue').Ref<object[]>} */
  const roles = ref([])

  const hasRole = computed(() => currentRoleId.value !== null)

  /** Compute permissions from the current role name */
  const permissions = computed(() => {
    if (!currentRole.value) return { canCreate: false, canEdit: false, canDelete: false, canAssign: false, canManageRoles: false }
    const name = (currentRole.value.name || '').toLowerCase()
    // Match built-in groups first
    for (const [key, perms] of Object.entries(BUILTIN_ROLE_PERMISSIONS)) {
      if (name === key) return perms
    }
    // Fallback: unknown named roles get Member-level permissions
    return BUILTIN_ROLE_PERMISSIONS.member
  })

  /**
   * @param {number} id
   * @param {object} [roleObj] - pass if you already have the role object
   */
  function setCurrentRoleId(id, roleObj = null) {
    currentRoleId.value = id
    localStorage.setItem(STORAGE_KEY, JSON.stringify(id))
    if (roleObj) currentRole.value = roleObj
  }

  function clearCurrentRole() {
    currentRoleId.value = null
    currentRole.value = null
    localStorage.removeItem(STORAGE_KEY)
  }

  /** Call after loading roles to re-hydrate currentRole from the roles list */
  function syncCurrentRole() {
    if (currentRoleId.value === null) {
      currentRole.value = null
      return
    }
    currentRole.value = roles.value.find((r) => r.id === currentRoleId.value) ?? null
  }

  return {
    currentRoleId,
    currentRole,
    roles,
    hasRole,
    permissions,
    setCurrentRoleId,
    clearCurrentRole,
    syncCurrentRole,
  }
})
