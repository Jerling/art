/**
 * Shared permission helpers for the Art web UI.
 *
 * Centralises role-name comparison and status-transition rules so that
 * TasksView, KanbanBoard, RolesView and the router guard all agree.
 */

/**
 * Valid state transitions, encoding the KanbanBoard semantics:
 *   - PENDING       -> IN_PROGRESS, CANCELLED
 *   - IN_PROGRESS  -> PENDING (revert), DONE, CANCELLED
 *   - DONE         -> IN_PROGRESS (reopen)
 *   - CANCELLED    -> PENDING (reopen)
 *
 * Revert/reopen is intentionally allowed; TasksView previously used a
 * stricter map and the two must now agree.
 */
const VALID_TRANSITIONS = {
  PENDING: ['IN_PROGRESS', 'CANCELLED'],
  IN_PROGRESS: ['PENDING', 'DONE', 'CANCELLED'],
  DONE: ['IN_PROGRESS'],
  CANCELLED: ['PENDING'],
}

/**
 * Normalise a role/user object to a lower-cased trimmed name string.
 * Accepts either { name } or { role } fields and tolerates nullish input.
 */
function _nameOf(user) {
  if (!user) return ''
  const raw = user.name ?? user.role ?? ''
  return String(raw).toLowerCase().trim()
}

/**
 * Returns true if the given user/role object represents an admin.
 * Comparison is case-insensitive and whitespace-trimmed.
 */
export function isAdmin(user) {
  return _nameOf(user) === 'admin'
}

/**
 * Returns true if the given user/role object is a read-only visitor.
 * Comparison is case-insensitive and whitespace-trimmed.
 */
export function isReadOnly(user) {
  return _nameOf(user) === 'visitor'
}

/**
 * Returns true if a task currently in `from` status may be moved to `to`.
 * The optional `roleName` parameter is reserved for future role-aware
 * transition rules; today all named roles share the same transition table.
 */
export function canTransition(from, to, roleName = null) {
  if (!from || !to) return false
  if (from === to) return false
  const allowed = VALID_TRANSITIONS[from] || []
  return allowed.includes(to)
}

/** Returns the list of legal next statuses from `from`. */
export function nextStatuses(from) {
  return VALID_TRANSITIONS[from] || []
}

export { VALID_TRANSITIONS }
