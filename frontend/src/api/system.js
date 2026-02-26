import request from './request'

export default {
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
  factoryReset: () => request.post('/system/factory-reset'),
  getDownloadStatus: () => request.get('/download/status'),
  addToDownload: (bvid, quality) => request.post(`/download/add/${bvid}`, null, { params: { quality } }),
  exportLibrary: (req) => request.post('/library/export', req, { responseType: 'blob' }),
  analyzeImport: (formData) => request.post('/library/import/analyze', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }),
  executeImport: (req) => request.post('/library/import/execute', req)
}
