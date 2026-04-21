import axios from 'axios'

const isDev = window.location.port === '5173' || window.location.port === '3000'
const isElectron = window.location.protocol === 'file:'
const API_BASE = import.meta.env.VITE_API_URL || (isDev || isElectron ? 'http://127.0.0.1:12280/api' : `${window.location.origin}/api`)

console.log('[API Config] 环境检测:', { isDev, isElectron, API_BASE })

const service = axios.create({
  baseURL: API_BASE,
  timeout: 30000
})

// 请求拦截器 - 添加日志
service.interceptors.request.use(
  config => {
    console.log(`[API Request] ${config.method?.toUpperCase()} ${config.url}`, config.params || config.data)
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
    console.log(`[API Response] ${response.config.url}`, response.data)
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
