import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// In dev, /api and /ws are proxied to the FastAPI backend (BACKEND_URL, default :8002).
// In production the backend serves the built app, so everything is same-origin.
const backend = process.env.BACKEND_URL || 'http://localhost:8002'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    chunkSizeWarningLimit: 1100, // three.js alone is ~950 kB
    // separate long-lived vendor chunks: the 3D engine and charts download only when a page needs them
    rolldownOptions: {
      output: {
        advancedChunks: {
          groups: [
            { name: 'three', test: /node_modules[\/](three|@react-three|three-stdlib|camera-controls|maath|meshline|troika)/ },
            { name: 'charts', test: /node_modules[\/](recharts|d3-|victory-vendor)/ },
            { name: 'react', test: /node_modules[\/](react|react-dom|react-router|scheduler)/ },
          ],
        },
      },
    },
  },
  server: {
    host: true,
    proxy: {
      '/api': backend,
      '/ws': { target: backend.replace('http', 'ws'), ws: true },
    },
  },
})
