<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { XMarkIcon, MinusIcon, StopIcon, Square2StackIcon } from '@heroicons/vue/24/outline'
import { useSettingsStore } from '../stores/modules/settings'
import { usePlayerStore } from '../stores/modules/player'

const settingsStore = useSettingsStore()
const playerStore = usePlayerStore()
const isMaximized = ref(false)
const isMouseIdle = ref(false)
let mouseTimer = null

let ipcRenderer = null
if (window.require) {
  ipcRenderer = window.require('electron').ipcRenderer
}

function resetMouseTimer() {
  isMouseIdle.value = false
  if (mouseTimer) clearTimeout(mouseTimer)
  mouseTimer = setTimeout(() => {
    isMouseIdle.value = true
  }, 3000) // 3秒无操作隐藏
}

onMounted(() => {
  if (ipcRenderer) {
    ipcRenderer.on('window-maximized', () => {
      isMaximized.value = true
    })
    ipcRenderer.on('window-unmaximized', () => {
      isMaximized.value = false
    })
  }
  
  window.addEventListener('mousemove', resetMouseTimer)
  window.addEventListener('click', resetMouseTimer)
  resetMouseTimer()
})

onUnmounted(() => {
  window.removeEventListener('mousemove', resetMouseTimer)
  window.removeEventListener('click', resetMouseTimer)
  if (mouseTimer) clearTimeout(mouseTimer)
})

function minimize() {
  if (ipcRenderer) ipcRenderer.send('window-minimize')
}

function toggleMaximize() {
  if (ipcRenderer) ipcRenderer.send('window-maximize')
}

function close() {
  if (ipcRenderer) ipcRenderer.send('window-close')
}
</script>

<template>
  <div v-if="!settingsStore.isMiniMode"
       class="h-8 w-full flex items-center justify-between bg-transparent absolute top-0 left-0 z-[100] select-none transition-opacity duration-500"
       :class="[
         isMouseIdle ? 'opacity-0 pointer-events-none' : 'opacity-100',
         !playerStore.isUiCollapsed ? 'pointer-events-none' : ''
       ]"
       :style="playerStore.isUiCollapsed ? { webkitAppRegion: 'drag' } : {}">
    <div class="flex items-center pl-4 h-full">
    </div>
    <div class="flex h-full pointer-events-auto" style="-webkit-app-region: no-drag;">
      <button @click="minimize" class="h-full px-4 hover:bg-gray-200 dark:hover:bg-white/10 text-gray-600 dark:text-gray-300 transition-colors flex items-center justify-center">
        <MinusIcon class="w-4 h-4" />
      </button>
      <button @click="toggleMaximize" class="h-full px-4 hover:bg-gray-200 dark:hover:bg-white/10 text-gray-600 dark:text-gray-300 transition-colors flex items-center justify-center">
        <Square2StackIcon v-if="isMaximized" class="w-4 h-4" />
        <StopIcon v-else class="w-4 h-4" />
      </button>
      <button @click="close" class="h-full px-4 hover:bg-red-500 hover:text-white text-gray-600 dark:text-gray-300 transition-colors flex items-center justify-center">
        <XMarkIcon class="w-4 h-4" />
      </button>
    </div>
  </div>
</template>
