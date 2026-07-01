import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
//
// Local dev: Vite serves the SPA at :5173 and proxies API calls to uvicorn
// at :8000 (matching ART_SERVER__PORT in .env.example).  Production builds
// (vite build → web/dist/) are served directly by FastAPI's StaticFiles
// mount, so the same :8000 origin serves both the SPA and the API.
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/roles': 'http://localhost:8000',
      '/tasks': 'http://localhost:8000',
      '/api': 'http://localhost:8000',
      '/metrics': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
