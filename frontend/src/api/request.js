import axios from 'axios'

const isDev = window.location.port === '5173' || window.location.port === '3000'
const isElectron = window.location.protocol === 'file:'
const API_BASE = import.meta.env.VITE_API_URL || (isDev || isElectron ? 'http://127.0.0.1:12280/api' : `${window.location.origin}/api`)

const service = axios.create({
  baseURL: API_BASE,
  timeout: 30000
})

// 响应拦截器
service.interceptors.response.use(
  response => response.data,
  error => {
    const msg = error.response?.data?.detail || error.message || '网络请求失败'
    // 这里可以根据需要触发全局错误提示，但由于 Store 还没完全重构，暂时保留在 Store 中处理或通过 Promise 抛出
    return Promise.reject(error)
  }
)

export default service
