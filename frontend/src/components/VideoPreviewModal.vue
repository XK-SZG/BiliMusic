<script setup>
import { ref, watch, computed, onMounted } from 'vue'
import { usePlayerStore } from '../stores/modules/player'
import { UserIcon, MusicalNoteIcon, SpeakerWaveIcon, SpeakerXMarkIcon, XMarkIcon, ChevronDownIcon } from '@heroicons/vue/24/solid'
import biliApi from '../api/bili'

const props = defineProps({
  show: {
    type: Boolean,
    default: false
  },
  videoInfo: {
    type: Object,
    default: null
  },
  modalStyle: {
    type: String,
    default: 'floating', // 'floating' (顶部浮窗) 或 'centered' (居中全局弹窗)
    validator: (value) => ['floating', 'centered'].includes(value)
  }
})

const emit = defineEmits(['close', 'confirm'])

const store = usePlayerStore()
const isHovering = ref(false)
const isVideoMuted = ref(true)
const videoRef = ref(null)
const videoParts = ref([])
const selectedPartIndex = ref(0)
const showPartsDropdown = ref(false)

// 计算当前选中的分集信息
const currentPart = computed(() => {
  if (videoParts.value.length === 0) return null
  return videoParts.value[selectedPartIndex.value]
})

// 计算当前显示的视频信息（如果有分集则使用分集信息）
const displayVideoInfo = computed(() => {
  if (!props.videoInfo) return null
  
  if (videoParts.value.length > 1 && currentPart.value) {
    // 多集视频，使用选中的分集信息
    const cleanBvid = props.videoInfo.clean_bvid || props.videoInfo.bvid.split('_p')[0]
    
    // 构造组合标题，保留主标题信息
    const baseTitle = props.videoInfo.title ? props.videoInfo.title.split(' - P')[0] : ''
    const partTitle = currentPart.value.title || currentPart.value.part || ''
    const finalTitle = baseTitle && partTitle ? `${baseTitle} - P${currentPart.value.page}: ${partTitle}` : (partTitle || baseTitle)
    
    return {
      ...props.videoInfo,
      bvid: `${cleanBvid}_p${currentPart.value.page}`, // 修复：使用规范的 bvid 格式而非不存在的 id 字段
      title: finalTitle,
      duration: currentPart.value.duration,
      is_part: true,
      part_num: currentPart.value.page,
      clean_bvid: cleanBvid
    }
  }
  
  return props.videoInfo
})

watch(() => props.show, async (newVal) => {
  if (!newVal) {
    isHovering.value = false
    isVideoMuted.value = true
    showPartsDropdown.value = false
  } else if (newVal && props.videoInfo) {
    // 弹窗打开时，获取分集信息
    await loadVideoParts()
  }
})

async function loadVideoParts() {
  if (!props.videoInfo) return
  
  try {
    const cleanBvid = props.videoInfo.clean_bvid || props.videoInfo.bvid.split('_p')[0]
    const res = await biliApi.getVideoParts(cleanBvid)
    
    if (res.parts && res.parts.length > 0) {
      videoParts.value = res.parts
      
      // 如果当前视频信息包含分集编号，自动选中对应分集
      if (props.videoInfo.is_part && props.videoInfo.part_num) {
        const partIndex = videoParts.value.findIndex(p => p.page === props.videoInfo.part_num)
        if (partIndex !== -1) {
          selectedPartIndex.value = partIndex
        }
      }
    } else {
      videoParts.value = []
    }
  } catch (e) {
    console.error('获取分集信息失败:', e)
    videoParts.value = []
  }
}

function selectPart(index) {
  selectedPartIndex.value = index
  showPartsDropdown.value = false
  // 重置视频预览状态
  isHovering.value = false
  isVideoMuted.value = true
  
}

function toggleMute() {
  isVideoMuted.value = !isVideoMuted.value
  if (videoRef.value) {
    videoRef.value.muted = isVideoMuted.value
    if (!isVideoMuted.value) {
      videoRef.value.volume = store.volume
    }
  }
}

function openVideoPage() {
  if (!displayVideoInfo.value) return
  const cleanBvid = displayVideoInfo.value.clean_bvid || displayVideoInfo.value.bvid.split('_p')[0]
  let url = `https://www.bilibili.com/video/${cleanBvid}`
  if (displayVideoInfo.value.is_part && displayVideoInfo.value.part_num) {
    url += `?p=${displayVideoInfo.value.part_num}`
  }
  if (window.require) {
    const { shell } = window.require('electron')
    shell.openExternal(url)
  } else {
    window.open(url, '_blank')
  }
}

function handleConfirm() {
  // 传递当前选中的分集信息
  emit('confirm', displayVideoInfo.value)
}

function handleClose() {
  emit('close')
}
</script>

<template>
  <transition name="toast-fade">
    <!-- 顶部浮窗式（剪贴板监听） -->
    <div v-if="show && videoInfo && modalStyle === 'floating'"
         class="fixed top-20 left-1/2 -translate-x-1/2 z-[300] rounded-2xl shadow-2xl backdrop-blur-md border bg-white/95 dark:bg-gray-900/95 border-primary-500 overflow-hidden w-[400px] max-w-[90vw]">
      <div class="relative group flex flex-col">
        
        <div class="relative group flex-shrink-0">
          <!-- 封面图 -->
          <div class="w-full aspect-video bg-gray-200 dark:bg-gray-800 relative overflow-hidden" @mouseenter="isHovering = true" @mouseleave="isHovering = false">
            <img v-if="displayVideoInfo.pic" :src="store.formatImg(displayVideoInfo.pic, '480w_270h_1c_1s.webp')"
                 @error="(e) => { if (e.target.src.indexOf('default-cover.svg') === -1) e.target.src = '/default-cover.svg' }"
                 class="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110"
                 style="image-rendering: auto; transform: translateZ(0); backface-visibility: hidden;" />
            <div v-else class="w-full h-full flex items-center justify-center">
              <MusicalNoteIcon class="w-16 h-16 text-gray-400" />
            </div>
          
          <!-- 视频预览 -->
          <transition name="fade">
            <div v-if="isHovering && displayVideoInfo.bvid" class="absolute inset-0 z-10 bg-black overflow-hidden">
              <video ref="videoRef"
                     :key="displayVideoInfo.bvid"
                     :src="`http://127.0.0.1:12243/api/play/stream/${displayVideoInfo.bvid}?quality=16`"
                     class="w-full h-full object-cover pointer-events-none select-none"
                     autoplay muted loop playsinline crossorigin="anonymous"></video>
              <div class="absolute inset-0 z-20 pointer-events-auto cursor-default bg-black/10"></div>
              
              <!-- 音量控制按钮 -->
              <button @click.stop="toggleMute"
                      class="absolute bottom-2 left-2 z-30 p-2 bg-black/60 backdrop-blur-md rounded-lg hover:bg-black/80 transition-colors active:scale-95">
                <SpeakerWaveIcon v-if="!isVideoMuted" class="w-5 h-5 text-white" />
                <SpeakerXMarkIcon v-else class="w-5 h-5 text-white" />
              </button>
            </div>
          </transition>

          <!-- 时长标签 -->
          <div v-if="displayVideoInfo.duration" class="absolute bottom-2 right-2 px-2 py-0.5 bg-black/60 backdrop-blur-md rounded-md text-[10px] text-white font-bold z-20">
            {{ Math.floor(displayVideoInfo.duration / 60) }}:{{ (displayVideoInfo.duration % 60).toString().padStart(2, '0') }}
          </div>
          
          <!-- 分集标识 -->
          <div v-if="displayVideoInfo.is_part" class="absolute top-2 left-2 px-2 py-0.5 bg-primary-500/90 backdrop-blur-md rounded-md text-[10px] text-white font-bold z-20">
            P{{ displayVideoInfo.part_num }}
          </div>
          </div>
        </div>
        
        <!-- 信息区域 -->
        <div class="p-4 flex flex-col gap-3">
          <!-- 分集选择器（如果有多集） -->
          <div v-if="videoParts.length > 1" class="relative" v-click-outside="() => showPartsDropdown = false">
            <button @click="showPartsDropdown = !showPartsDropdown" class="w-full flex items-center justify-between px-3 py-2 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-white/20 rounded-lg text-sm hover:bg-gray-200 dark:hover:bg-gray-700 transition">
              <span class="font-bold text-gray-800 dark:text-white">P{{ currentPart.page }}: {{ currentPart.title.split(': ')[1] || currentPart.title }}</span>
              <ChevronDownIcon class="w-4 h-4 text-gray-500 transition-transform" :class="{ 'rotate-180': showPartsDropdown }" />
            </button>
            
            <transition name="dropdown">
              <div v-if="showPartsDropdown" class="absolute top-full left-0 right-0 mt-1 bg-white dark:bg-gray-800 border border-gray-300 dark:border-white/20 rounded-lg shadow-xl max-h-60 overflow-y-auto z-50">
                <button
                  v-for="(part, index) in videoParts"
                  :key="part.id"
                  @click="selectPart(index)"
                  class="w-full flex items-center gap-2 px-3 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition"
                  :class="{ 'bg-primary-50 dark:bg-primary-500/10': index === selectedPartIndex }">
                  <div class="w-6 h-6 rounded bg-gray-200 dark:bg-gray-700 flex items-center justify-center shrink-0 text-xs font-bold" :class="{ 'bg-primary-500 text-white': index === selectedPartIndex }">
                    {{ part.page }}
                  </div>
                  <div class="flex-1 min-w-0">
                    <div class="font-bold text-gray-800 dark:text-white truncate">{{ part.title.split(': ')[1] || part.title }}</div>
                    <div class="text-xs text-gray-500">{{ Math.floor(part.duration / 60) }}:{{ (part.duration % 60).toString().padStart(2, '0') }}</div>
                  </div>
                </button>
              </div>
            </transition>
          </div>
          
          <div class="flex items-start gap-3">
            <div @click="openVideoPage" class="w-10 h-10 rounded-full bg-gray-200 dark:bg-gray-800 flex items-center justify-center shrink-0 overflow-hidden border border-gray-200 dark:border-white/10 cursor-pointer hover:ring-2 hover:ring-primary-500 transition-all">
              <img v-if="displayVideoInfo.owner_face" :src="store.formatImg(displayVideoInfo.owner_face, '128w_128h_1c_1s.webp')" @error="(e) => e.target.style.display='none'" class="w-full h-full object-cover" />
              <UserIcon v-else class="w-6 h-6 text-gray-400" />
            </div>
            <div class="flex-1 min-w-0">
              <div @click="openVideoPage" class="text-sm font-black text-gray-800 dark:text-white line-clamp-2 leading-relaxed cursor-pointer hover:text-primary-500 transition-colors" :title="displayVideoInfo.title">
                {{ displayVideoInfo.title }}
              </div>
              <div @click="openVideoPage" class="text-xs text-gray-500 dark:text-gray-400 mt-1 cursor-pointer hover:text-primary-500 transition-colors">@{{ displayVideoInfo.owner }}</div>
              <div class="text-[10px] text-gray-400 dark:text-gray-500 font-mono mt-1">{{ displayVideoInfo.bvid }}</div>
            </div>
          </div>
          
          <div class="text-xs text-gray-600 dark:text-gray-300 font-medium">确认将此视频添加到媒体库？</div>
          
          <div class="flex gap-2">
            <button @click="handleClose" class="flex-1 px-4 py-2.5 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-xl text-xs font-bold hover:bg-gray-300 dark:hover:bg-gray-600 transition active:scale-95">忽略</button>
            <button @click="handleConfirm" class="flex-1 px-4 py-2.5 bg-primary-500 text-white rounded-xl text-xs font-bold hover:bg-primary-600 transition shadow-lg shadow-primary-500/30 active:scale-95">继续</button>
          </div>
        </div>
        
      </div>
    </div>
    
    <!-- 居中全局弹窗式（手动添加视频） -->
    <div v-else-if="show && videoInfo && modalStyle === 'centered'"
         class="fixed inset-0 z-[300] flex items-center justify-center p-4"
         @click.self="handleClose">
      <!-- 背景遮罩 -->
      <div class="absolute inset-0 bg-black/50 backdrop-blur-sm"></div>
      
      <!-- 弹窗内容 -->
      <div class="relative bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-white/10 w-full max-w-md overflow-hidden">
        <div class="relative group flex flex-col">
        
        <div class="relative group flex-shrink-0">
          <!-- 封面图 -->
          <div class="w-full aspect-video bg-gray-200 dark:bg-gray-800 relative overflow-hidden" @mouseenter="isHovering = true" @mouseleave="isHovering = false">
            <img v-if="displayVideoInfo.pic" :src="store.formatImg(displayVideoInfo.pic, '480w_270h_1c_1s.webp')"
                 @error="(e) => { if (e.target.src.indexOf('default-cover.svg') === -1) e.target.src = '/default-cover.svg' }"
                 class="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110"
                 style="image-rendering: auto; transform: translateZ(0); backface-visibility: hidden;" />
            <div v-else class="w-full h-full flex items-center justify-center">
              <MusicalNoteIcon class="w-16 h-16 text-gray-400" />
            </div>
          
          <!-- 视频预览 -->
          <transition name="fade">
            <div v-if="isHovering && displayVideoInfo.bvid" class="absolute inset-0 z-10 bg-black overflow-hidden">
              <video ref="videoRef"
                     :key="displayVideoInfo.bvid"
                     :src="`http://127.0.0.1:12243/api/play/stream/${displayVideoInfo.bvid}?quality=16`"
                     class="w-full h-full object-cover pointer-events-none select-none"
                     autoplay muted loop playsinline crossorigin="anonymous"></video>
              <div class="absolute inset-0 z-20 pointer-events-auto cursor-default bg-black/10"></div>
              
              <!-- 音量控制按钮 -->
              <button @click.stop="toggleMute"
                      class="absolute bottom-2 left-2 z-30 p-2 bg-black/60 backdrop-blur-md rounded-lg hover:bg-black/80 transition-colors active:scale-95">
                <SpeakerWaveIcon v-if="!isVideoMuted" class="w-5 h-5 text-white" />
                <SpeakerXMarkIcon v-else class="w-5 h-5 text-white" />
              </button>
            </div>
          </transition>

          <!-- 时长标签 -->
          <div v-if="displayVideoInfo.duration" class="absolute bottom-2 right-2 px-2 py-0.5 bg-black/60 backdrop-blur-md rounded-md text-[10px] text-white font-bold z-20">
            {{ Math.floor(displayVideoInfo.duration / 60) }}:{{ (displayVideoInfo.duration % 60).toString().padStart(2, '0') }}
          </div>
          
          <!-- 分集标识 -->
          <div v-if="displayVideoInfo.is_part" class="absolute top-2 left-2 px-2 py-0.5 bg-primary-500/90 backdrop-blur-md rounded-md text-[10px] text-white font-bold z-20">
            P{{ displayVideoInfo.part_num }}
          </div>
          </div>
        </div>
        
        <!-- 信息区域 -->
        <div class="p-4 flex flex-col gap-3">
          <!-- 分集选择器（如果有多集） -->
          <div v-if="videoParts.length > 1" class="relative" v-click-outside="() => showPartsDropdown = false">
            <button @click="showPartsDropdown = !showPartsDropdown" class="w-full flex items-center justify-between px-3 py-2 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-white/20 rounded-lg text-sm hover:bg-gray-200 dark:hover:bg-gray-700 transition">
              <span class="font-bold text-gray-800 dark:text-white">P{{ currentPart.page }}: {{ currentPart.title.split(': ')[1] || currentPart.title }}</span>
              <ChevronDownIcon class="w-4 h-4 text-gray-500 transition-transform" :class="{ 'rotate-180': showPartsDropdown }" />
            </button>
            
            <transition name="dropdown">
              <div v-if="showPartsDropdown" class="absolute top-full left-0 right-0 mt-1 bg-white dark:bg-gray-800 border border-gray-300 dark:border-white/20 rounded-lg shadow-xl max-h-60 overflow-y-auto z-50">
                <button
                  v-for="(part, index) in videoParts"
                  :key="part.id"
                  @click="selectPart(index)"
                  class="w-full flex items-center gap-2 px-3 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition"
                  :class="{ 'bg-primary-50 dark:bg-primary-500/10': index === selectedPartIndex }">
                  <div class="w-6 h-6 rounded bg-gray-200 dark:bg-gray-700 flex items-center justify-center shrink-0 text-xs font-bold" :class="{ 'bg-primary-500 text-white': index === selectedPartIndex }">
                    {{ part.page }}
                  </div>
                  <div class="flex-1 min-w-0">
                    <div class="font-bold text-gray-800 dark:text-white truncate">{{ part.title.split(': ')[1] || part.title }}</div>
                    <div class="text-xs text-gray-500">{{ Math.floor(part.duration / 60) }}:{{ (part.duration % 60).toString().padStart(2, '0') }}</div>
                  </div>
                </button>
              </div>
            </transition>
          </div>
          
          <div class="flex items-start gap-3">
            <div @click="openVideoPage" class="w-10 h-10 rounded-full bg-gray-200 dark:bg-gray-800 flex items-center justify-center shrink-0 overflow-hidden border border-gray-200 dark:border-white/10 cursor-pointer hover:ring-2 hover:ring-primary-500 transition-all">
              <img v-if="displayVideoInfo.owner_face" :src="store.formatImg(displayVideoInfo.owner_face, '128w_128h_1c_1s.webp')" @error="(e) => e.target.style.display='none'" class="w-full h-full object-cover" />
              <UserIcon v-else class="w-6 h-6 text-gray-400" />
            </div>
            <div class="flex-1 min-w-0">
              <div @click="openVideoPage" class="text-sm font-black text-gray-800 dark:text-white line-clamp-2 leading-relaxed cursor-pointer hover:text-primary-500 transition-colors" :title="displayVideoInfo.title">
                {{ displayVideoInfo.title }}
              </div>
              <div @click="openVideoPage" class="text-xs text-gray-500 dark:text-gray-400 mt-1 cursor-pointer hover:text-primary-500 transition-colors">@{{ displayVideoInfo.owner }}</div>
              <div class="text-[10px] text-gray-400 dark:text-gray-500 font-mono mt-1">{{ displayVideoInfo.bvid }}</div>
            </div>
          </div>
          
          <div class="text-xs text-gray-600 dark:text-gray-300 font-medium">确认将此视频添加到媒体库？</div>
          
          <div class="flex gap-2">
            <button @click="handleClose" class="flex-1 px-4 py-2.5 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-xl text-xs font-bold hover:bg-gray-300 dark:hover:bg-gray-600 transition active:scale-95">取消</button>
            <button @click="handleConfirm" class="flex-1 px-4 py-2.5 bg-primary-500 text-white rounded-xl text-xs font-bold hover:bg-primary-600 transition shadow-lg shadow-primary-500/30 active:scale-95">继续</button>
          </div>
        </div>
        
      </div>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.toast-fade-enter-active, .toast-fade-leave-active { transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
.toast-fade-enter-from { opacity: 0; transform: translate(-50%, -20px) scale(0.9); }
.toast-fade-leave-to { opacity: 0; transform: translate(-50%, -20px) scale(0.9); }

.fade-enter-active, .fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.dropdown-enter-active, .dropdown-leave-active {
  transition: all 0.2s ease;
}

.dropdown-enter-from, .dropdown-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}
</style>
