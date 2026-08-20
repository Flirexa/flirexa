import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  root: fileURLToPath(new URL('./src/demo', import.meta.url)),
  plugins: [vue()],
  base: '/demo-authentic/portal/',
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  build: {
    outDir: '../../../../../landing/demo-authentic/portal',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1800,
    rollupOptions: {
      input: fileURLToPath(new URL('./src/demo/index.html', import.meta.url)),
    },
  },
})
