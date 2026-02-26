import request from './request'

export default {
  getVideos: () => request.get('/local/videos'),
  getCollections: () => request.get('/local/collections'),
  createCollection: (title) => request.post('/local/collections', null, { params: { title } }),
  deleteCollection: (colId) => request.delete(`/local/collections/${colId}`),
  reorderCollections: (ids) => request.post('/local/collections/reorder', ids),
  reorderVideos: (bvids) => request.post('/local/videos/reorder', bvids),
  importBiliVideos: (colId, videos) => request.post(`/local/collections/${colId}/import`, videos),
  addVideoToCollection: (colId, bvid) => request.post(`/local/collections/${colId}/add`, null, { params: { bvid } }),
  removeVideoFromCollection: (colId, bvid) => request.post(`/local/collections/${colId}/remove`, null, { params: { bvid } }),
  batchDeleteVideos: (bvids) => request.post('/local/batch/delete-videos', bvids),
  updateVideoScore: (bvid, params) => request.put(`/videos/${bvid}/score`, null, { params }),
  updateVideoTrim: (bvid, start, end) => request.post(`/videos/${bvid}/trim`, { start, end }),
  updateVideoMetadata: (bvid, formData) => request.post(`/videos/${bvid}/metadata`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }),
  batchAddTags: (reqData) => request.post('/batch/tags', reqData),
  removeTagFromVideo: (bvid, tagId) => request.delete(`/videos/${bvid}/tags/${tagId}`),
  importFile: (formData, collectionId) => {
    let targetUrl = '/local/import-file'
    if (collectionId && collectionId !== 'unclassified') {
      targetUrl += `?collection_id=${collectionId}`
    }
    return request.post(targetUrl, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  }
}
