import { defineStore } from 'pinia'
import { useSettingsStore } from './settings'
import { useThemeStore } from './theme'
import { db } from '../../utils/db'
import authApi from '../../api/auth'
import biliApi from '../../api/bili'
import localApi from '../../api/local'
import systemApi from '../../api/system'

const isDev = window.location.port === '5173' || window.location.port === '3000'
const isElectron = window.location.protocol === 'file:'
const API_BASE = import.meta.env.VITE_API_URL || (isDev || isElectron ? 'http://127.0.0.1:12243/api' : `${window.location.origin}/api`)

export const usePlayerStore = defineStore('player', {
  state: () => ({
    user: null,
    biliFolders: JSON.parse(localStorage.getItem('cache_bili_folders') || '[]'),
    folderCache: {}, // Moved to IndexedDB
    folderPagination: {}, // Moved to IndexedDB
    localVideos: [],
    localCollections: [],
    currentVideo: JSON.parse(localStorage.getItem('cache_current_video') || 'null'),
    playQueue: [], // Moved to IndexedDB
    queueIndex: parseInt(localStorage.getItem('cache_queue_index') || '-1'),
    isPlaying: false,
    isBuffering: false,
    audioElement: null,
    isUiCollapsed: false,
    isFullImmersive: false,
    isOffline: false,
    isBiliOffline: false,
    lastRoute: localStorage.getItem('last_route') || '/',
    filteredQueueIndices: [],
    selectedBiliBvids: [],
    selectedBvids: [],
    activeCollectionId: null,
    pollInterval: null,
    downloadSession: new Set(),
    activeDownloadCount: 0,
    globalDownloadProgress: 0,
    toast: { show: false, msg: '', type: 'info' },
    currentTime: 0,
    duration: 0,
    buffered: 0,
    volume: parseFloat(localStorage.getItem('player_volume') || '0.7'),
    volumeShowTrigger: 0,
    playMode: localStorage.getItem('player_mode') || 'list',
    weightedMode: 'positive',
    shuffleSnapshot: [],
    lengthControl: JSON.parse(localStorage.getItem('player_length_control') || JSON.stringify({
      enabled: false,
      type: 'count',
      target: 0,
      current: 0
    })),
    autoShutdown: localStorage.getItem('player_auto_shutdown') === 'true',
    userReacted: false,
    _lastTime: null,
    _lastSeekTime: 0
  }),

  actions: {
    showToast(msg, type = 'info') {
      this.toast.msg = msg; this.toast.type = type; this.toast.show = true
      setTimeout(() => { this.toast.show = false }, 3000)
    },

    async init() {
      const themeStore = useThemeStore()
      console.log("[Player Init] 开始初始化...");
      themeStore.applyTheme()

      // Load from IndexedDB
      let savedQueueData = []
      try {
         savedQueueData = await db.playQueue.toArray()
      } catch (e) {
         console.warn("IndexedDB load queue failed", e)
      }
      // Fallback or read from old localStorage if empty (migration handling)
      let savedQueue = []
      if (savedQueueData && savedQueueData.length > 0) {
         savedQueue = savedQueueData
      } else {
         const oldQueueData = localStorage.getItem('cache_play_queue')
         if (oldQueueData) {
           try {
             savedQueue = JSON.parse(oldQueueData)
           } catch(e) {}
         }
      }
      
      const savedIndex = parseInt(localStorage.getItem('cache_queue_index') || '-1')
      const savedBvid = localStorage.getItem('cache_current_video_bvid')
      
      // Load folder cache and pagination
      try {
        const allFolderCache = await db.folderCache.toArray()
        allFolderCache.forEach(item => {
          this.folderCache[item.id] = (item.data || []).map(v => this._normalizeVideo(v))
        })
      } catch(e){}
      
      try {
        const allPagination = await db.folderPagination.toArray()
        allPagination.forEach(item => { this.folderPagination[item.id] = item.data })
      } catch(e){}

      if (savedQueue.length > 0) {
        this.playQueue = savedQueue.map(v => this._normalizeVideo(v))
        if (savedBvid) {
          const idx = savedQueue.findIndex(v => v.bvid === savedBvid)
          if (idx !== -1) {
            this.queueIndex = idx
            this.currentVideo = savedQueue[idx]
          }
        }
        if (this.queueIndex === -1 && savedIndex >= 0 && savedIndex < savedQueue.length) {
          this.queueIndex = savedIndex
          this.currentVideo = savedQueue[savedIndex]
        }
      }

      themeStore.fetchStickersBundle()
      themeStore.updateThemeColor(themeStore.themeColor, false)
      await themeStore.fetchCustomBackgrounds()
      await this.checkLogin()
      
      window.addEventListener('online', () => {
        if (!this.user) this.checkLogin()
      })

      await themeStore.syncThemes()
      this.startStatusPolling()
    },

    formatImg(url, size = null) {
      if (!url) return ''
      if (url.startsWith('/local_covers/') || url.startsWith('/local_stickers/')) {
        return `${API_BASE.replace('/api', '')}${url}`
      }
      if (url.startsWith('http://127.0.0.1') || url.startsWith(window.location.origin)) return url
      
      let cleanUrl = url.replace(/^https?:/, '').replace(/^http:/, '')
      let result = cleanUrl.startsWith('//') ? `https:${cleanUrl}` : `https://${cleanUrl}`
      if (size && result.includes('hdslb.com')) {
        result = `${result}@${size}`
      }
      if (result.includes('hdslb.com')) {
        return `${API_BASE}/proxy/image?url=${encodeURIComponent(result)}`
      }
      return result
    },

    async checkLogin() {
      try {
        const data = await authApi.getStatus()
        this.user = data.is_logged_in ? data : null
        this.isOffline = false
        this.isBiliOffline = data.is_bili_offline || false
      } catch (e) {
        this.isOffline = true
      } finally {
        // 如果已经清除定时器（如正在手动注销），则不再递归
        if (this._checkLoginTimeout) clearTimeout(this._checkLoginTimeout)
        this._checkLoginTimeout = setTimeout(() => this.checkLogin(), 5000);
      }
    },

    async logout() { 
      try {
        await authApi.logout()
        this.user = null 
        this.showToast("账号已退出", "success")
      } catch (e) {
        console.error("Logout failed", e)
      }
    },

    async fetchBiliFolders() {
      try {
        const data = await biliApi.getFolders()
        if (data.code === 0) {
          this.biliFolders = data.data.map(f => ({ ...f, cover: this.formatImg(f.cover || f.pic) }))
          localStorage.setItem('cache_bili_folders', JSON.stringify(this.biliFolders))
        }
      } catch (e) { console.error(e) }
    },

    async fetchFolderVideos(mediaId, isLoadMore = false) {
      const idStr = String(mediaId)
      if (!this.folderPagination[idStr]) { this.folderPagination[idStr] = { page: 1, hasMore: true } }
      const pageInfo = this.folderPagination[idStr]
      if (!isLoadMore) { pageInfo.page = 1; pageInfo.hasMore = true }
      if (isLoadMore && !pageInfo.hasMore) return this.folderCache[idStr]
      try {
        const data = await biliApi.getFolderVideos(idStr, pageInfo.page)
        const rawVideos = data.medias || []
        const newVideos = rawVideos.map(v => this._normalizeVideo(v))

        if (!isLoadMore) {
          this.folderCache[idStr] = newVideos; pageInfo.page = 2; pageInfo.hasMore = data.has_more
        } else {
          const currentList = this.folderCache[idStr] || []
          const existingIds = new Set(currentList.map(v => v.bvid))
          this.folderCache[idStr] = [...currentList, ...newVideos.filter(v => !existingIds.has(v.bvid))]
          pageInfo.hasMore = data.has_more; if (pageInfo.hasMore) pageInfo.page++
        }
        this.folderPagination = { ...this.folderPagination }; this.folderCache = { ...this.folderCache }
        
        // Save to IndexedDB (unwrap from Proxy to raw object to prevent DataCloneError)
        // 进一步确保数据纯净，使用 JSON 序列化处理 Proxy 对象
        await db.folderCache.put({ id: idStr, data: JSON.parse(JSON.stringify(this.folderCache[idStr] || [])) })
        await db.folderPagination.put({ id: idStr, data: JSON.parse(JSON.stringify(this.folderPagination[idStr] || {})) })
      } catch (e) { console.error("Fetch videos failed", e) }
      return this.folderCache[idStr]
    },

    async fetchAllFolderVideos(mediaId) {
      const idStr = String(mediaId)
      await this.fetchFolderVideos(idStr, false)
      while (this.folderPagination[idStr]?.hasMore) { 
        await this.fetchFolderVideos(idStr, true)
        await new Promise(r => setTimeout(r, 350)) 
      }
      return this.folderCache[idStr]
    },

    async expandVideoParts(folderId, video, isSilent = false) {
      try {
        const data = await biliApi.getVideoParts(video.bvid)
        const parts = data.parts
        if (parts && parts.length > 0) {
          const newVideos = parts.map(p => this._normalizeVideo({
            ...p,
            bvid: p.id,
            owner: video.owner,
            pic: video.pic,
            is_part: true
          }))
          const id = String(folderId)
          if (folderId && this.folderCache[id]) {
            const idx = this.folderCache[id].findIndex(v => v.bvid === video.bvid)
            if (idx !== -1) {
              this.folderCache[id].splice(idx, 1, ...newVideos)
              this.folderCache = {...this.folderCache}
              await db.folderCache.put({ id, data: JSON.parse(JSON.stringify(this.folderCache[id] || [])) })
            }
          }
          return newVideos
        }
      } catch (e) { if (!isSilent) console.error("Expand failed", e) }
      return []
    },

    async fetchLocalVideos() {
      const data = await localApi.getVideos()
      this.localVideos = data.map(v => ({ ...v, progress: v.download_status === 'completed' ? 100 : 0 }))
    },

    async fetchLocalCollections() {
      const data = await localApi.getCollections()
      this.localCollections = data
    },

    getSyncedCollections(bvid) { 
      const v = this.localVideos.find(i => i.bvid === bvid)
      return v ? (v.collections || []) : [] 
    },

    async updateVideoCollections(video, targetColIds) {
      let toProcess = []
      if (video.page > 1 && !video.is_part) toProcess = await this.expandVideoParts(null, video, true)
      else toProcess = [video]
      for (const v of toProcess) {
        const currentIds = this.getSyncedCollections(v.bvid).map(c => c.id)
        const toAdd = targetColIds.filter(id => !currentIds.includes(id))
        const toRemove = currentIds.filter(id => !targetColIds.includes(id))
        for (const colId of toAdd) {
          await localApi.importBiliVideos(colId, [{ bvid: v.bvid, title: v.title, owner: v.owner || v.upper?.name, pic: this.formatImg(v.pic || v.cover), duration: v.duration }])
        }
        for (const colId of toRemove) await localApi.removeVideoFromCollection(colId, v.bvid)
      }
      await this.fetchLocalVideos()
    },

    async updateVideoTrim(bvid, start, end) {
      try {
        await localApi.updateVideoTrim(bvid, start, end)
        const v = this.localVideos.find(i => i.bvid === bvid)
        if (v) { v.trim_start = start; v.trim_end = end }
        if (this.currentVideo && this.currentVideo.bvid === bvid) {
          this.currentVideo.trim_start = start; this.currentVideo.trim_end = end
        }
        this.playQueue.forEach(item => {
          if (item.bvid === bvid) { item.trim_start = start; item.trim_end = end }
        })
        this.showToast("播放区间已更新", "success")
      } catch (e) { this.showToast("更新失败", "error") }
    },

    async updateVideoScore(bvid, score, metadata = null) {
      console.log(`[Store] Updating score for ${bvid}: ${score}`);
      try {
        const params = { score }
        // 自动提取元数据以支持后端自动归档逻辑
        if (metadata) {
            params.title = metadata.title
            params.owner = metadata.owner
            params.pic = metadata.pic
            params.duration = metadata.duration
        } else {
            const localV = this.localVideos.find(v => v.bvid === bvid)
            if (localV) {
                params.title = localV.title
                params.owner = localV.owner
                params.pic = localV.pic
                params.duration = localV.duration
            } else if (this.currentVideo && this.currentVideo.bvid === bvid) {
                params.title = this.currentVideo.title
                params.owner = this.currentVideo.owner
                params.pic = this.currentVideo.pic
                params.duration = this.currentVideo.duration
            }
        }
        await localApi.updateVideoScore(bvid, params)
        
        // 更新内存中的数据以保证 UI 响应
        const v = this.localVideos.find(i => i.bvid === bvid)
        if (v) v.score = score
        if (this.currentVideo && this.currentVideo.bvid === bvid) this.currentVideo.score = score
        this.playQueue.forEach(item => { if (item.bvid === bvid) item.score = score })
        
      } catch (e) { 
        console.error(`[Store] Score update failed for ${bvid}:`, e)
        throw e 
      }
    },

    async batchDelete() {
      await localApi.batchDeleteVideos(this.selectedBvids)
      await this.fetchLocalVideos()
    },

    async unsyncVideo(colId, bvid) {
      await localApi.removeVideoFromCollection(colId, bvid)
      await this.fetchLocalVideos()
    },

    async addToDownload(bvid) {
      const settingsStore = useSettingsStore()
      this.downloadSession.add(bvid)
      try {
        await systemApi.addToDownload(bvid, settingsStore.settings.cacheQuality)
        const v = this.localVideos.find(i => i.bvid === bvid); if (v) v.download_status = 'pending'
      } catch (e) { this.downloadSession.delete(bvid) }
    },

    startStatusPolling() {
      if (this.pollInterval) clearInterval(this.pollInterval)
      this.pollInterval = setInterval(async () => {
        try {
          const data = await systemApi.getDownloadStatus(); const tasks = data.tasks || []
          this.activeDownloadCount = tasks.filter(t => t.status === 'downloading').length
          this.localVideos.forEach(localV => {
            const task = tasks.find(t => t.bvid === localV.bvid)
            if (task) { localV.download_status = task.status; localV.progress = task.progress }
            else if (['downloading', 'pending'].includes(localV.download_status)) { localV.download_status = 'completed'; localV.progress = 100 }
          })
          const sessionBvids = Array.from(this.downloadSession)
          if (sessionBvids.length > 0) {
            let totalSum = 0, completed = 0
            sessionBvids.forEach(bvid => {
              const task = tasks.find(t => t.bvid === bvid); const localV = this.localVideos.find(v => v.bvid === bvid)
              if (task) totalSum += (task.progress || 0)
              else if (localV && localV.download_status === 'completed') { totalSum += 100; completed++ }
              else { totalSum += 100; completed++ }
            })
            this.globalDownloadProgress = totalSum / sessionBvids.length
            if (completed === sessionBvids.length && this.globalDownloadProgress >= 99.9) {
              setTimeout(() => { if (this.activeDownloadCount === 0) { this.downloadSession.clear(); this.globalDownloadProgress = 0 } }, 2000)
            }
          }
        } catch (e) {}
      }, 1000)
    },

    _saveQueue() {
      const seen = new Set()
      this.playQueue = this.playQueue.map(v => this._normalizeVideo(v)).filter(v => {
        if (!v.bvid || seen.has(v.bvid)) return false
        seen.add(v.bvid); return true
      })
      // 同时写入 IndexedDB，并使用 JSON.parse(JSON.stringify()) 脱水
      db.playQueue.clear().then(() => {
         db.playQueue.bulkAdd(JSON.parse(JSON.stringify(this.playQueue || []))).catch(e => console.warn("IndexedDB save queue failed", e))
      }).catch(e => console.warn("IndexedDB clear failed", e))

      // 备份到 localStorage
      try {
        localStorage.setItem('cache_play_queue', JSON.stringify(this.playQueue))
      } catch (e) {
        console.warn("localStorage quota exceeded for play_queue, skipped.")
      }
      
      localStorage.setItem('cache_queue_index', this.queueIndex.toString())
      if (this.currentVideo) {
        localStorage.setItem('cache_current_video_bvid', this.currentVideo.bvid)
        localStorage.setItem('cache_current_video', JSON.stringify(this.currentVideo))
      }
    },

    _normalizeVideo(v) {
      return {
        ...v,
        bvid: v.bvid || v.bv_id,
        pic: v.pic || v.cover,
        owner: v.owner || v.upper?.name || 'Unknown'
      }
    },

    async playVideo(video, autoDownload = false) {
      const normalized = this._normalizeVideo(video)
      const targetId = normalized.bvid
      if (autoDownload && normalized.download_status !== 'completed' && normalized.download_status !== 'pending' && normalized.download_status !== 'downloading') { this.addToDownload(targetId) }
      const idx = this.playQueue.findIndex(v => (v.bvid || v.bv_id) === targetId)
      if (idx !== -1) {
        this.playQueue[idx] = { ...this.playQueue[idx], ...normalized }
        this.queueIndex = idx
      } else {
        this.playQueue.splice(this.queueIndex + 1, 0, normalized)
        this.queueIndex++
      }
      this.currentVideo = this.playQueue[this.queueIndex]
      await this._saveQueue()
      this._loadAndPlay()
    },

    async playList(list, startIdx = 0, autoDownload = false) {
      const normalizedList = list.map(v => this._normalizeVideo(v))
      if (autoDownload) { normalizedList.forEach(v => { if (v.download_status !== 'completed' && v.download_status !== 'pending' && v.download_status !== 'downloading') { this.addToDownload(v.bvid) } }) }
      this.playQueue = normalizedList; this.queueIndex = startIdx; this.currentVideo = this.playQueue[startIdx]; this._loadAndPlay(); await this._saveQueue()
    },

    async addToQueue(video, autoDownload = false) {
      const normalized = this._normalizeVideo(video)
      const targetId = normalized.bvid; if (!targetId) return
      const idx = this.playQueue.findIndex(v => (v.bvid || v.bv_id) === targetId)
      if (idx !== -1) {
        this.playQueue[idx] = { ...this.playQueue[idx], ...normalized }
        this.showToast("该视频已在队列中", "info")
        return
      }
      if (autoDownload && normalized.download_status !== 'completed' && normalized.download_status !== 'pending' && normalized.download_status !== 'downloading') { this.addToDownload(normalized.bvid) }
      this.playQueue.push(normalized); this.showToast(`已加入队列`, "success"); await this._saveQueue()
    },

    async addToQueueList(list, autoDownload = false) {
      const existing = new Set(this.playQueue.map(v => v.bvid || v.bv_id)); const newOnes = []
      list.forEach(v => {
        const normalized = this._normalizeVideo(v)
        const id = normalized.bvid
        if (id && !existing.has(id)) {
          newOnes.push(normalized)
          if (autoDownload && normalized.download_status !== 'completed') this.addToDownload(id)
        }
      })
      if (newOnes.length === 0) { this.showToast("选中的视频均已在队列中", "info") ; return }
      this.playQueue.push(...newOnes); this.showToast(`已添加 ${newOnes.length} 个视频`, "success"); await this._saveQueue()
    },

    async removeFromQueue(index) {
      const isCurrent = index === this.queueIndex
      this.playQueue.splice(index, 1)
      if (index < this.queueIndex) this.queueIndex--
      else if (isCurrent) this._stopAndReset()
      await this._saveQueue()
    },

    async removeFromQueueBatch(bvids) {
      const curBvid = this.currentVideo?.bvid
      const isDeletingCurrent = bvids.includes(curBvid)
      this.playQueue = this.playQueue.filter(v => !bvids.includes(v.bvid))
      if (isDeletingCurrent) this._stopAndReset()
      else if (curBvid) {
        this.queueIndex = this.playQueue.findIndex(v => v.bvid === curBvid)
        if (this.queueIndex === -1) this._stopAndReset()
      } else this.queueIndex = -1
      await this._saveQueue()
    },

    _stopAndReset() {
      this.isPlaying = false; this.currentVideo = null; this.queueIndex = -1
      if (this.audioElement) { this.audioElement.pause(); this.audioElement.src = ''; this.audioElement.load() }
      this.currentTime = 0; this.duration = 0; this.buffered = 0
    },

    async playFromQueue(index) {
      if (index >= 0 && index < this.playQueue.length) {
        this.queueIndex = index; this.currentVideo = this.playQueue[index]
        await this._saveQueue(); this._loadAndPlay()
      }
    },

    playRandomFromQueue() {
      if (this.playQueue.length === 0) return
      
      let pool = []
      // 如果当前有筛选条件，只在筛选结果中随机
      if (this.filteredQueueIndices && this.filteredQueueIndices.length > 0) {
        pool = this.filteredQueueIndices
      } else {
        pool = this.playQueue.map((_, i) => i)
      }
      
      const randomIdx = pool[Math.floor(Math.random() * pool.length)]
      this.playFromQueue(randomIdx)
      this.showToast("已为您随机挑选一曲", "success")
    },

    async reorderQueue(newQueue) {
      const curBvid = this.currentVideo?.bvid
      this.playQueue = newQueue
      if (curBvid) this.queueIndex = this.playQueue.findIndex(v => v.bvid === curBvid)
      await this._saveQueue()
    },

    async next() {
      if (this.playQueue.length === 0) return
      const hasFilter = this.filteredQueueIndices.length > 0 && this.filteredQueueIndices.length < this.playQueue.length
      if (this.lengthControl.enabled && this.lengthControl.type === 'count' && this.lengthControl.target > 0) {
        this.lengthControl.current++; if (this.lengthControl.current >= this.lengthControl.target) { this._advanceIndexOnly(); this._handleAutoStop("已达到预设数量"); return }
      }
      if (this.playMode === 'single_loop') { this._loadAndPlay(); return }
      let nextIdx = -1; const pool = hasFilter ? this.filteredQueueIndices : this.playQueue.map((_, i) => i)
      if (this.playMode.startsWith('shuffle')) {
        nextIdx = pool[Math.floor(Math.random() * pool.length)]
      } else if (this.playMode === 'weighted') {
        nextIdx = this._getWeightedNextIndex(hasFilter ? this.filteredQueueIndices : null)
      } else if (this.playMode === 'list_loop') {
        const curPos = pool.indexOf(this.queueIndex); nextIdx = pool[(curPos + 1) % pool.length]
      } else {
        if (hasFilter) {
          const curPos = this.filteredQueueIndices.indexOf(this.queueIndex)
          if (curPos !== -1 && curPos < this.filteredQueueIndices.length - 1) nextIdx = this.filteredQueueIndices[curPos + 1]
          else { this._handleAutoStop("已播完筛选列表"); return }
        } else {
          if (this.queueIndex < this.playQueue.length - 1) nextIdx = this.queueIndex + 1
          else { this._handleAutoStop("列表已播完"); return }
        }
      }
      if (nextIdx !== -1) {
        this.queueIndex = nextIdx; this.currentVideo = this.playQueue[this.queueIndex];
        await this._saveQueue(); this._loadAndPlay()
      }
    },

    _advanceIndexOnly() {
      const settingsStore = useSettingsStore()
      const hasFilter = this.filteredQueueIndices.length > 0 && this.filteredQueueIndices.length < this.playQueue.length
      const pool = hasFilter ? this.filteredQueueIndices : this.playQueue.map((_, i) => i)
      const curPos = pool.indexOf(this.queueIndex); const nextIdx = pool[(curPos + 1) % pool.length]
      this.queueIndex = nextIdx; this.currentVideo = this.playQueue[nextIdx]
      const isOnline = this.currentVideo.download_status !== 'completed'
      if (this.audioElement) {
        if (!isOnline) this.audioElement.src = `${API_BASE.replace('/api', '')}/downloads/${this.currentVideo.bvid}.mp4`
        else this.audioElement.src = `${API_BASE}/play/stream/${this.currentVideo.bvid}?quality=${settingsStore.settings.streamQuality}`
      }
    },

    _getWeightedNextIndex(limitIndices = null) {
      const settingsStore = useSettingsStore()
      let pool = this.playQueue.map((v, i) => ({ v, i }))
      if (limitIndices) pool = pool.filter(item => limitIndices.includes(item.i))
      const sensitivity = settingsStore.settings.weightSensitivity || 2.0
      const weights = pool.map(item => { 
        const s = item.v.score ?? 5.0
        let baseWeight = this.weightedMode === 'positive' ? s : (11 - s)
        return Math.pow(baseWeight / 5, sensitivity)
      })
      const sum = weights.reduce((a, b) => a + b, 0); let rand = Math.random() * sum
      for (let i = 0; i < weights.length; i++) { if (rand < weights[i]) return pool[i].i; rand -= weights[i] }
      return pool[0].i
    },

    async prev() {
      const hasFilter = this.filteredQueueIndices.length > 0 && this.filteredQueueIndices.length < this.playQueue.length
      let prevIdx = -1; const pool = hasFilter ? this.filteredQueueIndices : this.playQueue.map((_, i) => i)
      if (this.playMode === 'list_loop') { const curPos = pool.indexOf(this.queueIndex); prevIdx = pool[(curPos - 1 + pool.length) % pool.length] }
      else {
        if (hasFilter) { const curPos = this.filteredQueueIndices.indexOf(this.queueIndex); if (curPos > 0) prevIdx = this.filteredQueueIndices[curPos - 1] }
        else { if (this.queueIndex > 0) prevIdx = this.queueIndex - 1 }
      }
      if (prevIdx !== -1) {
        this.queueIndex = prevIdx;
        this.currentVideo = this.playQueue[this.queueIndex];
        await this._saveQueue(); this._loadAndPlay()
      }
    },

    _handleAutoStop(reason) { 
      this.isPlaying = false; if (this.audioElement) this.audioElement.pause(); 
      this.showToast(reason, "info"); this.lengthControl.current = 0; 
    },

    _loadAndPlay(resumeTime = null) {
      if (!this.currentVideo || !this.audioElement) return
      const settingsStore = useSettingsStore()
      const isOnline = this.currentVideo.download_status !== 'completed'
      
      let targetSrc = this.currentVideo.is_local 
        ? `${API_BASE}/play/stream/${this.currentVideo.bvid}`
        : (isOnline 
            ? `${API_BASE}/play/stream/${this.currentVideo.bvid}?quality=${settingsStore.settings.streamQuality}`
            : `${API_BASE.replace('/api', '')}/downloads/${this.currentVideo.bvid}.mp4`)

      const targetVolume = this.volume
      this.audioElement.volume = settingsStore.settings.enableVolumeFade ? 0 : targetVolume
      this.isBuffering = true

      const onLoaded = () => {
        const startTrim = this.currentVideo.trim_start || 0
        const initialSeek = (resumeTime !== null && resumeTime > 0) ? resumeTime : startTrim
        if (initialSeek > 0) this.audioElement.currentTime = initialSeek
        
        this.audioElement.play().then(() => {
          this.isPlaying = true
          this.updateMediaSession()
          if (settingsStore.settings.enableVolumeFade) {
            let currentV = 0; const step = targetVolume / 20
            const fadeInterval = setInterval(() => {
              currentV += step
              if (currentV >= targetVolume) { this.audioElement.volume = targetVolume; clearInterval(fadeInterval) }
              else this.audioElement.volume = currentV
            }, 25)
          } else this.audioElement.volume = targetVolume
        }).catch(e => { console.error("Playback failed:", e); this.isPlaying = false; this.isBuffering = false })
      }

      this.audioElement.removeEventListener('loadedmetadata', this._lastOnLoaded || (() => {}))
      this._lastOnLoaded = onLoaded
      this.audioElement.addEventListener('loadedmetadata', onLoaded, { once: true })

      this.audioElement.src = ''
      this.audioElement.load()
      this.audioElement.src = targetSrc
      this.audioElement.load()
    },

    _switchStreamingQuality() {
      const settingsStore = useSettingsStore()
      if (!this.audioElement || !this.currentVideo) return
      const currentTime = this.audioElement.currentTime; const wasPlaying = !this.audioElement.paused
      this.audioElement.src = `${API_BASE}/play/stream/${this.currentVideo.bvid}?quality=${settingsStore.settings.streamQuality}`
      const onLoaded = () => { this.audioElement.currentTime = currentTime; if (wasPlaying) this.audioElement.play(); this.audioElement.removeEventListener('loadedmetadata', onLoaded) }
      this.audioElement.addEventListener('loadedmetadata', onLoaded)
    },

    updateMediaSession() {
      if ('mediaSession' in navigator && this.currentVideo) {
        navigator.mediaSession.metadata = new MediaMetadata({ title: this.currentVideo.title, artist: this.currentVideo.owner, artwork: [{ src: this.formatImg(this.currentVideo.pic) }] })
        navigator.mediaSession.setActionHandler('nexttrack', () => this.next()); navigator.mediaSession.setActionHandler('previoustrack', () => this.prev())
        navigator.mediaSession.setActionHandler('play', () => { this.audioElement.play(); this.isPlaying = true }); navigator.mediaSession.setActionHandler('pause', () => { this.audioElement.pause(); this.isPlaying = false })
      }
    },

    updateProgress() {
      if (!this.audioElement) return
      this.currentTime = this.audioElement.currentTime
      this.duration = this.audioElement.duration || 0
      if (this.audioElement.buffered.length > 0) this.buffered = this.audioElement.buffered.end(this.audioElement.buffered.length - 1)
      
      if (this.currentVideo && this.currentVideo.trim_end && this.currentVideo.trim_end > 0) {
        const isNearEnd = this.currentTime >= this.currentVideo.trim_end && this.currentTime < (this.currentVideo.trim_end + 3.0)
        const isNotSeeking = (Date.now() - (this._lastSeekTime || 0)) > 2000
        if (isNearEnd && isNotSeeking) { this.next(); return }
      }

      if (this.lengthControl.enabled && this.lengthControl.type === 'time' && this.isPlaying && this.lengthControl.target > 0) {
        if (!this._lastTime) this._lastTime = Date.now()
        const now = Date.now(); const deltaMin = (now - this._lastTime) / 1000 / 60
        this.lengthControl.current += deltaMin; this._lastTime = now
        if (this.lengthControl.current >= this.lengthControl.target) this._handleAutoStop("已达到预设播放时长")
      } else this._lastTime = null
    },

    seek(time) {
      if (!this.audioElement) return
      this.audioElement.currentTime = time; this.currentTime = time
      this._lastSeekTime = Date.now()
    },

    setVolume(val, showTrigger = false) {
      const newVol = Math.max(0, Math.min(1, val))
      this.volume = newVol
      localStorage.setItem('player_volume', newVol.toString())
      if (this.audioElement) {
        this.audioElement.volume = newVol
        // 如果音量为0，确保静音状态同步
        this.audioElement.muted = (newVol === 0)
      }
      if (showTrigger) {
        this.volumeShowTrigger++
      }
    },
    setPlayMode(mode) { this.playMode = mode; localStorage.setItem('player_mode', mode) },
    updateScoreBatch(delta) {
      if (!this.currentVideo || this.userReacted) return;
      const newScore = Math.max(1, Math.min(10, (this.currentVideo.score || 5.0) + delta));
      this.updateVideoScore(this.currentVideo.bvid, newScore);
      this.userReacted = true;
      this.showToast(`评分已更新: ${newScore.toFixed(1)}`, "success")
    },
    async executeShutdown() {
      try {
        await axios.post(`${API_BASE}/system/shutdown`)
      } catch (e) {
        this.showToast("系统关机指令发送失败", "error")
      }
    },
    toggleUi() { this.isUiCollapsed = !this.isUiCollapsed }
  }
})
