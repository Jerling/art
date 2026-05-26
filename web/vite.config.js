import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/roles': 'http://localhost:8765',
      '/tasks': 'http://localhost:8765',
    },
  },
})
