import request from './request'

export default {
  getFolders: () => request.get('/bili/folders'),
  getFolderVideos: (mediaId, page = 1) => request.get(`/bili/folder/${mediaId}/videos`, { params: { page } }),
  getVideoParts: (bvid) => request.get(`/bili/video/${bvid}/parts`),
  syncFolder: (mediaId) => request.get(`/bili/sync/${mediaId}`, { responseType: 'stream' })
}
