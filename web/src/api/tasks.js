const BASE = '/tasks'

/**
 * @param {{ page?: number, page_size?: number, role_id?: number|null, status?: string|null }} [params]
 */
export async function listTasks({ page = 1, page_size = 100, role_id = null, status = null } = {}) {
  const params = new URLSearchParams({ page: String(page), page_size: String(page_size) })
  if (role_id !== null) params.set('role_id', String(role_id))
  if (status !== null) params.set('status', status)
  const res = await fetch(`${BASE}?${params}`)
  if (!res.ok) throw new Error(`Failed to list tasks: ${res.status}`)
  return res.json()
}

/** @param {number} id */
export async function getTask(id) {
  const res = await fetch(`${BASE}/${id}`)
  if (!res.ok) throw new Error(`Failed to get task: ${res.status}`)
  return res.json()
}

/**
 * @param {{ title: string, description?: string|null, priority?: string, estimated_hours?: number|null, role_ids?: number[] }} data
 */
export async function createTask(data) {
  const res = await fetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `Failed to create task: ${res.status}`)
  }
  return res.json()
}

/**
 * @param {number} id
 * @param {{ title?: string, description?: string|null, priority?: string, estimated_hours?: number|null, role_ids?: number[] }} data
 */
export async function updateTask(id, data) {
  const res = await fetch(`${BASE}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `Failed to update task: ${res.status}`)
  }
  return res.json()
}

/** @param {number} id @param {boolean} [hard] */
export async function deleteTask(id, hard = false) {
  const url = `${BASE}/${id}${hard ? '?hard=true' : ''}`
  const res = await fetch(url, { method: 'DELETE' })
  if (!res.ok && res.status !== 204) throw new Error(`Failed to delete task: ${res.status}`)
}

/**
 * @param {number} id
 * @param {string} status - PENDING | IN_PROGRESS | DONE | CANCELLED
 */
export async function updateTaskStatus(id, status) {
  const res = await fetch(`${BASE}/${id}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `Failed to update task status: ${res.status}`)
  }
  return res.json()
}

/** @param {number} taskId @param {number[]} roleIds */
export async function setTaskRoles(taskId, roleIds) {
  const res = await fetch(`${BASE}/${taskId}/roles`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role_ids: roleIds }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `Failed to set task roles: ${res.status}`)
  }
  return res.json()
}
