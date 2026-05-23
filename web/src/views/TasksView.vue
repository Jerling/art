<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoleStore } from '../stores/role.js'
import { useTaskStore } from '../stores/task.js'
import { listTasks, createTask, updateTask, deleteTask, updateTaskStatus } from '../api/tasks.js'

const roleStore = useRoleStore()
const taskStore = useTaskStore()

// ── State ────────────────────────────────────────────────────────────────────
const tasks = ref([])
const loading = ref(false)
const error = ref(null)
const successMsg = ref(null)

// Role filter — null means "all roles"
const filterRoleId = ref(null)

const showCreateModal = ref(false)
const formLoading = ref(false)
const formError = ref(null)

const confirmDelete = ref(null)

const editingTask = ref(null)
const showEditModal = ref(false)

// Status transition map
const NEXT_STATUSES = {
  PENDING: ['IN_PROGRESS', 'CANCELLED'],
  IN_PROGRESS: ['DONE', 'CANCELLED'],
  DONE: [],
  CANCELLED: [],
}

const STATUS_COLORS = {
  PENDING: { bg: '#f3f4f6', color: '#374151', dot: '#9ca3af' },
  IN_PROGRESS: { bg: '#dbeafe', color: '#1d4ed8', dot: '#3b82f6' },
  DONE: { bg: '#dcfce7', color: '#15803d', dot: '#22c55e' },
  CANCELLED: { bg: '#fee2e2', color: '#991b1b', dot: '#ef4444' },
}

const PRIORITY_COLORS = {
  LOW: '#6b7280',
  MEDIUM: '#d97706',
  HIGH: '#ea580c',
  URGENT: '#dc2626',
}

// ── Form ─────────────────────────────────────────────────────────────────────
const PRIORITIES = ['LOW', 'MEDIUM', 'HIGH', 'URGENT']
const STATUSES = ['PENDING', 'IN_PROGRESS', 'DONE', 'CANCELLED']

const form = ref({
  title: '',
  description: '',
  priority: 'MEDIUM',
  estimated_hours: '',
  role_ids: [],
})

function resetForm() {
  form.value = { title: '', description: '', priority: 'MEDIUM', estimated_hours: '', role_ids: [] }
  formError.value = null
}

function openCreate() {
  resetForm()
  showCreateModal.value = true
}

function openEdit(task) {
  editingTask.value = task
  form.value = {
    title: task.title,
    description: task.description ?? '',
    priority: task.priority,
    estimated_hours: task.estimated_hours ?? '',
    role_ids: [...task.role_ids],
  }
  formError.value = null
  showEditModal.value = true
}

function closeCreateModal() {
  showCreateModal.value = false
  resetForm()
}

function closeEditModal() {
  showEditModal.value = false
  editingTask.value = null
  resetForm()
}

function clearMessages() {
  error.value = null
  successMsg.value = null
}

// ── Role filter ───────────────────────────────────────────────────────────────
const roleFilterLabel = computed(() => {
  if (filterRoleId.value === null) return 'All Tasks'
  const role = roleStore.roles.find((r) => r.id === filterRoleId.value)
  return role ? role.name : 'All Tasks'
})

function setFilterRole(roleId) {
  filterRoleId.value = roleId
  fetchTasks()
}

function toggleRoleInForm(roleId) {
  const idx = form.value.role_ids.indexOf(roleId)
  if (idx === -1) {
    form.value.role_ids.push(roleId)
  } else {
    form.value.role_ids.splice(idx, 1)
  }
}

// ── API ───────────────────────────────────────────────────────────────────────
async function fetchTasks() {
  loading.value = true
  error.value = null
  try {
    const data = await listTasks({ page: 1, page_size: 200, role_id: filterRoleId.value })
    tasks.value = data.items
    taskStore.setTasks(data.items)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function submitCreate() {
  formLoading.value = true
  formError.value = null
  try {
    const payload = {
      title: form.value.title,
      description: form.value.description || null,
      priority: form.value.priority,
      estimated_hours: form.value.estimated_hours ? parseFloat(form.value.estimated_hours) : null,
      role_ids: form.value.role_ids.length ? form.value.role_ids : null,
    }
    const created = await createTask(payload)
    tasks.value.unshift(created)
    taskStore.addTask(created)
    closeCreateModal()
    successMsg.value = `Task "${created.title}" created.`
    setTimeout(() => { successMsg.value = null }, 3000)
  } catch (e) {
    formError.value = e.message
  } finally {
    formLoading.value = false
  }
}

async function submitEdit() {
  formLoading.value = true
  formError.value = null
  try {
    const payload = {
      title: form.value.title,
      description: form.value.description || null,
      priority: form.value.priority,
      estimated_hours: form.value.estimated_hours ? parseFloat(form.value.estimated_hours) : null,
      role_ids: form.value.role_ids.length ? form.value.role_ids : null,
    }
    const updated = await updateTask(editingTask.value.id, payload)
    const idx = tasks.value.findIndex((t) => t.id === updated.id)
    if (idx !== -1) tasks.value[idx] = updated
    taskStore.replaceTask(updated)
    closeEditModal()
    successMsg.value = `Task "${updated.title}" updated.`
    setTimeout(() => { successMsg.value = null }, 3000)
  } catch (e) {
    formError.value = e.message
  } finally {
    formLoading.value = false
  }
}

async function switchStatus(task, newStatus) {
  try {
    const updated = await updateTaskStatus(task.id, newStatus)
    const idx = tasks.value.findIndex((t) => t.id === updated.id)
    if (idx !== -1) tasks.value[idx] = updated
    taskStore.replaceTask(updated)
    successMsg.value = `Task "${updated.title}" → ${newStatus}.`
    setTimeout(() => { successMsg.value = null }, 3000)
  } catch (e) {
    error.value = e.message
    setTimeout(() => { error.value = null }, 5000)
  }
}

async function requestDelete(task) {
  confirmDelete.value = task.id
}

async function cancelDelete() {
  confirmDelete.value = null
}

async function confirmDeleteTask() {
  const id = confirmDelete.value
  confirmDelete.value = null
  try {
    await deleteTask(id)
    tasks.value = tasks.value.filter((t) => t.id !== id)
    taskStore.removeTask(id)
    successMsg.value = 'Task deleted.'
    setTimeout(() => { successMsg.value = null }, 3000)
  } catch (e) {
    error.value = e.message
  }
}

// ── Init ─────────────────────────────────────────────────────────────────────
onMounted(async () => {
  // Ensure roles are loaded
  if (!roleStore.roles.length) {
    try {
      const data = await listTasks({ page: 1, page_size: 1 })
      // roles might be loaded separately — trigger roles fetch from role store
      await roleStore.syncCurrentRole()
    } catch (_) {}
  }
  await fetchTasks()
  // Sync current role from store into filter
  if (roleStore.currentRoleId !== null) {
    filterRoleId.value = roleStore.currentRoleId
  }
})
</script>

<template>
  <div class="tasks-layout">
    <!-- Sidebar: role filter -->
    <aside class="sidebar">
      <div class="sidebar-header">Filter by Role</div>
      <button
        class="role-item"
        :class="{ active: filterRoleId === null }"
        @click="setFilterRole(null)"
      >
        All Tasks
        <span class="role-count">{{ tasks.length }}</span>
      </button>
      <button
        v-for="role in roleStore.roles"
        :key="role.id"
        class="role-item"
        :class="{ active: filterRoleId === role.id }"
        @click="setFilterRole(role.id)"
      >
        {{ role.name }}
      </button>

      <div class="sidebar-nav">
        <router-link to="/roles" class="nav-link">→ Roles</router-link>
      </div>
    </aside>

    <!-- Main content -->
    <main class="tasks-main">
      <!-- Header -->
      <div class="page-header">
        <h1>Tasks <span class="count-badge">{{ tasks.length }}</span></h1>
        <button class="btn-primary" @click="openCreate">+ New Task</button>
      </div>

      <!-- Messages -->
      <div v-if="error" class="msg msg-error" @click="clearMessages">{{ error }}</div>
      <div v-if="successMsg" class="msg msg-success" @click="clearMessages">{{ successMsg }}</div>

      <!-- Task list -->
      <div v-if="loading" class="empty">Loading…</div>
      <div v-else-if="!tasks.length" class="empty">No tasks yet. Create one!</div>
      <div v-else class="task-list">
        <div
          v-for="task in tasks"
          :key="task.id"
          class="task-card"
          :class="`status-${task.status}`"
        >
          <div class="task-top">
            <div class="task-title">{{ task.title }}</div>
            <div class="task-actions">
              <!-- Status switcher -->
              <div class="status-group">
                <button
                  v-for="next in NEXT_STATUSES[task.status]"
                  :key="next"
                  class="status-btn"
                  :style="{ '--btn-bg': STATUS_COLORS[next].bg, '--btn-color': STATUS_COLORS[next].color }"
                  @click="switchStatus(task, next)"
                  :title="`Move to ${next}`"
                >
                  → {{ next.replace('_', ' ') }}
                </button>
              </div>
              <button class="btn-icon" @click="openEdit(task)" title="Edit">✎</button>
              <button class="btn-icon btn-danger-icon" @click="requestDelete(task)" title="Delete">✕</button>
            </div>
          </div>

          <div v-if="task.description" class="task-desc">{{ task.description }}</div>

          <div class="task-meta">
            <!-- Status badge -->
            <span
              class="status-badge"
              :style="{ background: STATUS_COLORS[task.status].bg, color: STATUS_COLORS[task.status].color }"
            >
              <span class="status-dot" :style="{ background: STATUS_COLORS[task.status].dot }"></span>
              {{ task.status.replace('_', ' ') }}
            </span>

            <!-- Priority -->
            <span
              class="priority-badge"
              :style="{ color: PRIORITY_COLORS[task.priority] }"
            >
              {{ task.priority }}
            </span>

            <!-- Estimated hours -->
            <span v-if="task.estimated_hours" class="meta-item">
              ⏱ {{ task.estimated_hours }}h
            </span>

            <!-- Created -->
            <span class="meta-item">
              {{ new Date(task.created_at).toLocaleDateString() }}
            </span>

            <!-- Role IDs -->
            <span v-if="task.role_ids && task.role_ids.length" class="meta-item">
              👤 {{ task.role_ids.length }} role{{ task.role_ids.length !== 1 ? 's' : '' }}
            </span>
          </div>
        </div>
      </div>
    </main>
  </div>

  <!-- Create Modal -->
  <div v-if="showCreateModal" class="modal-overlay" @click.self="closeCreateModal">
    <div class="modal">
      <div class="modal-header">
        <h2>New Task</h2>
        <button class="btn-close" @click="closeCreateModal">×</button>
      </div>
      <form @submit.prevent="submitCreate">
        <div class="field">
          <label for="task-title">Title *</label>
          <input id="task-title" v-model="form.title" required maxlength="200" placeholder="Task title" />
        </div>
        <div class="field">
          <label for="task-desc">Description <span class="optional">(optional)</span></label>
          <textarea id="task-desc" v-model="form.description" maxlength="2000" rows="3" placeholder="What needs to be done?"></textarea>
        </div>
        <div class="field-row">
          <div class="field">
            <label for="task-priority">Priority</label>
            <select id="task-priority" v-model="form.priority">
              <option v-for="p in PRIORITIES" :key="p" :value="p">{{ p }}</option>
            </select>
          </div>
          <div class="field">
            <label for="task-hours">Estimated Hours <span class="optional">(optional)</span></label>
            <input id="task-hours" type="number" v-model="form.estimated_hours" min="0" step="0.5" placeholder="e.g. 2.5" />
          </div>
        </div>
        <div class="field">
          <label>Assign Roles <span class="optional">(optional)</span></label>
          <div class="role-checkboxes">
            <label
              v-for="role in roleStore.roles"
              :key="role.id"
              class="role-checkbox"
              :class="{ checked: form.role_ids.includes(role.id) }"
            >
              <input
                type="checkbox"
                :checked="form.role_ids.includes(role.id)"
                @change="toggleRoleInForm(role.id)"
              />
              {{ role.name }}
            </label>
          </div>
        </div>
        <div v-if="formError" class="msg msg-error">{{ formError }}</div>
        <div class="modal-footer">
          <button type="button" class="btn-secondary" @click="closeCreateModal">Cancel</button>
          <button type="submit" class="btn-primary" :disabled="formLoading">
            {{ formLoading ? 'Creating…' : 'Create Task' }}
          </button>
        </div>
      </form>
    </div>
  </div>

  <!-- Edit Modal -->
  <div v-if="showEditModal" class="modal-overlay" @click.self="closeEditModal">
    <div class="modal">
      <div class="modal-header">
        <h2>Edit Task</h2>
        <button class="btn-close" @click="closeEditModal">×</button>
      </div>
      <form @submit.prevent="submitEdit">
        <div class="field">
          <label for="edit-title">Title *</label>
          <input id="edit-title" v-model="form.title" required maxlength="200" />
        </div>
        <div class="field">
          <label for="edit-desc">Description <span class="optional">(optional)</span></label>
          <textarea id="edit-desc" v-model="form.description" maxlength="2000" rows="3"></textarea>
        </div>
        <div class="field-row">
          <div class="field">
            <label for="edit-priority">Priority</label>
            <select id="edit-priority" v-model="form.priority">
              <option v-for="p in PRIORITIES" :key="p" :value="p">{{ p }}</option>
            </select>
          </div>
          <div class="field">
            <label for="edit-hours">Estimated Hours <span class="optional">(optional)</span></label>
            <input id="edit-hours" type="number" v-model="form.estimated_hours" min="0" step="0.5" />
          </div>
        </div>
        <div class="field">
          <label>Assign Roles</label>
          <div class="role-checkboxes">
            <label
              v-for="role in roleStore.roles"
              :key="role.id"
              class="role-checkbox"
              :class="{ checked: form.role_ids.includes(role.id) }"
            >
              <input
                type="checkbox"
                :checked="form.role_ids.includes(role.id)"
                @change="toggleRoleInForm(role.id)"
              />
              {{ role.name }}
            </label>
          </div>
        </div>
        <div v-if="formError" class="msg msg-error">{{ formError }}</div>
        <div class="modal-footer">
          <button type="button" class="btn-secondary" @click="closeEditModal">Cancel</button>
          <button type="submit" class="btn-primary" :disabled="formLoading">
            {{ formLoading ? 'Saving…' : 'Save Changes' }}
          </button>
        </div>
      </form>
    </div>
  </div>

  <!-- Delete Confirmation -->
  <div v-if="confirmDelete !== null" class="modal-overlay" @click.self="cancelDelete">
    <div class="modal modal-sm">
      <div class="modal-header">
        <h2>Delete Task?</h2>
      </div>
      <p>This will soft-delete the task. Are you sure?</p>
      <div class="modal-footer">
        <button class="btn-secondary" @click="cancelDelete">Cancel</button>
        <button class="btn-danger" @click="confirmDeleteTask">Delete</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── Layout ─────────────────────────────────────────────────────────────── */
.tasks-layout {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  width: 200px;
  min-width: 200px;
  border-right: 1px solid var(--border);
  padding: 24px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: var(--social-bg);
}

.sidebar-header {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: var(--text);
  padding: 0 8px 12px;
}

.role-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--text-h);
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  text-align: left;
  width: 100%;
  transition: background 0.15s;
}

.role-item:hover { background: var(--border); }
.role-item.active {
  background: var(--accent-bg);
  color: var(--accent);
  font-weight: 600;
}

.role-count {
  font-size: 11px;
  background: var(--border);
  padding: 1px 6px;
  border-radius: 99px;
  color: var(--text);
}

.sidebar-nav {
  margin-top: auto;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.nav-link {
  font-size: 12px;
  color: var(--accent);
  text-decoration: none;
  padding: 4px 8px;
  display: block;
}

.nav-link:hover { text-decoration: underline; }

/* ── Main ────────────────────────────────────────────────────────────────── */
.tasks-main {
  flex: 1;
  padding: 32px 28px;
  max-width: 860px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.page-header h1 {
  font-size: 26px;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 10px;
}

.count-badge {
  font-size: 14px;
  font-weight: 400;
  background: var(--border);
  color: var(--text);
  padding: 2px 10px;
  border-radius: 99px;
}

/* ── Messages ────────────────────────────────────────────────────────────── */
.msg {
  padding: 10px 14px;
  border-radius: 6px;
  margin-bottom: 16px;
  cursor: pointer;
  font-size: 14px;
}
.msg-error { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
.msg-success { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }

/* ── Task list ───────────────────────────────────────────────────────────── */
.task-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.task-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
  background: var(--bg);
  border-left: 4px solid transparent;
  transition: box-shadow 0.15s;
}

.task-card:hover { box-shadow: var(--shadow); }

.task-card.status-PENDING { border-left-color: #9ca3af; }
.task-card.status-IN_PROGRESS { border-left-color: #3b82f6; }
.task-card.status-DONE { border-left-color: #22c55e; }
.task-card.status-CANCELLED { border-left-color: #ef4444; }

.task-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}

.task-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-h);
  flex: 1;
}

.task-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.status-group {
  display: flex;
  gap: 4px;
}

.status-btn {
  padding: 3px 8px;
  font-size: 11px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--btn-bg, var(--social-bg));
  color: var(--btn-color, var(--text));
  cursor: pointer;
  font-family: inherit;
  transition: opacity 0.15s;
}

.status-btn:hover { opacity: 0.75; }

.btn-icon {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  color: var(--text);
  padding: 2px 4px;
  border-radius: 4px;
  transition: background 0.15s;
}

.btn-icon:hover { background: var(--border); }
.btn-danger-icon:hover { background: #fee2e2; color: #991b1b; }

.task-desc {
  font-size: 13px;
  color: var(--text);
  margin-bottom: 8px;
  line-height: 1.5;
}

.task-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  border-radius: 99px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.3px;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.priority-badge {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.3px;
}

.meta-item {
  font-size: 12px;
  color: var(--text);
}

/* ── Buttons (shared with RolesView) ─────────────────────────────────────── */
.btn-primary {
  padding: 8px 16px;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  font-family: inherit;
  transition: opacity 0.15s;
}
.btn-primary:hover { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-secondary {
  padding: 8px 16px;
  background: var(--social-bg);
  color: var(--text-h);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-family: inherit;
  transition: background 0.15s;
}
.btn-secondary:hover { background: var(--border); }

.btn-danger {
  padding: 8px 16px;
  background: #fee2e2;
  color: #991b1b;
  border: 1px solid #fecaca;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-family: inherit;
  font-weight: 500;
}
.btn-danger:hover { background: #fecaca; }

.btn-close {
  background: none;
  border: none;
  font-size: 22px;
  cursor: pointer;
  color: var(--text);
  line-height: 1;
  padding: 0;
}

.empty {
  text-align: center;
  padding: 48px;
  color: var(--text);
  font-size: 15px;
}

/* ── Modal ────────────────────────────────────────────────────────────────── */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal {
  background: var(--bg);
  border-radius: 10px;
  padding: 24px;
  width: 500px;
  max-width: calc(100vw - 32px);
  box-shadow: var(--shadow);
}

.modal-sm { width: 340px; }

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.modal-header h2 {
  font-size: 18px;
  margin: 0;
}

.field {
  margin-bottom: 16px;
}

.field label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
  color: var(--text-h);
}

.field-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.optional {
  font-weight: 400;
  color: var(--text);
}

input, textarea, select {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--text-h);
  font-size: 14px;
  font-family: inherit;
  resize: vertical;
}

input:focus, textarea:focus, select:focus {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}

p {
  color: var(--text);
  font-size: 14px;
}

/* ── Role checkboxes ─────────────────────────────────────────────────────── */
.role-checkboxes {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.role-checkbox {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-h);
  user-select: none;
  transition: background 0.15s;
}

.role-checkbox input[type="checkbox"] {
  width: auto;
  margin: 0;
}

.role-checkbox:hover { background: var(--social-bg); }
.role-checkbox.checked {
  background: var(--accent-bg);
  border-color: var(--accent-border);
  color: var(--accent);
}
</style>
