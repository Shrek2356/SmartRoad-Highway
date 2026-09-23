import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import { tmpdir } from 'os'
import fontScale from './scripts/fontScale.js'

/**
 * Vite 配置
 * 【后续修改入口】若后端代理地址变化，请修改下方 server.proxy
 */
export default defineConfig({
  plugins: [vue()],
  css: { postcss: { plugins: [fontScale()] } },
  cacheDir: resolve(tmpdir(), 'smartroad-pc-admin-vite-cache'),
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5273,
    // 正式入口由 start-platform.bat 统一打开 /login，避免 Vite 另开根路径页面。
    open: false,
    proxy: {
      // 实时检测桥接：detectmodel/maincode/.../detect_bridge.py （默认 8910）
      '/detect-api': {
        target: 'http://127.0.0.1:8910',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/detect-api/, ''),
      },
      '/business-api': {
        target: 'http://127.0.0.1:8900',
        changeOrigin: true,
        ws: true,
        rewrite: (path) => path.replace(/^\/business-api/, ''),
      },
    },
  },
})
