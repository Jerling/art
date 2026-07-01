<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { login, isAuthenticated } from '../utils/auth.js'

const router = useRouter()
const route = useRoute()

const username = ref('')
const password = ref('')
const submitting = ref(false)
const error = ref(null)

// Pre-fill the default admin credentials so the user can get in
// with a single click — matches the backend's seeded admin user.
function fillAdmin() {
  username.value = 'admin'
  password.value = 'admin'
}

// If we're already logged in, bounce straight to the intended
// destination (or the tasks list as a sane default).
onMounted(() => {
  if (isAuthenticated()) {
    const next = (route.query.next && String(route.query.next)) || '/tasks'
    router.replace(next)
  }
})

async function handleSubmit() {
  error.value = null
  if (!username.value.trim() || !password.value) {
    error.value = 'Please enter both username and password.'
    return
  }
  submitting.value = true
  try {
    await login(username.value.trim(), password.value)
    const next = (route.query.next && String(route.query.next)) || '/tasks'
    router.replace(next)
  } catch (e) {
    error.value = e.message || 'Login failed.'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <div class="login-logo">📋</div>
        <h1>Art Board</h1>
        <p class="login-subtitle">Sign in to manage your tasks</p>
      </div>

      <form class="login-form" @submit.prevent="handleSubmit">
        <div class="field">
          <label for="login-username">Username</label>
          <input
            id="login-username"
            v-model="username"
            type="text"
            autocomplete="username"
            autofocus
            required
            :disabled="submitting"
            placeholder="admin"
          />
        </div>

        <div class="field">
          <label for="login-password">Password</label>
          <input
            id="login-password"
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
            :disabled="submitting"
            placeholder="••••••"
          />
        </div>

        <div v-if="error" class="login-error" role="alert">
          <span class="login-error-icon">⚠</span>
          <span>{{ error }}</span>
        </div>

        <button type="submit" class="btn-primary login-submit" :disabled="submitting">
          <span v-if="submitting" class="spinner" aria-hidden="true"></span>
          <span>{{ submitting ? 'Signing in…' : 'Sign in' }}</span>
        </button>

        <button
          type="button"
          class="btn-secondary login-fill"
          :disabled="submitting"
          @click="fillAdmin"
        >
          Use default admin credentials
        </button>
      </form>

      <p class="login-hint">
        Default credentials: <code>admin</code> / <code>admin</code>
      </p>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: linear-gradient(135deg, #16171d 0%, #1f2028 50%, #2a1f3d 100%);
}

.login-card {
  width: 100%;
  max-width: 400px;
  background: #fff;
  border-radius: 12px;
  padding: 36px 32px 28px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.4);
  color: #08060d;
}

@media (prefers-color-scheme: dark) {
  .login-card {
    background: #1f2028;
    color: #f3f4f6;
    border: 1px solid #2e303a;
  }
}

.login-header {
  text-align: center;
  margin-bottom: 24px;
}

.login-logo {
  font-size: 36px;
  margin-bottom: 8px;
}

.login-header h1 {
  margin: 0 0 4px;
  font-size: 22px;
  font-weight: 700;
  color: inherit;
  letter-spacing: -0.3px;
}

.login-subtitle {
  margin: 0;
  font-size: 13px;
  color: #6b6375;
}

@media (prefers-color-scheme: dark) {
  .login-subtitle { color: #9ca3af; }
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field label {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  color: #6b6375;
}

@media (prefers-color-scheme: dark) {
  .field label { color: #9ca3af; }
}

.field input {
  padding: 10px 12px;
  border: 1px solid #e5e4e7;
  border-radius: 6px;
  font-size: 14px;
  font-family: inherit;
  background: #fff;
  color: inherit;
  transition: border-color 0.15s, box-shadow 0.15s;
}

@media (prefers-color-scheme: dark) {
  .field input {
    background: #16171d;
    border-color: #2e303a;
  }
}

.field input:focus {
  outline: none;
  border-color: #aa3bff;
  box-shadow: 0 0 0 3px rgba(170, 59, 255, 0.15);
}

.field input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.login-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: #fee2e2;
  color: #991b1b;
  border: 1px solid #fecaca;
  border-radius: 6px;
  font-size: 13px;
}

@media (prefers-color-scheme: dark) {
  .login-error {
    background: rgba(239, 68, 68, 0.15);
    color: #fca5a5;
    border-color: rgba(239, 68, 68, 0.3);
  }
}

.login-error-icon {
  font-weight: 700;
  flex-shrink: 0;
}

.btn-primary,
.btn-secondary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 16px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background 0.15s, transform 0.05s;
}

.btn-primary {
  background: #aa3bff;
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background: #9333ea;
}

.btn-primary:active:not(:disabled) {
  transform: translateY(1px);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: transparent;
  color: #6b6375;
  border-color: #e5e4e7;
}

.btn-secondary:hover:not(:disabled) {
  background: rgba(170, 59, 255, 0.05);
  color: #aa3bff;
  border-color: rgba(170, 59, 255, 0.4);
}

.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

@media (prefers-color-scheme: dark) {
  .btn-secondary {
    color: #9ca3af;
    border-color: #2e303a;
  }
  .btn-secondary:hover:not(:disabled) {
    background: rgba(192, 132, 252, 0.1);
    color: #c084fc;
    border-color: rgba(192, 132, 252, 0.4);
  }
}

.login-submit {
  margin-top: 4px;
}

.login-fill {
  font-size: 12px;
  padding: 8px 12px;
}

.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.login-hint {
  margin: 18px 0 0;
  text-align: center;
  font-size: 12px;
  color: #9ca3af;
}

.login-hint code {
  background: rgba(170, 59, 255, 0.1);
  color: #aa3bff;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 12px;
}

@media (prefers-color-scheme: dark) {
  .login-hint code {
    background: rgba(192, 132, 252, 0.15);
    color: #c084fc;
  }
}
</style>
