<script setup>
import { ref, watch, onMounted } from 'vue'
import { useRoleStore } from '../stores/role.js'
import { useRouter, useRoute } from 'vue-router'
import { listRoles } from '../api/roles.js'

const roleStore = useRoleStore()
const router = useRouter()
const route = useRoute()

const roles = ref([])
const loading = ref(true)
const mobileMenuOpen = ref(false)

onMounted(async () => {
  try {
    const data = await listRoles({ page: 1, page_size: 100 })
    roles.value = data.items || []
    roleStore.roles = roles.value
    roleStore.syncCurrentRole()
  } catch (e) {
    console.warn('Failed to load roles:', e.message)
  } finally {
    loading.value = false
  }
})

function selectRole(roleId, roleObj) {
  roleStore.setCurrentRoleId(roleId, roleObj)
  mobileMenuOpen.value = false
}

function clearRole() {
  roleStore.clearCurrentRole()
  mobileMenuOpen.value = false
}

function navigateTo(path) {
  router.push(path)
  mobileMenuOpen.value = false
}

function toggleMobileMenu() {
  mobileMenuOpen.value = !mobileMenuOpen.value
}

// Role label for the current selection
const currentLabel = 'Perspective'
</script>

<template>
  <nav class="nav-header">
    <div class="nav-inner">
      <!-- Brand / Logo -->
      <div class="nav-brand" @click="navigateTo('/tasks')">
        <span class="brand-icon">◈</span>
        <span class="brand-text">ArtBoard</span>
      </div>

      <!-- Desktop Nav Links -->
      <div class="nav-links">
        <router-link to="/tasks" class="nav-link" :class="{ active: route.path.startsWith('/tasks') }">
          Tasks
        </router-link>
        <router-link to="/roles" class="nav-link" :class="{ active: route.path === '/roles' }">
          Roles
        </router-link>
      </div>

      <!-- Desktop Role Switcher -->
      <div class="nav-perspective">
        <span class="perspective-label">View as</span>
        <div class="perspective-selector">
          <button
            class="perspective-btn"
            :class="{ active: !roleStore.hasRole }"
            @click="clearRole"
            title="Show all tasks"
          >
            All
          </button>
          <button
            v-for="role in roles"
            :key="role.id"
            class="perspective-btn"
            :class="{ active: roleStore.currentRoleId === role.id }"
            @click="selectRole(role.id, role)"
            :title="`Filter by ${role.name}`"
          >
            {{ role.name }}
          </button>
        </div>
      </div>

      <!-- Mobile Menu Toggle -->
      <button class="hamburger" @click="toggleMobileMenu" :aria-label="mobileMenuOpen ? 'Close menu' : 'Open menu'">
        <span class="hamburger-line" :class="{ open: mobileMenuOpen }"></span>
        <span class="hamburger-line" :class="{ open: mobileMenuOpen }"></span>
        <span class="hamburger-line" :class="{ open: mobileMenuOpen }"></span>
      </button>
    </div>

    <!-- Mobile Menu -->
    <div v-if="mobileMenuOpen" class="mobile-menu">
      <div class="mobile-nav-links">
        <button class="mobile-nav-link" :class="{ active: route.path.startsWith('/tasks') }" @click="navigateTo('/tasks')">
          📋 Tasks
        </button>
        <button class="mobile-nav-link" :class="{ active: route.path === '/roles' }" @click="navigateTo('/roles')">
          👥 Roles
        </button>
      </div>
      <div class="mobile-perspective">
        <div class="mobile-perspective-label">View as</div>
        <button
          class="mobile-perspective-btn"
          :class="{ active: !roleStore.hasRole }"
          @click="clearRole"
        >
          👁 All Tasks
        </button>
        <button
          v-for="role in roles"
          :key="role.id"
          class="mobile-perspective-btn"
          :class="{ active: roleStore.currentRoleId === role.id }"
          @click="selectRole(role.id, role)"
        >
          {{ role.name }}
        </button>
      </div>
    </div>
  </nav>
</template>

<style scoped>
.nav-header {
  position: sticky;
  top: 0;
  z-index: 50;
  background: var(--bg);
  border-bottom: 1px solid var(--border);
  backdrop-filter: blur(8px);
}

.nav-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 20px;
  height: 52px;
  display: flex;
  align-items: center;
  gap: 24px;
}

.nav-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  flex-shrink: 0;
  user-select: none;
}

.brand-icon {
  font-size: 20px;
  color: var(--accent);
}

.brand-text {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-h);
  letter-spacing: -0.3px;
}

.nav-links {
  display: flex;
  gap: 4px;
}

.nav-link {
  padding: 6px 12px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
  text-decoration: none;
  border-radius: 6px;
  transition: background 0.15s, color 0.15s;
}

.nav-link:hover {
  background: var(--social-bg);
  color: var(--text-h);
}

.nav-link.active {
  background: var(--accent-bg);
  color: var(--accent);
  font-weight: 600;
}

/* ── Perspective Switcher ───────────────────────────────────────────────── */
.nav-perspective {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

.perspective-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text);
  font-weight: 600;
}

.perspective-selector {
  display: flex;
  gap: 2px;
  background: var(--social-bg);
  border-radius: 8px;
  padding: 2px;
  border: 1px solid var(--border);
}

.perspective-btn {
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text);
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-family: inherit;
  white-space: nowrap;
  transition: all 0.15s;
}

.perspective-btn:hover {
  color: var(--text-h);
}

.perspective-btn.active {
  background: var(--bg);
  color: var(--accent);
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

/* ── Hamburger ──────────────────────────────────────────────────────────── */
.hamburger {
  display: none;
  flex-direction: column;
  gap: 4px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 6px;
  margin-left: auto;
}

.hamburger-line {
  display: block;
  width: 20px;
  height: 2px;
  background: var(--text-h);
  border-radius: 2px;
  transition: all 0.2s;
}

.hamburger-line.open:nth-child(1) {
  transform: rotate(45deg) translate(4px, 4px);
}

.hamburger-line.open:nth-child(2) {
  opacity: 0;
}

.hamburger-line.open:nth-child(3) {
  transform: rotate(-45deg) translate(4px, -4px);
}

/* ── Mobile Menu ────────────────────────────────────────────────────────── */
.mobile-menu {
  display: none;
  padding: 8px 20px 16px;
  border-top: 1px solid var(--border);
  background: var(--bg);
}

.mobile-nav-links {
  display: flex;
  gap: 4px;
  margin-bottom: 12px;
}

.mobile-nav-link {
  flex: 1;
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  font-family: inherit;
}

.mobile-nav-link.active {
  background: var(--accent-bg);
  color: var(--accent);
  border-color: var(--accent-border);
  font-weight: 600;
}

.mobile-perspective-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text);
  font-weight: 600;
  margin-bottom: 6px;
}

.mobile-perspective {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.mobile-perspective-btn {
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text);
  background: var(--social-bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  font-family: inherit;
}

.mobile-perspective-btn.active {
  background: var(--accent-bg);
  color: var(--accent);
  border-color: var(--accent-border);
  font-weight: 600;
}

/* ── Responsive ─────────────────────────────────────────────────────────── */
@media (max-width: 768px) {
  .nav-links { display: none; }
  .nav-perspective { display: none; }
  .hamburger { display: flex; }
  .mobile-menu { display: block; }
}

@media (min-width: 769px) {
  .mobile-menu { display: none !important; }
}
</style>
