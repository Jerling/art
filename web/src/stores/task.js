import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useTaskStore = defineStore('task', () => {
  /** @type {import('vue').Ref<object[]>} */
  const tasks = ref([])

  /** @type {import('vue').Ref<boolean>} */
  const loading = ref(false)

  /** @type {import('vue').Ref<string|null>} */
  const error = ref(null)

  function setTasks(list) {
    tasks.value = list
  }

  function addTask(task) {
    tasks.value.unshift(task)
  }

  function replaceTask(updated) {
    const idx = tasks.value.findIndex((t) => t.id === updated.id)
    if (idx !== -1) tasks.value[idx] = updated
  }

  function removeTask(id) {
    tasks.value = tasks.value.filter((t) => t.id !== id)
  }

  function setLoading(v) {
    loading.value = v
  }

  function setError(v) {
    error.value = v
  }

  return { tasks, loading, error, setTasks, addTask, replaceTask, removeTask, setLoading, setError }
})
