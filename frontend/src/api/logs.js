import request, { API_BASE } from './request'

/**
 * 实时日志推送（SSE）
 *
 * 与「手动刷新」相比，这里的长连接会在后端产生新日志时立即推送，
 * 因此日志面板无需轮询、无需点击刷新。
 *
 * 注意：EventSource 不经过 axios，因此这里显式复用 request.js 推导出的
 * API_BASE（开发环境下为同源相对路径 /api，由 vite 代理转发到后端）。
 *
 * @param {Function} onLog   收到单条日志时的回调
 * @param {Function} onReady 连接就绪回调（携带当前最新序号与服务器时间）
 * @param {Object}   filters 服务端筛选条件：{ hide_heartbeat, hide_heartbeat_categories, levels, keyword, exclude }
 * @returns {EventSource}
 */
export function initLogStream(onLog, onReady, filters = {}) {
  const params = new URLSearchParams()
  if (filters.hide_heartbeat) params.set('hide_heartbeat', 'true')
  if (filters.hide_heartbeat_categories) {
    params.set('hide_heartbeat_categories', filters.hide_heartbeat_categories)
  }
  if (filters.levels) params.set('levels', filters.levels)
  if (filters.keyword) params.set('keyword', filters.keyword)
  if (filters.exclude) params.set('exclude', filters.exclude)
  params.set('request_timeout', '1800')

  const eventSource = new EventSource(`${API_BASE}/logs/stream?${params.toString()}`)

  eventSource.addEventListener('ready', (event) => {
    try {
      const data = JSON.parse(event.data)
      if (onReady) onReady(data)
    } catch (e) {
      console.error('日志 SSE ready 解析失败', e)
    }
  })

  eventSource.addEventListener('log', (event) => {
    try {
      const data = JSON.parse(event.data)
      if (onLog) onLog(data)
    } catch (e) {
      console.error('日志 SSE 解析失败', e)
    }
  })

  return eventSource
}

export default {
  // ---- 内存日志（筛选 / 实时 / 导出）----
  getStats: () => request.get('/logs/stats'),
  getMeta: () => request.get('/logs/meta'),
  getLogs: (params = {}) => request.get('/logs/list', { params }),
  clearLogs: (memoryOnly = true) =>
    request.post('/logs/clear', null, { params: { memory_only: memoryOnly } }),

  /** 导出筛选后的日志（一键复制）：返回纯文本 */
  exportLogs: (params = {}) => request.get('/logs/export', {
    params,
    responseType: 'text',
    transformResponse: [(data) => data]
  }),

  /** 下载筛选后的日志文件 */
  downloadLogs: (params = {}) => request.get('/logs/export', {
    params: { ...params, download: true },
    responseType: 'blob',
    timeout: 120000
  }),

  // ---- 物理日志目录管理 ----
  getLogFiles: () => request.get('/logs/files'),
  readLogFile: (filename, maxBytes = 512 * 1024) =>
    request.get(`/logs/files/${encodeURIComponent(filename)}`, { params: { max_bytes: maxBytes } }),
  openLogDir: () => request.post('/logs/open-dir'),
  setRetention: (params) => request.post('/logs/retention', null, { params }),
  purgeLogFiles: (includeActive = false) =>
    request.post('/logs/purge', null, { params: { include_active: includeActive, confirmed: true } })
}
