import request from './request'

// 初始化 SSE 连接，统一订阅后端事件
export function initSSE(onClipboardPending, onDownloadStatus) {
  const isDev = window.location.port === '5173' || window.location.port === '3000'
  const isElectron = window.location.protocol === 'file:'
  const API_BASE = import.meta.env.VITE_API_URL || (isDev || isElectron ? 'http://127.0.0.1:12180/api' : `${window.location.origin}/api`)
  
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
  cancelDownload: (bvid) => request.post(`/download/cancel/${bvid}`),
  cancelAllDownloads: () => request.post('/download/cancel-all'),
  exportLibrary: (req) => request.post('/library/export', req, { responseType: req.save_path ? 'json' : 'blob', timeout: 0 }),
  analyzeImport: (formData) => request.post('/library/import/analyze', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }),
  executeImport: (req) => request.post('/library/import/execute', req)
}
