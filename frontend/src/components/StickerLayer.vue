# -*- coding: utf-8 -*-
# Path: frontend/src/components/StickerLayer.vue

<script setup>
import { computed, ref, onUnmounted, reactive } from 'vue'
import { usePlayerStore } from '../stores/modules/player'
import { useSettingsStore } from '../stores/modules/settings'
import { useThemeStore } from '../stores/modules/theme'

const props = defineProps({
  target: {
    type: String,
    required: true,
    validator: (v) => ['uiBackground', 'sidebar', 'mainView', 'playerBar', 'immersive'].includes(v)
  }
})

const store = usePlayerStore()
const settingsStore = useSettingsStore()
const themeStore = useThemeStore()
const containerRef = ref(null)

// 重新定义 activeStickers 计算属性
const activeStickers = computed(() => {
  if (settingsStore.settings.stickersEnabled === false) return []
  return settingsStore.settings.stickers?.[props.target] || []
})

// 使用响应式对象记录加载状态
const loadedStatus = reactive({})

// 构造内联样式
const getStickerStyle = (s) => {
  const isLoaded = loadedStatus[s.url]
  return {
    position: 'absolute',
    left: `${s.x ?? 50}%`,
    top: `${s.y ?? 50}%`,
    width: `${s.width ?? 50}%`,
    // 如果已经加载过或者是编辑模式，直接显示；否则等待加载完成淡入
    opacity: (isLoaded || themeStore.isStickerEditMode) ? (s.opacity ?? 0.8) : 0, 
    transform: `translate(-50%, -50%) rotate(${s.rotate || 0}deg)`,
    pointerEvents: themeStore.isStickerEditMode ? 'auto' : 'none', 
    zIndex: themeStore.isStickerEditMode ? 100 : 10, 
    cursor: themeStore.isStickerEditMode ? 'move' : 'default',
    filter: themeStore.isStickerEditMode ? 'drop-shadow(0 0 10px rgba(236, 72, 153, 0.8))' : 'none',
    transition: 'opacity 0.4s ease-out, transform 0.1s linear'
  }
}

function onImageLoad(url) {
  loadedStatus[url] = true
}

// 拖拽逻辑
let currentDragId = null
let startMouseX = 0, startMouseY = 0
let startStickerX = 0, startStickerY = 0

function startDrag(e, s) {
  if (!themeStore.isStickerEditMode) return
  currentDragId = s.id
  startMouseX = e.clientX
  startMouseY = e.clientY
  startStickerX = s.x
  startStickerY = s.y
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
}

function onMouseMove(e) {
  if (!currentDragId || !containerRef.value) return
  const rect = containerRef.value.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) return
  
  const dx = e.clientX - startMouseX
  const dy = e.clientY - startMouseY
  
  let pctX = (dx / rect.width) * 100
  const pctY = (dy / rect.height) * 100

  // 若当前容器被镜像翻转，拖拽方向需反转以符合视觉直觉
  if (props.target === 'sidebar' && settingsStore.settings.sidebarPosition === 'right') {
    pctX = -pctX
  }
  
  // 直接修改 store 内的数据以实现实时预览，但不触发深层持久化
  const stickers = settingsStore.settings.stickers[props.target]
  const idx = stickers.findIndex(i => i.id === currentDragId)
  if (idx !== -1) {
    stickers[idx].x = parseFloat((startStickerX + pctX).toFixed(1))
    stickers[idx].y = parseFloat((startStickerY + pctY).toFixed(1))
  }
}

function onMouseUp() {
  currentDragId = null
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
  // 拖拽结束后，强制保存到 localStorage
  settingsStore.updateSettings({ stickers: settingsStore.settings.stickers })
}

// 滚轮逻辑：缩放与旋转
let wheelTimeout = null
function handleWheel(e, s) {
  if (!themeStore.isStickerEditMode) return
  
  const stickers = settingsStore.settings.stickers[props.target]
  const idx = stickers.findIndex(i => i.id === s.id)
  if (idx === -1) return
  
  if (e.shiftKey) {
    // 旋转
    let delta = e.deltaY > 0 ? 5 : -5
    if (props.target === 'sidebar' && settingsStore.settings.sidebarPosition === 'right') {
      delta = -delta // 容器翻转后，旋转视觉方向也需取反
    }
    stickers[idx].rotate += delta
  } else {
    // 缩放
    stickers[idx].width += e.deltaY > 0 ? -2 : 2
    if (stickers[idx].width < 5) stickers[idx].width = 5
  }
  
  if (wheelTimeout) clearTimeout(wheelTimeout)
  wheelTimeout = setTimeout(() => {
    settingsStore.updateSettings({ stickers: settingsStore.settings.stickers })
  }, 300)
}

onUnmounted(() => {
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
  if (wheelTimeout) clearTimeout(wheelTimeout)
})
</script>

<template>
  <div ref="containerRef" v-if="activeStickers.length > 0" 
       class="absolute inset-0 overflow-hidden pointer-events-none"
       :class="[
         themeStore.isStickerEditMode && themeStore.stickerEditingTarget === props.target 
           ? 'z-[99] ring-2 ring-primary-500/50 bg-primary-500/5 !pointer-events-auto' 
           : 'z-0'
       ]"
       :style="(props.target === 'sidebar' && settingsStore.settings.sidebarPosition === 'right') ? { transform: 'scaleX(-1)' } : {}">
    <img v-for="s in activeStickers" :key="s.id"
         :src="themeStore.stickerDataBundle[s.url] || (s.url.startsWith('http') ? s.url : `http://127.0.0.1:12243${s.url}`)"
         :style="getStickerStyle(s)"
         @load="onImageLoad(s.url)"
         @mousedown.stop.prevent="startDrag($event, s)"
         @wheel.stop.prevent="handleWheel($event, s)"
         class="object-contain max-w-none"
         :class="{ 'hover:scale-105 pointer-events-auto': themeStore.isStickerEditMode && themeStore.stickerEditingTarget === props.target }" />
  </div>
</template>
