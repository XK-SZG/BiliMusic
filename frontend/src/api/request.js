import axios from 'axios'

const isDev = window.location.port === '5173' || window.location.port === '3000'
const isElectron = window.location.protocol === 'file:'
const API_BASE = import.meta.env.VITE_API_URL || (isDev || isElectron ? 'http://127.0.0.1:12180/api' : `${window.location.origin}/api`)

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
