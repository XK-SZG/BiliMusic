# -*- coding: utf-8 -*-
# Path: frontend/src/components/AudioVisualizer.vue

<script setup>
import { ref, onMounted, onUnmounted, watch, reactive, computed } from 'vue'
import { usePlayerStore } from '../stores/modules/player'
import { useSettingsStore } from '../stores/modules/settings'
import { useThemeStore } from '../stores/modules/theme'

const store = usePlayerStore()
const settingsStore = useSettingsStore()
const themeStore = useThemeStore()

const canvasLeftRef = ref(null)
const canvasRightRef = ref(null)
// 新增：顶部 Canvas 引用 (仅在 double 模式下使用)
const canvasLeftTopRef = ref(null)
const canvasRightTopRef = ref(null)

let audioCtx = null
let analyser = null
let sourceNode = null
let animationFrameId = null
let prevHeights = []

// 动画状态管理
const layoutState = {
  width: window.innerWidth, // 当前渲染总宽度
  startX: 0 // 当前起始 X 坐标
}

const win = reactive({ width: window.innerWidth })
const handleResize = () => { win.width = window.innerWidth }

// 辅助：Hex 转 RGB
const hexToRgb = (hex) => {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
  return result ? `${parseInt(result[1], 16)}, ${parseInt(result[2], 16)}, ${parseInt(result[3], 16)}` : null
}

const themeColors = {
  pink:   { s: '255, 102, 153', e: '255, 140, 180' }, 
  purple: { s: '168, 85, 247', e: '192, 132, 252' }, 
  blue:   { s: '0, 135, 189', e: '50, 165, 210' }, 
  green:  { s: '34, 197, 94',  e: '74, 222, 128' }, 
  orange: { s: '249, 115, 22', e: '251, 146, 60' }, 
  red:    { s: '239, 68, 68',  e: '248, 113, 113' }   
}

const sidebarWidth = computed(() => win.width >= 1024 ? 224 : 80)

function initAudioContext() {
  if (audioCtx) return
  if (!store.audioElement) return
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext
    audioCtx = new AudioContext()
    analyser = audioCtx.createAnalyser()
    analyser.fftSize = 4096 
    analyser.smoothingTimeConstant = 0.85 
    sourceNode = audioCtx.createMediaElementSource(store.audioElement)
    sourceNode.connect(analyser)
    analyser.connect(audioCtx.destination)
  } catch (e) { console.warn("AudioContext fail", e) }
}

function draw() {
  // 1. 获取所有 Canvas 引用
  const canvasL = canvasLeftRef.value
  const canvasR = canvasRightRef.value
  const canvasLT = canvasLeftTopRef.value
  const canvasRT = canvasRightTopRef.value
  
  if (!canvasL || !canvasR) { animationFrameId = requestAnimationFrame(draw); return }

  const ctxL = canvasL.getContext('2d')
  const ctxR = canvasR.getContext('2d')
  
  // 安全获取顶部 Context
  let ctxLT = null, ctxRT = null
  if (settingsStore.settings.visPosition === 'double') {
    if (canvasLT) ctxLT = canvasLT.getContext('2d')
    if (canvasRT) ctxRT = canvasRT.getContext('2d')
  }

  // 尺寸同步
  const sidebarIsRight = settingsStore.settings.sidebarPosition === 'right'
  const totalWidth = window.innerWidth
  const sbW = sidebarWidth.value
  
  // 宽度逻辑：L 永远对应侧边栏宽度，R 永远对应主内容宽度
  const wL = sbW
  const wR = totalWidth - sbW
  const h = settingsStore.isMiniMode ? 80 : 128 

  const resize = (c, w, hVal) => { if(c && (c.width!==w || c.height!==hVal)) { c.width=w; c.height=hVal } }
  resize(canvasL, wL, h); resize(canvasR, wR, h)
  if (ctxLT) { resize(canvasLT, wL, h); resize(canvasRT, wR, h) }

  // 页面隐藏时暂停渲染逻辑以节省资源
  if (!analyser || document.hidden) { animationFrameId = requestAnimationFrame(draw); return }

  const bufferLength = analyser.frequencyBinCount
  const dataArray = new Uint8Array(bufferLength)
  analyser.getByteFrequencyData(dataArray)

  // 关键：清除所有画布
  ctxL.clearRect(0, 0, wL, h); ctxR.clearRect(0, 0, wR, h)
  if (ctxLT) { ctxLT.clearRect(0, 0, wL, h); ctxRT.clearRect(0, 0, wR, h) }

  const barCount = settingsStore.settings.visCount || 64
  if (prevHeights.length !== barCount) prevHeights = new Array(barCount).fill(0)

  // 动画插值
  const isImmersive = store.isUiCollapsed || settingsStore.isMiniMode
  let tW, tX

  if (isImmersive) { 
    tW = totalWidth; tX = 0 
  } else {
    if (sidebarIsRight) { tW = wR; tX = 0 } 
    else { tW = wR; tX = sbW }
  }

  layoutState.width += (tW - layoutState.width) * 0.1
  layoutState.startX += (tX - layoutState.startX) * 0.1
  if (Math.abs(tW - layoutState.width) < 0.5) layoutState.width = tW
  if (Math.abs(tX - layoutState.startX) < 0.5) layoutState.startX = tX

  const unitW = layoutState.width / barCount 
  
  // 采样步长计算
  const cutLow = settingsStore.settings.visCutoffLow || 0
  const cutHigh = settingsStore.settings.visCutoffHigh || 75 
  const realLow = Math.min(cutLow, cutHigh); const realHigh = Math.max(cutLow, cutHigh)
  const startBin = Math.floor(bufferLength * (realLow / 100))
  const endBin = Math.floor(bufferLength * (realHigh / 100))
  const validSpan = Math.max(1, endBin - startBin)
  const step = validSpan / barCount
  
  const getDataValue = (index) => {
    let sourceIdx = index
    const dir = settingsStore.settings.visDirection || 'forward'
    const center = barCount / 2
    
    if (dir === 'reverse') sourceIdx = barCount - 1 - index
    else if (dir === 'symmetric') sourceIdx = Math.abs(index - center) * 2
    else if (dir === 'reverse_symmetric') sourceIdx = Math.max(0, barCount - 1 - Math.abs(index - center) * 2)
    
    // 最小化模式增强：自动聚焦低中频段 (前 40%) 并提升灵敏度
    let finalStep = step
    if (settingsStore.isMiniMode) {
      finalStep = (validSpan * 0.4) / barCount
    }

    const dataIndex = Math.floor(startBin + sourceIdx * finalStep)
    const safeIndex = Math.min(dataArray.length - 1, Math.max(0, dataIndex))
    
    let s = settingsStore.settings.visSensitivity || 1.0
    if (settingsStore.isMiniMode) s *= 1.8 // 背景频谱倍增

    let rawVal = dataArray[safeIndex] * s
    const threshold = 180; const maxVal = 255
    if (rawVal > threshold) {
      const overflow = rawVal - threshold; const headroom = maxVal - threshold
      rawVal = threshold + headroom * Math.tanh(overflow / headroom)
    }
    return rawVal
  }
  
  // 颜色准备
  let colorStart = '255, 102, 153'; let colorEnd = '255, 140, 180'
  if (themeColors[settingsStore.settings.visColor]) {
    colorStart = themeColors[settingsStore.settings.visColor].s; colorEnd = themeColors[settingsStore.settings.visColor].e
  } else if (settingsStore.settings.visColor === 'custom') {
    const c1 = hexToRgb(settingsStore.settings.visColorCustom); const c2 = hexToRgb(settingsStore.settings.visColorCustomSec)
    if (c1) colorStart = c1; if (c2) colorEnd = c2; if (!c2 && c1) colorEnd = c1
  }

  // 物理计算
  const gravity = (settingsStore.settings.visGravity || 2.0) * 0.1
  const sensitivity = settingsStore.settings.visSensitivity || 1.0
  const dir = settingsStore.settings.visDirection || 'forward'
  const center = barCount / 2

  for (let i = 0; i < barCount; i++) {
    let sourceIdx = i
    if (dir === 'reverse') sourceIdx = barCount - 1 - i
    else if (dir === 'symmetric') sourceIdx = Math.abs(i - center) * 2
    else if (dir === 'reverse_symmetric') sourceIdx = Math.max(0, barCount - 1 - Math.abs(i - center) * 2)
    
    const dataIndex = Math.floor(startBin + sourceIdx * step)
    const safeIndex = Math.min(dataArray.length - 1, Math.max(0, dataIndex))
    
    let rawVal = dataArray[safeIndex] * sensitivity
    const threshold = 180; const maxVal = 255
    if (rawVal > threshold) {
      const overflow = rawVal - threshold; const headroom = maxVal - threshold
      rawVal = threshold + headroom * Math.tanh(overflow / headroom)
    }
    
    if (rawVal > prevHeights[i]) prevHeights[i] += (rawVal - prevHeights[i]) * 0.5 
    else prevHeights[i] -= (prevHeights[i] - rawVal) * gravity
  }

  // 绘制核心
  const heightLimit = settingsStore.settings.visHeightLimit || 0.8
  const gain = settingsStore.settings.visGain || 1.0
  const style = settingsStore.settings.visualizerStyle || 'bars'

  const drawZone = (ctx, zoneStart, zoneEnd, ctxOffset, isTopMode) => {
    if (!ctx) return
    
    // 渐变构建
    let g
    if (isTopMode) {
      g = ctx.createLinearGradient(0, 0, 0, h)
      g.addColorStop(0, `rgba(${colorStart}, 0.8)`) // 根部深
      g.addColorStop(0.7, `rgba(${colorStart}, 0.2)`) 
      g.addColorStop(1, `rgba(${colorEnd}, 0.9)`)   // 梢部亮
    } else {
      g = ctx.createLinearGradient(0, h, 0, 0)
      g.addColorStop(0, `rgba(${colorStart}, 0.8)`)
      g.addColorStop(0.7, `rgba(${colorStart}, 0.2)`)
      g.addColorStop(1, `rgba(${colorEnd}, 0.9)`)
    }
    
    ctx.fillStyle = g
    ctx.strokeStyle = `rgba(${colorEnd}, 0.9)`
    ctx.lineWidth = 2; ctx.lineCap = 'round'; ctx.lineJoin = 'round'

    if (style === 'bars') {
      const barWidth = unitW * 0.6; const gap = unitW * 0.4
      const radii = isTopMode ? [0, 0, 4, 4] : [4, 4, 0, 0]
      
      for (let i = 0; i < barCount; i++) {
        const xGlobal = layoutState.startX + i * unitW + gap / 2
        if (xGlobal + barWidth < zoneStart || xGlobal > zoneEnd) continue
        
        const bh = (prevHeights[i] / 255) * h * heightLimit * gain
        const y = isTopMode ? 0 : h - bh
        
        ctx.beginPath()
        ctx.roundRect(xGlobal - ctxOffset, y, barWidth, bh, radii)
        ctx.fill()
      }
    } else if (style === 'particles') {
      const radius = unitW * 0.3
      for (let i = 0; i < barCount; i++) {
        if (prevHeights[i] < 5) continue
        const xGlobal = layoutState.startX + i * unitW + unitW / 2
        if (xGlobal < zoneStart || xGlobal > zoneEnd) continue
        
        const bh = (prevHeights[i] / 255) * h * heightLimit * gain
        const y = isTopMode ? bh : h - bh
        
        ctx.beginPath()
        ctx.arc(xGlobal - ctxOffset, y, radius, 0, Math.PI * 2)
        ctx.fill()
      }
    } else {
      const points = []
      const anchorY = isTopMode ? 0 : h
      points.push({x: layoutState.startX - ctxOffset, y: anchorY})
      
      for(let i=0; i<barCount; i++) {
        const bh = (prevHeights[i] / 255) * h * heightLimit * gain
        const x = layoutState.startX + i * unitW + unitW / 2 - ctxOffset
        const y = isTopMode ? bh : h - bh
        points.push({x, y})
      }
      points.push({x: layoutState.startX + layoutState.width - ctxOffset, y: anchorY})

      if (points.length > 0) {
        ctx.beginPath()
        if (style === 'curve') {
          ctx.moveTo(points[0].x, points[0].y)
          for (let i = 0; i < points.length - 1; i++) {
            const pCurrent = points[i]; const pNext = points[i+1]
            const midX = (pCurrent.x + pNext.x) / 2; const midY = (pCurrent.y + pNext.y) / 2
            ctx.quadraticCurveTo(pCurrent.x, pCurrent.y, midX, midY)
          }
          ctx.lineTo(points[points.length-1].x, points[points.length-1].y)
        } else {
          ctx.moveTo(points[0].x, points[0].y)
          for (let p of points) ctx.lineTo(p.x, p.y)
        }
        ctx.stroke()
        ctx.lineTo(points[points.length-1].x, anchorY)
        ctx.lineTo(points[0].x, anchorY)
        ctx.closePath()
        ctx.fill()
      }
    }
  }

  // 分发绘制
  const pos = settingsStore.settings.visPosition || 'bottom'
  
  const performDraw = (isTop) => {
    if (!sidebarIsRight) {
      drawZone(ctxR, sbW, totalWidth, sbW, isTop)
      drawZone(ctxL, 0, sbW, 0, isTop)
      if (pos === 'double' && !settingsStore.isMiniMode) {
        if (ctxRT) drawZone(ctxRT, sbW, totalWidth, sbW, true)
        if (ctxLT) drawZone(ctxLT, 0, sbW, 0, true)
      }
    } else {
      drawZone(ctxR, 0, totalWidth - sbW, 0, isTop)
      drawZone(ctxL, totalWidth - sbW, totalWidth, totalWidth - sbW, isTop)
      if (pos === 'double' && !settingsStore.isMiniMode) {
        if (ctxRT) drawZone(ctxRT, 0, totalWidth - sbW, 0, true)
        if (ctxLT) drawZone(ctxLT, totalWidth - sbW, totalWidth, totalWidth - sbW, true)
      }
    }
  }

  if (pos === 'bottom' || pos === 'double') {
    performDraw(false)
  }
  
  if (pos === 'top' || pos === 'double') {
    if (pos === 'double') {
      if (!sidebarIsRight) {
        if (ctxRT) drawZone(ctxRT, sbW, totalWidth, sbW, true)
        if (ctxLT) drawZone(ctxLT, 0, sbW, 0, true)
      } else {
        if (ctxRT) drawZone(ctxRT, 0, totalWidth - sbW, 0, true)
        if (ctxLT) drawZone(ctxLT, totalWidth - sbW, totalWidth, totalWidth - sbW, true)
      }
    } else {
      performDraw(true)
    }
  }

  animationFrameId = requestAnimationFrame(draw)
}

watch(() => store.isPlaying, (p) => { if (p && !audioCtx) initAudioContext(); if (p && audioCtx?.state === 'suspended') audioCtx.resume() })
onMounted(() => { window.addEventListener('resize', handleResize); draw() })
onUnmounted(() => { window.removeEventListener('resize', handleResize); if (animationFrameId) cancelAnimationFrame(animationFrameId) })
</script>

<template>
  <div v-if="settingsStore.settings.visEnabled !== false">
    <!-- 侧边栏对应频谱 (左侧或右侧) -->
    <div class="fixed pointer-events-none transition-all duration-[600ms] ease-in-out"
         :class="[ 
           settingsStore.settings.sidebarPosition === 'right' ? 'right-0' : 'left-0',
           settingsStore.isMiniMode ? 'z-[105] h-20 bottom-0 filter blur-[2px] opacity-70' : 'z-0 h-32',
           !settingsStore.isMiniMode && store.isFullImmersive 
             ? (settingsStore.settings.visPosition === 'top' ? 'top-0' : 'bottom-0') 
             : (!settingsStore.isMiniMode ? (settingsStore.settings.visPosition === 'top' ? 'top-0' : 'bottom-20') : '')
         ]"
         :style="{ width: sidebarWidth + 'px' }">
      <canvas ref="canvasLeftRef" class="w-full h-full"></canvas>
    </div>

    <!-- 主视图对应频谱 (右侧或左侧) -->
    <div class="fixed pointer-events-none transition-all duration-[600ms] ease-in-out"
         :class="[ 
           settingsStore.settings.sidebarPosition === 'right' ? 'left-0' : 'right-0',
           settingsStore.isMiniMode ? 'z-[105] h-20 bottom-0 filter blur-[2px] opacity-70' : 'z-[25] h-32',
           !settingsStore.isMiniMode && store.isFullImmersive 
             ? (settingsStore.settings.visPosition === 'top' ? 'top-0' : 'bottom-0') 
             : (!settingsStore.isMiniMode ? (settingsStore.settings.visPosition === 'top' ? 'top-0' : 'bottom-20') : '')
         ]"
         :style="settingsStore.settings.sidebarPosition === 'right' ? { right: sidebarWidth + 'px' } : { left: sidebarWidth + 'px' }">
      <canvas ref="canvasRightRef" class="w-full h-full"></canvas>
    </div>

    <!-- 顶部双向模式专用 Canvas (侧边栏) -->
    <div v-if="settingsStore.settings.visPosition === 'double' && !settingsStore.isMiniMode"
         class="fixed z-0 pointer-events-none transition-all duration-[600ms] ease-in-out h-32 top-0"
         :class="settingsStore.settings.sidebarPosition === 'right' ? 'right-0' : 'left-0'"
         :style="{ width: sidebarWidth + 'px' }">
      <canvas ref="canvasLeftTopRef" class="w-full h-full"></canvas>
    </div>

    <!-- 顶部双向模式专用 Canvas (主视图) -->
    <div v-if="settingsStore.settings.visPosition === 'double' && !settingsStore.isMiniMode"
         class="fixed top-0 z-[25] pointer-events-none transition-all duration-[600ms] ease-in-out h-32"
         :class="settingsStore.settings.sidebarPosition === 'right' ? 'left-0' : 'right-0'"
         :style="settingsStore.settings.sidebarPosition === 'right' ? { right: sidebarWidth + 'px' } : { left: sidebarWidth + 'px' }">
      <canvas ref="canvasRightTopRef" class="w-full h-full"></canvas>
    </div>
  </div>
</template>
