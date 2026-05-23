<script setup>
import { ref, onMounted, computed } from 'vue'
import { useTaskStore } from '../stores/task.js'
import { useRoleStore } from '../stores/role.js'
import { listTasks, createTask, updateTask, deleteTask, updateTaskStatus, setTaskRoles } from '../api/tasks.js'
import { listRoles } from '../api/roles.js'

const taskStore = useTaskStore()
const roleStore = useRoleStore()

// ── Constants ─────────────────────────────────────────────────────────────────
const STATUSES = ['PENDING', 'IN_PROGRESS', 'DONE', 'CANCELLED']
const PRIORITIES = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']

const STATUS_ORDER = { PENDING: 0, IN_PROGRESS: 1, DONE: 2, CANCELLED: 3 }

// ── State ────────────────────────────────────────────────────────────────────
const tasks = ref([])
const loading = ref(false)
const error = ref(null)
const successMsg = ref(null)

const allRoles = ref([])

const showModal = ref(false)
const modalMode = ref('create') // 'create' | 'edit'
const editingTask = ref(null)

const form = ref({ title: '', description: '', priority: 'MEDIUM', estimated_hours: null, role_ids: [] })
const formLoading = ref(false)
const formError = ref(null)

const confirmDelete = ref(null) // task id pending delete

const filterRoleId = ref(null)
const filterStatus = ref(null)

// ── Computed ─────────────────────────────────────────────────────────────────
const filteredTasks = computed(() => tasks.value)

function getNextStatus(current) {
  if (current === 'PENDING') return 'IN_PROGRESS'
  if (current === 'IN_PROGRESS') return 'DONE'
  return null
}

function canAdvance(current) {
  return current === 'PENDING' || current === 'IN_PROGRESS'
}

// ── Helpers ──────────────────────────────────────────────────────────────────
function clearMessages() {
  error.value = null
  successMsg.value = null
}

function clearFilters() {
  filterRoleId.value = null
  filterStatus.value = null
}

function showCreate() {
  form.value = { title: '', description: '', priority: 'MEDIUM', estimated_hours: null, role_ids: [] }
  formError.value = null
  modalMode.value = 'create'
  editingTask.value = null
  showModal.value = true
}

function showEdit(task) {
  form.value = {
    title: task.title,
    description: task.description ?? '',
    priority: task.priority,
    estimated_hours: task.estimated_hours ?? null,
    role_ids: (task.roles || []).map((r) => (typeof r === 'number' ? r : r.id)),
  }
  formError.value = null
  modalMode.value = 'edit'
  editingTask.value = task
  showModal.value = true
}

function closeModal() {
  showModal.value = false
  editingTask.value = null
  formError.value = null
}

// ── API ───────────────────────────────────────────────────────────────────────
async function fetchRoles() {
  try {
    const data = await listRoles({ page: 1, page_size: 100 })
    allRoles.value = data.items || []
    roleStore.roles = allRoles.value
  } catch (e) {
    console.warn('Failed to load roles for filter:', e.message)
  }
}

async function fetchTasks() {
  loading.value = true
  error.value = null
  try {
    const params = {}
    if (filterRoleId.value) params.role_id = filterRoleId.value
    if (filterStatus.value) params.status = filterStatus.value
    const data = await listTasks(params)
    tasks.value = data.items || []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function submitForm() {
  formLoading.value = true
  formError.value = null
  try {
    const payload = {
      title: form.value.title,
      description: form.value.description || null,
      priority: form.value.priority,
      estimated_hours: form.value.estimated_hours ?? null,
    }

    if (modalMode.value === 'create') {
      const created = await createTask(payload)
      // Assign roles if any selected
      if (form.value.role_ids.length > 0) {
        await setTaskRoles(created.id, form.value.role_ids)
        created.roles = form.value.role_ids.map((id) => allRoles.value.find((r) => r.id === id)).filter(Boolean)
      }
      tasks.value.push(created)
      successMsg.value = `Task "${created.title}" created.`
    } else {
      const updated = await updateTask(editingTask.value.id, payload)
      // Update roles if changed
      const currentRoleIds = (editingTask.value.roles || []).map((r) => (typeof r === 'number' ? r : r.id))
      if (JSON.stringify(currentRoleIds.sort()) !== JSON.stringify([...form.value.role_ids].sort())) {
        await setTaskRoles(editingTask.value.id, form.value.role_ids)
        updated.roles = form.value.role_ids.map((id) => allRoles.value.find((r) => r.id === id)).filter(Boolean)
      } else {
        updated.roles = editingTask.value.roles
      }
      const idx = tasks.value.findIndex((t) => t.id === updated.id)
      if (idx !== -1) tasks.value[idx] = updated
      successMsg.value = `Task "${updated.title}" updated.`
    }
    closeModal()
    setTimeout(() => { successMsg.value = null }, 3000)
  } catch (e) {
    formError.value = e.message
  } finally {
    formLoading.value = false
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
    successMsg.value = 'Task deleted.'
    setTimeout(() => { successMsg.value = null }, 3000)
  } catch (e) {
    error.value = e.message
  }
}

async function quickAdvanceStatus(task) {
  const next = getNextStatus(task.status)
  if (!next) return
  try {
    const updated = await updateTaskStatus(task.id, next)
    updated.roles = task.roles
    const idx = tasks.value.findIndex((t) => t.id === task.id)
    if (idx !== -1) tasks.value[idx] = updated
    successMsg.value = `Task moved to ${next}.`
    setTimeout(() => { successMsg.value = null }, 2000)
  } catch (e) {
    error.value = e.message
  }
}

// ── Init ─────────────────────────────────────────────────────────────────────
onMounted(() => {
  fetchRoles()
  fetchTasks()
})
</script>

<template>
  <div class="tasks-page">
    <!-- Header -->
    <div class="page-header">
      <h1>Tasks</h1>
      <button class="btn-primary" @click="showCreate">+ New Task</button>
    </div>

    <!-- Messages -->
    <div v-if="error" class="msg msg-error" @click="clearMessages">{{ error }}</div>
    <div v-if="successMsg" class="msg msg-success" @click="clearMessages">{{ successMsg }}</div>

    <!-- Filters -->
    <div class="filters">
      <div class="filter-group">
        <label for="filter-role">Filter by Role</label>
        <select id="filter-role" v-model="filterRoleId" @change="fetchTasks">
          <option :value="null">All Roles</option>
          <option v-for="role in allRoles" :key="role.id" :value="role.id">
            {{ role.name }}
          </option>
        </select>
      </div>
      <div class="filter-group">
        <label for="filter-status">Filter by Status</label>
        <select id="filter-status" v-model="filterStatus" @change="fetchTasks">
          <option :value="null">All Statuses</option>
          <option v-for="s in STATUSES" :key="s" :value="s">{{ s }}</option>
        </select>
      </div>
      <button v-if="filterRoleId || filterStatus" class="btn-small" @click="clearFilters(); fetchTasks()">
        Clear Filters
      </button>
    </div>

    <!-- Table -->
    <div class="table-wrap">
      <table v-if="!loading && tasks.length">
        <thead>
          <tr>
            <th>Title</th>
            <th>Status</th>
            <th>Priority</th>
            <th>Est. Hours</th>
            <th>Roles</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="task in tasks" :key="task.id">
            <td>
              <span class="task-title">{{ task.title }}</span>
              <span v-if="task.description" class="task-desc">{{ task.description }}</span>
            </td>
            <td>
              <span class="badge" :class="`badge-${task.status.toLowerCase()}`">{{ task.status }}</span>
              <button
                v-if="canAdvance(task.status)"
                class="btn-advance"
                @click="quickAdvanceStatus(task)"
                :title="`Move to ${getNextStatus(task.status)}`"
              >
                →
              </button>
            </td>
            <td>
              <span class="badge-priority" :class="`priority-${task.priority.toLowerCase()}`">{{ task.priority }}</span>
            </td>
            <td>{{ task.estimated_hours ?? '—' }}</td>
            <td>
              <span v-if="task.roles && task.roles.length" class="role-tags">
                <span v-for="role in task.roles" :key="role.id" class="role-tag">
                  {{ typeof role === 'object' ? role.name : role }}
                </span>
              </span>
              <span v-else class="no-roles">—</span>
            </td>
            <td class="actions">
              <button class="btn-small" @click="showEdit(task)">Edit</button>
              <button class="btn-small btn-danger" @click="requestDelete(task)">Delete</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-else-if="loading" class="empty">Loading…</div>
      <div v-else class="empty">No tasks yet. Create one!</div>
    </div>

    <!-- Create / Edit Modal -->
    <div v-if="showModal" class="modal-overlay" @click.self="closeModal">
      <div class="modal">
        <div class="modal-header">
          <h2>{{ modalMode === 'create' ? 'New Task' : 'Edit Task' }}</h2>
          <button class="btn-close" @click="closeModal">×</button>
        </div>
        <form @submit.prevent="submitForm">
          <div class="field">
            <label for="task-title">Title</label>
            <input id="task-title" v-model="form.title" required maxlength="200" placeholder="Task title" />
          </div>
          <div class="field">
            <label for="task-desc">Description <span class="optional">(optional)</span></label>
            <textarea id="task-desc" v-model="form.description" maxlength="1000" rows="3" placeholder="What needs to be done?"></textarea>
          </div>
          <div class="field-row">
            <div class="field">
              <label for="task-priority">Priority</label>
              <select id="task-priority" v-model="form.priority">
                <option v-for="p in PRIORITIES" :key="p" :value="p">{{ p }}</option>
              </select>
            </div>
            <div class="field">
              <label for="task-hours">Est. Hours <span class="optional">(optional)</span></label>
              <input id="task-hours" v-model.number="form.estimated_hours" type="number" min="0" step="0.5" placeholder="0" />
            </div>
          </div>
          <div class="field">
            <label for="task-roles">Roles <span class="optional">(optional, hold Ctrl/Cmd to select multiple)</span></label>
            <select id="task-roles" v-model="form.role_ids" multiple size="4">
              <option v-for="role in allRoles" :key="role.id" :value="role.id">{{ role.name }}</option>
            </select>
          </div>
          <div v-if="formError" class="msg msg-error">{{ formError }}</div>
          <div class="modal-footer">
            <button type="button" class="btn-secondary" @click="closeModal">Cancel</button>
            <button type="submit" class="btn-primary" :disabled="formLoading">
              {{ formLoading ? 'Saving…' : (modalMode === 'create' ? 'Create' : 'Save') }}
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
        <p>This will permanently delete the task. Are you sure?</p>
        <div class="modal-footer">
          <button class="btn-secondary" @click="cancelDelete">Cancel</button>
          <button class="btn-danger" @click="confirmDeleteTask">Delete</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tasks-page {
  padding: 32px 24px;
  max-width: 1100px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.page-header h1 {
  font-size: 28px;
  margin: 0;
  color: var(--text-h);
}

.msg {
  padding: 10px 14px;
  border-radius: 6px;
  margin-bottom: 16px;
  cursor: pointer;
  font-size: 14px;
}

.msg-error {
  background: #fee2e2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

.msg-success {
  background: #dcfce7;
  color: #166534;
  border: 1px solid #bbf7d0;
}

/* Filters */
.filters {
  display: flex;
  align-items: flex-end;
  gap: 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.filter-group label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-h);
}

.filter-group select {
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--text-h);
  font-size: 14px;
  min-width: 160px;
}

/* Table */
.table-wrap {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

th, td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}

th {
  font-weight: 600;
  color: var(--text-h);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

tr:hover {
  background: var(--social-bg);
}

.task-title {
  font-weight: 500;
  color: var(--text-h);
}

.task-desc {
  display: block;
  font-size: 12px;
  color: var(--text);
  margin-top: 2px;
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Status badges */
.badge {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 99px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.badge-pending {
  background: #fef3c7;
  color: #92400e;
  border: 1px solid #fde68a;
}

.badge-in_progress {
  background: #dbeafe;
  color: #1e40af;
  border: 1px solid #bfdbfe;
}

.badge-done {
  background: #dcfce7;
  color: #166534;
  border: 1px solid #bbf7d0;
}

.badge-cancelled {
  background: #f3f4f6;
  color: #6b7280;
  border: 1px solid #e5e7eb;
}

/* Priority badges */
.badge-priority {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.priority-low {
  background: #f3f4f6;
  color: #6b7280;
}

.priority-medium {
  background: #dbeafe;
  color: #1e40af;
}

.priority-high {
  background: #fef3c7;
  color: #92400e;
}

.priority-critical {
  background: #fee2e2;
  color: #991b1b;
}

/* Role tags */
.role-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.role-tag {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  background: var(--accent-bg);
  color: var(--accent);
  border: 1px solid var(--accent-border);
}

.no-roles {
  color: var(--text);
}

/* Actions */
.actions {
  white-space: nowrap;
}

.btn-advance {
  margin-left: 6px;
  padding: 2px 6px;
  font-size: 12px;
  border-radius: 4px;
  cursor: pointer;
  background: var(--accent);
  color: #fff;
  border: none;
  transition: opacity 0.15s;
}

.btn-advance:hover {
  opacity: 0.85;
}

/* Buttons */
.btn-primary {
  padding: 8px 16px;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
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
  transition: background 0.15s;
}

.btn-secondary:hover { background: var(--border); }

.btn-small {
  padding: 4px 10px;
  font-size: 12px;
  border-radius: 4px;
  cursor: pointer;
  border: 1px solid var(--border);
  background: var(--social-bg);
  color: var(--text-h);
  transition: background 0.15s;
}

.btn-small:hover { background: var(--border); }

.btn-danger {
  background: #fee2e2;
  color: #991b1b;
  border-color: #fecaca;
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

/* Modal */
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
  width: 480px;
  max-width: calc(100vw - 32px);
  box-shadow: var(--shadow);
}

.modal-sm {
  width: 340px;
}

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
  display: flex;
  gap: 12px;
}

.field-row .field {
  flex: 1;
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

select[multiple] {
  height: auto;
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
</style>
