import request, { API_BASE } from './request'

// 初始化 SSE 连接，统一订阅后端事件
//
// 事件类型：
//   clipboard_pending  剪贴板检测到新的 BV 号
//   download_status    下载队列 / 进度变化
//   error              错误系统产生了一条需要用户处理的错误（触发弹窗）
//   error_resolved     错误已被处理（修复 / 绕过 / 查看）
//
// 注意：EventSource 不经过 axios，因此复用 request.js 推导出的 API_BASE。
export function initSSE(onClipboardPending, onDownloadStatus, onError, onErrorResolved) {
  const eventSource = new EventSource(`${API_BASE}/system/events`)
  
  eventSource.addEventListener('clipboard_pending', (event) => {
    try {
      const data = JSON.parse(event.data)
      if (onClipboardPending) onClipboardPending(data)
    } catch (e) {
      console.error('SSE clipboard parsing error', e)
    }
  })

  eventSource.addEventListener('download_status', (event) => {
    try {
      const data = JSON.parse(event.data)
      if (onDownloadStatus) onDownloadStatus(data)
    } catch (e) {
      console.error('SSE download parsing error', e)
    }
  })

  // 错误系统事件：这是错误弹窗的数据来源
  eventSource.addEventListener('error', (event) => {
    try {
      const data = JSON.parse(event.data)
      if (onError) onError(data)
    } catch (e) {
      console.error('SSE error parsing error', e)
    }
  })

  eventSource.addEventListener('error_resolved', (event) => {
    try {
      const data = JSON.parse(event.data)
      if (onErrorResolved) onErrorResolved(data)
    } catch (e) {
      console.error('SSE error_resolved parsing error', e)
    }
  })

  eventSource.onerror = (err) => {
    console.error('SSE Connection Error', err)
  }

  return eventSource
}

export default {
  getLogs: () => request.get('/system/logs'),
  getFonts: () => request.get('/system/fonts'),
  uploadFont: (formData) => request.post('/system/fonts/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }),
  getStickers: () => request.get('/system/stickers'),
  uploadSticker: (formData) => request.post('/system/stickers/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }),
  getStickersBundle: () => request.get('/system/stickers/bundle'),
  getBackgrounds: () => request.get('/system/backgrounds'),
  uploadBackground: (formData) => request.post('/system/backgrounds/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }),
  deleteBackground: (filename) => request.delete(`/system/backgrounds/${filename}`),
  uploadParticle: (formData) => request.post('/system/particles/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }),
  shutdown: () => request.post('/system/shutdown'),
  sleep: () => request.post('/system/sleep'),
  factoryReset: () => request.post('/system/factory-reset'),
  getDownloadStatus: () => request.get('/download/status'),
  getPendingBvids: () => request.get('/system/clipboard/pending'),
  confirmBvid: (bvid, collectionId = null, title = null, duration = null) => request.post('/system/clipboard/confirm', { bvid, collection_id: collectionId, title, duration }),
  dismissBvid: (bvid) => request.post('/system/clipboard/dismiss', { bvid }),
  pauseClipboard: () => request.post('/system/clipboard/pause'),
  resumeClipboard: () => request.post('/system/clipboard/resume'),
  addToDownload: (bvid, quality) => request.post(`/download/add/${bvid}`, null, { params: { quality } }),
  retryDownload: (bvid, quality) => request.post(`/download/retry/${bvid}`, null, { params: { quality } }),
  cancelDownload: (bvid) => request.post(`/download/cancel/${bvid}`),
  cancelAllDownloads: () => request.post('/download/cancel-all'),
  exportLibrary: (req) => request.post('/library/export', req, { responseType: req.save_path ? 'json' : 'blob', timeout: 0 }),
  analyzeImport: (formData) => request.post('/library/import/analyze', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }),
  executeImport: (req) => request.post('/library/import/execute', req),

  // ---- 错误系统 ----
  // 说明：错误弹窗（ErrorDialog.vue）与 player store 都通过 systemApi 调用这些方法
  getErrors: (params = {}) => request.get('/system/errors', { params }),
  getError: (errorId) => request.get(`/system/errors/${errorId}`),
  getErrorCatalog: () => request.get('/system/errors/catalog'),
  markErrorViewed: (errorId) => request.post(`/system/errors/${errorId}/viewed`),
  repairError: (errorId) => request.post(`/system/errors/${errorId}/repair`),
  bypassError: (errorId, note = null) => request.post(`/system/errors/${errorId}/bypass`, { note }),
  suppressError: (errorId, suppressed = true) =>
    request.post(`/system/errors/${errorId}/suppress`, null, { params: { suppressed } }),
  downloadErrorPackage: (errorId, includeLogs = true) =>
    request.get(`/system/errors/${errorId}/package`, {
      params: { include_logs: includeLogs },
      responseType: 'blob',
      timeout: 120000
    }),

  // ---- 调试系统 ----
  // 注意：日志系统接口在 ../api/logs.js（logsApi），不要混用
  getDebugStatus: (includeToken = true) =>
    request.get('/debug/status', { params: { include_token: includeToken } }),
  getDebugAgreement: () => request.get('/debug/agreement'),
  acceptDebugConsent: (checklist) => request.post('/debug/consent', { checklist, source: 'ui' }),
  revokeDebugConsent: () => request.delete('/debug/consent'),
  enableDebug: (allowPython = false, allowShell = false) =>
    request.post('/debug/enable', { allow_python: allowPython, allow_shell: allowShell, source: 'ui' }),
  disableDebug: (reason = '用户关闭') => request.post('/debug/disable', { reason }),
  rotateDebugToken: () => request.post('/debug/token/rotate'),

  // 以下接口在后端受 require_debug_token 保护，必须携带 X-Debug-Token 请求头
  getDebugAudit: (token, limit = 100) =>
    request.get('/debug/audit', { params: { limit }, headers: debugHeaders(token) }),
  clearDebugAudit: (token) =>
    request.delete('/debug/audit', { headers: debugHeaders(token) }),
  getDebugHelp: (token) => request.get('/debug/help', { headers: debugHeaders(token) }),
  debugAction: (token, action, payload) => request.post('/debug/action', { action, payload }, {
    headers: debugHeaders(token)
  }),
  debugPing: (token) => request.get('/debug/ping', { headers: debugHeaders(token) })
}

/** 构造调试接口所需的鉴权请求头（令牌为空时给出空对象，由后端统一返回 403） */
function debugHeaders(token) {
  return token ? { 'X-Debug-Token': token } : {}
}
