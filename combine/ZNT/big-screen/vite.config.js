import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import { tmpdir } from 'os'

export default defineConfig({
  plugins: [vue()],
  cacheDir: resolve(tmpdir(), 'znt-big-screen-vite-cache'),
  resolve: {
    alias: { '@': resolve(__dirname, 'src') },
  },
  server: {
    port: 5174,
    open: false,
  },
})
