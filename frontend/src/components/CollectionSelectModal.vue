<script setup>
import { ref, computed, onMounted } from 'vue'
import { usePlayerStore } from '../stores/modules/player'
import { FolderIcon, PlusIcon, XMarkIcon } from '@heroicons/vue/24/solid'

const props = defineProps({
  show: {
    type: Boolean,
    default: false
  },
  title: {
    type: String,
    default: '选择媒体库'
  },
  videoInfo: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['close', 'confirm'])

const store = usePlayerStore()
const selectedCollectionId = ref(null)
const showCreateNew = ref(false)
const newCollectionName = ref('')

onMounted(async () => {
  if (store.localCollections.length === 0) {
    await store.fetchLocalCollections()
  }
})

function handleConfirm() {
  if (!selectedCollectionId.value) {
    store.showToast('请先选择一个本地媒体库', 'error')
    return
  }
  emit('confirm', selectedCollectionId.value)
}

function handleClose() {
  selectedCollectionId.value = null
  showCreateNew.value = false
  newCollectionName.value = ''
  emit('close')
}

async function handleCreateNew() {
  if (!newCollectionName.value.trim()) {
    store.showToast('请输入媒体库名称', 'error')
    return
  }
  
  try {
    const localApi = (await import('../api/local')).default
    // createCollection 只接受 title 参数
    await localApi.createCollection(newCollectionName.value.trim())
    
    await store.fetchLocalCollections()
    
    // 自动选中新建的媒体库
    const newCol = store.localCollections.find(c => c.title === newCollectionName.value.trim())
    if (newCol) {
      selectedCollectionId.value = newCol.id
    }
    
    showCreateNew.value = false
    newCollectionName.value = ''
    store.showToast('媒体库创建成功', 'success')
  } catch (e) {
    console.error('创建媒体库失败:', e)
    store.showToast('创建媒体库失败', 'error')
  }
}

const localCollections = computed(() => {
  return store.localCollections.filter(c => c.type === 'local').map(col => {
    // 计算每个媒体库的视频数量
    const videoCount = store.localVideos.filter(v =>
      v.collections && v.collections.some(c => c.id === col.id)
    ).length
    return {
      ...col,
      videoCount
    }
  })
})
</script>

<template>
  <transition name="modal-fade">
    <div v-if="show" class="fixed inset-0 z-[300] flex items-center justify-center p-4" @click.self="handleClose">
      <!-- 背景遮罩 -->
      <div class="absolute inset-0 bg-black/50 backdrop-blur-sm"></div>
      
      <!-- 弹窗内容 -->
      <div class="relative bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-white/10 w-full max-w-md max-h-[80vh] flex flex-col overflow-hidden">
        <!-- 头部 -->
        <div class="flex items-center justify-between p-6 border-b border-gray-200 dark:border-white/10">
          <h3 class="text-lg font-black text-gray-800 dark:text-white">{{ title }}</h3>
          <button @click="handleClose" class="p-2 hover:bg-gray-100 dark:hover:bg-white/5 rounded-lg transition-colors">
            <XMarkIcon class="w-5 h-5 text-gray-500" />
          </button>
        </div>
        
        <!-- 视频信息（如果提供） -->
        <div v-if="videoInfo" class="p-4 bg-gray-50 dark:bg-white/5 border-b border-gray-200 dark:border-white/10">
          <div class="flex items-center gap-3">
            <img v-if="videoInfo.pic" :src="store.formatImg(videoInfo.pic, '160w_100h_1c_1s.webp')" @error="(e) => { if (e.target.src.indexOf('default-cover.svg') === -1) e.target.src = '/default-cover.svg' }" class="w-16 h-10 rounded object-cover" />
            <div class="flex-1 min-w-0">
              <div class="text-sm font-bold text-gray-800 dark:text-white truncate">{{ videoInfo.title }}</div>
              <div class="text-xs text-gray-500 dark:text-gray-400 truncate">@{{ videoInfo.owner }}</div>
            </div>
          </div>
        </div>
        
        <!-- 媒体库列表 -->
        <div class="flex-1 overflow-y-auto p-4">
          <div v-if="localCollections.length === 0" class="text-center py-8 text-gray-400">
            <FolderIcon class="w-12 h-12 mx-auto mb-2 opacity-50" />
            <p class="text-sm">暂无本地媒体库</p>
            <p class="text-xs mt-1">点击下方按钮创建</p>
          </div>
          
          <div v-else class="space-y-2">
            <button
              v-for="col in localCollections"
              :key="col.id"
              @click="selectedCollectionId = col.id"
              class="w-full flex items-center gap-3 p-3 rounded-xl border-2 transition-all text-left"
              :class="selectedCollectionId === col.id 
                ? 'border-primary-500 bg-primary-50 dark:bg-primary-500/10' 
                : 'border-gray-200 dark:border-white/10 hover:border-primary-300 dark:hover:border-primary-500/50'">
              <div class="w-10 h-10 rounded-lg bg-primary-100 dark:bg-primary-500/20 flex items-center justify-center shrink-0">
                <FolderIcon class="w-6 h-6 text-primary-500" />
              </div>
              <div class="flex-1 min-w-0">
                <div class="font-bold text-sm text-gray-800 dark:text-white truncate">{{ col.title }}</div>
                <div class="text-xs text-gray-500 dark:text-gray-400">{{ col.videoCount || 0 }} 个视频</div>
              </div>
              <div v-if="selectedCollectionId === col.id" class="w-5 h-5 rounded-full bg-primary-500 flex items-center justify-center shrink-0">
                <svg class="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
                </svg>
              </div>
            </button>
          </div>
        </div>
        
        <!-- 新建媒体库区域 -->
        <div class="p-4 border-t border-gray-200 dark:border-white/10">
          <transition name="expand">
            <div v-if="showCreateNew" class="mb-3 space-y-2">
              <input
                v-model="newCollectionName"
                type="text"
                placeholder="输入媒体库名称"
                class="w-full px-3 py-2 bg-white dark:bg-gray-800 border border-gray-300 dark:border-white/20 rounded-lg text-sm text-gray-800 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary-500"
                @keyup.enter="handleCreateNew"
                @keyup.esc="showCreateNew = false" />
              <div class="flex gap-2">
                <button @click="handleCreateNew" class="flex-1 px-3 py-2 bg-primary-500 text-white rounded-lg text-xs font-bold hover:bg-primary-600 transition active:scale-95">
                  创建
                </button>
                <button @click="showCreateNew = false; newCollectionName = ''" class="px-3 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg text-xs font-bold hover:bg-gray-300 dark:hover:bg-gray-600 transition active:scale-95">
                  取消
                </button>
              </div>
            </div>
          </transition>
          
          <button
            v-if="!showCreateNew"
            @click="showCreateNew = true"
            class="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-gray-100 dark:bg-white/5 text-gray-700 dark:text-gray-300 rounded-xl text-sm font-bold hover:bg-gray-200 dark:hover:bg-white/10 transition active:scale-95">
            <PlusIcon class="w-5 h-5" />
            <span>新建本地媒体库</span>
          </button>
        </div>
        
        <!-- 底部按钮 -->
        <div class="flex gap-3 p-4 border-t border-gray-200 dark:border-white/10">
          <button @click="handleClose" class="flex-1 px-4 py-2.5 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-xl text-sm font-bold hover:bg-gray-300 dark:hover:bg-gray-600 transition active:scale-95">
            取消
          </button>
          <button @click="handleConfirm" class="flex-1 px-4 py-2.5 bg-primary-500 text-white rounded-xl text-sm font-bold hover:bg-primary-600 transition shadow-lg shadow-primary-500/30 active:scale-95">
            确认添加
          </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.modal-fade-enter-active, .modal-fade-leave-active {
  transition: opacity 0.3s ease;
}

.modal-fade-enter-active > div:last-child,
.modal-fade-leave-active > div:last-child {
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.modal-fade-enter-from, .modal-fade-leave-to {
  opacity: 0;
}

.modal-fade-enter-from > div:last-child,
.modal-fade-leave-to > div:last-child {
  transform: scale(0.95) translateY(20px);
}

.expand-enter-active, .expand-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}

.expand-enter-from, .expand-leave-to {
  opacity: 0;
  max-height: 0;
}

.expand-enter-to, .expand-leave-from {
  opacity: 1;
  max-height: 200px;
}
</style>
