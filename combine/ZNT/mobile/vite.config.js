import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import { resolve } from 'node:path'
import { tmpdir } from 'node:os'

export default defineConfig({
  plugins: [vue()],
  cacheDir: resolve(tmpdir(), 'znt-mobile-vite-cache'),
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: { port: 5175, open: false },
})
