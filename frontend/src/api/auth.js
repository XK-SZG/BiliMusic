import request from './request'

export default {
  getStatus: () => request.get('/auth/status'),
  getQR: () => request.get('/auth/qr'),
  checkLogin: (qrKey) => request.get(`/auth/check/${qrKey}`),
  logout: () => request.post('/auth/logout')
}
