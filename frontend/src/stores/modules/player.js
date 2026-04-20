import { defineStore } from 'pinia'
import { debounce } from 'lodash-es'
import { useSettingsStore } from './settings'
import { useThemeStore } from './theme'
import { db } from '../../utils/db'
import { WeightedPlayEngine } from '../../utils/weightedPlayEngine'
import authApi from '../../api/auth'
import biliApi from '../../api/bili'
import localApi from '../../api/local'
import systemApi from '../../api/system'
import statsApi from '../../api/stats'

const isDev = window.location.port === '5173' || window.location.port === '3000'
const isElectron = window.location.protocol === 'file:'
const API_BASE = import.meta.env.VITE_API_URL || (isDev || isElectron ? 'http://127.0.0.1:12280/api' : `${window.location.origin}/api`)

export const usePlayerStore = defineStore('player', {
  state: () => ({
    user: JSON.parse(localStorage.getItem('cache_user_info') || 'null'),
    biliFolders: JSON.parse(localStorage.getItem('cache_bili_folders') || '[]'),
    folderCache: {}, // Moved to IndexedDB
    folderPagination: {}, // Moved to IndexedDB
    localVideos: [],
    localCollections: [],
    currentVideo: JSON.parse(localStorage.getItem('cache_current_video') || 'null'),
    playQueue: [], // Moved to IndexedDB
    _queueBvidsCache: new Set(), // [性能优化] O(1) 去重缓存
    _weightEngine: new WeightedPlayEngine(), // [性能优化] O(log N) 权重播放引擎
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
    recentPlayHistory: [], // 最近播放的视频索引，用于权重播放去重
    playHistory: [], // 播放历史记录，用于"上一首"功能
    playHistoryIndex: -1, // 当前在播放历史中的位置
    lengthControl: JSON.parse(localStorage.getItem('player_length_control') || JSON.stringify({
      enabled: false,
      type: 'count',
      target: 0,
      current: 0
    })),
    autoShutdown: localStorage.getItem('player_auto_shutdown') === 'true',
    userReacted: false,
    _lastTime: null,
    _lastSeekTime: 0,
    _playStartTime: null,
    _appStartTime: Date.now(),
    _lastAppUsageReport: Date.now()
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
        // [性能优化] 初始化 bvid 缓存集合
        this._queueBvidsCache = new Set(this.playQueue.map(v => v.bvid).filter(Boolean))
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
      this.startAppUsageTracking()
    },

    startAppUsageTracking() {
      // 每5分钟上报一次软件使用时长
      setInterval(() => {
        this._reportAppUsage()
      }, 5 * 60 * 1000)
      
      // 页面关闭时上报最后一次
      window.addEventListener('beforeunload', () => {
        this._reportAppUsage()
      })
    },

    formatImg(url, size = null) {
      if (!url) return ''
      if (url.startsWith('/local_covers/') || url.startsWith('/local_stickers/')) {
        return `${API_BASE.replace('/api', '')}${url}`
      }
      
      // [修复锯齿] 强制替换图片大小后缀。本地数据库可能缓存了原始高分辨率URL或者不合适的尺寸
      let cleanUrl = url.replace(/^https?:/, '').replace(/^http:/, '')
      let result = cleanUrl.startsWith('//') ? `https:${cleanUrl}` : `https://${cleanUrl}`
      
      // 检查是否为代理URL，提取真实目标
      if (result.includes('/proxy/image?url=')) {
        try {
          const urlParams = new URL(url).searchParams
          result = decodeURIComponent(urlParams.get('url') || result)
        } catch (e) {}
      }

      // 处理 B 站相关的图片源，即使它在 archive.biliimg.com 等其它域下
      if (result.includes('hdslb.com') || result.includes('biliimg.com')) {
        // 剥离所有的尺寸后缀，如 @xxx.webp
        const baseUrl = result.split('@')[0]
        
        // 重新应用目标尺寸，如果没有传递 size 则默认使用中等压缩，防止过度加载高分辨率图片
        // 极重要的修改：对于从 SQLite 取出的纯原始 URL（如高清无后缀图），必须在此强制进行 down-scaling
        const targetSize = size || '640w_360h_1c_1s.webp'
        const processedUrl = `${baseUrl}@${targetSize}`
        
        return `${API_BASE}/proxy/image?url=${encodeURIComponent(processedUrl)}`
      }
      
      return result
    },

    async checkLogin() {
      try {
        const data = await authApi.getStatus()
        const wasLoggedIn = !!this.user
        const isNowLoggedIn = data.is_logged_in
        
        this.user = isNowLoggedIn ? data : null
        
        // 登录状态变化时清除缓存
        if (!wasLoggedIn && isNowLoggedIn) {
          console.log('[checkLogin] 检测到新登录，清除收藏夹缓存')
          localStorage.removeItem('cache_bili_folders')
          this.biliFolders = []
        }
        // 缓存用户信息到 localStorage，下次启动时立即显示
        if (this.user) {
          localStorage.setItem('cache_user_info', JSON.stringify(this.user))
        } else {
          localStorage.removeItem('cache_user_info')
        }
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
        localStorage.removeItem('cache_user_info')
        this.showToast("账号已退出", "success")
      } catch (e) {
        console.error("Logout failed", e)
      }
    },

    async fetchBiliFolders(retryCount = 0) {
      const MAX_RETRIES = 3
      try {
        const data = await biliApi.getFolders()
        console.log('[fetchBiliFolders] API 响应:', data)
        if (data.code === 0) {
          if (data.data && data.data.length === 0 && retryCount < MAX_RETRIES) {
            // 返回空数组，可能是缓存问题，重试
            console.warn(`[fetchBiliFolders] 收藏夹为空，重试 ${retryCount + 1}/${MAX_RETRIES}`)
            await new Promise(r => setTimeout(r, 1000)) // 等待 1 秒
            return this.fetchBiliFolders(retryCount + 1)
          }
          this.biliFolders = data.data.map(f => ({ ...f, cover: this.formatImg(f.cover || f.pic) }))
          localStorage.setItem('cache_bili_folders', JSON.stringify(this.biliFolders))
          console.log('[fetchBiliFolders] 成功获取收藏夹:', this.biliFolders.length, '个')
          if (this.biliFolders.length === 0) {
            this.showToast('收藏夹列表为空，请确认是否有收藏内容', 'info')
          }
        } else {
          console.warn('[fetchBiliFolders] API 返回非 0 code:', data)
          this.showToast(`获取收藏夹失败: ${data.message || '未知错误'}`, 'error')
        }
      } catch (e) {
        console.error('[fetchBiliFolders] 请求失败:', e)
        if (retryCount < MAX_RETRIES) {
          console.warn(`[fetchBiliFolders] 请求失败，重试 ${retryCount + 1}/${MAX_RETRIES}`)
          await new Promise(r => setTimeout(r, 1000))
          return this.fetchBiliFolders(retryCount + 1)
        }
        this.showToast('获取收藏夹失败，请检查网络或登录状态', 'error')
      }
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

    async cancelDownload(bvid) {
      try {
        await systemApi.cancelDownload(bvid)
        const v = this.localVideos.find(i => i.bvid === bvid)
        if (v) v.download_status = 'not_downloaded'
        this.downloadSession.delete(bvid)
        this.showToast('已取消下载', 'success')
      } catch (e) {
        console.error('取消下载失败:', e)
        this.showToast('取消下载失败', 'error')
      }
    },

    async cancelAllDownloads() {
      try {
        const result = await systemApi.cancelAllDownloads()
        // 更新所有正在下载的视频状态
        this.localVideos.forEach(v => {
          if (v.download_status === 'pending' || v.download_status === 'downloading') {
            v.download_status = 'not_downloaded'
            this.downloadSession.delete(v.bvid)
          }
        })
        this.showToast(`已取消 ${result.count} 个下载任务`, 'success')
      } catch (e) {
        console.error('批量取消下载失败:', e)
        this.showToast('批量取消下载失败', 'error')
      }
    },

    startStatusPolling() {
      // 废弃之前的轮询方法，改由 App.vue 统一通过 SSE 处理
      // 此处仅做空函数保留或可将部分状态计算逻辑移到专门的 update 方法
    },
    
    updateDownloadStateFromSSE(data) {
      const tasks = data.tasks || []
      
      // 记录这次 SSE 中活跃的任务 bvid
      const activeBvids = new Set(tasks.map(t => t.bvid))
      let needRefresh = false
      
      // [修复] 乐观更新所有可能包含下载状态的集合（本地库、B站收藏夹缓存、播放队列），消除卡片卡在下载中的Bug
      const updateList = (list) => {
        if (!list) return
        list.forEach(v => {
          const task = tasks.find(t => t.bvid === v.bvid)
          if (task) {
            v.download_status = task.status
            v.progress = task.progress
          } else if (v.download_status === 'pending' || v.download_status === 'downloading') {
            v.download_status = 'completed'
            v.progress = 100
            needRefresh = true
          }
        })
      }

      updateList(this.localVideos)
      updateList(this.playQueue)
      Object.values(this.folderCache).forEach(folder => updateList(folder))
      if (this.currentVideo) updateList([this.currentVideo])
      
      if (needRefresh) {
        this.fetchLocalVideos()
      }
      
      // [修复] 活跃下载数应为所有未完成任务的总和（含等待中），而不是仅显示正在 downloading 的 3 个
      this.activeDownloadCount = tasks.length
      
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
    },

    // [性能优化] 防抖版本的持久化方法
    _saveQueue() {
      this._debouncedSaveQueue()
    },

    // [性能优化] 实际的持久化逻辑（防抖 2 秒，最大等待 5 秒）
    _debouncedSaveQueue: debounce(async function() {
      const seen = new Set()
      this.playQueue = this.playQueue.map(v => this._normalizeVideo(v)).filter(v => {
        if (!v.bvid || seen.has(v.bvid)) return false
        seen.add(v.bvid); return true
      })
      
      // [性能优化] 同步更新 bvid 缓存集合
      this._queueBvidsCache = new Set(this.playQueue.map(v => v.bvid).filter(Boolean))
      
      // [性能优化] 轻量化序列化：仅保存核心字段，避免深拷贝整个响应式对象
      const serializedQueue = this.playQueue.map(v => ({
        bvid: v.bvid,
        title: v.title,
        owner: typeof v.owner === 'object' ? v.owner?.name : v.owner,
        duration: v.duration,
        pic: v.pic,
        score: v.score,
        download_status: v.download_status,
        trim_start: v.trim_start,
        trim_end: v.trim_end
      }))

      // 写入 IndexedDB
      try {
        await db.playQueue.clear()
        await db.playQueue.bulkAdd(serializedQueue)
      } catch (e) {
        console.warn("[Performance] IndexedDB save queue failed", e)
      }

      // [性能优化] LocalStorage 仅存储极轻量的索引信息，不再备份完整队列
      localStorage.setItem('cache_queue_index', this.queueIndex.toString())
      if (this.currentVideo) {
        localStorage.setItem('cache_current_video_bvid', this.currentVideo.bvid)
      }
    }, 2000, { maxWait: 5000 }),

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
      
      // [性能优化] 使用 O(1) 缓存集合检查是否存在
      if (this._queueBvidsCache.has(targetId)) {
        const idx = this.playQueue.findIndex(v => (v.bvid || v.bv_id) === targetId)
        if (idx !== -1) {
          this.playQueue[idx] = { ...this.playQueue[idx], ...normalized }
        }
        this.showToast("该视频已在队列中", "info")
        return
      }
      
      if (autoDownload && normalized.download_status !== 'completed' && normalized.download_status !== 'pending' && normalized.download_status !== 'downloading') {
        this.addToDownload(normalized.bvid)
      }
      this.playQueue.push(normalized)
      this._queueBvidsCache.add(targetId) // [性能优化] 同步更新缓存
      this._resetPlayState() // 队列变化，重置播放状态
      this.showToast(`已加入队列`, "success")
      await this._saveQueue()
    },

    async addToQueueList(list, autoDownload = false) {
      // [性能优化] 直接使用缓存集合，避免每次都遍历队列创建 Set
      const newOnes = []
      list.forEach(v => {
        const normalized = this._normalizeVideo(v)
        const id = normalized.bvid
        if (id && !this._queueBvidsCache.has(id)) {
          newOnes.push(normalized)
          this._queueBvidsCache.add(id) // [性能优化] 同步更新缓存
          if (autoDownload && normalized.download_status !== 'completed') this.addToDownload(id)
        }
      })
      if (newOnes.length === 0) { this.showToast("选中的视频均已在队列中", "info") ; return }
      this.playQueue.push(...newOnes)
      this._resetPlayState() // 队列变化，重置播放状态
      this.showToast(`已添加 ${newOnes.length} 个视频`, "success")
      await this._saveQueue()
    },

    async removeFromQueue(index) {
      const isCurrent = index === this.queueIndex
      const removedBvid = this.playQueue[index]?.bvid
      this.playQueue.splice(index, 1)
      if (removedBvid) this._queueBvidsCache.delete(removedBvid) // [性能优化] 同步更新缓存
      this._resetPlayState() // 队列变化，重置播放状态
      if (index < this.queueIndex) this.queueIndex--
      else if (isCurrent) this._stopAndReset()
      await this._saveQueue()
    },

    async removeFromQueueBatch(bvids) {
      const curBvid = this.currentVideo?.bvid
      const isDeletingCurrent = bvids.includes(curBvid)
      this.playQueue = this.playQueue.filter(v => !bvids.includes(v.bvid))
      // [性能优化] 批量删除缓存
      bvids.forEach(bvid => this._queueBvidsCache.delete(bvid))
      this._resetPlayState() // 队列变化，重置播放状态
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

    _resetPlayState() {
      // 队列变化时，清空洗牌序列和播放历史
      this.shuffleSnapshot = []
      this.recentPlayHistory = []
      this.playHistory = []
      this.playHistoryIndex = -1
      // [性能优化] 重置权重引擎，下次使用时重新构建
      this._weightEngine.reset()
    },

    _addToPlayHistory(index) {
      // 如果当前不在历史末尾，清除后面的历史
      if (this.playHistoryIndex < this.playHistory.length - 1) {
        this.playHistory = this.playHistory.slice(0, this.playHistoryIndex + 1)
      }
      
      // 添加新的播放记录
      this.playHistory.push(index)
      this.playHistoryIndex = this.playHistory.length - 1
      
      // 限制历史长度（最多 100 首）
      if (this.playHistory.length > 100) {
        this.playHistory.shift()
        this.playHistoryIndex--
      }
    },

    async playFromQueue(index) {
      if (index >= 0 && index < this.playQueue.length) {
        this._addToPlayHistory(index) // 添加到播放历史
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
      this.userReacted = false // 重置当前播放歌曲的点赞/点踩状态
      if (this.playQueue.length === 0) return
      const hasFilter = this.filteredQueueIndices.length > 0 && this.filteredQueueIndices.length < this.playQueue.length
      if (this.lengthControl.enabled && this.lengthControl.type === 'count' && this.lengthControl.target > 0) {
        this.lengthControl.current++; if (this.lengthControl.current >= this.lengthControl.target) { this._advanceIndexOnly(); this._handleAutoStop("已达到预设数量"); return }
      }
      if (this.playMode === 'single_loop') { this._loadAndPlay(); return }
      let nextIdx = -1; const pool = hasFilter ? this.filteredQueueIndices : this.playQueue.map((_, i) => i)
      if (this.playMode.startsWith('shuffle')) {
        nextIdx = this._getShuffleNextIndex(pool)
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
        this._addToPlayHistory(nextIdx) // 添加到播放历史
        this.queueIndex = nextIdx; this.currentVideo = this.playQueue[this.queueIndex];
        await this._saveQueue(); this._loadAndPlay()
      }
    },

    _advanceIndexOnly() {
      this.userReacted = false // 重置当前播放歌曲的点赞/点踩状态
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

    _getShuffleNextIndex(pool) {
      // 如果洗牌序列为空或已播完，重新生成
      if (this.shuffleSnapshot.length === 0) {
        // Fisher-Yates 洗牌算法
        const snapshot = [...pool]
        for (let i = snapshot.length - 1; i > 0; i--) {
          const j = Math.floor(Math.random() * (i + 1))
          ;[snapshot[i], snapshot[j]] = [snapshot[j], snapshot[i]]
        }
        this.shuffleSnapshot = snapshot
      }
      
      // 从洗牌序列中取出下一个
      return this.shuffleSnapshot.shift()
    },

    _getWeightedNextIndex(limitIndices = null) {
      /**
       * [性能优化] 使用 O(log N) 权重引擎代替 O(N) 遍历计算
       */
      const settingsStore = useSettingsStore()
      
      // 确定有效的播放池
      let effectiveQueue = this.playQueue
      let effectiveIndices = this.playQueue.map((_, i) => i)
      
      if (limitIndices && limitIndices.length > 0) {
        effectiveQueue = limitIndices.map(i => this.playQueue[i])
        effectiveIndices = limitIndices
      }
      
      // 边界情况：队列为空
      if (effectiveQueue.length === 0) return 0
      
      // 历史大小：最少 2 首，最多 5 首
      const historySize = Math.max(2, Math.min(5, Math.floor(effectiveQueue.length * 0.1)))
      const sensitivity = settingsStore.settings.weightSensitivity || 2.0
      
      // [性能优化] 检查引擎是否需要重建
      if (!this._weightEngine.isReady()) {
        this._weightEngine.build(
          effectiveQueue,
          this.recentPlayHistory,
          this.weightedMode,
          sensitivity
        )
        
        // 开发模式下输出权重分布
        if (import.meta.env.DEV) {
          const distribution = this._weightEngine.getWeightDistribution(effectiveQueue)
          console.log('[权重播放] 权重分布:', distribution.slice(0, 10)) // 仅显示前 10 个
        }
      }
      
      // [性能优化] O(log N) 查询下一首
      const selectedLocalIdx = this._weightEngine.next()
      
      if (selectedLocalIdx === -1) {
        // 引擎失败，回退到随机选择
        console.warn('[权重播放] 引擎失败，回退到随机选择')
        const randomIdx = effectiveIndices[Math.floor(Math.random() * effectiveIndices.length)]
        this._updatePlayHistory(randomIdx, historySize)
        return randomIdx
      }
      
      // 将局部索引映射回全局索引
      const selectedIdx = effectiveIndices[selectedLocalIdx]
      this._updatePlayHistory(selectedIdx, historySize)
      
      // 更新历史后，标记引擎需要重建（因为历史变化会影响权重）
      this._weightEngine.reset()
      
      return selectedIdx
    },

    _updatePlayHistory(index, historySize) {
      // 更新播放历史
      this.recentPlayHistory.push(index)
      if (this.recentPlayHistory.length > historySize) {
        this.recentPlayHistory.shift()
      }
    },

    async prev() {
      this.userReacted = false // 重置当前播放歌曲的点赞/点踩状态
      // 在随机/权重模式下，从播放历史中获取上一首
      if (this.playMode.startsWith('shuffle') || this.playMode === 'weighted') {
        if (this.playHistoryIndex > 0) {
          this.playHistoryIndex--
          const prevIdx = this.playHistory[this.playHistoryIndex]
          this.queueIndex = prevIdx
          this.currentVideo = this.playQueue[this.queueIndex]
          await this._saveQueue()
          this._loadAndPlay()
          return
        } else {
          this.showToast("已经是第一首了", "info")
          return
        }
      }
      
      // 其他模式：顺序播放
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
      this.userReacted = false // 重置当前播放歌曲的点赞/点踩状态
      
      // 记录上一首歌的播放时长
      if (this._playStartTime && this.currentVideo) {
        const playDuration = Math.floor((Date.now() - this._playStartTime) / 1000)
        if (playDuration > 5) { // 只记录播放超过5秒的
          this._reportPlayRecord(this.currentVideo.bvid, playDuration)
        }
      }
      
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
          this._playStartTime = Date.now() // 记录播放开始时间
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

    async _reportPlayRecord(bvid, duration) {
      try {
        await statsApi.recordPlay(bvid, duration)
      } catch (e) {
        console.error('上报播放记录失败:', e)
      }
    },

    async _reportAppUsage() {
      const now = Date.now()
      const duration = Math.floor((now - this._lastAppUsageReport) / 1000)
      if (duration > 0) {
        try {
          await statsApi.recordAppUsage(duration)
          this._lastAppUsageReport = now
        } catch (e) {
          console.error('上报使用时长失败:', e)
        }
      }
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
    async updateScoreBatch(delta) {
      if (!this.currentVideo || this.userReacted) return;
      
      const bvid = this.currentVideo.bvid;
      const isLocal = this.localVideos.some(v => v.bvid === bvid);
      
      if (!isLocal) {
        // 如果不在本地库，则先导入
        try {
          // 这里的 collection_id 'unclassified' 或者其他的合适的值，取决于后端的逻辑
          // 需要调用 importBiliVideos
          await localApi.importBiliVideos('unclassified', [{
            bvid: this.currentVideo.bvid,
            title: this.currentVideo.title,
            owner: this.currentVideo.owner,
            pic: this.formatImg(this.currentVideo.pic),
            duration: this.currentVideo.duration
          }]);
          // 同步获取本地视频列表
          await this.fetchLocalVideos();
        } catch (e) {
          console.error("Failed to import video before scoring:", e);
          this.showToast("同步视频失败，无法评分", "error");
          return;
        }
      }
      
      const newScore = Math.max(1, Math.min(10, (this.currentVideo.score || 5.0) + delta));
      try {
        await this.updateVideoScore(this.currentVideo.bvid, newScore);
        this.userReacted = true;
        this.showToast(`评分已更新: ${newScore.toFixed(1)}`, "success")
      } catch (e) {
        this.showToast(`评分更新失败`, "error")
      }
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
