import axios from 'axios'

// API 基址解析
//
// 1. 优先使用 VITE_API_URL（显式指定时）。
// 2. 开发服务器（vite dev）下走**同源相对路径** /api —— vite.config.js 已把
//    /api 代理到后端，因此不再依赖「当前端口是不是 3000 / 5173」这种脆弱判断，
//    用 localhost、127.0.0.1 还是别的端口都能正常访问。
// 3. Electron 打包环境（file:// 协议）没有同源后端，直接指向本机后端。
// 4. 其它情况（例如由后端自身托管前端产物）使用当前 origin。
function resolveApiBase() {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL
  const { protocol, port, hostname, origin } = window.location
  const isHttp = protocol === 'http:' || protocol === 'https:'
  const isLocalHost = hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '[::1]'
  // 开发服务器：本地 http 且端口不是后端端口
  if (isHttp && isLocalHost && port && port !== '12180') return '/api'
  // Electron 打包环境
  if (protocol === 'file:') return 'http://127.0.0.1:12180/api'
  return `${origin}/api`
}

export const API_BASE = resolveApiBase()

const service = axios.create({
  baseURL: API_BASE,
  timeout: 30000
})

// 请求拦截器 - 添加日志
service.interceptors.request.use(
  config => {
    return config
  },
  error => {
    console.error('[API Request Error]', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
service.interceptors.response.use(
  response => {
    return response.data
  },
  error => {
    const msg = error.response?.data?.detail || error.message || '网络请求失败'
    console.error('[API Error]', {
      url: error.config?.url,
      method: error.config?.method,
      status: error.response?.status,
      message: msg,
      detail: error.response?.data
    })
    // 这里可以根据需要触发全局错误提示，但由于 Store 还没完全重构，暂时保留在 Store 中处理或通过 Promise 抛出
    return Promise.reject(error)
  }
)

export default service
