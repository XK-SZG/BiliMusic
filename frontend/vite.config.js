import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { readFileSync } from 'fs'
import { resolve } from 'path'

// 读取 package.json 获取版本号
const packageJson = JSON.parse(
  readFileSync(resolve(__dirname, 'package.json'), 'utf-8')
)

// https://vitejs.dev/config/
export default defineConfig({
  base: './',
  plugins: [vue()],
  // 定义全局常量
  define: {
    __APP_VERSION__: JSON.stringify(packageJson.version)
  },
  server: {
    host: '127.0.0.1',
    port: 3000,
    strictPort: true,
    // 自动打开浏览器
    open: false
  },
  optimizeDeps: {
    include: ['echarts', 'axios', 'vue', 'vue-router', 'pinia']
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['vue', 'vue-router', 'pinia']
        }
      }
    }
  }
})