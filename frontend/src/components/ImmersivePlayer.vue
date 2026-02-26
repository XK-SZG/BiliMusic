# -*- coding: utf-8 -*-
# Path: frontend/src/components/ImmersivePlayer.vue

<script setup>
import { ref, watch, computed, onMounted, onUnmounted, reactive } from 'vue'
import { usePlayerStore } from '../stores/modules/player'
import { useSettingsStore } from '../stores/modules/settings'
import { useThemeStore } from '../stores/modules/theme'
import { MusicalNoteIcon } from '@heroicons/vue/24/outline'
import StickerLayer from './StickerLayer.vue'
import ParticleEngine from './ParticleEngine.vue'
import { DARK_LOADING_ICON_FRAMES, LIGHT_LOADING_ICON_FRAMES } from '../assets/LoadingIconData'

const store = usePlayerStore()
const settingsStore = useSettingsStore()
const themeStore = useThemeStore()

// 判断是否为本地纯音频文件
const isAudioOnly = computed(() => {
  const v = store.currentVideo
  if (!v || !v.is_local || !v.local_path) return false
  const ext = v.local_path.split('.').pop().toLowerCase()
  return ['mp3', 'm4a', 'wav', 'flac', 'ogg'].includes(ext)
})

// --- 加载中自适应逻辑 ---
const isDarkBackground = ref(false)
const currentFrameIndex = ref(0)
let frameTimer = null

// 探测视频当前帧亮度
async function detectBrightness() {
  const video = store.audioElement
  if (!video) return

  // 1. 如果视频完全没初始化或没元数据，由于此时一定是黑屏，强制设为深色(白图标)
  if (video.readyState === 0 || video.videoWidth === 0) {
    isDarkBackground.value = true
    return
  }

  // 2. 尝试采样
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  canvas.width = 10
  canvas.height = 10

  try {
    const srcX = video.videoWidth * 0.4
    const srcY = video.videoHeight * 0.4
    const srcW = video.videoWidth * 0.2
    const srcH = video.videoHeight * 0.2
    
    // 即使 readyState < 2，只要有尺寸，也尝试抓取当前屏幕上显示的像素
    ctx.drawImage(video, srcX, srcY, srcW, srcH, 0, 0, 10, 10)
    
    const imageData = ctx.getImageData(0, 0, 10, 10).data
    let r = 0, g = 0, b = 0
    let hasContent = false
    
    for (let i = 0; i < imageData.length; i += 4) {
      r += imageData[i]; g += imageData[i + 1]; b += imageData[i + 2]
      if (imageData[i] > 0 || imageData[i+1] > 0 || imageData[i+2] > 0) hasContent = true
    }
    
    // 3. 核心改进：如果没有抓取到有效像素 (全黑/透明)
    if (!hasContent) {
      // 如果是视频刚开始播放 (currentTime 很近)，假定是黑屏
      if (video.currentTime < 1) {
        isDarkBackground.value = true
      }
      // 如果是播放中途跳转，抓不到像素可能是 GPU 忙，此时【保持现状】，不切换颜色
      return
    }

    const count = imageData.length / 4
    const luminance = (0.299 * (r/count) + 0.587 * (g/count) + 0.114 * (b/count))
    
    // 4. 只有抓到真实像素后，才更新状态
    isDarkBackground.value = luminance < 135
  } catch (e) {
    // 跨域错误等回退到安全色 (深色背景默认白图标)
    isDarkBackground.value = true
  }
}

watch(() => store.isBuffering, (buffering) => {
  console.log("[加载状态] Buffering 变化 ->", buffering);
  if (buffering) {
    // 延迟 100ms 检测，确保视频帧已在内存中
    setTimeout(detectBrightness, 100)
    
    if (frameTimer) clearInterval(frameTimer)
    frameTimer = setInterval(() => {
      currentFrameIndex.value = (currentFrameIndex.value + 1) % 5
      detectBrightness()
    }, 150)
  } else {
    clearInterval(frameTimer)
    currentFrameIndex.value = 0
  }
})

const LOADING_FRAMES = computed(() => {
  return isDarkBackground.value ? LIGHT_LOADING_ICON_FRAMES : DARK_LOADING_ICON_FRAMES
})

onUnmounted(() => {
  if (frameTimer) clearInterval(frameTimer)
})

// --- 动态动效逻辑 ---
const activeEffect = ref('')

// --- 几何与状态监控 ---
const windowSize = reactive({ w: window.innerWidth, h: window.innerHeight })
const isNativeFullscreen = ref(false)
const isHoveringVideo = ref(false)

const handleResize = () => { windowSize.w = window.innerWidth; windowSize.h = window.innerHeight }
const handleFsChange = () => { isNativeFullscreen.value = !!document.fullscreenElement }

// --- 鼠标指针控制 ---
const isMouseIdle = ref(false)
let mouseTimer = null

function resetMouseTimer() {
  isMouseIdle.value = false
  if (mouseTimer) clearTimeout(mouseTimer)
  const timeout = (settingsStore.settings.idleTimeout || 3) * 1000
  mouseTimer = setTimeout(() => {
    isMouseIdle.value = true
  }, timeout)
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
  document.addEventListener('fullscreenchange', handleFsChange)
  window.addEventListener('mousemove', resetMouseTimer)
  window.addEventListener('click', resetMouseTimer)
  resetMouseTimer()
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  document.removeEventListener('fullscreenchange', handleFsChange)
  window.removeEventListener('mousemove', resetMouseTimer)
  window.removeEventListener('click', resetMouseTimer)
  if (mouseTimer) clearTimeout(mouseTimer)
})

const criticalScale = computed(() => {
  const diagonal = Math.sqrt(Math.pow(windowSize.w, 2) + Math.pow(windowSize.h, 2))
  const minSide = Math.min(windowSize.w, windowSize.h)
  return (diagonal / minSide) * 1.02
})

watch(() => store.currentVideo?.bvid, () => {
  // 切歌时触发自定义背景轮换
  if (settingsStore.settings.bgType === 'custom') {
    themeStore.rotateCustomBackground()
  }

  const effects = settingsStore.settings.bgEffects || []
  if (effects.length > 0) activeEffect.value = effects[Math.floor(Math.random() * effects.length)]
  else activeEffect.value = ''
}, { immediate: true })

// 视频容器动态样式：恢复 transform 的独立过渡，避免影响基础布局
const videoContainerStyle = computed(() => {
  let scale = settingsStore.settings.videoScale || 1.0
  if (isHoveringVideo.value) scale *= 1.05
  return {
    transform: `scale(${scale})`,
    // 关键：仅针对 transform 设置过渡，且使用弹性曲线
    transition: 'transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)',
    willChange: 'transform'
  }
})

const bgImageStyle = computed(() => {
  let url = ''
  if (settingsStore.settings.bgType === 'custom' && themeStore.customBgUrl) {
    url = `http://127.0.0.1:12243${themeStore.customBgUrl}`
  } else {
    url = store.currentVideo ? store.formatImg(store.currentVideo.pic) : ''
  }
  
  return {
    backgroundImage: url ? `url(${url})` : 'none',
    opacity: settingsStore.settings.bgOpacity || 0.6
  }
})

const blurStyle = computed(() => ({
  filter: `blur(${settingsStore.settings.bgBlur}px)`,
  transition: 'filter 0.3s ease'
}))

// 背景动效动态样式
const bgEffectStyle = computed(() => ({
  ...bgImageStyle.value,
  '--critical-scale': criticalScale.value,
  '--anim-speed': `${10 / (settingsStore.settings.bgAnimationSpeed || 1.0)}s`,
  '--anim-amplitude': settingsStore.settings.bgAnimationAmplitude || 1.0,
  animationDuration: 'var(--anim-speed)'
}))

// --- 交互控制 ---
function toggleVideoFullScreen(e) {
  e.stopPropagation()
  if (!document.fullscreenElement) {
    const el = document.getElementById('video-mount-point')
    if (el) el.requestFullscreen().catch(() => {})
  } else {
    document.exitFullscreen()
  }
}

function toggleFullImmersive() {
  if (store.isUiCollapsed) {
    store.isFullImmersive = !store.isFullImmersive
  }
}
</script>

<template>
  <div class="absolute inset-0 z-0 overflow-hidden bg-black flex flex-col justify-center items-center select-none"
       :class="[
         store.isUiCollapsed ? 'cursor-default' : '',
         isMouseIdle && (store.isFullImmersive || isNativeFullscreen) ? 'cursor-none' : ''
       ]"
       @click="toggleFullImmersive">

    <!-- 背景渲染层 -->
    <div v-if="store.currentVideo" class="absolute inset-0 z-0" :style="blurStyle">
      <div class="absolute inset-0 bg-cover bg-center transition-opacity duration-1000"
           :class="[
             activeEffect === 'float' ? 'animate-bg-float' : '',
             activeEffect === 'ripple' ? 'animate-bg-ripple' : '',
             activeEffect === 'rotate' ? 'animate-bg-rotate' : '',
             activeEffect === 'drift' ? 'animate-bg-drift' : '',
             activeEffect === 'zoom' ? 'animate-bg-zoom' : '',
             activeEffect === 'glitch' ? 'animate-bg-glitch' : '',
             activeEffect === 'wave' ? 'animate-bg-wave' : '',
             activeEffect === 'pulse' ? 'animate-bg-pulse' : '',
             activeEffect === 'color' ? 'animate-bg-color' : ''
           ]"
           :style="bgEffectStyle">
      </div>
    </div>
    
    <div v-else
         class="absolute inset-0 z-0 transition-colors duration-1000 bg-gradient-to-br"
         :class="themeStore.isDarkMode 
           ? 'from-gray-900 via-indigo-950/40 to-black' 
           : 'from-blue-50 via-primary-50/30 to-white'">
    </div>

    <div class="absolute inset-0 bg-black/40 z-0"></div>

    <!-- 粒子系统：移入此处以实现与视频组件的层级交互 -->
    <div v-if="settingsStore.settings.particleEnabled" class="absolute inset-0 pointer-events-none transition-opacity duration-500"
         :style="{ zIndex: settingsStore.settings.particleAboveVideo !== false ? 20 : 0 }"
         :class="[
           store.isFullImmersive || settingsStore.isMiniMode ? 'opacity-100' : 'opacity-70'
         ]">
      <ParticleEngine region="full" />
    </div>

    <!-- 2. 视频播放区域 -->
    <div class="relative z-10 w-full h-full p-4 md:p-10 flex flex-col items-center justify-center pointer-events-none">
      
      <!-- 视频容器外层 -->
      <div class="transition-transform duration-700 pointer-events-auto shrink-0"
           :class="{ 'animate-comp-float': store.isFullImmersive && (settingsStore.settings.immersiveVideoFloat !== false) }">
        
        <div @click="toggleVideoFullScreen"
             @mouseenter="isHoveringVideo = true"
             @mouseleave="isHoveringVideo = false"
             class="relative w-full max-w-4xl bg-black shadow-2xl overflow-hidden border border-white/5 group cursor-pointer transition-all duration-700"
             :class="[
               store.isFullImmersive ? 'ring-4 ring-primary-500/50 shadow-primary-500/20' : '',
               isAudioOnly ? 'aspect-square md:w-[500px] lg:w-[600px] rounded-full bg-[#111] !border-transparent !shadow-[0_0_50px_rgba(0,0,0,0.8)]' : 'md:w-[85vw] lg:w-[70vw] aspect-video rounded-2xl'
             ]"
             :style="videoContainerStyle">
          
          <div id="video-mount-point" class="w-full h-full flex items-center justify-center overflow-hidden relative transition-opacity duration-300"
               :class="{ 'opacity-0 pointer-events-none': isAudioOnly }">
            <!-- 针对音频媒体：如果没有封面图 (或加载失败)，显示纯黑背景和跳动的音符 -->
            <div v-if="store.currentVideo && store.currentVideo.is_local && (!store.currentVideo.pic || !store.formatImg(store.currentVideo.pic))" class="absolute inset-0 bg-black flex flex-col items-center justify-center pointer-events-none">
              <MusicalNoteIcon class="w-24 h-24 text-primary-500/50 animate-pulse drop-shadow-2xl" />
              <div class="mt-4 text-xs font-black tracking-widest text-primary-500/50 uppercase">AUDIO STREAM</div>
            </div>

            <!-- 加载中动画叠加层 (移入挂载点内部以支持全屏显示) -->
            <div v-if="store.isBuffering" class="absolute inset-0 flex items-center justify-center bg-black/20 backdrop-blur-[2px] z-50">
              <img :src="LOADING_FRAMES[currentFrameIndex]" class="w-12 h-12 object-contain drop-shadow-[0_0_8px_rgba(255,255,255,0.2)]" v-if="LOADING_FRAMES[currentFrameIndex]" />
              <div v-else class="w-10 h-10 border-4 border-primary-500 border-t-transparent rounded-full animate-spin"></div>
            </div>
          </div>

          <!-- 黑胶唱片视觉容器 (仅音频模式显示) -->
          <div v-if="isAudioOnly" class="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div class="relative w-full h-full rounded-full overflow-hidden flex items-center justify-center"
                 :class="{ 'animate-spin-slow': store.isPlaying }">
              <!-- 纹理层 -->
              <div class="absolute inset-0 rounded-full border-[10px] sm:border-[16px] border-gray-800/50 m-[8%]"></div>
              <div class="absolute inset-0 rounded-full border-[15px] sm:border-[24px] border-gray-800/30 m-[18%]"></div>
              <div class="absolute inset-0 rounded-full border-[20px] sm:border-[30px] border-gray-700/20 m-[28%]"></div>
              <div class="absolute inset-0 rounded-full border border-gray-700/50 m-[40%]"></div>
              
              <!-- 光泽层 (模拟反射) -->
              <div class="absolute inset-0 rounded-full bg-gradient-to-tr from-transparent via-white/5 to-transparent mix-blend-overlay"></div>
              
              <!-- 封面 -->
              <img v-if="store.currentVideo.pic && store.formatImg(store.currentVideo.pic)" 
                   :src="store.formatImg(store.currentVideo.pic)" 
                   class="w-[45%] h-[45%] object-cover rounded-full shadow-[0_0_20px_rgba(0,0,0,0.9)] z-10" />
              <div v-else class="w-[45%] h-[45%] bg-gray-900 rounded-full flex items-center justify-center shadow-[0_0_20px_rgba(0,0,0,0.9)] z-10">
                <MusicalNoteIcon class="w-16 h-16 text-primary-500/50" />
              </div>
            </div>
          </div>

          <div v-if="!store.isPlaying && !store.currentVideo" class="absolute inset-0 flex items-center justify-center text-white/20 pointer-events-none">
            <div class="flex flex-col items-center">
              <MusicalNoteIcon class="w-24 h-24 mb-4 opacity-20 animate-pulse" />
              <div class="text-xl font-black tracking-[0.5em] uppercase">BiliMusic</div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="store.currentVideo && settingsStore.settings.immersiveOverlay !== 'none'" 
           class="mt-8 text-center text-white animate-fade-in transition-all duration-500 max-w-[90vw]"
           :class="{ 'opacity-0 translate-y-10': store.isFullImmersive }"
           :style="{ transform: `translateY(${(settingsStore.settings.videoScale - 1) * 100}px)` }">
        <h1 class="text-xl md:text-2xl lg:text-3xl font-bold mb-2 text-shadow uppercase tracking-tight truncate">{{ store.currentVideo.title }}</h1>
        <p v-if="settingsStore.settings.immersiveOverlay === 'all'" 
           class="text-white/70 text-base md:text-lg font-medium italic">@{{ store.currentVideo.owner }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.text-shadow { text-shadow: 0 4px 12px rgba(0,0,0,0.5); }

@keyframes comp-float {
  0%, 100% { transform: translate3d(0, 0, 0); }
  50% { transform: translate3d(0, -15px, 0); }
}
.animate-comp-float {
  animation: comp-float 8s infinite ease-in-out;
  will-change: transform;
}

@keyframes spin-slow {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.animate-spin-slow {
  animation: spin-slow 15s linear infinite;
}

/* --- 动效定义库 --- */
@keyframes bg-float {
  0%, 100% { transform: scale(1.1) translate(0, 0); }
  33% { transform: scale(calc(1.1 + 0.05 * var(--anim-amplitude))) translate(calc(1% * var(--anim-amplitude)), calc(1% * var(--anim-amplitude))); }
  66% { transform: scale(calc(1.1 + 0.02 * var(--anim-amplitude))) translate(calc(-1% * var(--anim-amplitude)), calc(1% * var(--anim-amplitude))); }
}
.animate-bg-float { animation: bg-float var(--anim-speed) infinite ease-in-out; }

@keyframes bg-ripple {
  0%, 100% { transform: scale(1.15); opacity: 0.8; }
  50% { transform: scale(calc(1.15 + 0.15 * var(--anim-amplitude))); opacity: 0.4; }
}
.animate-bg-ripple { animation: bg-ripple var(--anim-speed) infinite ease-in-out; }

@keyframes bg-rotate {
  0% { transform: scale(var(--critical-scale, 1.5)) rotate(0deg); }
  100% { transform: scale(var(--critical-scale, 1.5)) rotate(360deg); }
}
.animate-bg-rotate { animation: bg-rotate calc(var(--anim-speed) * 10) infinite linear; }

@keyframes bg-drift {
  0% { transform: scale(1.3) translate(calc(-2% * var(--anim-amplitude)), calc(-2% * var(--anim-amplitude))); }
  50% { transform: scale(1.3) translate(calc(2% * var(--anim-amplitude)), calc(2% * var(--anim-amplitude))); }
  100% { transform: scale(1.3) translate(calc(-2% * var(--anim-amplitude)), calc(-2% * var(--anim-amplitude))); }
}
.animate-bg-drift { animation: bg-drift calc(var(--anim-speed) * 3) infinite ease-in-out; }

@keyframes bg-zoom {
  0%, 100% { transform: scale(1.1); }
  50% { transform: scale(calc(1.1 + 0.4 * var(--anim-amplitude))); }
}
.animate-bg-zoom { animation: bg-zoom calc(var(--anim-speed) * 2) infinite ease-in-out; }

@keyframes bg-glitch {
  0%, 100% { transform: scale(1.1); filter: hue-rotate(0deg) saturate(1) brightness(1); }
  25% { filter: hue-rotate(90deg) saturate(calc(1 + 0.5 * var(--anim-amplitude))) brightness(1.2); }
  50% { filter: hue-rotate(180deg) saturate(calc(1 + 1.0 * var(--anim-amplitude))) brightness(0.8); }
  75% { filter: hue-rotate(270deg) saturate(calc(1 + 0.2 * var(--anim-amplitude))) brightness(1.1); }
}
.animate-bg-glitch { animation: bg-glitch calc(var(--anim-speed) * 0.8) infinite linear; }

@keyframes bg-wave {
  0%, 100% { transform: scale(1.2) skew(0deg); }
  50% { transform: scale(1.25) skew(calc(2deg * var(--anim-amplitude)), calc(1deg * var(--anim-amplitude))); }
}
.animate-bg-wave { animation: bg-wave calc(var(--anim-speed) * 1.5) infinite ease-in-out; }

@keyframes bg-pulse {
  0%, 100% { transform: scale(1.1); }
  50% { transform: scale(calc(1.1 + 0.08 * var(--anim-amplitude))); }
}
.animate-bg-pulse { animation: bg-pulse calc(var(--anim-speed) * 0.3) infinite cubic-bezier(0.4, 0, 0.2, 1); }

@keyframes bg-color {
  0% { filter: hue-rotate(0deg); transform: scale(1.15); }
  100% { filter: hue-rotate(360deg); transform: scale(1.15); }
}
.animate-bg-color { animation: bg-color calc(var(--anim-speed) * 4) infinite linear; }

.animate-fade-in { animation: fadeIn 0.8s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

.cursor-none, .cursor-none * {
  cursor: none !important;
}
</style>