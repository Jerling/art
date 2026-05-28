<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoleStore } from '../stores/role.js'
import { listRoles, createRole, updateRole, deleteRole } from '../api/roles.js'

const roleStore = useRoleStore()

// ── State ────────────────────────────────────────────────────────────────────
const roles = ref([])
const loading = ref(false)
const error = ref(null)
const successMsg = ref(null)

const showModal = ref(false)
const modalMode = ref('create') // 'create' | 'edit'
const editingRole = ref(null)

const form = ref({ name: '', description: '' })
const formLoading = ref(false)
const formError = ref(null)

const confirmDelete = ref(null) // role id pending delete

// ── Computed ─────────────────────────────────────────────────────────────────
const isCurrentRole = (id) => roleStore.currentRoleId === id

// ── Helpers ──────────────────────────────────────────────────────────────────
function showCreate() {
  form.value = { name: '', description: '' }
  formError.value = null
  modalMode.value = 'create'
  editingRole.value = null
  showModal.value = true
}

function showEdit(role) {
  form.value = { name: role.name, description: role.description ?? '' }
  formError.value = null
  modalMode.value = 'edit'
  editingRole.value = role
  showModal.value = true
}

function closeModal() {
  showModal.value = false
  editingRole.value = null
  formError.value = null
}

function clearMessages() {
  error.value = null
  successMsg.value = null
}

// ── API ───────────────────────────────────────────────────────────────────────
async function fetchRoles() {
  loading.value = true
  error.value = null
  try {
    const data = await listRoles({ page: 1, page_size: 100 })
    roles.value = data.items
    roleStore.roles = data.items
    roleStore.syncCurrentRole()
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
    if (modalMode.value === 'create') {
      const created = await createRole({ name: form.value.name, description: form.value.description || null })
      roles.value.push(created)
      roleStore.roles = roles.value
      successMsg.value = `Role "${created.name}" created.`
    } else {
      const updated = await updateRole(editingRole.value.id, { name: form.value.name, description: form.value.description || null })
      const idx = roles.value.findIndex((r) => r.id === updated.id)
      if (idx !== -1) roles.value[idx] = updated
      roleStore.roles = roles.value
      roleStore.syncCurrentRole()
      successMsg.value = `Role "${updated.name}" updated.`
    }
    closeModal()
    setTimeout(() => { successMsg.value = null }, 3000)
  } catch (e) {
    formError.value = e.message
  } finally {
    formLoading.value = false
  }
}

async function requestDelete(role) {
  confirmDelete.value = role.id
}

async function cancelDelete() {
  confirmDelete.value = null
}

async function confirmDeleteRole() {
  const id = confirmDelete.value
  confirmDelete.value = null
  try {
    await deleteRole(id)
    roles.value = roles.value.filter((r) => r.id !== id)
    roleStore.roles = roles.value
    if (roleStore.currentRoleId === id) roleStore.clearCurrentRole()
    successMsg.value = 'Role deleted.'
    setTimeout(() => { successMsg.value = null }, 3000)
  } catch (e) {
    error.value = e.message
  }
}

function switchToRole(role) {
  roleStore.setCurrentRoleId(role.id, role)
  successMsg.value = `Switched to role "${role.name}".`
  setTimeout(() => { successMsg.value = null }, 3000)
}

// ── Init ─────────────────────────────────────────────────────────────────────
onMounted(fetchRoles)
</script>

<template>
  <div class="roles-page">
    <!-- Header -->
    <div class="page-header">
      <h1>Roles</h1>
      <button class="btn-primary" @click="showCreate">+ New Role</button>
    </div>

    <!-- Messages -->
    <div v-if="error" class="msg msg-error" @click="clearMessages">{{ error }}</div>
    <div v-if="successMsg" class="msg msg-success" @click="clearMessages">{{ successMsg }}</div>

    <!-- Current role badge -->
    <div v-if="roleStore.currentRole" class="current-role-badge">
      Current role: <strong>{{ roleStore.currentRole.name }}</strong>
    </div>

    <!-- Table -->
    <div class="table-wrap">
      <table v-if="!loading && roles.length">
        <thead>
          <tr>
            <th>Name</th>
            <th>Description</th>
            <th>Created</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="role in roles" :key="role.id" :class="{ 'row-current': isCurrentRole(role.id) }">
            <td>
              {{ role.name }}
              <span v-if="isCurrentRole(role.id)" class="badge-current">active</span>
            </td>
            <td>{{ role.description ?? '—' }}</td>
            <td>{{ new Date(role.created_at).toLocaleDateString() }}</td>
            <td class="actions">
              <button class="btn-small" @click="switchToRole(role)" :disabled="isCurrentRole(role.id)">Switch</button>
              <button class="btn-small" @click="showEdit(role)">Edit</button>
              <button class="btn-small btn-danger" @click="requestDelete(role)">Delete</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-else-if="loading" class="empty">Loading…</div>
      <div v-else class="empty">No roles yet. Create one!</div>
    </div>

    <!-- Create / Edit Modal -->
    <div v-if="showModal" class="modal-overlay" @click.self="closeModal">
      <div class="modal">
        <div class="modal-header">
          <h2>{{ modalMode === 'create' ? 'New Role' : 'Edit Role' }}</h2>
          <button class="btn-close" @click="closeModal">×</button>
        </div>
        <form @submit.prevent="submitForm">
          <div class="field">
            <label for="role-name">Name</label>
            <input id="role-name" v-model="form.name" required maxlength="100" placeholder="e.g. Admin" />
          </div>
          <div class="field">
            <label for="role-desc">Description <span class="optional">(optional)</span></label>
            <textarea id="role-desc" v-model="form.description" maxlength="500" rows="3" placeholder="What does this role do?"></textarea>
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
          <h2>Delete Role?</h2>
        </div>
        <p>This will soft-delete the role. Are you sure?</p>
        <div class="modal-footer">
          <button class="btn-secondary" @click="cancelDelete">Cancel</button>
          <button class="btn-danger" @click="confirmDeleteRole">Delete</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.roles-page {
  padding: 32px 24px;
  max-width: 900px;
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

.current-role-badge {
  font-size: 14px;
  margin-bottom: 16px;
  padding: 8px 12px;
  background: var(--accent-bg);
  border: 1px solid var(--accent-border);
  border-radius: 6px;
  color: var(--text-h);
}

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

.row-current {
  background: var(--accent-bg) !important;
}

.badge-current {
  margin-left: 8px;
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 99px;
  background: var(--accent);
  color: #fff;
  vertical-align: middle;
}

.actions {
  white-space: nowrap;
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
  margin-right: 6px;
  transition: background 0.15s;
}

.btn-small:hover { background: var(--border); }
.btn-small:disabled { opacity: 0.4; cursor: not-allowed; }

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
  width: 440px;
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

.optional {
  font-weight: 400;
  color: var(--text);
}

input, textarea {
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

input:focus, textarea:focus {
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

/* ── Responsive ──────────────────────────────────────────────────────────── */
@media (max-width: 768px) {
  .roles-page {
    padding: 20px 16px;
  }

  .page-header h1 {
    font-size: 22px;
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .btn-small {
    margin-right: 0;
    flex: 1;
    text-align: center;
  }

  th:nth-child(2), td:nth-child(2),
  th:nth-child(3), td:nth-child(3) {
    display: none;
  }
}

@media (max-width: 480px) {
  .roles-page {
    padding: 16px 12px;
  }

  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  th, td {
    padding: 8px;
  }
}
</style>
