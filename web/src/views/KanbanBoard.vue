<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useRoleStore } from '../stores/role.js'
import { useTaskStore } from '../stores/task.js'
import { listTasks, createTask, updateTask, deleteTask, updateTaskStatus, setTaskRoles } from '../api/tasks.js'
import { listRoles } from '../api/roles.js'

const router = useRouter()
const roleStore = useRoleStore()
const taskStore = useTaskStore()

// ── Constants ────────────────────────────────────────────────────────────
const STATUS_ORDER = ['PENDING', 'IN_PROGRESS', 'DONE', 'CANCELLED']

const STATUS_LABELS = {
  PENDING: 'Pending',
  IN_PROGRESS: 'In Progress',
  DONE: 'Done',
  CANCELLED: 'Cancelled',
}

const STATUS_COLORS = {
  PENDING: { bg: '#fef3c7', color: '#92400e', border: '#fde68a', header: '#fbbf24' },
  IN_PROGRESS: { bg: '#dbeafe', color: '#1e40af', border: '#bfdbfe', header: '#3b82f6' },
  DONE: { bg: '#dcfce7', color: '#166534', border: '#bbf7d0', header: '#22c55e' },
  CANCELLED: { bg: '#f3f4f6', color: '#6b7280', border: '#e5e7eb', header: '#9ca3af' },
}

const PRIORITY_COLORS = {
  LOW: '#6b7280',
  MEDIUM: '#d97706',
  HIGH: '#ea580c',
  URGENT: '#dc2626',
}

const PRIORITIES = ['LOW', 'MEDIUM', 'HIGH', 'URGENT']

/** Valid transitions: prevents skipping states */
const VALID_TRANSITIONS = {
  PENDING: ['IN_PROGRESS', 'CANCELLED'],
  IN_PROGRESS: ['PENDING', 'DONE', 'CANCELLED'],
  DONE: ['IN_PROGRESS'],
  CANCELLED: ['PENDING'],
}

// ── State ────────────────────────────────────────────────────────────────
const tasks = ref([])
const allRoles = ref([])
const loading = ref(false)
const error = ref(null)

// Drag state
const dragTask = ref(null)
const dragSourceStatus = ref(null)
const dragOverStatus = ref(null)
const isDragging = ref(false)

// Toast
const toasts = ref([])
let toastId = 0

// Modal
const showModal = ref(false)
const modalMode = ref('create')
const editingTask = ref(null)
const quickStatusTarget = ref(null)
const form = ref({ title: '', description: '', priority: 'MEDIUM', estimated_hours: null, role_ids: [] })
const formLoading = ref(false)
const formError = ref(null)

const confirmDelete = ref(null)

// ── Computed ─────────────────────────────────────────────────────────────
const columns = computed(() => {
  const grouped = {}
  for (const s of STATUS_ORDER) {
    grouped[s] = tasks.value.filter((t) => t.status === s)
  }
  return grouped
})

const canDrag = computed(() => {
  return roleStore.permissions.canEdit
})

// ── Toast system ─────────────────────────────────────────────────────────
function addToast(message, type = 'success', duration = 3000) {
  const id = ++toastId
  toasts.value.push({ id, message, type, leaving: false })
  setTimeout(() => {
    const t = toasts.value.find((t) => t.id === id)
    if (t) t.leaving = true
    setTimeout(() => {
      toasts.value = toasts.value.filter((t) => t.id !== id)
    }, 300)
  }, duration)
}

// ── Drag & Drop ──────────────────────────────────────────────────────────
function onDragStart(event, task) {
  if (!canDrag.value) {
    event.preventDefault()
    return
  }
  isDragging.value = true
  dragTask.value = task
  dragSourceStatus.value = task.status
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', String(task.id))
  // Add drag ghost class after a tick
  requestAnimationFrame(() => {
    event.target.classList.add('dragging')
  })
}

function onDragEnd(event) {
  event.target.classList.remove('dragging')
  isDragging.value = false
  dragTask.value = null
  dragSourceStatus.value = null
  dragOverStatus.value = null
}

function onDragOver(event, status) {
  event.preventDefault()
  event.dataTransfer.dropEffect = 'move'
  dragOverStatus.value = status
}

function onDragLeave(event, status) {
  if (dragOverStatus.value === status) {
    dragOverStatus.value = null
  }
}

function canDrop(task, targetStatus) {
  if (!task) return false
  if (task.status === targetStatus) return false
  const allowed = VALID_TRANSITIONS[task.status] || []
  return allowed.includes(targetStatus)
}

async function onDrop(event, targetStatus) {
  event.preventDefault()
  dragOverStatus.value = null

  const task = dragTask.value
  if (!task || task.status === targetStatus) {
    isDragging.value = false
    return
  }

  // Validate transition
  if (!canDrop(task, targetStatus)) {
    const sourceLabel = STATUS_LABELS[task.status] || task.status
    const targetLabel = STATUS_LABELS[targetStatus] || targetStatus
    addToast(`Cannot move task from "${sourceLabel}" to "${targetLabel}" — must go through intermediate states.`, 'error', 5000)
    isDragging.value = false
    return
  }

  // Check permissions
  if (!roleStore.permissions.canEdit) {
    addToast('Your role does not have permission to change task status.', 'error', 4000)
    isDragging.value = false
    return
  }

  // Optimistic update
  const oldStatus = task.status
  task.status = targetStatus
  isDragging.value = false

  try {
    const updated = await updateTaskStatus(task.id, targetStatus)
    // Sync with server response
    const idx = tasks.value.findIndex((t) => t.id === updated.id)
    if (idx !== -1) tasks.value[idx] = updated
    taskStore.replaceTask(updated)
    addToast(`"${task.title}" moved to ${STATUS_LABELS[targetStatus]}.`, 'success')
  } catch (e) {
    // Revert on failure
    task.status = oldStatus
    addToast(`Failed to move task: ${e.message}`, 'error', 5000)
  }
}

// ── API ──────────────────────────────────────────────────────────────────
async function fetchTasks() {
  loading.value = true
  error.value = null
  try {
    const data = await listTasks({ page: 1, page_size: 200 })
    tasks.value = data.items || []
    taskStore.setTasks(data.items || [])
  } catch (e) {
    error.value = e.message
    addToast(`Failed to load tasks: ${e.message}`, 'error', 5000)
  } finally {
    loading.value = false
  }
}

async function fetchRoles() {
  try {
    const data = await listRoles({ page: 1, page_size: 100 })
    allRoles.value = data.items || []
    roleStore.roles = data.items || []
    roleStore.syncCurrentRole()
  } catch (e) {
    console.warn('Failed to load roles:', e.message)
  }
}

// ── Modal ────────────────────────────────────────────────────────────────
function resetForm() {
  form.value = { title: '', description: '', priority: 'MEDIUM', estimated_hours: null, role_ids: [] }
  formError.value = null
}

function openCreate() {
  resetForm()
  modalMode.value = 'create'
  editingTask.value = null
  quickStatusTarget.value = null
  showModal.value = true
}

function openEdit(task) {
  editingTask.value = task
  form.value = {
    title: task.title,
    description: task.description ?? '',
    priority: task.priority,
    estimated_hours: task.estimated_hours ?? null,
    role_ids: (task.roles || []).map((r) => (typeof r === 'number' ? r : r.id)),
  }
  formError.value = null
  modalMode.value = 'edit'
  quickStatusTarget.value = null
  showModal.value = true
}

function closeModal() {
  showModal.value = false
  editingTask.value = null
  resetForm()
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
      if (form.value.role_ids.length > 0) {
        await setTaskRoles(created.id, form.value.role_ids)
        created.roles = form.value.role_ids.map((id) => allRoles.value.find((r) => r.id === id)).filter(Boolean)
      }
      tasks.value.push(created)
      taskStore.addTask(created)
      addToast(`Task "${created.title}" created.`, 'success')
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
      taskStore.replaceTask(updated)
      addToast(`Task "${updated.title}" updated.`, 'success')
    }
    closeModal()
  } catch (e) {
    formError.value = e.message
  } finally {
    formLoading.value = false
  }
}

// ── Delete ───────────────────────────────────────────────────────────────
function requestDelete(task) {
  confirmDelete.value = task.id
}

function cancelDelete() {
  confirmDelete.value = null
}

async function confirmDeleteTask() {
  const id = confirmDelete.value
  confirmDelete.value = null
  try {
    await deleteTask(id)
    tasks.value = tasks.value.filter((t) => t.id !== id)
    taskStore.removeTask(id)
    addToast('Task deleted.', 'success')
  } catch (e) {
    addToast(`Failed to delete: ${e.message}`, 'error', 5000)
  }
}

// ── Role toggle for form ─────────────────────────────────────────────────
function toggleRoleInForm(roleId) {
  const idx = form.value.role_ids.indexOf(roleId)
  if (idx === -1) {
    form.value.role_ids.push(roleId)
  } else {
    form.value.role_ids.splice(idx, 1)
  }
}

// ── Permission checks ────────────────────────────────────────────────────
const canCreate = computed(() => roleStore.permissions.canCreate)
const canEdit = computed(() => roleStore.permissions.canEdit)
const canDeleteTask = computed(() => roleStore.permissions.canDelete)
const isReadOnly = computed(() => !roleStore.permissions.canEdit && !roleStore.permissions.canCreate)

// ── Init ─────────────────────────────────────────────────────────────────
onMounted(() => {
  fetchRoles()
  fetchTasks()
})
</script>

<template>
  <div class="kanban-page">
    <!-- Header -->
    <div class="kanban-header">
      <div class="kanban-header-left">
        <h1>Kanban Board</h1>
        <span class="task-count">{{ tasks.length }} task{{ tasks.length !== 1 ? 's' : '' }}</span>
      </div>
      <div class="kanban-header-right">
        <!-- View toggle -->
        <router-link to="/tasks" class="btn-outline">List View</router-link>
        <button
          v-if="canCreate"
          class="btn-primary"
          @click="openCreate"
        >
          + New Task
        </button>
      </div>
    </div>

    <!-- Error banner (non-dismissable errors like fetch failure) -->
    <div v-if="error" class="kanban-error">
      {{ error }}
      <button class="error-retry" @click="fetchTasks">Retry</button>
    </div>

    <!-- Read-only banner -->
    <div v-if="isReadOnly" class="readonly-banner">
      <span>👁️ View-only mode</span>
      <span>Your current role has read-only access. Switch to a role with write permissions to make changes.</span>
    </div>

    <!-- Toast container -->
    <div class="toast-container">
      <transition-group name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="toast"
          :class="[`toast-${toast.type}`, { 'toast-leaving': toast.leaving }]"
        >
          <span class="toast-icon">
            {{ toast.type === 'success' ? '✓' : '✕' }}
          </span>
          <span class="toast-msg">{{ toast.message }}</span>
        </div>
      </transition-group>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="kanban-loading">
      <div class="loading-spinner"></div>
      <span>Loading tasks…</span>
    </div>

    <!-- Kanban columns -->
    <div v-else class="kanban-board">
      <div
        v-for="status in STATUS_ORDER"
        :key="status"
        class="kanban-column"
        :class="{
          'drag-over': dragOverStatus === status,
          'no-drop': dragOverStatus === status && !canDrop(dragTask, status),
        }"
        @dragover="onDragOver($event, status)"
        @dragleave="onDragLeave($event, status)"
        @drop="onDrop($event, status)"
      >
        <!-- Column header -->
        <div class="column-header" :style="{ '--col-header': STATUS_COLORS[status].header }">
          <div class="column-title-row">
            <span class="column-title">{{ STATUS_LABELS[status] }}</span>
            <span class="column-count">{{ columns[status].length }}</span>
          </div>
        </div>

        <!-- Column body -->
        <div class="column-body">
          <!-- Empty state -->
          <div v-if="!columns[status].length" class="column-empty">
            <span>No tasks</span>
            <span v-if="canCreate && status === 'PENDING'" class="empty-add" @click="openCreate">+ Add one</span>
          </div>

          <!-- Task cards -->
          <div
            v-for="task in columns[status]"
            :key="task.id"
            class="task-card"
            :class="{
              'dragging': isDragging && dragTask && dragTask.id === task.id,
              'can-drag': canDrag,
            }"
            :draggable="canDrag"
            @dragstart="onDragStart($event, task)"
            @dragend="onDragEnd"
            @click="canEdit ? openEdit(task) : null"
            :title="canEdit ? 'Click to edit' : ''"
          >
            <!-- Priority indicator bar -->
            <div
              class="priority-bar"
              :style="{ background: PRIORITY_COLORS[task.priority] || '#9ca3af' }"
            ></div>

            <div class="card-content">
              <!-- Title -->
              <div class="card-title">{{ task.title }}</div>

              <!-- Description preview -->
              <div v-if="task.description" class="card-desc">{{ task.description }}</div>

              <!-- Meta row -->
              <div class="card-meta">
                <!-- Priority badge -->
                <span
                  class="priority-badge"
                  :style="{ color: PRIORITY_COLORS[task.priority] || '#9ca3af' }"
                >
                  {{ task.priority }}
                </span>

                <!-- Hours -->
                <span v-if="task.estimated_hours" class="meta-item">
                  ⏱ {{ task.estimated_hours }}h
                </span>

                <!-- Roles -->
                <span v-if="task.roles && task.roles.length" class="role-tags">
                  <span
                    v-for="role in task.roles"
                    :key="role.id"
                    class="role-tag"
                  >
                    {{ typeof role === 'object' ? role.name : role }}
                  </span>
                </span>

                <!-- Created date -->
                <span class="meta-item date-item">
                  {{ new Date(task.created_at).toLocaleDateString() }}
                </span>
              </div>

              <!-- Action buttons (visible on hover) -->
              <div v-if="canEdit || canDeleteTask" class="card-actions">
                <button
                  v-if="canEdit"
                  class="card-btn"
                  @click.stop="openEdit(task)"
                  title="Edit"
                >
                  ✎ Edit
                </button>
                <button
                  v-if="canDeleteTask"
                  class="card-btn card-btn-danger"
                  @click.stop="requestDelete(task)"
                  title="Delete"
                >
                  ✕ Delete
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Create / Edit Modal -->
    <div v-if="showModal" class="modal-overlay" @click.self="closeModal">
      <div class="modal" :class="{ 'modal-enter': true }">
        <div class="modal-header">
          <h2>{{ modalMode === 'create' ? 'New Task' : 'Edit Task' }}</h2>
          <button class="btn-close" @click="closeModal">×</button>
        </div>
        <form @submit.prevent="submitForm">
          <div class="field">
            <label for="kanban-title">Title *</label>
            <input id="kanban-title" v-model="form.title" required maxlength="200" placeholder="Task title" />
          </div>
          <div class="field">
            <label for="kanban-desc">Description <span class="optional">(optional)</span></label>
            <textarea id="kanban-desc" v-model="form.description" maxlength="2000" rows="3" placeholder="What needs to be done?"></textarea>
          </div>
          <div class="field-row">
            <div class="field">
              <label for="kanban-priority">Priority</label>
              <select id="kanban-priority" v-model="form.priority">
                <option v-for="p in PRIORITIES" :key="p" :value="p">{{ p }}</option>
              </select>
            </div>
            <div class="field">
              <label for="kanban-hours">Est. Hours <span class="optional">(optional)</span></label>
              <input id="kanban-hours" type="number" v-model.number="form.estimated_hours" min="0" step="0.5" placeholder="e.g. 2.5" />
            </div>
          </div>
          <div class="field">
            <label>Assign Roles <span class="optional">(optional)</span></label>
            <div class="role-checkboxes">
              <label
                v-for="role in allRoles"
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
            <button type="button" class="btn-secondary" @click="closeModal">Cancel</button>
            <button type="submit" class="btn-primary" :disabled="formLoading">
              {{ formLoading ? 'Saving…' : (modalMode === 'create' ? 'Create Task' : 'Save Changes') }}
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
  </div>
</template>

<style scoped>
/* ── Page Layout ──────────────────────────────────────────────────────── */
.kanban-page {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.kanban-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}

.kanban-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.kanban-header-left h1 {
  font-size: 24px;
  margin: 0;
  color: var(--text-h);
}

.task-count {
  font-size: 13px;
  color: var(--text);
  background: var(--social-bg);
  padding: 3px 10px;
  border-radius: 99px;
}

.kanban-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-outline {
  padding: 7px 14px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: transparent;
  color: var(--text);
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  text-decoration: none;
  transition: background 0.15s, color 0.15s;
}

.btn-outline:hover {
  background: var(--social-bg);
  color: var(--text-h);
}

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

/* ── Error banner ─────────────────────────────────────────────────────── */
.kanban-error {
  padding: 10px 14px;
  background: #fee2e2;
  color: #991b1b;
  border: 1px solid #fecaca;
  border-radius: 6px;
  margin-bottom: 16px;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.error-retry {
  padding: 4px 10px;
  border: 1px solid #fca5a5;
  border-radius: 4px;
  background: #fff;
  color: #991b1b;
  font-size: 12px;
  cursor: pointer;
}

/* ── Read-only banner ─────────────────────────────────────────────────── */
.readonly-banner {
  padding: 10px 14px;
  background: #fef3c7;
  color: #92400e;
  border: 1px solid #fde68a;
  border-radius: 6px;
  margin-bottom: 16px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ── Toast System ─────────────────────────────────────────────────────── */
.toast-container {
  position: fixed;
  top: 64px;
  right: 20px;
  z-index: 200;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-radius: 8px;
  font-size: 14px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  pointer-events: auto;
  min-width: 240px;
  max-width: 400px;
}

.toast-success {
  background: #dcfce7;
  color: #166534;
  border: 1px solid #bbf7d0;
}

.toast-error {
  background: #fee2e2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

.toast-icon {
  font-weight: 700;
  font-size: 16px;
  flex-shrink: 0;
}

.toast-msg {
  flex: 1;
}

/* Toast transition */
.toast-enter-active {
  animation: toastIn 0.3s ease-out;
}

.toast-leave-active {
  animation: toastOut 0.3s ease-in forwards;
}

@keyframes toastIn {
  from { transform: translateX(100%); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}

@keyframes toastOut {
  from { transform: translateX(0); opacity: 1; }
  to { transform: translateX(100%); opacity: 0; }
}

.toast-leaving {
  opacity: 0.5;
}

/* ── Loading ──────────────────────────────────────────────────────────── */
.kanban-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px;
  color: var(--text);
  font-size: 15px;
}

.loading-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ── Kanban Board ─────────────────────────────────────────────────────── */
.kanban-board {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  min-height: calc(100vh - 180px);
}

@media (max-width: 1024px) {
  .kanban-board {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 640px) {
  .kanban-board {
    grid-template-columns: 1fr;
  }
}

/* ── Column ──────────────────────────────────────────────────────────── */
.kanban-column {
  background: var(--social-bg);
  border-radius: 10px;
  border: 2px solid transparent;
  display: flex;
  flex-direction: column;
  min-height: 200px;
  transition: border-color 0.15s, background 0.15s;
}

.kanban-column.drag-over {
  border-color: var(--accent);
  background: var(--accent-bg);
}

.kanban-column.no-drop {
  border-color: #ef4444;
  background: rgba(239, 68, 68, 0.05);
}

.column-header {
  padding: 14px 16px 10px;
  border-bottom: 2px solid var(--col-header, var(--border));
}

.column-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.column-title {
  font-size: 13px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: var(--text-h);
}

.column-count {
  font-size: 12px;
  background: var(--border);
  color: var(--text);
  padding: 1px 8px;
  border-radius: 99px;
  font-weight: 600;
}

.column-body {
  flex: 1;
  padding: 10px 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  max-height: calc(100vh - 260px);
}

.column-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 24px 12px;
  color: var(--text);
  font-size: 13px;
}

.empty-add {
  color: var(--accent);
  cursor: pointer;
  font-weight: 600;
  font-size: 13px;
}

.empty-add:hover {
  text-decoration: underline;
}

/* ── Task Card ────────────────────────────────────────────────────────── */
.task-card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: default;
  transition: box-shadow 0.15s, transform 0.15s, opacity 0.15s;
  overflow: hidden;
  position: relative;
}

.task-card.can-drag {
  cursor: grab;
}

.task-card.can-drag:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  transform: translateY(-1px);
}

.task-card.dragging {
  opacity: 0.4;
  transform: scale(0.95);
}

.priority-bar {
  height: 3px;
  width: 100%;
}

.card-content {
  padding: 10px 12px 12px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-h);
  margin-bottom: 4px;
  line-height: 1.4;
}

.card-desc {
  font-size: 12px;
  color: var(--text);
  margin-bottom: 8px;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.priority-badge {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.meta-item {
  font-size: 11px;
  color: var(--text);
}

.date-item {
  margin-left: auto;
}

.role-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
}

.role-tag {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--accent-bg);
  color: var(--accent);
  border: 1px solid var(--accent-border);
}

/* Card actions (appear on hover) */
.card-actions {
  display: flex;
  gap: 4px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
  opacity: 0;
  transition: opacity 0.15s;
}

.task-card:hover .card-actions {
  opacity: 1;
}

.card-btn {
  padding: 3px 8px;
  font-size: 11px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-h);
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s;
}

.card-btn:hover {
  background: var(--social-bg);
}

.card-btn-danger {
  color: #991b1b;
  border-color: #fecaca;
}

.card-btn-danger:hover {
  background: #fee2e2;
}

/* ── Modal ────────────────────────────────────────────────────────────── */
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
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.2);
}

.modal-sm {
  width: 340px;
}

.modal-enter {
  animation: modalIn 0.2s ease-out;
}

@keyframes modalIn {
  from { transform: translateY(10px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
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
  color: var(--text-h);
}

.btn-close {
  background: none;
  border: none;
  font-size: 22px;
  cursor: pointer;
  color: var(--text);
  line-height: 1;
  padding: 0;
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

.msg {
  padding: 10px 14px;
  border-radius: 6px;
  margin-bottom: 16px;
  font-size: 14px;
}

.msg-error {
  background: #fee2e2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}

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

p {
  color: var(--text);
  font-size: 14px;
}
</style>
