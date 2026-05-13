# -*- coding: utf-8 -*-
# Path: frontend/src/components/TrimEditor.vue

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { usePlayerStore } from '../stores/modules/player'
import { useSettingsStore } from '../stores/modules/settings'
import { PlayIcon, PauseIcon, ScissorsIcon, CheckIcon } from '@heroicons/vue/24/solid'

const props = defineProps({
  show: Boolean,
  bvid: String
})
const emit = defineEmits(['close'])

const store = usePlayerStore()
const settingsStore = useSettingsStore()
const videoRef = ref(null)
const isPlaying = ref(false)
const currentTime = ref(0)
const duration = ref(0)

const trimStart = ref(0)
const trimEnd = ref(0)

const videoUrl = computed(() => {
  if (!props.bvid) return ''
  const v = store.localVideos.find(i => i.bvid === props.bvid)
  if (v && v.download_status !== 'completed') {
    // 未缓存视频使用流媒体 API 预览
    return `http://127.0.0.1:12180/api/play/stream/${props.bvid}?quality=${settingsStore.settings.streamQuality}`
  }
  return `http://127.0.0.1:12180/downloads/${props.bvid}.mp4`
})

// 初始化加载
watch(() => props.show, async (val) => {
  if (val && props.bvid) {
    // 确保 DOM 渲染完成再设置音量
    await nextTick()
    if (videoRef.value) videoRef.value.volume = store.volume
    
    // 从 Store 中获取当前裁剪信息
    const v = store.localVideos.find(i => i.bvid === props.bvid)
    if (v) {
      trimStart.value = v.trim_start || 0
      trimEnd.value = v.trim_end || 0
    }
    // 暂停主播放器
    if (store.isPlaying) {
      store.audioElement.pause()
      store.isPlaying = false
    }
  }
})

// 实时同步音量
watch(() => store.volume, (val) => {
  if (videoRef.value) videoRef.value.volume = val
})

function onCanPlay() {
  // 备用机制：当视频就绪时再次强制同步音量
  if (videoRef.value) videoRef.value.volume = store.volume
}

function onTimeUpdate(e) {
  currentTime.value = e.target.currentTime
}
function onLoadedMetadata(e) {
  duration.value = e.target.duration
}
function togglePlay() {
  if (!videoRef.value) return
  if (isPlaying.value) videoRef.value.pause()
  else videoRef.value.play()
  isPlaying.value = !isPlaying.value
}
function setStart() { trimStart.value = currentTime.value }
function setEnd() { trimEnd.value = currentTime.value }
function clearTrim() { trimStart.value = 0; trimEnd.value = 0 }

function previewRange() {
  if (!videoRef.value) return
  // 同步主播放器音量
  videoRef.value.volume = store.volume
  videoRef.value.currentTime = trimStart.value
  videoRef.value.play()
  isPlaying.value = true
  
  // 简单的预览逻辑：播放到 End 暂停
  const stopAtEnd = () => {
    // 增加 videoRef.value 非空检查，防止组件销毁后事件触发报错
    if (!videoRef.value) return
    if (trimEnd.value > 0 && videoRef.value.currentTime >= trimEnd.value) {
      videoRef.value.pause()
      isPlaying.value = false
      videoRef.value.removeEventListener('timeupdate', stopAtEnd)
    }
  }
  videoRef.value.addEventListener('timeupdate', stopAtEnd)
}

async function save() {
  await store.updateVideoTrim(props.bvid, trimStart.value, trimEnd.value)
  emit('close')
}

// 格式化时间 mm:ss.ms
const fmt = (t) => {
  if (!t) return '0:00.0'
  const m = Math.floor(t / 60)
  const s = Math.floor(t % 60)
  const ms = Math.floor((t % 1) * 10)
  return `${m}:${s.toString().padStart(2,'0')}.${ms}`
}
</script>

<template>
  <div v-if="show" class="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fade-in" @click.self="emit('close')">
    <div class="bg-white dark:bg-gray-900 rounded-[2rem] shadow-2xl w-full max-w-2xl overflow-hidden border border-gray-200 dark:border-white/10 flex flex-col">
      <div class="p-6 border-b border-gray-100 dark:border-white/5 flex justify-between items-center">
        <h3 class="text-xl font-black text-gray-800 dark:text-white flex items-center gap-2">
          <ScissorsIcon class="w-6 h-6 text-pink-500" /> 设定播放区间
        </h3>
        <button @click="emit('close')" class="text-gray-400 hover:text-gray-600 dark:hover:text-white transition font-bold">关闭</button>
      </div>
      
      <div class="relative bg-black aspect-video group max-h-[50vh]">
        <video ref="videoRef" :src="videoUrl" class="w-full h-full object-contain"
               @timeupdate="onTimeUpdate" @loadedmetadata="onLoadedMetadata" @canplay="onCanPlay" @ended="isPlaying=false"></video>
        
        <!-- 控制层 -->
        <div class="absolute inset-0 flex items-center justify-center bg-black/20 opacity-0 group-hover:opacity-100 transition-opacity" @click="togglePlay">
          <PlayIcon v-if="!isPlaying" class="w-16 h-16 text-white/80 drop-shadow-lg" />
          <PauseIcon v-else class="w-16 h-16 text-white/80 drop-shadow-lg" />
        </div>
        
        <!-- 进度条 -->
        <div class="absolute bottom-0 left-0 right-0 h-10 bg-gradient-to-t from-black/80 to-transparent flex items-end px-4 pb-3">
          <div class="relative w-full h-1.5 bg-white/20 rounded-full">
            <div class="absolute h-full bg-pink-500 rounded-full" :style="{width: (currentTime/duration*100)+'%'}"></div>
            <!-- 区间标记 -->
            <div v-if="trimStart > 0" class="absolute top-0 bottom-0 bg-white/50 w-0.5 z-10" :style="{left: (trimStart/duration*100)+'%'}"></div>
            <div v-if="trimEnd > 0" class="absolute top-0 bottom-0 bg-white/50 w-0.5 z-10" :style="{left: (trimEnd/duration*100)+'%'}"></div>
            <input type="range" min="0" :max="duration" step="0.1" v-model="currentTime" 
                   @input="videoRef.currentTime = parseFloat($event.target.value)"
                   class="absolute inset-0 w-full opacity-0 cursor-pointer" />
          </div>
        </div>
        
        <div class="absolute top-4 right-4 bg-black/60 px-2 py-1 rounded-lg text-white font-mono text-xs">{{ fmt(currentTime) }} / {{ fmt(duration) }}</div>
      </div>

      <div class="p-6 space-y-6">
        <div class="flex items-center gap-4 justify-between bg-gray-50 dark:bg-white/5 p-4 rounded-2xl">
          <div class="text-center">
            <div class="text-[10px] text-gray-400 font-black uppercase tracking-widest mb-1">当前起点</div>
            <div class="text-xl font-bold font-mono text-green-500">{{ fmt(trimStart) }}</div>
          </div>
          <div class="flex-1 flex flex-col gap-2 px-4">
             <div class="flex gap-2">
               <button @click="setStart" class="flex-1 py-2 bg-gray-200 dark:bg-white/10 rounded-xl text-xs font-bold hover:bg-green-500 hover:text-white transition">设为起点 [</button>
               <button @click="setEnd" class="flex-1 py-2 bg-gray-200 dark:bg-white/10 rounded-xl text-xs font-bold hover:bg-red-500 hover:text-white transition">设为终点 ]</button>
             </div>
             <div class="flex gap-2">
               <button @click="previewRange" class="flex-1 py-2 border border-gray-200 dark:border-white/10 rounded-xl text-xs font-bold hover:bg-gray-100 dark:hover:bg-white/10 transition">预览区间</button>
               <button @click="clearTrim" class="flex-1 py-2 border border-gray-200 dark:border-white/10 rounded-xl text-xs font-bold hover:bg-gray-100 dark:hover:bg-white/10 transition text-gray-400">重置</button>
             </div>
          </div>
          <div class="text-center">
            <div class="text-[10px] text-gray-400 font-black uppercase tracking-widest mb-1">当前终点</div>
            <div class="text-xl font-bold font-mono text-red-500">{{ trimEnd > 0 ? fmt(trimEnd) : '末尾' }}</div>
          </div>
        </div>
        
        <button @click="save" class="w-full py-3 bg-pink-500 hover:bg-pink-600 text-white rounded-2xl font-bold shadow-lg shadow-pink-500/30 transition active:scale-95 flex items-center justify-center gap-2">
          <CheckIcon class="w-5 h-5" /> 保存配置
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.animate-fade-in { animation: fadeIn 0.2s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }
</style>
