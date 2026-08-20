import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  root: fileURLToPath(new URL('./src/demo-admin', import.meta.url)),
  plugins: [vue()],
  base: '/demo-authentic/admin/',
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  build: {
    outDir: '../../../../../landing/demo-authentic/admin',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1800,
    rollupOptions: {
      input: fileURLToPath(new URL('./src/demo-admin/index.html', import.meta.url)),
    },
  },
})
