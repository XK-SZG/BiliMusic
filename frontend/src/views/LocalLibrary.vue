<!-- frontend/src/views/LocalLibrary.vue -->
<script setup>
import { ref, onMounted, computed, reactive, onUnmounted, watch, nextTick } from 'vue'
import { usePlayerStore } from '../stores/modules/player'
import UniversalModal from '../components/UniversalModal.vue'
import ContextMenu from '../components/ContextMenu.vue'
import TrimEditor from '../components/TrimEditor.vue'
import AddVideoInputModal from '../components/AddVideoInputModal.vue'
import VideoPreviewModal from '../components/VideoPreviewModal.vue'
import CollectionSelectModal from '../components/CollectionSelectModal.vue'
import localApi from '../api/local'
import biliApi from '../api/bili'
import {
  PlayIcon,
  CheckCircleIcon,
  ArrowsUpDownIcon,
  FolderIcon,
  TrashIcon,
  PlusIcon,
  TagIcon,
  StarIcon,
  ArrowDownTrayIcon,
  DocumentDuplicateIcon,
  FolderArrowDownIcon,
  XCircleIcon,
  MagnifyingGlassIcon,
  QueueListIcon,
  ArrowPathIcon,
  ExclamationTriangleIcon,
  ChevronLeftIcon,
  ScissorsIcon,
  ArrowUpTrayIcon,
  MusicalNoteIcon as AudioIcon,
  VideoCameraIcon as VideoIcon,
  ServerIcon,
  PencilSquareIcon,
  Bars3Icon,
  CloudArrowDownIcon,
  LinkIcon
} from '@heroicons/vue/24/solid'
import { FolderIcon as FolderOutline } from '@heroicons/vue/24/outline'

// 窗口宽度监听
const windowWidth = ref(window.innerWidth)
const onResize = () => { windowWidth.value = window.innerWidth }
onMounted(() => window.addEventListener('resize', onResize))
onUnmounted(() => window.removeEventListener('resize', onResize))

const store = usePlayerStore()
const searchQuery = ref('')
const searchMode = ref('fuzzy')
const searchOptions = [
  { val: 'fuzzy', label: '模糊' },
  { val: 'title', label: '标题' },
  { val: 'upper', label: 'UP主' },
  { val: 'bvid', label: 'BV号' },
  { val: 'regex', label: '正则' }
]

const isSearchMenuOpen = ref(false)

const lastSelectedIndex = ref(-1)
const sortDesc = ref(true)

// --- 状态控制 ---
const modalState = reactive({
  show: false,
  type: 'input',
  title: '',
  initialValue: '',
  extraData: {},
  callback: null
})

const isManageOpen = ref(false)
const showTrimEditor = ref(false)
const trimTargetBvid = ref('')
const showAddVideoInput = ref(false)
const showAddVideoPreview = ref(false)
const showAddVideoCollectionSelect = ref(false)
const addVideoData = ref(null)

function openTrimEditor(bvid) {
  trimTargetBvid.value = bvid
  showTrimEditor.value = true
}

async function handleAddVideoInput(inputText) {
  // 关闭输入弹窗
  showAddVideoInput.value = false
  
  // 解析 BV 号
  const bvRegex = /BV[a-zA-Z0-9]{10}/
  const pParamRegex = /[?&]p=(\d+)/
  
  const bvMatch = bvRegex.exec(inputText)
  if (!bvMatch) {
    store.showToast('未找到有效的 BV 号', 'error')
    return
  }

  // 手动添加时，如果剪贴板轮询正在进行，可能和剪贴板添加冲突
  // 所以我们可以清空或忽略当前已缓存的 bvid，不过主要还是调用自己的逻辑
  
  const bvid = bvMatch[0]
  const pMatch = pParamRegex.exec(inputText)
  const partNum = pMatch ? pMatch[1] : null
  
  // 构造标准化的 bvid
  const normalizedBvid = partNum ? `${bvid}_p${partNum}` : bvid
  
  try {
    const cleanBvid = bvid
    const parts = await biliApi.getVideoParts(cleanBvid)
    
    // 注意：如果是单P视频，parts.parts 可能为空或者只有 1 个
    // 经过后端优化后，parts 会包含 title, pic, owner, duration
    
    if (!parts || (!parts.parts && !parts.title)) {
      store.showToast('无法获取视频信息', 'error')
      return
    }
    
    // 如果是分集视频，获取对应分集的信息
    let finalVideoInfo = null;
    
    // 获取UP主头像
    let ownerFace = '';
    if (parts.owner_face) {
      ownerFace = parts.owner_face;
    } else {
      // 尝试通过普通API获取UP主头像
      try {
          const url = `https://api.bilibili.com/x/web-interface/view?bvid=${cleanBvid}`;
          const res = await fetch(url).then(r => r.json());
          if (res.code === 0 && res.data && res.data.owner && res.data.owner.face) {
              ownerFace = res.data.owner.face;
          }
      } catch(err){}
    }

    if (partNum) {
      const pNum = parseInt(partNum)
      if (parts.parts && parts.parts.length > 0 && pNum > parts.parts.length) {
        store.showToast(`分集编号超出范围（共 ${parts.parts.length} 集）`, 'error')
        return
      }
      
      const partInfo = parts.parts && parts.parts.length > 0 ? parts.parts[pNum - 1] : null
      
      finalVideoInfo = {
        bvid: normalizedBvid,
        title: partInfo ? `${parts.title} - P${pNum}: ${partInfo.part}` : `${parts.title} - P${pNum}`,
        owner: parts.owner,
        owner_face: ownerFace,
        pic: parts.pic,
        duration: partInfo ? partInfo.duration : parts.duration,
        is_part: true,
        part_num: pNum,
        clean_bvid: cleanBvid
      }
    } else {
      finalVideoInfo = {
        bvid: normalizedBvid,
        title: parts.title,
        owner: parts.owner,
        owner_face: ownerFace,
        pic: parts.pic,
        duration: parts.duration,
        is_part: false,
        part_num: null,
        clean_bvid: cleanBvid
      }
    }
    
    // 保存视频信息并显示预览弹窗
    addVideoData.value = finalVideoInfo
    showAddVideoPreview.value = true
  } catch (e) {
    console.error('获取视频信息失败:', e)
    store.showToast('获取视频信息失败', 'error')
  }
}

async function handleAddVideoCollectionSelect(collectionId) {
  if (!addVideoData.value || !collectionId) return
  
  try {
    // 由于后端 importBiliVideos 不能保存 owner_face 和高维元数据，我们可以利用 confirmBvid 或者
    // 直接走 importBiliVideos。其实 importBiliVideos 可以自动下载默认状态的视频信息
    // 为了防止 422, duration 必须强转为 int
    
    if (addVideoData.value.from_clipboard) {
        try {
            await systemApi.confirmBvid(
                addVideoData.value.bvid,
                collectionId,
                addVideoData.value.title,
                addVideoData.value.duration
            );
        } catch(err){}
    } else {
        await localApi.importBiliVideos(collectionId, [{
          bvid: addVideoData.value.bvid,
          title: addVideoData.value.title,
          owner: addVideoData.value.owner,
          pic: addVideoData.value.pic, // 使用原始B站图片URL，后端会自动代理
          duration: parseInt(addVideoData.value.duration) || 0  // 确保是整数
        }])
    }
    
    // 为了防止剪贴板立即又把它抓出来，手动通知后端忽略这个BV号
    try {
        await systemApi.dismissBvid(addVideoData.value.bvid);
    } catch(err){}
    
    store.showToast('视频已添加到媒体库', 'success')
    await store.fetchLocalVideos()
    await store.fetchLocalCollections()
  } catch (e) {
    console.error('添加视频失败:', e)
    store.showToast('添加视频失败', 'error')
  } finally {
    showAddVideoCollectionSelect.value = false
    addVideoData.value = null
  }
}

function handleVideoPreviewConfirm(selectedVideoInfo) {
  // 更新 addVideoData 为用户选中的分集信息（如果有）
  if (selectedVideoInfo) {
    addVideoData.value = selectedVideoInfo
  }
  // 关闭预览弹窗，打开媒体库选择弹窗
  showAddVideoPreview.value = false
  showAddVideoCollectionSelect.value = true
}

function handleVideoPreviewClose() {
  showAddVideoPreview.value = false
  addVideoData.value = null
}

function handleAddVideoCollectionSelectClose() {
  showAddVideoCollectionSelect.value = false
  // 不清理 addVideoData，以便用户可以重新打开选择
}

function openEditMetadata() {
  if (selectionCount.value !== 1) return
  const bvid = store.selectedBvids[0]
  const v = store.localVideos.find(i => i.bvid === bvid)
  if (!v) return

  openModal('edit_metadata', '编辑媒体信息', { title: v.title, owner: v.owner }, { bvid }, async (formData) => {
    try {
      store.showToast("正在保存信息...", "info")
      const reqData = new FormData()
      if (formData.title) reqData.append('title', formData.title)
      if (formData.owner) reqData.append('owner', formData.owner)
      if (formData.cover) reqData.append('cover', formData.cover)
      
      const res = await localApi.updateVideoMetadata(bvid, reqData)
      await store.fetchLocalVideos()
      
      // 同步更新播放队列和当前播放视频的内存状态
      store.playQueue.forEach(item => {
        if (item.bvid === bvid) {
          if (res.title) item.title = res.title
          if (res.owner) item.owner = res.owner
          if (res.pic) item.pic = res.pic
        }
      })
      if (store.currentVideo && store.currentVideo.bvid === bvid) {
          if (res.title) store.currentVideo.title = res.title
          if (res.owner) store.currentVideo.owner = res.owner
          if (res.pic) store.currentVideo.pic = res.pic
      }
      store._saveQueue()
      store.showToast("信息已保存", "success")
      store.selectedBvids = []
    } catch (e) {
      console.error(e)
      store.showToast("保存失败", "error")
    }
  })
}

function openModal(type, title, initVal, extra, onConfirm) {
  modalState.type = type
  modalState.title = title
  modalState.initialValue = initVal
  modalState.extraData = extra
  modalState.callback = onConfirm
  modalState.show = true
}

// --- 排序函数 ---
function applyTimeSort() {
  const list = [...store.localVideos]
  list.sort((a, b) => {
    const tA = new Date(a.added_at).getTime()
    const tB = new Date(b.added_at).getTime()
    return sortDesc.value ? tB - tA : tA - tB
  })
  store.localVideos = list
}

// 监听排序切换
watch(sortDesc, () => {
  applyTimeSort()
})

// --- 初始化 ---
onMounted(async () => {
  await store.fetchLocalCollections()
  await store.fetchLocalVideos()
  // 首次加载后执行初始排序
  applyTimeSort()
})

// --- 计算属性 ---
const filteredVideos = computed(() => {
  let list = [...(store.localVideos || [])]
  
  if (store.activeCollectionId === 'unclassified') {
    // 特殊处理：未分类的资源（没有任何 collection 且是本地导入的）
    list = list.filter(v => v.is_local && (!v.collections || v.collections.length === 0))
  } else if (store.activeCollectionId) {
    // 正常媒体夹过滤
    list = list.filter(v => v.collections?.some(c => c.id === store.activeCollectionId))
  } else {
    // “全部视频”视图：包含所有关联了媒体夹的视频，以及未关联的本地导入视频
    list = list.filter(v => (v.collections && v.collections.length > 0) || v.is_local)
  }
  
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    try {
      if (searchMode.value === 'regex') {
        const regex = new RegExp(q, 'i')
        list = list.filter(v => regex.test(v.title) || regex.test(v.owner))
      } else {
        list = list.filter(v => {
          const titleMatch = v.title.toLowerCase().includes(q)
          const ownerMatch = v.owner.toLowerCase().includes(q)
          const bvidMatch = v.bvid.toLowerCase().includes(q)
          if (searchMode.value === 'title') return titleMatch
          if (searchMode.value === 'upper') return ownerMatch
          if (searchMode.value === 'bvid') return bvidMatch
          return titleMatch || ownerMatch || bvidMatch
        })
      }
    } catch (e) { }
  }
  return list
})

const selectionCount = computed(() => store.selectedBvids.length)

const isAllSelected = computed(() => {
  return filteredVideos.value.length > 0 && filteredVideos.value.every(v => store.selectedBvids.includes(v.bvid))
})

const isAllCached = computed(() => {
  if (selectionCount.value === 0) return false
  const selected = store.localVideos.filter(v => store.selectedBvids.includes(v.bvid))
  return selected.every(v => v.download_status === 'completed')
})

// --- 业务逻辑 ---
function handleCardClick(event, bvid, index) {
  // 阻止默认行为以防选择文本
  if (event.shiftKey) event.preventDefault()

  if (event.shiftKey && lastSelectedIndex.value !== -1) {
    const start = Math.min(lastSelectedIndex.value, index)
    const end = Math.max(lastSelectedIndex.value, index)
    const rangeBvids = filteredVideos.value.slice(start, end + 1).map(v => v.bvid)
    
    const isAdding = !store.selectedBvids.includes(bvid)
    if (isAdding) {
      store.selectedBvids = Array.from(new Set([...store.selectedBvids, ...rangeBvids]))
    } else {
      store.selectedBvids = store.selectedBvids.filter(id => !rangeBvids.includes(id))
    }
  } else {
    const idx = store.selectedBvids.indexOf(bvid)
    if (idx > -1) {
      store.selectedBvids.splice(idx, 1)
    } else {
      store.selectedBvids.push(bvid)
    }
    lastSelectedIndex.value = index
  }
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

function toggleSelectAll() {
  if (isAllSelected.value) store.selectedBvids = []
  else store.selectedBvids = filteredVideos.value.map(v => v.bvid)
}

function handlePlay(video) {
  if (video.download_status !== 'completed') {
    openModal('confirm', '正在播放网络流', null, {
      message: '视频未缓存，是否在播放时自动加入下载队列？',
      confirmText: '缓存并播放',
      cancelText: '仅播放',
      requireConfirm: true
    }, (confirmed) => {
      if (confirmed !== null) {
        store.playVideo(video, confirmed === true)
      }
    })
  } else {
    store.playVideo(video)
  }
}

function playAllFiltered() {
  if (filteredVideos.value.length === 0) return
  const hasUncached = filteredVideos.value.some(v => v.download_status !== 'completed')
  if (hasUncached) {
    openModal('confirm', '正在播放网络流', null, {
      message: '列表包含未缓存视频，是否在播放时批量加入下载队列？',
      confirmText: '缓存并播放',
      cancelText: '仅播放',
      requireConfirm: true
    }, (confirmed) => {
      if (confirmed !== null) {
        store.playList(filteredVideos.value, 0, confirmed === true)
      }
    })
  } else {
    store.playList(filteredVideos.value)
  }
}

function handleBatchPlay() {
  const selected = store.localVideos.filter(v => store.selectedBvids.includes(v.bvid))
  if (selected.length > 0) {
    const hasUncached = selected.some(v => v.download_status !== 'completed')
    if (hasUncached) {
       openModal('confirm', '正在播放网络流', null, {
         message: '选中视频包含未缓存项，是否在播放时同步缓存？',
         confirmText: '缓存并播放',
         cancelText: '仅播放',
         requireConfirm: true
       }, (confirmed) => {
         if (confirmed !== null) {
           store.playList(selected, 0, confirmed === true)
           store.selectedBvids = []
         }
       })
    } else {
      store.playList(selected)
      store.selectedBvids = []
    }
  }
}

function handleAddToQueue(video) {
  if (video.download_status !== 'completed') {
    openModal('confirm', '加入播放队列', null, {
      message: '视频未缓存，是否在加入队列时同步下载？',
      confirmText: '缓存并加入',
      cancelText: '仅加入',
      requireConfirm: true
    }, (confirmed) => {
      if (confirmed !== null) {
        store.addToQueue(video, confirmed === true)
      }
    })
  } else {
    store.addToQueue(video)
  }
}

function handleBatchQueue() {
  const selected = store.localVideos.filter(v => store.selectedBvids.includes(v.bvid))
  if (selected.length > 0) {
    const hasUncached = selected.some(v => v.download_status !== 'completed')
    if (hasUncached) {
       openModal('confirm', '加入播放队列', null, {
         message: '选中视频包含未缓存项，是否在加入队列时同步缓存？',
         confirmText: '缓存并加入',
         cancelText: '仅加入',
         requireConfirm: true
       }, (confirmed) => {
         if (confirmed !== null) {
           store.addToQueueList(selected, confirmed === true)
           store.selectedBvids = []
         }
       })
    } else {
      store.addToQueueList(selected)
      store.selectedBvids = []
    }
  }
}

function openCreateCollection() {
  openModal('input', '创建新媒体夹', '', {}, async (name) => {
    if (!name) return
    const exists = store.localCollections.some(c => c.title === name)
    if (exists) {
      store.showToast("媒体夹名称已存在", "error")
      return
    }
    await localApi.createCollection(name)
    await store.fetchLocalCollections()
  })
}

async function deleteCollection(id) {
  openModal('confirm', '确定删除此媒体夹吗？', null, {}, (confirmed) => {
    if (confirmed) {
      localApi.deleteCollection(id).then(() => {
        store.fetchLocalCollections()
        if (store.activeCollectionId === id) store.activeCollectionId = null
        store.fetchLocalVideos()
      })
    }
  })
}

function openRenameCollection(id, oldName) {
  openModal('input', '重命名媒体夹', oldName, {}, async (name) => {
    if (!name || name === oldName) return
    const exists = store.localCollections.some(c => c.title === name)
    if (exists) {
      store.showToast("媒体夹名称已存在", "error")
      return
    }
    await localApi.renameCollection(id, name)
    await store.fetchLocalCollections()
  })
}

function openScoreModal() {
  if (selectionCount.value === 0) return
  let initScore = selectionCount.value === 1
    ? (store.localVideos.find(v => v.bvid === store.selectedBvids[0])?.score || 5.0) : 5.0
  openModal('score', '批量评分', initScore, {}, async (score) => {
    for (const bvid of store.selectedBvids) await store.updateVideoScore(bvid, score)
    store.selectedBvids = []
  })
}

function openTagModal() {
  if (selectionCount.value === 0) return

  const getUnionTags = () => {
    const selected = store.localVideos.filter(v => store.selectedBvids.includes(v.bvid))
    const tagMap = new Map()
    selected.forEach(v => {
      (v.tags || []).forEach(t => tagMap.set(t.id, t))
    })
    return Array.from(tagMap.values())
  }

  modalState.type = 'tags'
  modalState.title = selectionCount.value > 1 ? `批量管理标签 (${selectionCount.value})` : '标签管理'
  modalState.initialValue = ''
  modalState.extraData = { existingTags: getUnionTags() }
  modalState.callback = async (tagName) => {
    if (!tagName) return
    try {
      await localApi.batchAddTags({
        bvids: store.selectedBvids,
        tag_name: tagName,
        videos: [] // 本地库中视频已存在，无需额外元数据
      })
      await store.fetchLocalVideos()
      modalState.extraData.existingTags = getUnionTags()
      store.showToast("标签已更新", "success")
    } catch (e) {
      console.error("添加标签失败", e)
      store.showToast("更新标签失败", "error")
    }
  }
  modalState.show = true
}

async function handleBatchCopy(targetColId) {
  if (!targetColId) return
  for (const bvid of store.selectedBvids) {
    await localApi.addVideoToCollection(targetColId, bvid)
  }
  await store.fetchLocalVideos()
  store.selectedBvids = []
}

async function handleBatchMove(targetColId) {
  if (!targetColId) return
  // 如果目标就是当前，则跳过
  if (targetColId === store.activeCollectionId) return

  if (!store.activeCollectionId) {
    handleBatchCopy(targetColId); return
  }

  for (const bvid of store.selectedBvids) {
    await localApi.addVideoToCollection(targetColId, bvid)
    await localApi.removeVideoFromCollection(store.activeCollectionId, bvid)
  }
  await store.fetchLocalVideos()
  store.selectedBvids = []
}

async function handleBatchRemoveLink() {
  if (!store.activeCollectionId) return
  openModal('confirm', '从当前媒体夹移除选中视频？', null, {}, async (confirmed) => {
    if (confirmed) {
      for (const bvid of store.selectedBvids) {
        await localApi.removeVideoFromCollection(store.activeCollectionId, bvid)
      }
      await store.fetchLocalVideos()
      store.selectedBvids = []
    }
  })
}

async function handleBatchDelete() {
  const msg = store.activeCollectionId
    ? '危险：这将从所有媒体夹及硬盘中彻底删除文件！'
    : '确定要彻底删除选中的视频及物理文件吗？'
  openModal('confirm', msg, null, { isDanger: true }, async (confirmed) => {
    if (confirmed) {
      await store.batchDelete()
      store.selectedBvids = []
    }
  })
}

async function handleBatchCache() {
  let count = 0
  for (const bvid of store.selectedBvids) {
    const v = store.localVideos.find(i => i.bvid === bvid)
    if (v && v.download_status !== 'completed' && v.download_status !== 'pending') {
      try { await store.addToDownload(bvid); count++ } catch (e) { }
    }
  }
  if (count > 0) {
    store.showToast(`已成功添加 ${count} 个缓存任务`, "success")
  }
}

async function handleLocalImport(e) {
  const files = e.target.files
  if (!files || files.length === 0) return
  
  let successCount = 0
  let existsCount = 0
  let errorCount = 0

  store.showToast(`正在导入 ${files.length} 个本地资源并提取元数据...`, "info")

  for (let i = 0; i < files.length; i++) {
    const formData = new FormData()
    formData.append('file', files[i])

    try {
      const res = await localApi.importFile(formData, store.activeCollectionId)
      if (res.status === 'success') {
        successCount++
      } else if (res.status === 'exists') {
        existsCount++
      }
    } catch (e) {
      errorCount++
      console.error("导入失败", files[i].name, e)
    }
  }

  await store.fetchLocalVideos()
  
  let msg = `导入完成。成功: ${successCount} 个`
  if (existsCount > 0) msg += `，已跳过 ${existsCount} 个重复项`
  if (errorCount > 0) msg += `，失败: ${errorCount} 个 (请检查 FFmpeg)`
  
  store.showToast(msg, errorCount > 0 ? "error" : "success")
  
  e.target.value = ''
}

// --- 拖拽排序逻辑 ---
const dragOverColId = ref(null)
let dragStartColId = null

const dragOverBvid = ref(null)
const dragInsertPosition = ref(null) // 'before' | 'after'
let dragStartBvid = null

function onColDragStart(event, colId) {
  dragStartColId = colId
  event.dataTransfer.effectAllowed = 'move'
}

function onColDragOver(event, colId) {
  event.preventDefault()
  if (colId === dragStartColId) return
  dragOverColId.value = colId
}

async function onColDrop(event, targetColId) {
  event.preventDefault()
  const sourceId = dragStartColId
  const targetId = targetColId
  dragOverColId.value = null
  dragStartColId = null

  if (!sourceId || sourceId === targetId) return

  const newCollections = [...store.localCollections]
  const sourceIdx = newCollections.findIndex(c => c.id === sourceId)
  const targetIdx = newCollections.findIndex(c => c.id === targetId)

  if (sourceIdx !== -1 && targetIdx !== -1) {
    const [movedItem] = newCollections.splice(sourceIdx, 1)
    newCollections.splice(targetIdx, 0, movedItem)
    store.localCollections = newCollections
    
    // 向后端同步排序
    localApi.reorderCollections(newCollections.map(c => c.id))
  }
}

// 视频卡片拖拽逻辑
function onVideoDragStart(event, bvid) {
  dragStartBvid = bvid
  event.dataTransfer.effectAllowed = 'move'
  // 拖拽时如果未选中该视频，则将其设为选中
  if (!store.selectedBvids.includes(bvid)) {
    store.selectedBvids = [bvid]
  }
}

function onVideoDragOver(event, bvid, index) {
  event.preventDefault()
  if (bvid === dragStartBvid) return
  
  // 防御检查：如果目标在选中集合内，不显示插入线
  if (store.selectedBvids.includes(bvid)) {
    dragOverBvid.value = null
    dragInsertPosition.value = null
    return
  }
  
  // 计算鼠标相对于卡片的位置，判断插入到左边还是右边
  const card = event.currentTarget
  const rect = card.getBoundingClientRect()
  const mouseX = event.clientX
  const cardMiddle = rect.left + rect.width / 2
  
  dragOverBvid.value = bvid
  // 如果鼠标在卡片左半部分，分隔线显示在该卡片左侧（before）
  // 如果鼠标在卡片右半部分，分隔线显示在该卡片右侧（after）
  dragInsertPosition.value = mouseX < cardMiddle ? 'before' : 'after'
}

function onVideoDrop(event, targetBvid, index) {
  event.preventDefault()
  const sourceBvid = dragStartBvid
  const targetIdFinal = targetBvid
  const insertPos = dragInsertPosition.value
  
  dragOverBvid.value = null
  dragInsertPosition.value = null
  dragStartBvid = null

  if (!sourceBvid || sourceBvid === targetIdFinal) return

  // 防御检查：如果放置目标处于当前选中的多选集合内，则视为原地无效拖放，避免数组塌陷
  if (store.selectedBvids.includes(targetIdFinal)) {
    console.warn('拖拽目标位于选中集合内，忽略此次拖放操作')
    return
  }

  // 这里的逻辑是实现"插入"：将所有选中的视频移动到目标位置
  const newVideos = [...store.localVideos]
  
  // 1. 获取选中的所有视频对象
  const movingVideos = newVideos.filter(v => store.selectedBvids.includes(v.bvid))
  
  // 2. 从原数组中移除这些视频
  const resultVideos = newVideos.filter(v => !store.selectedBvids.includes(v.bvid))
  
  // 3. 找到目标位置
  let targetIdx = resultVideos.findIndex(v => v.bvid === targetIdFinal)
  
  // 4. 根据插入位置（before/after）调整索引
  if (targetIdx !== -1) {
    if (insertPos === 'after') {
      targetIdx += 1
    }
    resultVideos.splice(targetIdx, 0, ...movingVideos)
  } else {
    // 如果没有找到目标位置（理论上不会走到这里，加一层兜底），则追加到末尾
    console.warn('未找到拖拽目标位置，将选中项追加到末尾')
    resultVideos.push(...movingVideos)
  }
  
  store.localVideos = resultVideos
  // 向后端同步排序
  localApi.reorderVideos(resultVideos.map(v => v.bvid))
}

// 处理拖拽到空白区域（最末尾）
function onGridDragOver(event) {
  event.preventDefault()
  // 如果不在任何卡片上，设置为在最后一个视频之后插入
  if (!dragOverBvid.value && filteredVideos.value.length > 0) {
    const lastVideo = filteredVideos.value[filteredVideos.value.length - 1]
    dragOverBvid.value = lastVideo.bvid
    dragInsertPosition.value = 'after'
  }
}

function onGridDrop(event) {
  event.preventDefault()
  if (dragOverBvid.value && filteredVideos.value.length > 0) {
    const lastVideo = filteredVideos.value[filteredVideos.value.length - 1]
    onVideoDrop(event, lastVideo.bvid, filteredVideos.value.length - 1)
  }
}

// 计算拖拽分隔线的位置（竖向分隔线）
function getDropLineStyle() {
  if (!dragOverBvid.value) return {}
  
  // 查找目标卡片的 DOM 元素
  const targetCard = document.querySelector(`[data-video-bvid="${dragOverBvid.value}"]`)
  if (!targetCard) return {}
  
  const rect = targetCard.getBoundingClientRect()
  
  let top, left, height
  
  if (dragInsertPosition.value === 'before') {
    // 鼠标在卡片左半部分，分隔线显示在该卡片左侧
    // gap-4 = 16px (1rem), 分隔线居中在间隙中 = -12px
    left = rect.left - 12
  } else {
    // 鼠标在卡片右半部分，分隔线显示在该卡片右侧
    // gap-4 = 16px (1rem), 分隔线居中在间隙中 = +12px
    left = rect.right + 12
  }
  
  top = rect.top
  height = rect.height
  
  return {
    top: `${top}px`,
    left: `${left}px`,
    height: `${height}px`,
    width: '4px'
  }
}

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

// 右键菜单项
const contextMenuItems = computed(() => {
  if (!contextMenu.video) return []
  
  const video = contextMenu.video
  const isCached = video.download_status === 'completed'
  const isLocal = video.is_local === 1
  
  const items = [
    {
      label: '播放',
      icon: PlayIcon,
      action: () => handlePlay(video)
    },
    {
      label: '添加到播放队列',
      icon: QueueListIcon,
      action: () => handleAddToQueue(video)
    },
    {
      type: 'divider'
    },
    {
      label: '编辑裁剪区间',
      icon: ScissorsIcon,
      action: () => openTrimEditor(video.bvid)
    },
    {
      label: '编辑媒体信息',
      icon: PencilSquareIcon,
      action: () => {
        store.selectedBvids = [video.bvid]
        openEditMetadata()
      }
    },
    {
      label: '管理标签',
      icon: TagIcon,
      action: () => {
        store.selectedBvids = [video.bvid]
        openTagModal()
      }
    },
    {
      label: '评分',
      icon: StarIcon,
      action: () => {
        store.selectedBvids = [video.bvid]
        openScoreModal()
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
  
  items.push(
    {
      type: 'divider'
    },
    {
      label: '从当前媒体库移除',
      icon: XCircleIcon,
      disabled: !store.activeCollectionId,
      action: () => {
        if (store.activeCollectionId) {
          store.selectedBvids = [video.bvid]
          handleBatchRemoveLink()
        }
      }
    },
    {
      label: '彻底删除',
      icon: TrashIcon,
      danger: true,
      action: () => {
        store.selectedBvids = [video.bvid]
        handleBatchDelete()
      }
    }
  )
  
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
  <div class="flex flex-col h-full animate-fade-in relative">
    <!-- 右键菜单 -->
    <ContextMenu
      :visible="contextMenu.visible"
      :x="contextMenu.x"
      :y="contextMenu.y"
      :items="contextMenuItems"
      @close="contextMenu.visible = false"
      @select="handleContextMenuSelect"
    />
    
    <!-- 全局进度条 -->
    <transition name="slide-down">
      <div v-if="store.activeDownloadCount > 0"
           class="mx-6 mt-4 p-4 bg-blue-600 rounded-2xl shadow-xl flex items-center gap-4 text-white z-20">
        <ArrowDownTrayIcon class="w-6 h-6 animate-bounce" />
        <div class="flex-1">
          <div class="flex justify-between text-[10px] font-black uppercase tracking-widest mb-1">
            <span>正在缓存 {{ store.activeDownloadCount }} 项</span>
            <span>{{ store.globalDownloadProgress.toFixed(1) }}%</span>
          </div>
          <div class="h-1 bg-white/20 rounded-full overflow-hidden">
            <div class="h-full bg-white transition-all duration-500" :style="{width: store.globalDownloadProgress + '%'}"></div>
          </div>
        </div>
        <button @click="store.cancelAllDownloads()" class="px-4 py-2 bg-red-500 hover:bg-red-600 text-white text-xs font-black rounded-xl transition-all active:scale-95 shadow-lg whitespace-nowrap">
          取消全部
        </button>
      </div>
    </transition>

    <div class="flex flex-1 gap-6 p-6 overflow-hidden">
      <!-- 左侧：媒体夹 -->
      <div class="w-48 lg:w-56 shrink-0 flex flex-col bg-white/50 dark:bg-gray-800/40 backdrop-blur-md rounded-[2rem] border border-gray-100 dark:border-white/5 overflow-hidden shadow-sm transition-all">
        <div class="p-4 lg:p-6 border-b border-gray-100 dark:border-white/5 flex justify-between items-center">
          <span class="text-xs lg:text-sm font-black text-gray-400 uppercase tracking-[0.2em]">媒体库</span>
          <button @click="openCreateCollection" class="p-1.5 bg-primary-500 text-white rounded-xl hover:scale-110 transition active:scale-95 shadow-lg shadow-primary-500/20">
            <PlusIcon class="w-4 h-4" />
          </button>
        </div>
        
        <!-- 新增：本地媒体导入按钮 -->
        <div class="px-4 lg:px-6 py-4 bg-gray-50 dark:bg-white/5 border-b border-gray-100 dark:border-white/5 space-y-2">
          <label class="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-gray-900 dark:bg-white text-white dark:text-black rounded-2xl text-[10px] font-black cursor-pointer hover:scale-[1.02] transition-transform shadow-md">
            <ArrowUpTrayIcon class="w-4 h-4" /> 导入本地资源
            <input type="file" class="hidden" accept="video/*,audio/*" multiple @change="handleLocalImport" />
          </label>
          <button @click="showAddVideoInput = true" class="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-primary-500 text-white rounded-2xl text-[10px] font-black hover:scale-[1.02] transition-transform shadow-md">
            <PlusIcon class="w-4 h-4" /> 添加 B 站视频
          </button>
        </div>

        <div class="flex-1 overflow-y-auto p-2 lg:p-4 space-y-1 scrollbar-none">
          <button @click="store.activeCollectionId = null"
                  :class="!store.activeCollectionId ? 'bg-primary-500 text-white shadow-xl shadow-primary-500/20' : 'text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-white/5'"
                  class="w-full text-left px-3 lg:px-5 py-3 lg:py-4 rounded-2xl text-xs lg:text-sm font-black transition-all flex items-center gap-2 lg:gap-3 shrink-0">
            <QueueListIcon class="w-5 h-5 shrink-0" /> 全部视频
          </button>

          <div v-for="col in store.localCollections" :key="col.id"
               class="group relative flex items-center"
               draggable="true"
               @dragstart="onColDragStart($event, col.id)"
               @dragover="onColDragOver($event, col.id)"
               @drop="onColDrop($event, col.id)"
               @dragend="dragOverColId = null">
            
            <!-- 拖拽提示条 -->
            <div v-if="dragOverColId === col.id"
                 class="absolute left-0 right-0 h-1 bg-primary-500 z-50 rounded-full shadow-[0_0_10px_rgba(236,72,153,0.5)] animate-pulse"
                 :class="store.localCollections.findIndex(c => c.id === dragStartColId) < store.localCollections.findIndex(c => c.id === col.id) ? '-bottom-0.5' : '-top-0.5'">
            </div>

            <button @click="store.activeCollectionId = col.id"
                    @contextmenu.prevent="col.type !== 'virtual' ? openRenameCollection(col.id, col.title) : null"
                    :class="store.activeCollectionId === col.id ? 'bg-primary-500 text-white shadow-xl shadow-primary-500/20' : 'text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-white/5'"
                    class="flex-1 text-left px-3 lg:px-5 py-3 lg:py-4 rounded-2xl text-xs lg:text-sm font-bold truncate transition-all flex items-center gap-2 lg:gap-3 pr-8 lg:pr-10">
              <div class="opacity-0 group-hover:opacity-40 transition-opacity shrink-0">
                <Bars3Icon class="w-3 h-3" />
              </div>
              <FolderOutline v-if="store.activeCollectionId !== col.id && col.type !== 'virtual'" class="w-5 h-5 shrink-0" />
              <FolderIcon v-if="store.activeCollectionId === col.id && col.type !== 'virtual'" class="w-5 h-5 shrink-0" />
              <ServerIcon v-if="col.type === 'virtual'" class="w-5 h-5 shrink-0" />
              <span class="truncate">{{ col.title }}</span>
            </button>
            <div class="absolute right-2 lg:right-3 opacity-0 group-hover:opacity-100 flex items-center gap-1 transition">
              <button v-if="col.type !== 'virtual'" @click.stop="openRenameCollection(col.id, col.title)"
                      class="p-1 text-gray-400 hover:text-blue-500 transition">
                <PencilSquareIcon class="w-4 h-4" />
              </button>
              <button v-if="col.type !== 'virtual'" @click.stop="deleteCollection(col.id)"
                      class="p-1 text-gray-400 hover:text-red-500 transition">
                <TrashIcon class="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧：主内容 -->
      <div class="flex-1 flex flex-col min-w-0">
        <!-- 工具栏 -->
        <div class="flex flex-col md:flex-row md:items-center justify-between mb-6 bg-white/50 dark:bg-gray-800/40 backdrop-blur-md p-3 rounded-[1.5rem] border border-gray-100 dark:border-white/5 shadow-sm min-h-[4.5rem] gap-3 relative z-30">
          <template v-if="selectionCount === 0">
            <div class="flex items-center gap-2 lg:gap-4 ml-2 shrink-0">
              <button @click="toggleSelectAll" class="flex items-center gap-2 text-xs font-black text-gray-400 hover:text-primary-500 transition uppercase tracking-widest active:scale-95">
                <div class="w-5 h-5 rounded-lg border-2 border-gray-200 dark:border-gray-700"></div>
                <span class="hidden sm:inline">全选</span>
              </button>
              <button @click="sortDesc = !sortDesc" class="p-2 bg-gray-50 dark:bg-white/5 rounded-xl text-gray-400 hover:text-primary-500 transition active:scale-95">
                <ArrowsUpDownIcon class="w-5 h-5" />
              </button>
            </div>
            
            <div class="flex-1 flex items-center gap-3 ml-2 lg:ml-4 min-w-0">
              <div class="relative flex-1 min-w-[50px] max-w-full md:max-w-xs xl:max-w-md transition-all">
                <MagnifyingGlassIcon class="w-4 h-4 absolute left-3.5 top-3 text-gray-400" />
                <input v-model="searchQuery" placeholder="高级搜索..."
                      class="w-full bg-gray-50 dark:bg-white/5 border-none rounded-2xl pl-10 pr-4 py-2.5 text-xs font-bold focus:ring-2 focus:ring-primary-500 uppercase truncate" />
              </div>
              
              <!-- 搜索选项：宽屏显示按钮，窄屏显示下拉 (断点上调至 1280px 以防拥挤) -->
              <div v-if="windowWidth >= 1280" class="flex bg-gray-50 dark:bg-white/5 p-1 rounded-xl shrink-0">
                <button v-for="opt in searchOptions" :key="opt.val"
                        @click="searchMode = opt.val"
                        :class="searchMode === opt.val ? 'bg-white dark:bg-gray-700 text-primary-500 shadow-sm' : 'text-gray-400 hover:text-gray-600'"
                        class="px-3 py-1.5 rounded-lg text-[10px] font-bold transition-all uppercase whitespace-nowrap relative group/tooltip"
                        :title="opt.val === 'regex' ? '支持JavaScript正则表达式语法，如 ^开头$ 结尾 .任意字符 .*任意内容 [abc]字符集 (a|b)或' : ''">
                  {{ opt.label }}
                  <div v-if="opt.val === 'regex'" class="absolute top-full left-1/2 -translate-x-1/2 mt-2 px-3 py-2 bg-gray-900 dark:bg-gray-800 text-white text-[10px] rounded-xl shadow-2xl border border-white/10 opacity-0 group-hover/tooltip:opacity-100 pointer-events-none transition-opacity duration-200 whitespace-nowrap z-50">
                    <div class="absolute bottom-full left-1/2 -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-b-4 border-transparent border-b-gray-900 dark:border-b-gray-800"></div>
                    <div class="font-black mb-1 text-primary-400">正则表达式帮助</div>
                    <div class="space-y-0.5 text-left">
                      <div><span class="text-yellow-400">^</span> 匹配开头 | <span class="text-yellow-400">$</span> 匹配结尾</div>
                      <div><span class="text-yellow-400">.</span> 任意字符 | <span class="text-yellow-400">.*</span> 任意内容</div>
                      <div><span class="text-yellow-400">[abc]</span> 字符集 | <span class="text-yellow-400">(a|b)</span> 或</div>
                    </div>
                  </div>
                </button>
              </div>
              <div v-else class="relative group z-50 shrink-0">
                 <button @click.stop="isSearchMenuOpen = !isSearchMenuOpen"
                         class="flex items-center gap-2 bg-gray-50 dark:bg-white/5 px-3 py-2.5 rounded-xl text-xs font-bold text-gray-600 dark:text-gray-300 hover:text-primary-500 transition whitespace-nowrap">
                   <span>{{ searchOptions.find(o => o.val === searchMode)?.label }}</span>
                 </button>
                 <div v-if="isSearchMenuOpen"
                      v-click-outside="() => isSearchMenuOpen = false"
                      class="absolute top-full right-0 mt-2 w-28 bg-white dark:bg-gray-800 rounded-xl shadow-xl border border-gray-100 dark:border-white/5 p-1 z-[100]">
                    <button v-for="opt in searchOptions" :key="opt.val"
                            @click="searchMode = opt.val; isSearchMenuOpen = false"
                            :class="searchMode === opt.val ? 'text-primary-500 bg-primary-50 dark:bg-white/5' : 'text-gray-500 hover:bg-gray-50 dark:hover:bg-white/5'"
                            class="w-full text-left px-3 py-2 rounded-lg text-xs font-bold transition-all whitespace-nowrap">
                      {{ opt.label }}
                    </button>
                 </div>
              </div>
            </div>

            <button @click="playAllFiltered" class="shrink-0 px-4 lg:px-6 py-2.5 bg-gray-900 dark:bg-white text-white dark:text-black rounded-2xl text-xs font-black hover:scale-105 active:scale-95 transition shadow-lg flex items-center gap-2 lg:ml-4 whitespace-nowrap">
              <PlayIcon class="w-4 h-4" /> <span class="uppercase hidden xl:inline">播放全部</span><span class="xl:hidden">播放</span>
            </button>
          </template>

          <template v-else>
            <div class="flex-1 flex flex-wrap items-center gap-2 animate-fade-in ml-2 py-1">
               <span class="px-3 py-1.5 bg-primary-500 text-white rounded-xl text-[10px] font-black shadow-lg shadow-primary-500/20 whitespace-nowrap">已选 {{ selectionCount }}</span>
               
               <button @click="handleBatchPlay" class="btn-batch text-primary-600 bg-primary-50 hover:bg-primary-100 dark:bg-primary-500/10 dark:text-primary-400" title="播放">
                 <PlayIcon class="w-4 h-4 shrink-0" /> <span>播放</span>
               </button>

               <button @click="handleBatchQueue" class="btn-batch text-purple-600 bg-purple-50 hover:bg-purple-100 dark:bg-purple-500/10 dark:text-purple-400" title="队列">
                 <PlusIcon class="w-4 h-4 shrink-0" /> <span>队列</span>
               </button>
               
               <button @click="handleBatchCache" :disabled="isAllCached" class="btn-batch text-blue-600 bg-blue-50 hover:bg-blue-100 dark:bg-blue-500/10 dark:text-blue-400 disabled:opacity-30" title="缓存">
                 <ArrowDownTrayIcon class="w-4 h-4 shrink-0" /> <span>{{ isAllCached ? '已缓存' : '缓存' }}</span>
               </button>
               
               <button @click="openScoreModal" class="btn-batch text-yellow-600 bg-yellow-50 hover:bg-yellow-100 dark:bg-yellow-500/10 dark:text-yellow-400" title="评分">
                 <StarIcon class="w-4 h-4 shrink-0" /> <span>评分</span>
               </button>
               
               <button @click="openTagModal" class="btn-batch text-purple-600 bg-purple-50 hover:bg-purple-100 dark:bg-purple-500/10 dark:text-purple-400" title="标签">
                 <TagIcon class="w-4 h-4 shrink-0" /> <span>标签</span>
               </button>
               
               <button v-if="selectionCount === 1" @click="openTrimEditor(store.selectedBvids[0])" class="btn-batch text-teal-600 bg-teal-50 hover:bg-teal-100 dark:bg-teal-500/10 dark:text-teal-400" title="裁剪">
                 <ScissorsIcon class="w-4 h-4 shrink-0" /> <span>裁剪</span>
               </button>
               
               <button v-if="selectionCount === 1" @click="openEditMetadata" class="btn-batch text-cyan-600 bg-cyan-50 hover:bg-cyan-100 dark:bg-cyan-500/10 dark:text-cyan-400" title="编辑信息">
                 <PencilSquareIcon class="w-4 h-4 shrink-0" /> <span>信息</span>
               </button>

               <!-- 管理按钮 -->
               <div class="relative">
                 <div v-if="isManageOpen" @click="isManageOpen = false" class="fixed inset-0 z-40"></div>
                 <button @click.stop="isManageOpen = !isManageOpen"
                         class="btn-batch text-gray-700 bg-gray-200 hover:bg-gray-300 dark:bg-white/20 dark:text-white relative z-50" title="管理">
                   <DocumentDuplicateIcon class="w-4 h-4 shrink-0" /> <span>管理</span>
                 </button>
                 
                 <transition name="fade">
                   <div v-if="isManageOpen"
                        class="absolute top-full left-0 mt-2 w-48 bg-white dark:bg-gray-900 rounded-[1.5rem] shadow-2xl border border-gray-100 dark:border-white/10 z-50 p-2 overflow-hidden">
                     <div class="px-3 py-2 text-[8px] font-black text-gray-400 uppercase tracking-widest border-b border-gray-100 dark:border-white/5 mb-1">复制到</div>
                     <div class="max-h-32 overflow-y-auto scrollbar-none">
                       <button v-for="c in store.localCollections" :key="'cp'+c.id"
                               @click="handleBatchCopy(c.id); isManageOpen = false"
                               :disabled="store.activeCollectionId === c.id"
                               :class="store.activeCollectionId === c.id ? 'opacity-30 cursor-not-allowed' : 'hover:bg-primary-50 dark:hover:bg-white/5'"
                               class="w-full text-left px-4 py-2 text-xs rounded-xl font-bold flex items-center gap-2 transition-colors">
                         <PlusIcon class="w-3 h-3"/> {{ c.title }}
                       </button>
                     </div>
                     <div class="px-3 py-2 text-[8px] font-black text-gray-400 uppercase tracking-widest border-b border-gray-100 dark:border-white/5 my-1">移动到</div>
                     <div class="max-h-32 overflow-y-auto scrollbar-none">
                       <button v-for="c in store.localCollections" :key="'mv'+c.id"
                               @click="handleBatchMove(c.id); isManageOpen = false"
                               :disabled="store.activeCollectionId === c.id"
                               :class="store.activeCollectionId === c.id ? 'opacity-30 cursor-not-allowed' : 'hover:bg-primary-50 dark:hover:bg-white/5'"
                               class="w-full text-left px-4 py-2 text-xs rounded-xl font-bold flex items-center gap-2 transition-colors">
                         <FolderArrowDownIcon class="w-3 h-3"/> {{ c.title }}
                       </button>
                     </div>
                   </div>
                 </transition>
               </div>

               <template v-if="store.activeCollectionId">
                 <button @click="handleBatchRemoveLink" class="btn-batch text-orange-600 bg-orange-50 hover:bg-orange-100 dark:bg-orange-500/10 dark:text-orange-400" title="移除">
                   <XCircleIcon class="w-4 h-4 shrink-0" /> <span>移除</span>
                 </button>
                 <button @click="handleBatchDelete" class="btn-batch text-red-600 bg-red-50 hover:bg-red-100 dark:bg-red-500/10 dark:text-red-400" title="删除文件">
                   <TrashIcon class="w-4 h-4 shrink-0" /> <span>删文件</span>
                 </button>
               </template>
               <template v-else>
                 <button @click="handleBatchDelete" class="btn-batch text-red-600 bg-red-50 hover:bg-red-100 dark:bg-red-500/10 dark:text-red-400" title="彻底删除">
                   <TrashIcon class="w-4 h-4 shrink-0" /> <span>彻底删除</span>
                 </button>
               </template>
               
               <button @click="store.selectedBvids = []" class="text-[10px] font-black text-gray-400 hover:text-primary-500 uppercase tracking-widest px-2 lg:px-4 active:scale-95 transition ml-auto">取消</button>
            </div>
          </template>
        </div>

        <!-- 视频网格 -->
        <div class="flex-1 overflow-y-auto pr-2 pb-24 scrollbar-thin relative">
          <!-- 拖拽分隔线覆盖层（竖向） -->
          <div v-if="dragOverBvid && dragInsertPosition"
               class="fixed pointer-events-none z-[100]"
               :style="getDropLineStyle()">
            <div class="w-full h-full bg-gradient-to-b from-transparent via-primary-500 to-transparent relative"
                 style="box-shadow: 0 0 20px rgba(236,72,153,1);">
              <div class="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-3 h-3 bg-white dark:bg-gray-900 rounded-full border-2 border-primary-500"></div>
            </div>
          </div>
          
          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-4 lg:gap-6 p-2"
               @dragover="onGridDragOver"
               @drop="onGridDrop">
            <div v-for="(v, index) in filteredVideos" :key="v.bvid"
                 @click="handleCardClick($event, v.bvid, index)"
                 @contextmenu="showContextMenu($event, v)"
                 draggable="true"
                 @dragstart="onVideoDragStart($event, v.bvid)"
                 @dragover="onVideoDragOver($event, v.bvid, index)"
                 @drop="onVideoDrop($event, v.bvid, index)"
                 @dragend="dragOverBvid = null; dragInsertPosition = null"
                 :data-video-bvid="v.bvid"
                 class="group flex flex-col bg-white dark:bg-white/5 rounded-[2rem] overflow-visible transition-all duration-200 cursor-pointer hover:shadow-2xl hover:-translate-y-1 box-border"
                   :class="[
                     store.selectedBvids.includes(v.bvid) ? 'ring-4 ring-primary-500 ring-offset-0 shadow-xl' : 'border border-gray-200 dark:border-white/5',
                     (v.download_status === 'downloading' || v.download_status === 'pending') ? 'bg-blue-50/50 dark:bg-blue-500/5 border-blue-200/50 dark:border-blue-500/20' : ''
                   ]">

              <div class="w-full aspect-video relative bg-gray-200 dark:bg-gray-900 overflow-hidden shrink-0 rounded-t-[2rem]">
              
              <!-- 封面图：处理本地音频可能没有封面的情况 -->
              <template v-if="v.pic && store.formatImg(v.pic)">
                <img :src="store.formatImg(v.pic, '640w_360h_1c_1s.webp')" @error="(e) => { if (e.target.src.indexOf('default-cover.svg') === -1) e.target.src = '/default-cover.svg' }" class="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110 rounded-t-[2rem]"
                     :class="{'opacity-40 blur-md': v.download_status === 'downloading'}"
                     style="image-rendering: auto; transform: translateZ(0); backface-visibility: hidden;" />
              </template>
              <div v-else class="w-full h-full bg-gray-900 flex items-center justify-center">
                <AudioIcon class="w-16 h-16 text-primary-500/20" />
              </div>
                
                <div v-if="v.download_status === 'downloading'" class="absolute inset-0 flex flex-col items-center justify-center p-6 bg-blue-600/10 backdrop-blur-sm">
                   <div class="text-2xl font-black text-blue-600 dark:text-blue-400 drop-shadow-sm">{{ v.progress?.toFixed(0) }}%</div>
                   <div class="w-full h-1 bg-black/10 dark:bg-white/10 rounded-full mt-3 overflow-hidden">
                     <div class="h-full bg-blue-500 transition-all duration-200" :style="{width: v.progress + '%'}"></div>
                   </div>
                   <button @click.stop="store.cancelDownload(v.bvid)" class="mt-3 px-3 py-1.5 bg-red-500/90 hover:bg-red-600 text-white text-xs font-black rounded-lg transition-all active:scale-95 shadow-lg">
                     取消下载
                   </button>
                </div>
                
                <div v-else-if="v.download_status === 'pending'" class="absolute inset-0 flex flex-col items-center justify-center bg-black/40">
                   <ArrowPathIcon class="w-8 h-8 text-white/50 animate-spin" />
                   <button @click.stop="store.cancelDownload(v.bvid)" class="mt-3 px-3 py-1.5 bg-red-500/90 hover:bg-red-600 text-white text-xs font-black rounded-lg transition-all active:scale-95 shadow-lg">
                     取消
                   </button>
                </div>
                
                <template v-else>
                   <div v-if="store.selectedBvids.includes(v.bvid)" class="absolute inset-0 bg-primary-500/20 flex items-center justify-center backdrop-blur-[2px] z-10">
                      <CheckCircleIcon class="w-12 h-12 text-white drop-shadow-lg" />
                   </div>
                   <div v-else class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity gap-2 z-10">
                      <button @click.stop="handlePlay(v)" class="w-12 h-12 bg-white/90 dark:bg-black/60 backdrop-blur-md rounded-full flex items-center justify-center text-primary-500 shadow-xl hover:scale-110 transition-all active:scale-90">
                        <PlayIcon class="w-6 h-6 ml-0.5" />
                      </button>
                      <button @click.stop="handleAddToQueue(v)" class="w-12 h-12 bg-white/90 dark:bg-black/60 backdrop-blur-md rounded-full flex items-center justify-center text-purple-500 shadow-xl hover:scale-110 transition-all active:scale-90">
                        <PlusIcon class="w-6 h-6" />
                      </button>
                   </div>
                </template>
                
                <div class="absolute bottom-2 right-2 px-2 py-0.5 bg-black/60 backdrop-blur-md rounded-lg text-[10px] text-yellow-400 font-bold border border-white/10 flex items-center gap-1">
                  <StarIcon class="w-3 h-3" /> {{ (v.score || 5).toFixed(1) }}
                </div>
              </div>

              <div class="p-5 flex flex-col flex-1 min-h-[110px]">
                <h3 class="text-sm font-bold text-gray-800 dark:text-gray-100 line-clamp-2 mb-2 leading-relaxed" :title="v.title">{{ v.title }}</h3>
                <div class="mt-auto flex justify-between items-end">
                  <div class="flex flex-wrap gap-1.5">
                    <template v-if="v.tags && v.tags.length > 0">
                      <span v-for="t in v.tags.slice(0, 5)" :key="t.id" class="px-2 py-0.5 bg-blue-500/10 text-blue-600 dark:text-blue-400 text-[8px] font-black rounded-md border border-blue-500/10 uppercase tracking-tighter hover:scale-110 transition-transform">#{{ t.name }}</span>
                    </template>
                    <span v-else class="text-[8px] font-black text-gray-300 dark:text-gray-600 uppercase tracking-widest">未分类</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <span v-if="v.is_local" class="text-[8px] font-black text-blue-500 bg-blue-500/10 px-2 py-1 rounded-lg border border-blue-500/10 uppercase tracking-tighter flex items-center gap-1">
                      <ServerIcon class="w-2.5 h-2.5" /> 物理
                    </span>
                    <span v-else-if="v.download_status === 'completed'" class="text-[8px] font-black text-green-500 bg-green-500/10 px-2 py-1 rounded-lg border border-green-500/10 uppercase tracking-tighter flex items-center gap-1">
                      <CheckCircleIcon class="w-2.5 h-2.5" /> 已存
                    </span>
                    <button v-else-if="v.download_status === 'failed'" @click.stop="store.addToDownload(v.bvid)" class="text-[8px] font-black text-red-500 uppercase tracking-tighter underline active:scale-95 transition">重试</button>
                    <button v-else @click.stop="store.addToDownload(v.bvid)" :disabled="v.download_status === 'pending' || v.download_status === 'downloading'" class="text-[8px] font-black text-gray-400 hover:text-blue-500 transition border border-current px-2 py-1 rounded-lg disabled:opacity-30 disabled:cursor-not-allowed active:scale-95">下载</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
          
          <div v-if="filteredVideos.length === 0" class="col-span-full py-40 text-center opacity-20">
            <QueueListIcon class="w-20 h-20 mx-auto mb-4" />
            <p class="font-black uppercase tracking-[0.3em]">暂无内容</p>
          </div>
        </div>
      </div>
    </div>

    <!-- 弹窗挂载 -->
    <UniversalModal
      :show="modalState.show" :type="modalState.type" :title="modalState.title"
      :initial-value="modalState.initialValue" :extra-data="modalState.extraData"
      @close="modalState.show = false"
      @confirm="(val) => modalState.callback && modalState.callback(val)"
      @remove-tag="async (tid) => {
        // 多选移除逻辑
        for (const bvid of store.selectedBvids) {
          try { await localApi.removeTagFromVideo(bvid, tid) } catch(e){}
        }
        await store.fetchLocalVideos()
        // 重新计算并集
        const selected = store.localVideos.filter(v => store.selectedBvids.includes(v.bvid))
        const tagMap = new Map()
        selected.forEach(v => {
          (v.tags || []).forEach(t => tagMap.set(t.id, t))
        })
        modalState.extraData.existingTags = Array.from(tagMap.values())
      }"
    >
      <template #confirm-icon>
        <ExclamationTriangleIcon v-if="modalState.extraData?.isDanger" class="w-12 h-12 text-red-500 mx-auto mb-4" />
      </template>
    </UniversalModal>
    
    <TrimEditor :show="showTrimEditor" :bvid="trimTargetBvid" @close="showTrimEditor = false" />
    
    <!-- 添加视频输入弹窗 -->
    <AddVideoInputModal
      :show="showAddVideoInput"
      @close="showAddVideoInput = false"
      @confirm="handleAddVideoInput" />
    
    <!-- 添加视频预览弹窗 -->
    <VideoPreviewModal
      :show="showAddVideoPreview"
      :video-info="addVideoData"
      modal-style="centered"
      @close="handleVideoPreviewClose"
      @confirm="handleVideoPreviewConfirm" />
    
    <!-- 添加视频媒体库选择弹窗 -->
    <CollectionSelectModal
      :show="showAddVideoCollectionSelect"
      :video-info="addVideoData"
      title="选择媒体库"
      @close="handleAddVideoCollectionSelectClose"
      @confirm="handleAddVideoCollectionSelect" />
  </div>
</template>

<style scoped>
.btn-batch {
  @apply flex items-center px-3 py-2 rounded-xl text-[10px] font-black transition-all whitespace-nowrap uppercase tracking-tighter shadow-sm hover:scale-105 active:scale-95;
}

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.scrollbar-thin::-webkit-scrollbar { width: 4px; }
.scrollbar-thin::-webkit-scrollbar-thumb { background: rgba(156, 163, 175, 0.2); border-radius: 10px; }
.scrollbar-none::-webkit-scrollbar { display: none; }

.fade-enter-active, .fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.slide-down-enter-active, .slide-down-leave-active { transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1); }
.slide-down-enter-from, .slide-down-leave-to { transform: translateY(-20px); opacity: 0; }

.group {
  user-select: none;
  -webkit-user-select: none;
}

.group img {
  pointer-events: none;
  -webkit-user-drag: none;
}
</style>
