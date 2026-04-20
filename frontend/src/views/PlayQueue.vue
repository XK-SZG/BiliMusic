# -*- coding: utf-8 -*-
# Path: frontend/src/views/PlayQueue.vue

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { usePlayerStore } from '../stores/modules/player'
import UniversalModal from '../components/UniversalModal.vue'
import ContextMenu from '../components/ContextMenu.vue'
import localApi from '../api/local'
import {
  TrashIcon,
  PlayIcon,
  MusicalNoteIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  MagnifyingGlassIcon,
  FolderPlusIcon,
  Bars3Icon,
  FunnelIcon,
  XMarkIcon,
  PencilSquareIcon,
  ArrowsRightLeftIcon,
  AdjustmentsHorizontalIcon,
  ClockIcon,
  TagIcon,
  StarIcon,
  UserIcon,
  HashtagIcon,
  PowerIcon,
  QueueListIcon,
  SparklesIcon,
  MapPinIcon,
  ArrowUpIcon,
  CloudArrowDownIcon,
  LinkIcon
} from '@heroicons/vue/24/solid'

const store = usePlayerStore()

// --- 状态定义 ---
const searchQuery = ref('')
const selectedBvids = ref([])
const lastSelectedIndex = ref(-1)

// --- 筛选系统状态 ---
const showFilterPopover = ref(false)
const activeFilters = ref(JSON.parse(localStorage.getItem('cache_play_queue_filters') || '[]'))

const filterTypes = [
  { id: 'local', label: '本地状态', icon: FolderPlusIcon },
  { id: 'duration', label: '视频时长', icon: ClockIcon },
  { id: 'title', label: '视频标题', icon: MagnifyingGlassIcon },
  { id: 'tags', label: '视频标签', icon: TagIcon },
  { id: 'score', label: '视频评分', icon: StarIcon },
  { id: 'upper', label: 'UP主', icon: UserIcon },
  { id: 'bvid', label: 'BV号', icon: HashtagIcon },
  { id: 'collection', label: '所属媒体夹', icon: QueueListIcon }
]

const modalState = reactive({
  show: false,
  type: 'confirm',
  title: '',
  callback: null,
  extraData: {},
  initialValue: null
})

// --- 持久化 ---
watch(activeFilters, (newVal) => {
  localStorage.setItem('cache_play_queue_filters', JSON.stringify(newVal))
}, { deep: true })

// --- 核心过滤算法 ---
const filteredQueueAll = computed(() => {
  let fullList = store.playQueue.map((v, index) => ({ ...v, originalIndex: index, isMatched: true }))
  
  // 1. 文本搜索
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    fullList.forEach(v => { if (!v.title.toLowerCase().includes(q) && !v.owner.toLowerCase().includes(q)) v.isMatched = false })
  }

  // 2. 标签匹配
  const enabledFilters = activeFilters.value.filter(f => f.isEnabled)
  if (enabledFilters.length > 0) {
    const andFilters = enabledFilters.filter(f => f.logic === 'AND')
    const orFilters = enabledFilters.filter(f => f.logic === 'OR')

    const checkMatch = (filter, item) => {
      let matched = true
      if (filter.id === 'local') matched = item.download_status === 'completed'
      else if (filter.id === 'duration') matched = item.duration >= (filter.params.start || 0) && item.duration <= (filter.params.end || 999999)
      else if (filter.id === 'score') { const s = item.score ?? 5.0; matched = s >= (filter.params.start || 0) && s <= (filter.params.end || 10) }
      else if (filter.id === 'title') {
        const tq = (filter.params.text || '').toLowerCase()
        if (filter.params.isStrict) matched = item.title.toLowerCase() === tq
        else { const ks = tq.split(' ').filter(k => k); matched = ks.every(k => item.title.toLowerCase().includes(k)) }
      } else if (['tags', 'upper', 'bvid', 'collection'].includes(filter.id)) {
        const targets = filter.params || []
        if (targets.length === 0) matched = true
        else {
          const cur = store.localVideos.find(lv => lv.bvid === item.bvid) || item
          if (filter.id === 'tags') matched = (cur.tags || []).some(t => targets.includes(t.name))
          else if (filter.id === 'upper') matched = targets.some(t => item.owner.toLowerCase().includes(t.toLowerCase()))
          else if (filter.id === 'bvid') matched = targets.includes(item.bvid)
          else if (filter.id === 'collection') matched = (cur.collections || []).some(c => targets.includes(c.title))
        }
      }
      return filter.isNegative ? !matched : matched
    }

    fullList.forEach(item => {
      if (!item.isMatched) return
      const passAnd = andFilters.every(f => checkMatch(f, item))
      const passOr = orFilters.length === 0 ? true : orFilters.some(f => checkMatch(f, item))
      item.isMatched = passAnd && passOr
    })
  }
  return fullList
})

const filteredQueue = computed(() => filteredQueueAll.value.filter(v => v.isMatched))

// 同步索引到 store 供下一首逻辑使用
// 【精简逻辑】移除对 filteredQueueIndices 的复杂副作用，防止干扰初始化恢复
watch(filteredQueue, (newList) => { 
  store.filteredQueueIndices = newList.map(v => v.originalIndex) 
})

const isAllSelected = computed(() => filteredQueue.value.length > 0 && filteredQueue.value.every(v => selectedBvids.value.includes(v.bvid)))

// --- 忽略静默媒体 ---
const hideUnmatched = ref(localStorage.getItem('cache_queue_hide_unmatched') !== 'false')
watch(hideUnmatched, (val) => localStorage.setItem('cache_queue_hide_unmatched', String(val)))

const isFilterActive = computed(() => {
  return searchQuery.value.trim().length > 0 || activeFilters.value.some(f => f.isEnabled)
})

// 最终显示的列表
const displayQueue = computed(() => {
  if (isFilterActive.value && hideUnmatched.value) {
    return filteredQueue.value
  }
  return filteredQueueAll.value
})

// --- 交互逻辑 ---
function toggleFilterPopover(e) { e.stopPropagation(); showFilterPopover.value = !showFilterPopover.value }
function removeFilter(index) { activeFilters.value.splice(index, 1) }
function toggleFilterProperty(index, prop) {
  if (prop === 'logic') activeFilters.value[index].logic = activeFilters.value[index].logic === 'AND' ? 'OR' : 'AND'
  else activeFilters.value[index][prop] = !activeFilters.value[index][prop]
}

function openFilterConfig(typeId, isEdit = false, editIndex = -1) {
  const type = filterTypes.find(t => t.id === typeId); if (!type) return
  if (typeId === 'local' && !isEdit) { activeFilters.value.push({ id: 'local', label: '本地状态', isNegative: false, isEnabled: true, logic: 'AND', params: {}, displayValue: '已缓存视频' }); return }
  let initialValue = isEdit ? JSON.parse(JSON.stringify(activeFilters.value[editIndex].params)) : null
  modalState.type = 'input'; modalState.title = `配置筛选: ${type.label}`; modalState.extraData = { editIndex: isEdit ? editIndex : activeFilters.value.length, isGlobalFilter: true }
  if (typeId === 'duration') { modalState.type = 'range'; modalState.extraData.unit = '秒 (s)'; initialValue = initialValue || { start: 0, end: 300 } }
  else if (typeId === 'score') { modalState.type = 'range'; modalState.extraData.unit = '分 (1-10)'; initialValue = initialValue || { start: 5, end: 10 } }
  else if (typeId === 'title') { modalState.type = 'title_filter'; initialValue = initialValue || { text: '', isStrict: false } }
  else if (typeId === 'collection') { modalState.type = 'checklist'; modalState.extraData.options = store.localCollections.map(c => ({ id: c.title, label: c.title })); initialValue = initialValue || [] }
  else if (['tags', 'upper', 'bvid'].includes(typeId)) { modalState.type = 'tags'; modalState.extraData.placeholder = `添加关键词...`; modalState.extraData.existingTags = initialValue || [] }

  modalState.callback = (val) => {
    if (!val) return
    let params = val; let displayValue = ''
    if (typeId === 'duration') displayValue = `${val.start}s - ${val.end}s`
    else if (typeId === 'score') displayValue = `${val.start} - ${val.end} 分`
    else if (typeId === 'title') displayValue = `${val.isStrict ? '[严格]' : '[模糊]'} ${val.text}`
    else if (typeId === 'collection') { params = val; displayValue = val.join(', ') }
    else if (['tags', 'upper', 'bvid'].includes(typeId)) {
      const cIdx = modalState.extraData.editIndex; const cParams = (isEdit && activeFilters.value[cIdx]) ? activeFilters.value[cIdx].params : (initialValue || [])
      if (!cParams.includes(val)) cParams.push(val)
      params = cParams; displayValue = cParams.join(', '); modalState.extraData.existingTags = [...cParams]
    }
    if (isEdit && activeFilters.value[editIndex]) { activeFilters.value[editIndex].params = params; activeFilters.value[editIndex].displayValue = displayValue }
    else if (!isEdit) {
      activeFilters.value.push({ id: typeId, label: type.label, isNegative: false, isEnabled: true, logic: 'AND', params, displayValue }); isEdit = true; editIndex = activeFilters.value.length - 1; modalState.extraData.editIndex = editIndex
    }
  }
  modalState.initialValue = initialValue; modalState.show = true
}

function handleFilterTagRemove(targetId) {
  const index = modalState.extraData.editIndex; if (index === undefined || !activeFilters.value[index]) return
  const list = activeFilters.value[index].params; const idx = list.indexOf(targetId); if (idx > -1) { list.splice(idx, 1); activeFilters.value[index].displayValue = list.join(', '); modalState.extraData.existingTags = [...list]; if (list.length === 0) { removeFilter(index); modalState.show = false } }
}

function getUnionTags() {
  const tagMap = new Map(); selectedBvids.value.forEach(bvid => { const video = store.localVideos.find(lv => lv.bvid === bvid) || store.playQueue.find(pv => pv.bvid === bvid); if (video && video.tags) video.tags.forEach(t => tagMap.set(t.id, t)) })
  return Array.from(tagMap.values())
}

function openTagModal() {
  if (selectedBvids.value.length === 0) return
  modalState.type = 'tags'; modalState.title = selectedBvids.value.length > 1 ? `批量管理标签 (${selectedBvids.value.length})` : '标签管理'; modalState.initialValue = ''
  modalState.extraData = { existingTags: getUnionTags(), isGlobalFilter: false }
  modalState.callback = async (tagName) => {
    if (!tagName) return
    try {
      const selectedVideos = store.playQueue.filter(v => selectedBvids.value.includes(v.bvid))
      await localApi.batchAddTags({
        bvids: selectedBvids.value, tag_name: tagName,
        videos: selectedVideos.map(v => ({ bvid: v.bvid, title: v.title, owner: v.owner, pic: v.pic, duration: v.duration }))
      })
      await store.fetchLocalVideos()
      store.playQueue.forEach(v => { if (selectedBvids.value.includes(v.bvid)) { const updated = store.localVideos.find(lv => lv.bvid === v.bvid); if (updated) v.tags = updated.tags } })
      modalState.extraData.existingTags = getUnionTags()
    } catch (e) {}
  }
  modalState.show = true
}

async function handleBatchTagRemove(tid) {
  for (const bvid of selectedBvids.value) {
    try { await localApi.removeTagFromVideo(bvid, tid) } catch(e){}
  }
  await store.fetchLocalVideos()
  store.playQueue.forEach(v => { if (selectedBvids.value.includes(v.bvid)) { const updated = store.localVideos.find(lv => lv.bvid === v.bvid); if (updated) v.tags = updated.tags } })
  modalState.extraData.existingTags = getUnionTags()
}

function openBatchScore() {
  if (selectedBvids.value.length === 0) return
  let initScore = selectedBvids.value.length === 1 ? (filteredQueue.value.find(v => v.bvid === selectedBvids.value[0])?.score || 5.0) : 5.0
  modalState.type = 'score'; modalState.title = `批量评分 (${selectedBvids.value.length}项)`; modalState.initialValue = initScore
  modalState.callback = async (score) => {
    for (const bvid of selectedBvids.value) {
      const v = store.playQueue.find(item => item.bvid === bvid)
      await store.updateVideoScore(bvid, score)
      if (v) v.score = score
    }
    selectedBvids.value = []; store.showToast("评分已批量更新", "success")
  }
  modalState.show = true
}

function handleSelect(event, bvid, index) {
  // 阻止默认行为以防选择文本
  if (event.shiftKey) event.preventDefault()

  if (event.shiftKey && lastSelectedIndex.value !== -1) {
    const start = Math.min(lastSelectedIndex.value, index); const end = Math.max(lastSelectedIndex.value, index)
    const rangeBvids = filteredQueueAll.value.slice(start, end + 1).map(v => v.bvid)
    
    const isAdding = !selectedBvids.value.includes(bvid)
    if (isAdding) {
      selectedBvids.value = Array.from(new Set([...selectedBvids.value, ...rangeBvids]))
    } else {
      selectedBvids.value = selectedBvids.value.filter(id => !rangeBvids.includes(id))
    }
  } else {
    const idx = selectedBvids.value.indexOf(bvid); if (idx > -1) selectedBvids.value.splice(idx, 1); else selectedBvids.value.push(bvid); lastSelectedIndex.value = index
  }
}
function toggleSelectAll() { if (isAllSelected.value) selectedBvids.value = []; else selectedBvids.value = filteredQueue.value.map(v => v.bvid) }
function playAtIndex(originalIndex) { 
  store.playFromQueue(originalIndex)
  store.isUiCollapsed = true 
  store.isPlaying = true 
}
function removeSelected() { if (selectedBvids.value.length === 0) return; store.removeFromQueueBatch(selectedBvids.value); selectedBvids.value = []; store.showToast("已从队列移除选中项", "info") }
function openAddToCollection() {
  if (selectedBvids.value.length === 0) return
  const options = store.localCollections.map(c => ({ id: c.id, label: c.title }))
  modalState.type = 'checklist'; modalState.title = `批量归档 (${selectedBvids.value.length}个视频)`; modalState.extraData = { options, allowCreate: true }
  modalState.callback = async (colIds) => {
    if (!colIds || colIds.length === 0) {
      store.showToast("请先选择一个本地媒体库", "error")
      return
    }
    const selectedVideos = store.playQueue.filter(v => selectedBvids.value.includes(v.bvid))
    for (const v of selectedVideos) { await store.updateVideoCollections(v, colIds) }
    store.showToast("已添加至指定媒体库", "success"); selectedBvids.value = []
  }
  modalState.show = true
}

async function handleCreateCollection(name) {
  if (!name) return
  const exists = store.localCollections.some(c => c.title === name)
  if (exists) {
    store.showToast("媒体库名称已存在", "error")
    return
  }
  try {
    await localApi.createCollection(name)
    await store.fetchLocalCollections()
    store.showToast("媒体库创建成功", "success")
    // 更新弹窗选项
    modalState.extraData.options = store.localCollections.map(c => ({ id: c.id, label: c.title }))
  } catch (e) {
    console.error('创建媒体库失败:', e)
    store.showToast('创建媒体库失败', 'error')
  }
}

const dragOverIndex = ref(-1); const isDragging = ref(false); let dragStartIndex = -1
function onDragStart(event, index) { if (!selectedBvids.value.includes(filteredQueueAll.value[index].bvid)) { selectedBvids.value = [filteredQueueAll.value[index].bvid] }; dragStartIndex = index; isDragging.value = true; event.dataTransfer.effectAllowed = 'move' }
function onDragOver(event, index) { event.preventDefault(); dragOverIndex.value = index; event.dataTransfer.dropEffect = 'move' }
function onDrop(event, targetIndex) {
  event.preventDefault(); const finalDragStart = dragStartIndex; const finalTargetIndex = targetIndex
  isDragging.value = false; dragOverIndex.value = -1; dragStartIndex = -1
  if (finalDragStart === -1 || finalDragStart === finalTargetIndex) return
  const newQueue = [...store.playQueue]
  const selectedOriginalIndices = filteredQueueAll.value.filter(v => selectedBvids.value.includes(v.bvid)).map(v => v.originalIndex).sort((a, b) => a - b)
  const movingItems = selectedOriginalIndices.map(idx => store.playQueue[idx])
  for (let i = selectedOriginalIndices.length - 1; i >= 0; i--) { newQueue.splice(selectedOriginalIndices[i], 1) }
  const targetOriginalItem = filteredQueueAll.value[finalTargetIndex]
  let insertAt = newQueue.findIndex(v => v.bvid === targetOriginalItem.bvid)
  if (finalDragStart < finalTargetIndex) insertAt += 1
  newQueue.splice(insertAt, 0, ...movingItems); store.reorderQueue(newQueue)
}
function onDragEnd() { isDragging.value = false; dragOverIndex.value = -1; dragStartIndex = -1 }

// 定位当前播放视频
const currentVideoRef = ref(null)
function scrollToCurrentPlaying() {
  const currentIndex = store.queueIndex
  if (currentIndex === -1) {
    store.showToast("当前没有正在播放的视频", "info")
    return
  }
  
  // 找到当前播放视频在过滤后列表中的位置
  const filteredIndex = filteredQueueAll.value.findIndex(v => v.originalIndex === currentIndex)
  if (filteredIndex === -1) {
    store.showToast("当前播放的视频已被筛选隐藏", "warning")
    return
  }
  
  // 滚动到目标元素
  const targetElement = document.querySelector(`[data-video-index="${filteredIndex}"]`)
  if (targetElement) {
    targetElement.scrollIntoView({ behavior: 'smooth', block: 'center' })
    
    // 添加高亮动画
    targetElement.classList.add('highlight-flash')
    setTimeout(() => {
      targetElement.classList.remove('highlight-flash')
    }, 2000)
  }
}

// 快捷键处理
function handleKeyDown(e) {
  // 如果焦点在输入框中，不处理快捷键
  const activeEl = document.activeElement
  if (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.isContentEditable) return
  
  // Ctrl+L 或 Cmd+L：定位当前播放
  if ((e.ctrlKey || e.metaKey) && e.key === 'l') {
    e.preventDefault()
    scrollToCurrentPlaying()
  }
}

const closePopovers = () => { showFilterPopover.value = false }
onMounted(async () => {
  await store.fetchLocalVideos()
  await store.fetchLocalCollections()
  window.addEventListener('click', closePopovers)
  window.addEventListener('keydown', handleKeyDown)
})
onUnmounted(() => {
  window.removeEventListener('click', closePopovers)
  window.removeEventListener('keydown', handleKeyDown)
})

// 右键菜单状态
const contextMenu = reactive({
  visible: false,
  x: 0,
  y: 0,
  video: null
})

// 显示右键菜单
function showContextMenu(event, video) {
  event.preventDefault()
  event.stopPropagation()
  contextMenu.video = video
  contextMenu.x = event.clientX
  contextMenu.y = event.clientY
  contextMenu.visible = true
}

// 打开B站视频
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

// 右键菜单项
const contextMenuItems = computed(() => {
  if (!contextMenu.video) return []
  
  const video = contextMenu.video
  const isCached = video.download_status === 'completed'
  const isLocal = video.is_local === 1
  const isCurrentPlaying = video.originalIndex === store.queueIndex
  
  const items = [
    {
      label: isCurrentPlaying ? '重新播放' : '播放',
      icon: PlayIcon,
      action: () => playAtIndex(video.originalIndex)
    },
    {
      type: 'divider'
    },
    {
      label: '置顶',
      icon: ArrowUpIcon,
      disabled: video.originalIndex === 0,
      action: () => {
        const newQueue = [...store.playQueue]
        const [item] = newQueue.splice(video.originalIndex, 1)
        newQueue.unshift(item)
        store.reorderQueue(newQueue)
      }
    },
    {
      label: '从队列移除',
      icon: XMarkIcon,
      action: () => store.removeFromQueue(video.originalIndex)
    },
    {
      type: 'divider'
    },
    {
      label: '归档到媒体库',
      icon: FolderPlusIcon,
      action: () => {
        selectedBvids.value = [video.bvid]
        openAddToCollection()
      }
    },
    {
      label: '管理标签',
      icon: TagIcon,
      action: () => {
        selectedBvids.value = [video.bvid]
        openTagModal()
      }
    },
    {
      label: '评分',
      icon: StarIcon,
      action: () => {
        selectedBvids.value = [video.bvid]
        openBatchScore()
      }
    }
  ]
  
  if (!isLocal) {
    items.push(
      {
        type: 'divider'
      },
      {
        label: isCached ? '已缓存' : '下载缓存',
        icon: CloudArrowDownIcon,
        disabled: isCached,
        action: () => !isCached && store.addToDownload(video.bvid)
      },
      {
        label: '在B站打开',
        icon: LinkIcon,
        action: () => openBiliVideo(video.bvid)
      }
    )
  }
  
  return items
})

// 处理右键菜单选择
function handleContextMenuSelect(item) {
  if (item.action) {
    item.action()
  }
  contextMenu.visible = false
}
</script>

<template>
  <div class="h-full flex flex-col animate-fade-in relative">
    <UniversalModal :show="modalState.show" :type="modalState.type" :title="modalState.title" :initial-value="modalState.initialValue" :extra-data="modalState.extraData" @close="modalState.show = false" @confirm="(val) => modalState.callback && modalState.callback(val)"
                    @create-collection="handleCreateCollection"
                    @remove-tag="async (tid) => {
                      if (modalState.type === 'tags' && !modalState.extraData.isGlobalFilter) {
                        await handleBatchTagRemove(tid)
                      } else { handleFilterTagRemove(tid) }
                    }" />
    
    <!-- 右键菜单 -->
    <ContextMenu
      :visible="contextMenu.visible"
      :x="contextMenu.x"
      :y="contextMenu.y"
      :items="contextMenuItems"
      @close="contextMenu.visible = false"
      @select="handleContextMenuSelect"
    />
    
    <div class="flex flex-col gap-4 mb-8 relative z-30">
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div class="flex flex-wrap items-center gap-4">
          <h2 class="text-4xl font-black text-gray-800 dark:text-white tracking-tight shrink-0">播放队列</h2>
          <button @click="store.playRandomFromQueue()" class="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-primary-500 to-fuchsia-500 hover:from-primary-400 hover:to-fuchsia-400 text-white rounded-xl shadow-lg shadow-primary-500/30 font-black text-xs transition-all hover:scale-105 active:scale-95 uppercase tracking-wider whitespace-nowrap">
            <SparklesIcon class="w-4 h-4 shrink-0" /> 随机一曲
          </button>
          <button @click="store.reorderQueue([...store.playQueue].sort(() => Math.random() - 0.5))" class="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-white rounded-xl shadow-lg shadow-emerald-500/30 font-black text-xs transition-all hover:scale-105 active:scale-95 uppercase tracking-wider whitespace-nowrap" title="随机排列播放队列">
            <ArrowPathIcon class="w-4 h-4 shrink-0" /> 随机排列
          </button>
          <button @click="scrollToCurrentPlaying" class="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-blue-500 to-cyan-500 hover:from-blue-400 hover:to-cyan-400 text-white rounded-xl shadow-lg shadow-blue-500/30 font-black text-xs transition-all hover:scale-105 active:scale-95 uppercase tracking-wider whitespace-nowrap" title="定位当前播放 (Ctrl+L)">
            <MapPinIcon class="w-4 h-4 shrink-0" /> 定位当前
          </button>
        </div>
      </div>
      
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <p class="text-gray-500 font-medium italic shrink-0">即将播放: {{ filteredQueue.length }} 首曲目</p>
        <div class="flex items-center gap-3 bg-white/50 dark:bg-gray-800/40 backdrop-blur-md p-2 rounded-2xl border border-gray-100 dark:border-white/5 shadow-sm relative self-start md:self-auto overflow-x-auto scrollbar-none" :class="{'z-50': showFilterPopover}">
          <div class="relative group shrink-0"><MagnifyingGlassIcon class="w-4 h-4 absolute left-3 top-3 text-gray-400" /><input v-model="searchQuery" placeholder="搜索标题或UP..." class="bg-gray-100 dark:bg-white/5 border-none rounded-xl pl-9 pr-4 py-2.5 text-xs font-bold focus:ring-2 focus:ring-primary-500 w-32 sm:w-40 md:w-64 transition-all" /></div>
          <label v-if="isFilterActive" class="flex items-center gap-2 cursor-pointer text-xs font-bold text-gray-500 hover:text-primary-500 transition px-2 whitespace-nowrap shrink-0">
            <input type="checkbox" v-model="hideUnmatched" class="rounded border-gray-300 text-primary-500 shadow-sm focus:border-primary-300 focus:ring focus:ring-primary-200 focus:ring-opacity-50 w-4 h-4 transition-all">
            <span class="hidden sm:inline">忽略静默媒体</span>
          </label>
          <div class="h-8 w-px bg-gray-200 dark:bg-white/10 mx-1 shrink-0"></div>
          <!-- 为了避免 absolute 浮窗撑开外部容器导致布局闪烁，将其直接放置在具有确切定位上下文的父级 -->
          <div class="shrink-0">
          <button @click="toggleFilterPopover" :class="activeFilters.length > 0 ? 'text-primary-500 bg-primary-500/10' : 'text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5'" class="p-2.5 rounded-xl transition-all flex items-center gap-2 text-[14px] font-black uppercase whitespace-nowrap">
            <AdjustmentsHorizontalIcon class="w-4 h-4 shrink-0" /><span class="hidden md:inline">高级筛选</span><span v-if="activeFilters.length > 0" class="ml-1 w-4 h-4 bg-primary-500 text-white rounded-full flex items-center justify-center text-[8px]">{{ activeFilters.length }}</span>
          </button>
          <transition name="dropdown">
            <div v-if="showFilterPopover" @click.stop class="absolute top-full right-0 mt-3 w-80 sm:w-[26rem] z-[100] bg-white dark:bg-gray-900 rounded-[2rem] shadow-2xl border border-gray-100 dark:border-white/10 overflow-hidden backdrop-blur-2xl">
              <div class="p-6">
                <div class="flex items-center justify-between mb-5"><h4 class="text-sm font-black text-gray-400 uppercase tracking-[0.2em]">活跃筛选器</h4><button v-if="activeFilters.length > 0" @click="activeFilters = []" class="text-xs font-bold text-primary-500 hover:underline">全部清除</button></div>
                <div class="space-y-3 mb-6 max-h-80 overflow-y-auto scrollbar-thin pr-1">
                  <div v-for="(filter, index) in activeFilters" :key="index" class="flex flex-col gap-2 p-4 rounded-2xl border transition-all group/f" :class="filter.isEnabled ? 'bg-gray-50 dark:bg-white/5 border-transparent shadow-sm' : 'bg-gray-100/50 dark:bg-black/20 border-transparent opacity-50'">
                    <div class="flex items-center gap-3">
                      <button @click="toggleFilterProperty(index, 'isEnabled')" class="w-10 h-10 rounded-xl flex items-center justify-center transition-colors" :class="filter.isEnabled ? 'bg-blue-500 text-white shadow-lg shadow-blue-500/30' : 'bg-gray-200 dark:bg-white/10 text-gray-400'"><PowerIcon class="w-5 h-5" /></button>
                      <button @click="toggleFilterProperty(index, 'logic')" class="px-2.5 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-tighter transition-all" :class="filter.logic === 'AND' ? 'bg-indigo-500/20 text-indigo-500 border border-indigo-500/20' : 'bg-orange-500/20 text-orange-500 border border-orange-500/20'">{{ filter.logic === 'AND' ? '且' : '或' }}</button>
                      <button @click="toggleFilterProperty(index, 'isNegative')" class="w-10 h-10 rounded-xl flex items-center justify-center transition-colors" :class="filter.isNegative ? 'bg-red-500/10 text-red-500' : 'bg-green-500/10 text-green-500'"><ArrowsRightLeftIcon class="w-5 h-5" /></button>
                      <div class="flex-1 min-w-0"><div class="text-xs font-black uppercase text-gray-400 mb-0.5 tracking-wider">{{ filter.label }}</div><div class="text-sm font-bold truncate text-gray-700 dark:text-gray-200 leading-tight">{{ filter.displayValue }}</div></div>
                      <div class="flex items-center gap-1 opacity-0 group-hover/f:opacity-100 transition-opacity">
                        <button v-if="filter.id !== 'local'" @click="openFilterConfig(filter.id, true, index)" class="p-2 text-gray-400 hover:text-blue-500"><PencilSquareIcon class="w-5 h-5" /></button>
                        <button @click="removeFilter(index)" class="p-2 text-gray-400 hover:text-red-500"><TrashIcon class="w-5 h-5" /></button>
                      </div>
                    </div>
                  </div>
                  <div v-if="activeFilters.length === 0" class="py-10 text-center opacity-30"><FunnelIcon class="w-8 h-8 mx-auto mb-2" /><p class="text-[12px] font-bold uppercase tracking-widest">暂无筛选条件</p></div>
                </div>
                <div class="border-t border-gray-100 dark:border-white/5 pt-4"><p class="text-[12px] font-black text-gray-400 uppercase tracking-widest mb-3 px-1">添加筛选维度</p>
                  <div class="grid grid-cols-2 gap-2"><button v-for="type in filterTypes" :key="type.id" @click="openFilterConfig(type.id)" class="flex items-center gap-2 px-3 py-2 bg-gray-50 dark:bg-white/5 hover:bg-primary-500/10 hover:text-primary-500 rounded-xl transition-all text-left group/add"><component :is="type.icon" class="w-3.5 h-3.5 text-gray-400 group-hover/add:text-primary-500" /><span class="text-[12px] font-bold">{{ type.label }}</span></button></div>
                </div>
                </div>
              </div>
            </transition>
          </div>
        </div>
      </div>
    </div>

    <!-- 列表展示区 (修正：如果没有选中项，始终显示列表) -->
    <div class="flex-1 overflow-y-auto space-y-1 pr-2 scrollbar-thin pb-24">
      <div class="flex items-center p-3 mb-2 opacity-60 hover:opacity-100 transition-opacity">
        <button @click="toggleSelectAll" class="flex items-center gap-3 text-[12px] font-black uppercase tracking-[0.2em] text-gray-500">
          <div class="w-5 h-5 rounded-lg border-2 flex items-center justify-center transition-all" :class="isAllSelected ? 'bg-primary-500 border-primary-500' : 'border-gray-300 dark:border-gray-600'"><CheckCircleIcon v-if="isAllSelected" class="w-3 h-3 text-white" /></div>全选所有
        </button>
      </div>

      <div v-for="(video, index) in displayQueue" :key="video.bvid" :data-video-index="video.originalIndex" class="relative transition-all duration-200">
        <div v-if="isDragging && dragOverIndex === video.originalIndex" class="absolute left-0 right-0 h-1 bg-primary-500 z-20 rounded-full shadow-[0_0_12px_rgba(236,72,153,1)] animate-pulse" :class="dragStartIndex < video.originalIndex ? '-bottom-1' : '-top-1'"></div>
        <div draggable="true" @dragstart="video.isMatched && onDragStart($event, video.originalIndex)" @dragover="video.isMatched && onDragOver($event, video.originalIndex)" @drop="video.isMatched && onDrop($event, video.originalIndex)" @dragend="onDragEnd"
             class="group flex items-center p-3 rounded-2xl border border-transparent transition-all relative"
             :class="[video.isMatched ? 'cursor-pointer' : 'opacity-40 grayscale pointer-events-none scale-[0.98]', video.originalIndex === store.queueIndex ? 'bg-primary-500/10 border-primary-500/20 shadow-inner' : (video.isMatched ? 'hover:bg-white/40 dark:hover:bg-white/5' : ''), selectedBvids.includes(video.bvid) ? 'bg-blue-500/10 border-blue-500/20' : '', isDragging && dragOverIndex === video.originalIndex ? 'opacity-40 translate-x-2' : '']"
             @click="video.isMatched && handleSelect($event, video.bvid, video.originalIndex)"
             @contextmenu="showContextMenu($event, video)">
          <div class="w-8 flex justify-center text-gray-300 group-hover:text-gray-500 cursor-grab active:cursor-grabbing"><Bars3Icon class="w-4 h-4" /></div>
          <div class="w-10 flex justify-center">
            <div v-if="selectedBvids.includes(video.bvid)" class="w-5 h-5 rounded-full bg-blue-500 flex items-center justify-center shadow-lg"><CheckCircleIcon class="w-4 h-4 text-white" /></div>
            <template v-else>
              <div v-if="video.originalIndex === store.queueIndex" class="relative">
                <span class="text-primary-500 group-hover:hidden"><PlayIcon class="w-5 h-5 animate-pulse" /></span>
                <button @click.stop="playAtIndex(video.originalIndex)" class="hidden group-hover:block text-primary-600 dark:text-primary-400"><ArrowPathIcon class="w-5 h-5" /></button>
              </div>
              <span v-else class="text-xs font-black text-gray-400 group-hover:hidden">{{ index + 1 }}</span>
              <button v-if="video.originalIndex !== store.queueIndex" @click.stop="playAtIndex(video.originalIndex)" class="hidden group-hover:block text-gray-400 hover:text-primary-500 transition-colors"><PlayIcon class="w-5 h-5" /></button>
            </template>
          </div>
          <div class="w-14 aspect-video rounded-lg overflow-hidden bg-gray-200 dark:bg-gray-800 shrink-0 mx-4 shadow-sm flex items-center justify-center relative">
            <template v-if="video.pic && store.formatImg(video.pic || video.cover)">
              <img :src="store.formatImg(video.pic || video.cover, '480w_270h_1c_1s.webp')" @error="(e) => { if (e.target.src.indexOf('default-cover.svg') === -1) e.target.src = '/default-cover.svg' }" class="w-full h-full object-cover" style="image-rendering: auto; transform: translateZ(0); backface-visibility: hidden;" />
            </template>
            <MusicalNoteIcon v-else class="w-6 h-6 text-gray-400 opacity-50" />
          </div>
          <div class="flex-1 min-w-0">
            <div class="font-bold text-sl text-gray-800 dark:text-gray-100 truncate" :class="{'text-primary-600 dark:text-primary-400': video.originalIndex === store.queueIndex}">{{ video.title }}</div>
            <div class="flex items-center gap-3 mt-0.5">
              <span class="text-[13px] text-gray-400 font-bold truncate">@{{ video.owner }}</span>
              <span v-if="video.download_status === 'completed'" class="px-1.5 py-0.5 bg-green-500/10 text-green-500 text-[8px] font-black rounded uppercase tracking-tighter">本地</span>
              <div class="flex items-center bg-gray-100 dark:bg-white/5 rounded-md px-1.5 py-0.5 gap-1 group/score hover:bg-primary-500/10 transition-colors"><StarIcon class="w-2.5 h-2.5 text-yellow-500" /><span class="text-[12px] font-black text-gray-500 dark:text-gray-400">{{ (video.score || 5.0).toFixed(1) }}</span></div>
              <div v-if="(store.localVideos.find(lv => lv.bvid === video.bvid) || video).tags?.length" class="flex flex-wrap gap-1">
                <span v-for="t in (store.localVideos.find(lv => lv.bvid === video.bvid) || video).tags.slice(0,3)" :key="t.id" class="px-1.5 py-0.5 bg-purple-500/10 text-purple-500 text-[10px] font-bold rounded border border-purple-500/10">#{{ t.name }}</span>
              </div>
            </div>
          </div>
          <div class="opacity-0 group-hover:opacity-100 flex items-center gap-1 transition-opacity">
             <button @click.stop="store.removeFromQueue(video.originalIndex)" class="p-2 text-gray-400 hover:text-red-500 transition-colors" title="移除"><XMarkIcon class="w-5 h-5" /></button>
          </div>
        </div>
      </div>
    </div>

    <!-- 批量操作栏 -->
    <transition name="slide-up">
      <div v-if="selectedBvids.length > 0" 
           class="fixed bottom-24 left-1/2 -translate-x-1/2 z-[40] flex items-center gap-2 px-3 py-2 rounded-2xl shadow-2xl transition-all border
                  bg-white/90 dark:bg-gray-900/90 backdrop-blur-xl border-gray-200 dark:border-white/10
                  min-w-[320px] lg:min-w-[520px]">
        <span class="px-2 lg:px-4 text-[10px] font-black text-gray-500 dark:text-gray-400 uppercase tracking-widest border-r border-gray-100 dark:border-white/10 mr-1 lg:mr-2">
          {{ selectedBvids.length }} 项
        </span>
        <button @click="openAddToCollection" class="btn-batch-q bg-blue-500 text-white shadow-lg shadow-blue-500/30 shrink-0">
          <FolderPlusIcon class="w-4 h-4" /> <span>归档</span>
        </button>
        <button @click="openBatchScore" class="btn-batch-q bg-yellow-500 text-white shadow-lg shadow-yellow-500/30 shrink-0">
          <StarIcon class="w-4 h-4" /> <span>评分</span>
        </button>
        <button @click="openTagModal" class="btn-batch-q bg-purple-500 text-white shadow-lg shadow-purple-500/30 shrink-0">
          <TagIcon class="w-4 h-4" /> <span>标签</span>
        </button>
        <button @click="removeSelected" class="btn-batch-q bg-red-500 text-white shadow-lg shadow-red-500/30 shrink-0">
          <TrashIcon class="w-4 h-4" /> <span>移除</span>
        </button>
        <button @click="selectedBvids = []" class="p-2 text-gray-400 hover:text-primary-500 transition shrink-0">
          <XMarkIcon class="w-5 h-5" />
        </button>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.btn-batch-q { @apply flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-black transition-all hover:scale-105 active:scale-95; }
.slide-up-enter-active, .slide-up-leave-active { transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
.slide-up-enter-from, .slide-up-leave-to { transform: translate(-50%, 100px); opacity: 0; }
.scrollbar-thin::-webkit-scrollbar { width: 4px; }
.scrollbar-thin::-webkit-scrollbar-thumb { background: rgba(156, 163, 175, 0.2); border-radius: 10px; }
[draggable="true"] { user-select: none; }

/* 高亮闪烁动画 */
@keyframes highlight-flash {
  0%, 100% { background-color: transparent; }
  50% { background-color: rgba(59, 130, 246, 0.2); }
}

.highlight-flash {
  animation: highlight-flash 1s ease-in-out 2;
}
</style>
