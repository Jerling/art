<script setup>
import { computed } from 'vue'
import { updateTaskStatus } from '../api/tasks.js'

const props = defineProps({
  tasks: { type: Array, required: true },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['task-moved', 'error'])

const COLUMNS = [
  { key: 'PENDING', label: 'Inbox', subtitle: 'pending', icon: '📥', color: '#9ca3af' },
  { key: 'IN_PROGRESS', label: 'Todo', subtitle: 'in progress', icon: '🔄', color: '#3b82f6' },
  { key: 'DONE', label: 'Done', subtitle: 'completed', icon: '✅', color: '#22c55e' },
]

const PRIORITY_COLORS = {
  LOW: '#6b7280',
  MEDIUM: '#d97706',
  HIGH: '#ea580c',
  URGENT: '#dc2626',
}

const PRIORITY_LABELS = {
  LOW: 'Low',
  MEDIUM: 'Med',
  HIGH: 'High',
  URGENT: 'Urgent',
}

const columns = computed(() => {
  return COLUMNS.map((col) => ({
    ...col,
    items: props.tasks.filter((t) => t.status === col.key),
  }))
})

function niceStatus(s) {
  return s === 'IN_PROGRESS' ? 'IN PROGRESS' : s
}

function getNextStatus(current) {
  if (current === 'PENDING') return { to: 'IN_PROGRESS', label: '→ Todo' }
  if (current === 'IN_PROGRESS') return { to: 'DONE', label: '→ Done' }
  return null
}

async function advance(task) {
  const next = getNextStatus(task.status)
  if (!next) return
  try {
    const updated = await updateTaskStatus(task.id, next.to)
    emit('task-moved', updated)
  } catch (e) {
    emit('error', e.message)
  }
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return `${d.getMonth() + 1}/${d.getDate()}`
}
</script>

<template>
  <div class="kanban-board">
    <div v-if="loading" class="kanban-loading">Loading…</div>
    <div v-else class="kanban-columns">
      <div
        v-for="col in columns"
        :key="col.key"
        class="kanban-col"
        :class="`col-${col.key.toLowerCase()}`"
      >
        <div class="col-header">
          <span class="col-icon">{{ col.icon }}</span>
          <div class="col-title-group">
            <span class="col-title">{{ col.label }}</span>
            <span class="col-subtitle">{{ col.subtitle }}</span>
          </div>
          <span class="col-count">{{ col.items.length }}</span>
        </div>

        <div class="col-body">
          <div
            v-for="task in col.items"
            :key="task.id"
            class="board-card"
            :class="{ 'is-done': task.status === 'DONE' }"
          >
            <div class="card-header">
              <span class="card-title">{{ task.title }}</span>
              <span
                class="card-priority"
                :style="{ color: PRIORITY_COLORS[task.priority] }"
              >
                {{ PRIORITY_LABELS[task.priority] || task.priority }}
              </span>
            </div>

            <div v-if="task.description" class="card-desc">{{ task.description }}</div>

            <div class="card-footer">
              <span v-if="task.estimated_hours" class="card-meta">⏱ {{ task.estimated_hours }}h</span>
              <span class="card-meta">{{ formatDate(task.created_at) }}</span>
              <span v-if="task.role_ids && task.role_ids.length" class="card-meta">👤 {{ task.role_ids.length }}</span>
            </div>

            <!-- Advance button -->
            <button
              v-if="getNextStatus(task.status)"
              class="advance-btn"
              :style="{
                '--adv-color': col.color,
              }"
              @click="advance(task)"
              :title="`Move to ${getNextStatus(task.status).to}`"
            >
              {{ getNextStatus(task.status).label }}
              <span class="adv-arrow">→</span>
            </button>
          </div>

          <div v-if="!col.items.length" class="col-empty">
            No tasks
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.kanban-board {
  margin-top: 4px;
}

.kanban-loading {
  text-align: center;
  padding: 48px;
  color: var(--text);
  font-size: 15px;
}

.kanban-columns {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  align-items: start;
}

.kanban-col {
  background: var(--social-bg);
  border-radius: 10px;
  padding: 14px;
  min-height: 200px;
  border: 1px solid var(--border);
  display: flex;
  flex-direction: column;
}

.col-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 2px solid var(--border);
}

.col-icon {
  font-size: 18px;
  line-height: 1;
}

.col-title-group {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.col-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-h);
  letter-spacing: 0.3px;
}

.col-subtitle {
  font-size: 11px;
  color: var(--text);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.col-count {
  font-size: 12px;
  font-weight: 600;
  background: var(--border);
  padding: 2px 8px;
  border-radius: 99px;
  color: var(--text);
}

.col-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
}

.board-card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  transition: box-shadow 0.15s, transform 0.1s;
  border-left: 3px solid transparent;
  position: relative;
}

.board-card:hover {
  box-shadow: var(--shadow);
  transform: translateY(-1px);
}

.board-card.is-done {
  opacity: 0.75;
}

.col-PENDING .board-card {
  border-left-color: #9ca3af;
}

.col-in_progress .board-card {
  border-left-color: #3b82f6;
}

.col-done .board-card {
  border-left-color: #22c55e;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 6px;
}

.card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-h);
  line-height: 1.4;
  word-break: break-word;
}

.card-priority {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  white-space: nowrap;
  flex-shrink: 0;
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

.card-footer {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.card-meta {
  font-size: 11px;
  color: var(--text);
}

.advance-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  width: 100%;
  padding: 6px 10px;
  border: 1px dashed var(--adv-color, var(--border));
  border-radius: 6px;
  background: transparent;
  color: var(--adv-color, var(--text));
  font-size: 11px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s;
}

.advance-btn:hover {
  background: color-mix(in srgb, var(--adv-color, var(--accent)) 10%, transparent);
}

.adv-arrow {
  font-size: 13px;
  transition: transform 0.15s;
}

.advance-btn:hover .adv-arrow {
  transform: translateX(3px);
}

.col-empty {
  text-align: center;
  padding: 20px;
  color: var(--text);
  font-size: 12px;
  font-style: italic;
}

/* ── Responsive ──────────────────────────────────────────────────────────── */
@media (max-width: 860px) {
  .kanban-columns {
    grid-template-columns: 1fr;
  }
}

@media (min-width: 861px) and (max-width: 1100px) {
  .kanban-columns {
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
  }

  .kanban-col {
    padding: 10px;
  }
}
</style>
