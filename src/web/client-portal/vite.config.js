import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5174,
    proxy: {
      '/client-portal': {
        target: 'http://localhost:10090',
        changeOrigin: true,
      },
      '/api/v1/tariffs': {
        target: 'http://localhost:10090',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: '../client-portal-dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-vue': ['vue', 'vue-router', 'pinia', 'vue-i18n'],
          'vendor-bootstrap': ['bootstrap'],
        },
      },
    },
  },
})
