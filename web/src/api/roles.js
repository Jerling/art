import { authFetch } from '../utils/auth.js'

async function _err(res, fallback) {
  try {
    const data = await res.json()
    if (data?.detail) return data.detail
  } catch (_) {
    /* not JSON */
  }
  return fallback
}

const BASE = '/roles'

/** @param {{ page?: number, page_size?: number }} [params] */
export async function listRoles({ page = 1, page_size = 50 } = {}) {
  const res = await authFetch(`${BASE}?page=${page}&page_size=${page_size}`)
  if (!res.ok) throw new Error(await _err(res, `Failed to list roles: ${res.status}`))
  return res.json()
}

/** @param {number} id */
export async function getRole(id) {
  const res = await authFetch(`${BASE}/${id}`)
  if (!res.ok) throw new Error(await _err(res, `Failed to get role: ${res.status}`))
  return res.json()
}

/** @param {{ name: string, description?: string|null }} data */
export async function createRole(data) {
  const res = await authFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(await _err(res, `Failed to create role: ${res.status}`))
  return res.json()
}

/** @param {number} id @param {{ name?: string, description?: string|null }} data */
export async function updateRole(id, data) {
  const res = await authFetch(`${BASE}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(await _err(res, `Failed to update role: ${res.status}`))
  return res.json()
}

/** @param {number} id @param {boolean} [hard] */
export async function deleteRole(id, hard = false) {
  const url = `${BASE}/${id}${hard ? '?hard=true' : ''}`
  const res = await authFetch(url, { method: 'DELETE' })
  if (!res.ok && res.status !== 204) throw new Error(`Failed to delete role: ${res.status}`)
}
