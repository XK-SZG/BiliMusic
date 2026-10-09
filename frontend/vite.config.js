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
    open: false,
    // 把 /api 代理到后端。
    // 这样前端无论通过 127.0.0.1、localhost 还是其它端口访问，
    // 走同源相对路径都能正常请求后端，不再依赖「判断端口号」这种脆弱逻辑。
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:12180',
        changeOrigin: true
      },
      // 后端静态挂载的媒体目录，同样走代理
      '/local_covers': { target: 'http://127.0.0.1:12180', changeOrigin: true },
      '/local_stickers': { target: 'http://127.0.0.1:12180', changeOrigin: true },
      '/local_backgrounds': { target: 'http://127.0.0.1:12180', changeOrigin: true },
      '/downloads': { target: 'http://127.0.0.1:12180', changeOrigin: true }
    }
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