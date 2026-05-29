<script setup>
import { onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useRoleStore } from '../stores/role.js'
import { listRoles } from '../api/roles.js'

const router = useRouter()
const route = useRoute()
const roleStore = useRoleStore()

const rolesLoading = ref(false)

/** Show a tooltip-like permission label for the current role */
function permissionLabel() {
  const p = roleStore.permissions
  if (p.canManageRoles) return 'Full Access'
  if (p.canCreate) return 'Read + Write'
  return 'Read Only'
}

function switchRole(roleId) {
  const role = roleStore.roles.find((r) => r.id === roleId)
  if (role) {
    roleStore.setCurrentRoleId(roleId, role)
  }
}

async function loadRoles() {
  rolesLoading.value = true
  try {
    const data = await listRoles({ page: 1, page_size: 100 })
    roleStore.roles = data.items || []
    roleStore.syncCurrentRole()
  } catch (e) {
    console.warn('Failed to load roles for nav:', e.message)
  } finally {
    rolesLoading.value = false
  }
}

onMounted(() => {
  if (!roleStore.roles.length) {
    loadRoles()
  }
})
</script>

<template>
  <nav class="navbar">
    <div class="navbar-inner">
      <!-- Brand -->
      <router-link to="/tasks" class="navbar-brand">
        <span class="brand-icon">📋</span>
        <span class="brand-text">Art Board</span>
      </router-link>

      <!-- Nav links -->
      <div class="navbar-links">
        <router-link
          to="/tasks"
          class="nav-link-item"
          :class="{ active: route.path.startsWith('/tasks') }"
        >
          Tasks
        </router-link>
        <router-link
          to="/roles"
          class="nav-link-item"
          :class="{ active: route.path.startsWith('/roles') }"
        >
          Roles
        </router-link>
      </div>

      <!-- Right side: role switcher -->
      <div class="navbar-right">
        <!-- Current role label -->
        <div v-if="roleStore.currentRole" class="current-role-label">
          <span class="role-dot" :style="{ background: roleStore.permissions.canManageRoles ? '#c084fc' : roleStore.permissions.canCreate ? '#22c55e' : '#9ca3af' }"></span>
          <span class="role-name">{{ roleStore.currentRole.name }}</span>
          <span class="role-perms-badge">{{ permissionLabel() }}</span>
        </div>

        <!-- Role selector dropdown -->
        <div class="role-selector">
          <select
            :value="roleStore.currentRoleId ?? ''"
            @change="switchRole(Number($event.target.value))"
            :disabled="rolesLoading || !roleStore.roles.length"
            class="role-select"
          >
            <option value="" disabled>
              {{ rolesLoading ? 'Loading…' : 'Select role…' }}
            </option>
            <option
              v-for="role in roleStore.roles"
              :key="role.id"
              :value="role.id"
            >
              {{ role.name }}
            </option>
          </select>
        </div>
      </div>
    </div>
  </nav>
</template>

<style scoped>
.navbar {
  position: sticky;
  top: 0;
  z-index: 90;
  background: var(--bg);
  border-bottom: 1px solid var(--border);
  backdrop-filter: blur(8px);
}

.navbar-inner {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 0 20px;
  height: 52px;
}

/* Brand */
.navbar-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  color: var(--text-h);
  font-weight: 700;
  font-size: 16px;
  flex-shrink: 0;
}

.brand-icon {
  font-size: 18px;
}

/* Nav links */
.navbar-links {
  display: flex;
  gap: 4px;
}

.nav-link-item {
  padding: 6px 12px;
  border-radius: 6px;
  text-decoration: none;
  color: var(--text);
  font-size: 14px;
  font-weight: 500;
  transition: background 0.15s, color 0.15s;
}

.nav-link-item:hover {
  background: var(--social-bg);
  color: var(--text-h);
}

.nav-link-item.active {
  background: var(--accent-bg);
  color: var(--accent);
  font-weight: 600;
}

/* Right side */
.navbar-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
}

.current-role-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.role-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.role-name {
  font-weight: 600;
  color: var(--text-h);
}

.role-perms-badge {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--social-bg);
  color: var(--text);
}

.role-select {
  padding: 5px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--text-h);
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  min-width: 140px;
}

.role-select:focus {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}

.role-select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
