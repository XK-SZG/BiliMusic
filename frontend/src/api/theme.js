import request from './request'

export default {
  getThemes: () => request.get('/themes'), // Note: backend main.py doesn't have a simple GET /themes, it uses sync
  syncThemes: (data) => request.post('/themes/sync', data),
  saveTheme: (theme) => request.post('/themes', theme),
  deleteTheme: (themeId) => request.delete(`/themes/${themeId}`),
  exportTheme: (themeId) => request.get(`/themes/export/${themeId}`, { responseType: 'blob' }),
  importTheme: (formData) => request.post('/themes/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}
