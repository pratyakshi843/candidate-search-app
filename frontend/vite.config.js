import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// Backend URL for the /api proxy; override with API_TARGET=http://127.0.0.1:8001 npm run dev
const apiTarget = process.env.API_TARGET || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { '/api': apiTarget },
  },
})
