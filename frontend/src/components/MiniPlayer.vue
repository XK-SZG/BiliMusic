# -*- coding: utf-8 -*-
# Path: frontend/src/components/MiniPlayer.vue

<script setup>
import { usePlayerStore } from '../stores/modules/player'
import { useSettingsStore } from '../stores/modules/settings'
import {
  PlayIcon,
  PauseIcon,
  BackwardIcon,
  ForwardIcon,
  ArrowsPointingOutIcon
} from '@heroicons/vue/24/solid'

const store = usePlayerStore()
const settingsStore = useSettingsStore()

function handleTogglePlay() {
  if (!store.audioElement || !store.currentVideo) return
  if (store.isPlaying) store.audioElement.pause()
  else store.audioElement.play().catch(() => {})
}
</script>

<template>
  <div class="fixed inset-0 z-[110] flex items-center bg-white/40 dark:bg-gray-900/40 backdrop-blur-[4px] border border-gray-200 dark:border-white/10 shadow-2xl overflow-hidden animate-fade-in group" style="-webkit-app-region: drag;">
    
    <!-- 封面图 -->
    <div class="w-20 h-20 shrink-0 relative overflow-hidden">
      <img v-if="store.currentVideo" :src="store.formatImg(store.currentVideo.pic, '320w_320h_1c_1s.webp')" @error="(e) => { if (e.target.src.indexOf('default-cover.svg') === -1) e.target.src = '/default-cover.svg' }" class="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110" style="image-rendering: auto; transform: translateZ(0); backface-visibility: hidden;" />
      <div v-else class="w-full h-full bg-gray-100 dark:bg-white/5 flex items-center justify-center">
        <div class="w-2 h-2 bg-primary-500 rounded-full animate-ping"></div>
      </div>
      <!-- 进度条叠加在底部 -->
      <div class="absolute bottom-0 left-0 right-0 h-1 bg-black/20">
        <div class="h-full bg-primary-500 transition-all duration-300" :style="{ width: (store.currentTime / store.duration * 100 || 0) + '%' }"></div>
      </div>
    </div>

    <!-- 信息与控制 -->
    <div class="flex-1 flex items-center justify-between px-4 min-w-0">
      <div class="flex flex-col justify-center min-w-0 flex-1 mr-4">
        <div class="font-bold text-sm truncate text-gray-800 dark:text-white" :title="store.currentVideo?.title">
          {{ store.currentVideo?.title || '未在播放' }}
        </div>
        <div class="text-[10px] font-bold text-gray-400 truncate uppercase tracking-tighter">
          {{ store.currentVideo?.owner || 'BiliMusic' }}
        </div>
      </div>

      <!-- 控制器 -->
      <div class="flex items-center gap-3 shrink-0" style="-webkit-app-region: no-drag;">
        <button @click="store.prev()" class="p-1.5 text-gray-400 hover:text-primary-500 transition-colors active:scale-90">
          <BackwardIcon class="w-5 h-5" />
        </button>
        
        <button @click="handleTogglePlay" 
                class="w-10 h-10 bg-primary-500 rounded-full text-white flex items-center justify-center hover:bg-primary-600 shadow-lg transform transition active:scale-95">
          <PauseIcon v-if="store.isPlaying" class="w-5 h-5" />
          <PlayIcon v-else class="w-5 h-5 ml-0.5" />
        </button>

        <button @click="store.next()" class="p-1.5 text-gray-400 hover:text-primary-500 transition-colors active:scale-90">
          <ForwardIcon class="w-5 h-5" />
        </button>

        <div class="w-px h-6 bg-gray-200 dark:bg-white/10 mx-1"></div>

        <button @click="settingsStore.toggleMiniMode()" class="p-1.5 text-gray-400 hover:text-primary-500 transition-colors active:scale-90" title="退出最小化">
          <ArrowsPointingOutIcon class="w-5 h-5" />
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.animate-fade-in { animation: fadeIn 0.3s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: scale(0.98); } to { opacity: 1; transform: scale(1); } }
</style>
