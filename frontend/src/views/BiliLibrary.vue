# -*- coding: utf-8 -*-
# Path: frontend/src/views/BiliLibrary.vue

<script setup>
import { ref, onMounted, onUnmounted, computed, reactive, watch, nextTick } from 'vue'
import { usePlayerStore } from '../stores/modules/player'
import UniversalModal from '../components/UniversalModal.vue'
import localApi from '../api/local'
import {
  PlayIcon,
  CheckCircleIcon,
  ArrowPathIcon,
  MagnifyingGlassIcon,
  ChevronLeftIcon,
  FolderIcon,
  SquaresPlusIcon,
  SparklesIcon,
  PlusIcon
} from '@heroicons/vue/24/solid'

const store = usePlayerStore()
const windowWidth = ref(window.innerWidth)
const onResize = () => { windowWidth.value = window.innerWidth }

const currentFolderId = ref(null)
const isLoading = ref(false)
const isSelectAllLoading = ref(false)
const searchQuery = ref('')
const searchMode = ref('fuzzy')
const loadTrigger = ref(null)
const scrollContainer = ref(null)
const lastSelectedIndex = ref(-1)
const isSearchMenuOpen = ref(false)

const searchOptions = [
  { val: 'fuzzy', label: '模糊' },
  { val: 'title', label: '标题' },
  { val: 'upper', label: 'UP主' },
  { val: 'bvid',  label: 'BV号' },
  { val: 'regex', label: '正则' }
]

const modalState = reactive({
  show: false,
  type: 'checklist',
  title: '',
  initialValue: [],
  extraData: {},
  callback: null
})

// 计算属性映射
const currentVideos = computed(() => store.folderCache[String(currentFolderId.value)] || [])
const pageInfo = computed(() => store.folderPagination[String(currentFolderId.value)])

const filteredVideos = computed(() => {
  let list = currentVideos.value
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return list
  try {
    if (searchMode.value === 'regex') {
      const regex = new RegExp(q, 'i')
      return list.filter(v => regex.test(v.title) || regex.test(v.upper?.name || v.owner || ''))
    }
    return list.filter(v => {
      const tM = v.title.toLowerCase().includes(q)
      const oM = (v.upper?.name || v.owner || '').toLowerCase().includes(q)
      const bM = v.bvid.toLowerCase().includes(q)
      if (searchMode.value === 'title') return tM
      if (searchMode.value === 'upper') return oM
      if (searchMode.value === 'bvid') return bM
      return tM || oM || bM
    })
  } catch (e) { return list }
})

const selectionCount = computed(() => store.selectedBiliBvids.length)
const isAllSelected = computed(() => filteredVideos.value.length > 0 && filteredVideos.value.every(v => store.selectedBiliBvids.includes(v.bvid)))

onMounted(() => {
  window.addEventListener('resize', onResize)
  store.fetchBiliFolders()
  store.fetchLocalCollections()
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  if (observer) observer.disconnect()
})

function getFolderCover(folder) {
  if (folder.cover && folder.cover !== '') return store.formatImg(folder.cover)
  const cached = store.folderCache[String(folder.id)]
  if (cached && cached.length > 0) return store.formatImg(cached[0].cover || cached[0].pic)
  return null
}

let observer = null
const setupObserver = () => {
  if (observer) observer.disconnect()
  observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && currentFolderId.value && !isLoading.value) {
      if (pageInfo.value?.hasMore) checkAndLoadMore()
    }
  }, { root: scrollContainer.value, rootMargin: '400px' })
  if (loadTrigger.value) observer.observe(loadTrigger.value)
}

async function checkAndLoadMore() {
  if (isLoading.value || !pageInfo.value?.hasMore) return
  isLoading.value = true
  await store.fetchFolderVideos(currentFolderId.value, true)
  isLoading.value = false
  
  await nextTick()
  // 如果内容仍未填满屏幕，递归拉取
  const rect = loadTrigger.value?.getBoundingClientRect()
  if (rect && rect.top < window.innerHeight) {
    checkAndLoadMore()
  }
}

async function openFolder(mediaId) {
  const idStr = String(mediaId)
  currentFolderId.value = idStr
  store.selectedBiliBvids = []
  searchQuery.value = ''
  lastSelectedIndex.value = -1
  
  // 核心逻辑：不论是否有缓存，打开时强制执行首页刷新校验
  isLoading.value = true
  await store.fetchFolderVideos(idStr, false)
  isLoading.value = false
  
  await nextTick()
  setupObserver()
}

async function toggleSelectAll() {
  if (isAllSelected.value) { store.selectedBiliBvids = []; return }
  if (pageInfo.value?.hasMore) {
    modalState.type = 'confirm'; 
    modalState.title = '获取完整列表'
    modalState.extraData = { 
      message: '当前收藏夹还有部分视频未显示，是否加载完整列表并全选？',
      confirmText: '加载全部',
      cancelText: '取消'
    }
    modalState.callback = async (confirmed) => {
      if (!confirmed) { modalState.show = false; return }
      isSelectAllLoading.value = true
      try { await store.fetchAllFolderVideos(currentFolderId.value); store.selectedBiliBvids = filteredVideos.value.map(v => v.bvid) } 
      finally { isSelectAllLoading.value = false; modalState.show = false }
    }
    modalState.show = true
    return
  }
  store.selectedBiliBvids = filteredVideos.value.map(v => v.bvid)
}

function handleCardClick(event, bvid, index) {
  if (event.shiftKey && lastSelectedIndex.value !== -1) {
    const start = Math.min(lastSelectedIndex.value, index); const end = Math.max(lastSelectedIndex.value, index)
    const rangeBvids = filteredVideos.value.slice(start, end + 1).map(v => v.bvid)
    if (store.selectedBiliBvids.includes(filteredVideos.value[lastSelectedIndex.value].bvid)) {
      store.selectedBiliBvids = store.selectedBiliBvids.filter(id => !rangeBvids.includes(id))
    } else { store.selectedBiliBvids = Array.from(new Set([...store.selectedBiliBvids, ...rangeBvids])) }
  } else {
    const idx = store.selectedBiliBvids.indexOf(bvid)
    if (idx > -1) store.selectedBiliBvids.splice(idx, 1); else store.selectedBiliBvids.push(bvid)
    lastSelectedIndex.value = index
  }
}

function handlePlay(video) {
  const pObj = { ...video, download_status: 'not_downloaded' }
  const localV = store.localVideos.find(v => v.bvid === video.bvid)
  if (localV && localV.download_status === 'completed') {
    store.playVideo({ ...pObj, ...localV, download_status: 'completed' })
  } else {
    modalState.type = 'confirm'; modalState.title = '正在播放网络流'
    modalState.extraData = { message: '视频未缓存，是否同步加入下载队列？', confirmText: '缓存并播放', cancelText: '仅播放' }
    modalState.callback = (conf) => { store.playVideo(pObj, conf); modalState.show = false }
    modalState.show = true
  }
}

function handleAddToQueue(video) {
  const pObj = { ...video, download_status: 'not_downloaded' }
  const localV = store.localVideos.find(v => v.bvid === video.bvid)
  if (localV && localV.download_status === 'completed') {
    store.addToQueue({ ...pObj, ...localV, download_status: 'completed' })
  } else {
    modalState.type = 'confirm'; modalState.title = '加入播放队列'
    modalState.extraData = { message: '视频未缓存，是否同步加入下载队列？', confirmText: '缓存并加入', cancelText: '仅加入' }
    modalState.callback = (conf) => { store.addToQueue(pObj, conf); modalState.show = false }
    modalState.show = true
  }
}

function handleBatchPlay() {
  const sel = currentVideos.value.filter(v => store.selectedBiliBvids.includes(v.bvid))
  if (sel.length === 0) return
  const hasUn = sel.some(v => !store.localVideos.find(lv => lv.bvid === v.bvid)?.download_status === 'completed')
  if (hasUn) {
    modalState.type = 'confirm'; modalState.title = '正在播放网络流'
    modalState.extraData = { message: '部分视频未缓存，是否同步执行缓存？', confirmText: '缓存并播放', cancelText: '仅播放' }
    modalState.callback = (conf) => { store.playList(sel, 0, conf); store.selectedBiliBvids = []; modalState.show = false }
    modalState.show = true
  } else { store.playList(sel); store.selectedBiliBvids = [] }
}

function handleBatchQueue() {
  const sel = currentVideos.value.filter(v => store.selectedBiliBvids.includes(v.bvid))
  if (sel.length === 0) return
  const hasUn = sel.some(v => !store.localVideos.find(lv => lv.bvid === v.bvid)?.download_status === 'completed')
  if (hasUn) {
    modalState.type = 'confirm'; modalState.title = '加入播放队列'
    modalState.extraData = { message: '部分视频未缓存，是否同步执行缓存？', confirmText: '缓存并加入', cancelText: '仅加入' }
    modalState.callback = (conf) => { store.addToQueueList(sel, conf); store.selectedBiliBvids = []; modalState.show = false }
    modalState.show = true
  } else { store.addToQueueList(sel); store.selectedBiliBvids = [] }
}

async function handleExpand(video) { isExpanding.value = video.bvid; await store.expandVideoParts(currentFolderId.value, video); isExpanding.value = null }
function openSyncModal(vOrL) {
  const vList = Array.isArray(vOrL) ? vOrL : [vOrL]; const opts = store.localCollections.map(c => ({ id: c.id, label: c.title }))
  modalState.type = 'checklist'; modalState.title = '同步到本地媒体夹'; modalState.extraData = { options: opts }
  modalState.callback = async (cIds) => {
    if (!cIds) return
    isLoading.value = true; try { for (const v of vList) await store.updateVideoCollections(v, cIds); store.selectedBiliBvids = []; store.showToast("同步完成", "success") } 
    finally { isLoading.value = false; modalState.show = false }
  }
  modalState.show = true
}
async function removeSync(bvid, colId) {
  modalState.type = 'confirm'; modalState.title = '取消关联'
  modalState.callback = async (conf) => { if (conf) { await store.unsyncVideo(colId, bvid); store.showToast("已取消同步关联", "info") }; modalState.show = false }
  modalState.show = true
}

function openBiliVideo(bvid) {
  let url = 'https://www.bilibili.com/video/'
  if (bvid.includes('_p')) {
    const [id, p] = bvid.split('_p')
    url += id + '/?p=' + p
  } else {
    url += bvid
  }
  window.open(url, '_blank')
}

const isExpanding = ref(null)
</script>

<template>
  <div class="h-full flex flex-col animate-fade-in relative">
    <UniversalModal :show="modalState.show" :type="modalState.type" :title="modalState.title" :initial-value="modalState.initialValue" :extra-data="modalState.extraData" @close="modalState.show = false" @confirm="(val) => modalState.callback && modalState.callback(val)" />

    <div v-if="!currentFolderId" class="flex-1 overflow-y-auto pr-2 scrollbar-thin">
       <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 2xl:grid-cols-6 gap-6">
          <div v-for="folder in store.biliFolders" :key="folder.id" @click="openFolder(folder.id)"
               class="relative aspect-square rounded-[2.5rem] cursor-pointer overflow-hidden group bg-gray-100 dark:bg-gray-800 transition-all duration-200 border border-transparent hover:border-primary-500 shadow-sm hover:shadow-2xl hover:-translate-y-1">
             <img v-if="getFolderCover(folder)" :src="getFolderCover(folder)" class="absolute inset-0 w-full h-full object-cover transition-transform duration-1000 group-hover:scale-110" />
             <div class="absolute inset-0 bg-gradient-to-t from-black/90 via-black/20 to-transparent"></div>
             <div class="absolute bottom-6 left-6 right-6 text-white"><h3 class="font-bold truncate text-lg drop-shadow-xl">{{ folder.title }}</h3><p class="text-[10px] font-black opacity-60 uppercase tracking-[0.2em] mt-1">{{ folder.media_count }} 视频</p></div>
             <div class="absolute inset-0 flex items-center justify-center bg-primary-500/10 opacity-0 group-hover:opacity-100 transition-opacity"><FolderIcon class="w-12 h-12 text-white/20" /></div>
          </div>
       </div>
    </div>

    <div v-else class="flex flex-col h-full overflow-hidden">
      <div class="flex flex-col xl:flex-row xl:items-center justify-between mb-6 bg-white/50 dark:bg-gray-800/40 backdrop-blur-md p-3 rounded-3xl border border-gray-200 dark:border-white/5 shadow-sm min-h-[4.5rem] gap-3 relative z-30">
        <div class="flex items-center gap-4 pr-4 xl:border-r border-gray-200 dark:border-white/10 mr-4 shrink-0">
          <button @click="currentFolderId = null" class="p-2 hover:bg-gray-100 dark:hover:bg-white/5 rounded-2xl transition text-gray-500 hover:text-primary-500"><ChevronLeftIcon class="w-6 h-6" /></button>
          <button @click="toggleSelectAll" :disabled="isSelectAllLoading" class="flex items-center gap-2 text-sm font-bold text-gray-600 dark:text-gray-300 hover:text-primary-500 transition disabled:opacity-50">
             <ArrowPathIcon v-if="isSelectAllLoading" class="w-5 h-5 animate-spin text-primary-500" />
             <div v-else class="w-5 h-5 rounded border-2 flex items-center justify-center transition-colors" :class="isAllSelected ? 'bg-primary-500 border-primary-500 shadow-lg shadow-primary-500/30' : 'border-gray-300 dark:border-gray-600'"><CheckCircleIcon v-if="isAllSelected" class="w-4 h-4 text-white" /></div>
             {{ isSelectAllLoading ? '正在加载...' : `全选结果 (${filteredVideos.length})` }}
          </button>
        </div>

        <div v-if="selectionCount === 0" class="flex-1 flex flex-col md:flex-row items-stretch md:items-center gap-3">
           <div class="relative flex-1 min-w-[150px] max-w-full md:max-w-md transition-all duration-300"><MagnifyingGlassIcon class="w-4 h-4 absolute left-3.5 top-3 text-gray-400" /><input v-model="searchQuery" placeholder="搜索此文件夹..." class="w-full bg-gray-100 dark:bg-white/5 border-none rounded-2xl pl-10 pr-4 py-2.5 text-sm focus:ring-2 focus:ring-primary-500 transition-all" /></div>
           <div v-if="windowWidth < 1100" class="relative group z-50">
              <button @click.stop="isSearchMenuOpen = !isSearchMenuOpen" class="flex items-center gap-2 bg-gray-100 dark:bg-white/5 px-4 py-2.5 rounded-2xl text-xs font-bold text-gray-600 dark:text-gray-300 hover:text-primary-500 transition"><span>{{ searchOptions.find(o => o.val === searchMode)?.label }}</span><ChevronLeftIcon class="-rotate-90 w-3 h-3" /></button>
              <div v-if="isSearchMenuOpen" class="absolute top-full right-0 mt-2 w-32 bg-white dark:bg-gray-800 rounded-xl shadow-xl border border-gray-100 dark:border-white/5 z-[100] p-1"><button v-for="opt in searchOptions" :key="opt.val" @click="searchMode = opt.val; isSearchMenuOpen = false" :class="searchMode === opt.val ? 'text-primary-500 bg-primary-50 dark:bg-white/5' : 'text-gray-500 hover:bg-gray-50 dark:hover:bg-white/5'" class="w-full text-left px-4 py-2 rounded-lg text-xs font-bold transition-all">{{ opt.label }}</button></div>
           </div>
           <div v-else class="flex bg-gray-100 dark:bg-white/5 p-1 rounded-xl shrink-0"><button v-for="opt in searchOptions" :key="opt.val" @click="searchMode = opt.val" :class="searchMode === opt.val ? 'bg-white dark:bg-gray-700 text-primary-500 shadow-sm' : 'text-gray-400 hover:text-gray-600'" class="px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase transition-all">{{ opt.label }}</button></div>
        </div>

        <div v-else class="flex-1 flex flex-wrap items-center gap-2 animate-fade-in">
           <span class="px-3 py-1.5 bg-primary-500 text-white rounded-xl text-xs font-black shadow-lg shadow-primary-500/30 whitespace-nowrap">已选 {{ selectionCount }}</span>
           <button @click="handleBatchPlay" class="px-4 py-2 bg-primary-600 text-white rounded-2xl text-xs font-bold hover:bg-primary-700 transition flex items-center gap-2 shadow-lg shadow-primary-500/20"><PlayIcon class="w-4 h-4" /> <span v-if="windowWidth >= 1200">批量播放</span></button>
           <button @click="handleBatchQueue" class="px-4 py-2 bg-purple-600 text-white rounded-2xl text-xs font-bold hover:bg-purple-700 transition flex items-center gap-2 shadow-lg shadow-purple-500/20"><PlusIcon class="w-4 h-4" /> <span v-if="windowWidth >= 1200">批量队列</span></button>
           <button @click="openSyncModal(currentVideos.filter(v => store.selectedBiliBvids.includes(v.bvid)))" class="px-4 py-2 bg-blue-600 text-white rounded-2xl text-xs font-bold hover:bg-blue-700 transition flex items-center gap-2 shadow-lg shadow-blue-500/20"><ArrowPathIcon class="w-4 h-4" /> <span v-if="windowWidth >= 1200">批量同步</span></button>
           <button @click="store.selectedBiliBvids = []" class="ml-auto text-xs text-gray-400 font-bold px-4 hover:text-primary-500">取消</button>
        </div>
      </div>

      <div ref="scrollContainer" class="flex-1 overflow-y-auto pr-2 scrollbar-thin">
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-4 lg:gap-6 pb-20">
          <div v-for="(v, index) in filteredVideos" :key="v.bvid" @click="handleCardClick($event, v.bvid, index)"
               class="group relative flex flex-col bg-white dark:bg-white/5 rounded-[2rem] overflow-hidden border border-gray-200 dark:border-white/5 transition-all cursor-pointer hover:shadow-2xl hover:-translate-y-1"
               :class="{'ring-2 ring-primary-500 ring-offset-4 dark:ring-offset-black shadow-xl': store.selectedBiliBvids.includes(v.bvid)}">
            <div class="w-full aspect-video relative bg-gray-200 dark:bg-gray-900 overflow-hidden shrink-0"
                 @contextmenu.prevent="openBiliVideo(v.bvid)">
              <img :src="store.formatImg(v.cover || v.pic)" class="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110" />
              <div v-if="store.selectedBiliBvids.includes(v.bvid)" class="absolute inset-0 bg-primary-500/20 flex items-center justify-center backdrop-blur-[2px]"><CheckCircleIcon class="w-12 h-12 text-white drop-shadow-lg" /></div>
              <div v-else class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity gap-3 bg-black/40">
                 <template v-if="v.page > 1 && !v.is_part"><button @click.stop="handleExpand(v)" :disabled="isExpanding === v.bvid" class="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-full text-xs font-bold shadow-xl hover:bg-purple-700 transition-all"><SquaresPlusIcon v-if="isExpanding !== v.bvid" class="w-5 h-5" /><ArrowPathIcon v-else class="w-5 h-5 animate-spin" />{{ isExpanding === v.bvid ? '展开中' : `展开 ${v.page} 集` }}</button></template>
                 <template v-else><button @click.stop="handlePlay(v)" class="w-12 h-12 bg-white rounded-full flex items-center justify-center text-primary-500 shadow-xl hover:scale-110 transition-all"><PlayIcon class="w-6 h-6 ml-0.5" /></button><button @click.stop="handleAddToQueue(v)" class="w-12 h-12 bg-white rounded-full flex items-center justify-center text-purple-500 shadow-xl hover:scale-110 transition-all"><PlusIcon class="w-6 h-6" /></button><button @click.stop="openSyncModal(v)" class="w-12 h-12 bg-white rounded-full flex items-center justify-center text-blue-500 shadow-xl hover:scale-110 transition-all"><ArrowPathIcon class="w-6 h-6" /></button></template>
              </div>
              <div class="absolute bottom-2 left-2 px-1.5 py-0.5 bg-black/60 backdrop-blur-md rounded-md text-[9px] text-white font-bold border border-white/10 flex items-center gap-1"><span v-if="v.is_part" class="text-primary-400 font-black">分P</span>{{ Math.floor(v.duration / 60) }}:{{ (v.duration % 60).toString().padStart(2, '0') }}</div>
            </div>
            <div class="p-5 flex flex-col flex-1 min-h-[100px]"><h3 class="text-sm font-bold text-gray-800 dark:text-gray-100 line-clamp-2 mb-1 leading-relaxed" :title="v.title">{{ v.title }}</h3><div class="text-[10px] text-gray-400 font-medium mb-3">@{{ v.upper?.name || v.owner || 'Unknown' }}</div>
              <div class="mt-auto flex flex-wrap gap-1.5"><template v-if="store.getSyncedCollections(v.bvid).length > 0"><button v-for="col in store.getSyncedCollections(v.bvid)" :key="col.id" @click.stop="removeSync(v.bvid, col.id)" class="px-2.5 py-1 bg-green-500/10 text-green-600 dark:text-green-400 text-[9px] font-black rounded-lg border border-green-500/20 transition-all hover:bg-red-500 hover:text-white group/tag flex items-center gap-1"><CheckCircleIcon class="w-3 h-3 group-hover/tag:hidden" /><span class="group-hover/tag:hidden">{{ col.title }}</span><span class="hidden group-hover/tag:inline uppercase tracking-tight">移除同步</span></button></template><span v-else class="text-[9px] font-bold text-gray-300 dark:text-gray-600 uppercase tracking-widest py-1 px-2 flex items-center gap-1.5 bg-gray-100/50 dark:bg-white/5 rounded-lg"><SparklesIcon class="w-3 h-3" /> 未同步</span></div>
            </div>
          </div>
        </div>
        <div ref="loadTrigger" class="h-20 mb-20 flex flex-col items-center justify-center gap-3">
           <template v-if="pageInfo?.hasMore || isLoading"><div class="w-10 h-10 border-[3px] border-primary-500 border-t-transparent rounded-full animate-spin"></div><span class="text-[10px] font-black text-gray-400 uppercase tracking-[0.4em]">正在检索最新数据...</span></template>
           <div v-else class="w-full flex items-center gap-4 text-gray-200 dark:text-gray-800"><div class="flex-1 h-px bg-current opacity-10"></div><span class="text-[10px] font-black uppercase tracking-[0.3em]">同步完成 (共 {{ currentVideos.length }}个)</span><div class="flex-1 h-px bg-current opacity-10"></div></div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.text-shadow { text-shadow: 0 4px 16px rgba(0,0,0,0.5); }
.line-clamp-2 { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.scrollbar-thin::-webkit-scrollbar { width: 5px; }
.scrollbar-thin::-webkit-scrollbar-thumb { background: rgba(156, 163, 175, 0.2); border-radius: 10px; }
.fade-enter-active, .fade-leave-active { transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); }
.fade-enter-from, .fade-leave-to { opacity: 0; transform: translateY(20px); }
.group { user-select: none; -webkit-user-select: none; }
.group img { pointer-events: none; -webkit-user-drag: none; }
</style>
