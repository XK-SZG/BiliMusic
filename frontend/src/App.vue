<script setup>
import { onMounted, ref, watch, onUnmounted, nextTick, computed, defineAsyncComponent } from 'vue'
import { initSSE } from './api/system'
import { useRoute, useRouter } from 'vue-router'
import { usePlayerStore } from './stores/modules/player'
import { useSettingsStore } from './stores/modules/settings'
import { useThemeStore } from './stores/modules/theme'
import { useShortcuts } from './hooks/useShortcuts'
import Sidebar from './components/Sidebar.vue'
import PlayerBar from './components/PlayerBar.vue'
import TitleBar from './components/TitleBar.vue'
import AgreementModal from './components/AgreementModal.vue'
import systemApi from './api/system'

const isElectron = !!window.require
const urlParams = new URLSearchParams(window.location.search)
const forceTitleBar = urlParams.get('titlebar') === '1'
const showTitleBar = isElectron || forceTitleBar

// 异步加载重型组件
const ImmersivePlayer = defineAsyncComponent(() => import('./components/ImmersivePlayer.vue'))
const MiniPlayer = defineAsyncComponent(() => import('./components/MiniPlayer.vue'))
const AudioVisualizer = defineAsyncComponent(() => import('./components/AudioVisualizer.vue'))
const UniversalModal = defineAsyncComponent(() => import('./components/UniversalModal.vue'))
const StickerLayer = defineAsyncComponent(() => import('./components/StickerLayer.vue'))
const ParticleEngine = defineAsyncComponent(() => import('./components/ParticleEngine.vue'))
const CollectionSelectModal = defineAsyncComponent(() => import('./components/CollectionSelectModal.vue'))
const VideoPreviewModal = defineAsyncComponent(() => import('./components/VideoPreviewModal.vue'))

import { SparklesIcon, ArrowRightOnRectangleIcon, UserIcon, MusicalNoteIcon, SpeakerWaveIcon, SpeakerXMarkIcon } from '@heroicons/vue/24/solid'
import { ICON_ANNUAL_VIP } from './assets/icons'

const store = usePlayerStore()
const settingsStore = useSettingsStore()
const themeStore = useThemeStore()
const route = useRoute()
const router = useRouter()
const videoRef = ref(null)

const showAgreementModal = ref(false)

// 启用全局快捷键
useShortcuts()

const showLogoutModal = ref(false)
const clipboardBvid = ref(null)
const clipboardVideo = ref(null)
const showClipboardModal = ref(false)
const showCollectionSelectModal = ref(false)
let sseConnection = null

// 沉浸全屏模式下的底部唤醒逻辑
const isMouseIdleGlobal = ref(false)
const isHoveringBottom = ref(false)
let mouseIdleTimer = null

function handleGlobalMouseMove(e) {
  isMouseIdleGlobal.value = false
  
  // 检测是否处于底部触发区 (底部 100px)
  const triggerHeight = 100
  isHoveringBottom.value = e.clientY > (window.innerHeight - triggerHeight)

  if (mouseIdleTimer) clearTimeout(mouseIdleTimer)
  
  // 联动设置中的超时时间，默认 3s
  const timeout = (settingsStore.settings.idleTimeout || 3) * 1000
  mouseIdleTimer = setTimeout(() => {
    isMouseIdleGlobal.value = true
  }, timeout)
}

const isShimmering = ref(false)
let shimmerTimer = null

function triggerShimmer() {
  // 1. 先强制关闭动画（如果在运行中）
  isShimmering.value = false
  
  // 2. 清除之前的定时器
  if (shimmerTimer) clearTimeout(shimmerTimer)

  // 3. 利用 setTimeout(0) 将状态切换放入下一个宏任务
  setTimeout(() => {
    isShimmering.value = true
    // 4. 动画时长为 600ms，为确保不被提早切断，定时器放宽至 700ms
    shimmerTimer = setTimeout(() => {
      isShimmering.value = false
    }, 700)
  }, 0)
}

// 动态计算全局字体样式
const appStyle = computed(() => {
  let family = "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
  const f = settingsStore.settings.uiFontFamily
  
  if (f === 'serif') family = "ui-serif, Georgia, Cambria, 'Times New Roman', Times, serif"
  else if (f === 'mono') family = "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace"
  else if (f === 'rounded') family = "'Varela Round', 'Nunito', 'Quicksand', ui-sans-serif, system-ui" // 需引入或依赖系统
  else if (f === 'custom' && settingsStore.settings.uiFontCustom) family = `"${settingsStore.settings.uiFontCustom}", ui-sans-serif, system-ui`
  
  return {
    '--font-family': family,
    '--font-scale': settingsStore.settings.uiFontSize || 1.0,
    fontSize: `calc(16px * ${settingsStore.settings.uiFontSize || 1.0})`,
    fontFamily: 'var(--font-family)'
  }
})

function handleLogout() {
  store.logout()
  showLogoutModal.value = false
}

// 记录路由历史逻辑
watch(() => route.path, (newPath) => {
  if (!store.isUiCollapsed && newPath !== '/') {
    store.lastRoute = newPath
    localStorage.setItem('last_route', newPath)
  }
})

async function syncVideoElement() {
  await nextTick()
  const mountPoint = document.getElementById('video-mount-point')
  if (mountPoint && videoRef.value && !mountPoint.contains(videoRef.value)) {
    mountPoint.appendChild(videoRef.value)
    videoRef.value.classList.remove('hidden')
    videoRef.value.removeAttribute('controls')
    // 将 object-contain 改为从 store 读取动态 class
    videoRef.value.className = `w-full h-full bg-black transition-opacity duration-500 object-${settingsStore.settings.videoFitMode || 'contain'}`
  } else if (videoRef.value) {
    // 如果已经挂载，实时更新 object-fit
    videoRef.value.className = `w-full h-full bg-black transition-opacity duration-500 object-${settingsStore.settings.videoFitMode || 'contain'}`
  }
}

async function checkClipboardBvids() {
  try {
    const res = await systemApi.getPendingBvids()
    if (res.videos && res.videos.length > 0 && !showClipboardModal.value) {
      // 标记视频来源为剪贴板，以便后续处理
      const videoInfo = { ...res.videos[0], from_clipboard: true }
      clipboardVideo.value = videoInfo
      clipboardBvid.value = videoInfo.bvid
      showClipboardModal.value = true
    }
  } catch (e) {
    // 静默失败，不影响主流程
  }
}

async function handleClipboardConfirm(selectedVideoInfo) {
  // 如果传入了选中的分集信息，更新 clipboardVideo 和 clipboardBvid
  if (selectedVideoInfo) {
    // 保留 from_clipboard 标记
    clipboardVideo.value = { ...selectedVideoInfo, from_clipboard: true }
    clipboardBvid.value = selectedVideoInfo.bvid
    console.log('[剪贴板] 用户选择的分集信息:', {
      bvid: selectedVideoInfo.bvid,
      title: selectedVideoInfo.title,
      duration: selectedVideoInfo.duration,
      is_part: selectedVideoInfo.is_part,
      part_num: selectedVideoInfo.part_num
    })
    console.log('[剪贴板] 更新后的 clipboardVideo:', clipboardVideo.value)
    console.log('[剪贴板] 更新后的 clipboardBvid:', clipboardBvid.value)
  }
  
  if (!clipboardBvid.value) return
  
  // 关闭剪贴板弹窗，打开媒体库选择弹窗
  showClipboardModal.value = false
  showCollectionSelectModal.value = true
}

async function handleCollectionSelect(collectionId) {
  if (!clipboardVideo.value || !collectionId) return
  
  try {
    // 调用确认接口，传入 collection_id 以及标题和时长（应对分集切换导致的值变化）
    // 直接使用 clipboardVideo.value.bvid，而不是 clipboardBvid.value
    await systemApi.confirmBvid(
      clipboardVideo.value.bvid,
      collectionId,
      clipboardVideo.value.title,
      clipboardVideo.value.duration
    )
    store.showToast(`视频已添加到媒体库`, 'success')
    await store.fetchLocalVideos()
  } catch (e) {
    console.error('[剪贴板] 添加视频失败:', e)
    store.showToast('添加视频失败', 'error')
  } finally {
    showCollectionSelectModal.value = false
    cleanupClipboardModal()
  }
}

function handleCollectionSelectClose() {
  showCollectionSelectModal.value = false
  // 不清理 clipboardBvid 和 clipboardVideo，以便用户可以重新打开选择
}

async function handleClipboardDismiss() {
  if (!clipboardBvid.value) return
  try {
    await systemApi.dismissBvid(clipboardBvid.value)
  } catch (e) {
    // 静默失败
  } finally {
    cleanupClipboardModal()
  }
}

function cleanupClipboardModal() {
  showClipboardModal.value = false
  clipboardBvid.value = null
  clipboardVideo.value = null
}

function handleAgree() {
  localStorage.setItem('user_agreed_20260416', 'true')
  showAgreementModal.value = false
}

function handleDecline() {
  if (window.require) {
    const { ipcRenderer } = window.require('electron')
    ipcRenderer.send('window-close')
  } else {
    window.close()
  }
}

onMounted(async () => {
  if (localStorage.getItem('user_agreed_20260416') !== 'true') {
    showAgreementModal.value = true
  }

  if (window.require) {
    const { ipcRenderer } = window.require('electron')
    ipcRenderer.on('window-maximized', () => {
      if (settingsStore.isMiniMode) {
        settingsStore.toggleMiniMode()
      }
    })
    ipcRenderer.on('force-exit-mini-mode', () => {
      if (settingsStore.isMiniMode) {
        settingsStore.toggleMiniMode()
      }
    })
  }

  store.init()
  store.audioElement = videoRef.value
  if (videoRef.value) {
    videoRef.value.volume = store.volume
    videoRef.value.addEventListener('timeupdate', store.updateProgress)
    videoRef.value.addEventListener('durationchange', store.updateProgress)
    videoRef.value.addEventListener('progress', store.updateProgress)
    
    // 加载状态监听：确保初始加载也能触发
    if (videoRef.value.seeking) store.isBuffering = true

    videoRef.value.addEventListener('play', () => { store.isPlaying = true })
    videoRef.value.addEventListener('pause', () => { store.isPlaying = false })
    
    // 缓冲逻辑的细粒度控制
    videoRef.value.addEventListener('waiting', () => { store.isBuffering = true })
    videoRef.value.addEventListener('loadstart', () => { store.isBuffering = true })
    videoRef.value.addEventListener('loadeddata', () => { store.isBuffering = false })
    videoRef.value.addEventListener('playing', () => { store.isBuffering = false })
    videoRef.value.addEventListener('canplay', () => { store.isBuffering = false })
  }
  syncVideoElement()
  window.addEventListener('mousemove', handleGlobalMouseMove)
  
  // 建立 SSE 长连接以替代轮询
  sseConnection = initSSE(
    (clipboardData) => {
      // 当剪贴板有新数据时触发获取
      if (clipboardData.count > 0 && !showClipboardModal.value) {
        checkClipboardBvids()
      }
    },
    (downloadState) => {
      // 实时更新下载状态
      store.updateDownloadStateFromSSE(downloadState)
    }
  )
})

onUnmounted(() => {
  window.removeEventListener('mousemove', handleGlobalMouseMove)
  if (mouseIdleTimer) clearTimeout(mouseIdleTimer)
  if (sseConnection) sseConnection.close()
})

watch(() => store.currentVideo, () => { syncVideoElement() }, { deep: true })
watch(() => store.isUiCollapsed, (collapsed) => { if (collapsed) syncVideoElement() })
// 监听填充模式变化，实时同步
watch(() => settingsStore.settings.videoFitMode, () => { syncVideoElement() })
</script>

<template>
  <div class="flex h-screen overflow-hidden relative transition-colors duration-200
              bg-gray-100 dark:bg-black
              text-gray-800 dark:text-white"
       :style="appStyle">

    <!-- 最小化模式覆盖层 -->
    <MiniPlayer v-if="settingsStore.isMiniMode" />

    <!-- 层级 0: 沉浸式播放器背景 -->
    <ImmersivePlayer />

    <!-- 沉浸界面贴画层 (Sticker Layer for Immersive) 
         随主视图同步移动：
         - 展开状态 (!isUiCollapsed)：悬停在顶部外 (-translate-y-full)。
         - 沉浸模式 (isUiCollapsed && !isFullImmersive)：降下归位 (translate-y-0)。
         - 沉浸全屏模式 (isFullImmersive)：跟随播放栏整体偏移一段合适的距离 (translate-y-[5rem] 等于 80px) 并且渐渐隐去，以防飞出屏幕造成断层感。
    -->
    <StickerLayer target="immersive" 
                  class="absolute inset-0 z-[5] pointer-events-none transition-all duration-[600ms] ease-in-out"
                  :class="[
                    (store.isStickerEditMode && store.stickerEditingTarget === 'immersive') 
                      ? 'translate-y-0 opacity-100' 
                      : (store.isFullImmersive 
                          ? 'translate-y-[5rem] opacity-100' 
                          : (store.isUiCollapsed ? 'translate-y-0 opacity-100' : '-translate-y-full opacity-0'))
                  ]" />

    <!-- 层级 1: UI 面板 (侧边栏 + 主内容) -->
    <div class="absolute inset-0 z-20 transition-all duration-[600ms] ease-in-out"
         :class="[
           settingsStore.isMiniMode ? 'translate-y-full pointer-events-none' :
           (store.isFullImmersive
             ? (isHoveringBottom && !isMouseIdleGlobal ? 'translate-y-[calc(100%-5rem)] pointer-events-auto' : 'translate-y-full pointer-events-none')
             : (store.isUiCollapsed ? 'translate-y-[calc(100%-5rem)]' : 'translate-y-0'))
         ]">

      <!-- 背景子层 (z-0)：单独提取出的颜色与模糊背景 -->
      <div class="absolute inset-0 flex pointer-events-none z-0">
        
        <!-- 左侧边栏背景 -->
        <transition name="sidebar-left">
          <div v-if="settingsStore.settings.sidebarPosition === 'left'"
               class="w-20 md:w-20 lg:w-56 h-full backdrop-blur-xl transition-all duration-[600ms] ease-in-out shadow-2xl shrink-0 border-r"
               :style="{
                 borderColor: themeStore.isDarkMode ? 'rgba(255,255,255,0.05)' : 'rgba(229,231,235,1)',
                 backgroundColor: themeStore.isDarkMode 
                   ? `rgba(17, 24, 39, ${settingsStore.settings.uiOpacity})` 
                   : `rgba(255, 255, 255, ${Math.min(0.95, Math.max(0.6, settingsStore.settings.uiOpacity))})`, 
                 backdropFilter: `blur(${settingsStore.settings.uiBlur}px)`,
                 WebkitBackdropFilter: `blur(${settingsStore.settings.uiBlur}px)`
               }">
          </div>
        </transition>

        <!-- 主视图背景 -->
        <div class="flex-1 h-full bg-white/80 dark:bg-black/60 transition-all duration-[600ms] cubic-bezier(0.4, 0, 0.2, 1)"></div>

        <!-- 右侧边栏背景 -->
        <transition name="sidebar-right">
          <div v-if="settingsStore.settings.sidebarPosition === 'right'"
               class="w-20 md:w-20 lg:w-56 h-full backdrop-blur-xl transition-all duration-[600ms] ease-in-out shadow-2xl shrink-0 border-l"
               :style="{
                 borderColor: themeStore.isDarkMode ? 'rgba(255,255,255,0.05)' : 'rgba(229,231,235,1)',
                 backgroundColor: themeStore.isDarkMode 
                   ? `rgba(17, 24, 39, ${settingsStore.settings.uiOpacity})` 
                   : `rgba(255, 255, 255, ${Math.min(0.95, Math.max(0.6, settingsStore.settings.uiOpacity))})`, 
                 backdropFilter: `blur(${settingsStore.settings.uiBlur}px)`,
                 WebkitBackdropFilter: `blur(${settingsStore.settings.uiBlur}px)`
               }">
          </div>
        </transition>
      </div>

      <!-- 面板背景图 (uiBackground, z-10)：在背景层之上，不被模糊，无缝贯穿全屏 -->
      <StickerLayer target="uiBackground" class="z-10" />

      <!-- 内容子层 (z-20) -->
      <div class="absolute inset-0 flex z-20 pointer-events-none">

        <!-- 左侧：侧边栏及按钮容器 -->
        <transition name="sidebar-left">
          <div v-if="settingsStore.settings.sidebarPosition === 'left'"
               class="relative w-20 md:w-20 lg:w-56 flex flex-col h-full transition-all duration-300 ease-in-out pointer-events-auto shrink-0">
            <StickerLayer target="sidebar" />
            <Sidebar class="z-10 bg-transparent border-none w-full" />
            <button @click="store.toggleUi"
                    @mouseenter="triggerShimmer"
                    @mouseleave="triggerShimmer"
                    class="relative group/imm h-[90px] mt-auto flex items-center justify-center border-t border-gray-200 dark:border-white/10
                           bg-white/40 dark:bg-white/5 backdrop-blur-md hover:bg-white/80 dark:hover:bg-white/10
                           transition-all duration-500 active:scale-95 overflow-hidden z-10 select-none cursor-pointer"
                    :class="{ 'opacity-0 pointer-events-none': store.isFullImmersive }">
               <div class="absolute inset-0 z-10 pointer-events-none -translate-y-full
                           bg-[linear-gradient(180deg,transparent,rgb(var(--color-primary)/0.5)_10%,rgba(168,85,247,0.5)_30%,rgba(59,130,246,0.5)_50%,transparent)]
                           dark:bg-[linear-gradient(180deg,transparent,rgb(var(--color-primary)/0.6)_10%,rgba(168,85,247,0.6)_30%,rgba(59,130,246,0.6)_50%,transparent)]
                           dark:mix-blend-plus-lighter"
                    :class="{ 'animate-shimmer-down': isShimmering }">
               </div>
               <span class="relative z-20 font-black tracking-[0.2em] uppercase text-[20px] flex items-center gap-3 drop-shadow-md">
                 <SparklesIcon class="w-7 h-7 text-primary-500 group-hover/imm:text-violet-500 transition-colors animate-pulse drop-shadow-md" />
                 <span class="hidden lg:inline bg-gradient-to-br from-primary-500 to-violet-600 bg-clip-text text-transparent group-hover/imm:from-primary-400 group-hover/imm:to-violet-500 transition-all">沉浸模式</span>
               </span>
            </button>
          </div>
        </transition>

        <!-- 中间：主视图 (MainView) -->
        <div class="relative flex-1 flex flex-col h-full overflow-hidden pointer-events-auto transition-all duration-[600ms] cubic-bezier(0.4, 0, 0.2, 1)">
          <StickerLayer target="mainView" />
          <header class="h-[90px] flex items-center justify-between px-6 shrink-0 border-b relative z-10 border-gray-200 dark:border-white/5"
                  :style="{ webkitAppRegion: !store.isUiCollapsed ? 'drag' : 'no-drag' }">
             <div class="flex-1 h-full"></div>
             <div class="flex items-center space-x-4 h-full" style="-webkit-app-region: no-drag;">
               <button v-if="store.user" @click="showLogoutModal = true"
                       class="group flex items-center px-2 lg:px-3 py-1.5 rounded-2xl transition-all duration-300
                              bg-white/60 dark:bg-black/40 backdrop-blur-md border border-gray-200 dark:border-white/10
                              hover:border-red-500/50 hover:bg-red-50/90 dark:hover:bg-red-500/20 hover:shadow-lg hover:shadow-red-500/20">
                  <div class="relative w-8 h-8 shrink-0">
                    <div class="w-full h-full rounded-full overflow-hidden border border-gray-200 dark:border-white/10 group-hover:border-red-500/40 transition-colors">
                      <img :src="store.user.face" @error="(e) => e.target.style.display='none'" draggable="false" class="w-full h-full object-cover" v-if="store.user.face" />
                      <UserIcon v-else class="w-full h-full p-1.5 text-gray-400" />
                    </div>
                    <img v-if="store.user.vip_status === 1" :src="ICON_ANNUAL_VIP" @error="(e) => e.target.style.display='none'" draggable="false" class="absolute -bottom-1 -right-1 w-4 h-4 object-contain drop-shadow-md" />
                  </div>
                  <span class="block text-sm font-bold text-gray-700 dark:text-gray-200 group-hover:text-red-600 dark:group-hover:text-red-400 transition-colors ml-3">{{ store.user.uname }}</span>
                  <div class="flex overflow-hidden transition-all duration-300 max-w-0 opacity-0 group-hover:max-w-[28px] group-hover:opacity-100 items-center">
                    <ArrowRightOnRectangleIcon class="w-4 h-4 text-red-600 dark:text-red-400 ml-2 shrink-0" />
                  </div>
               </button>
             </div>
          </header>

          <UniversalModal
            :show="showLogoutModal"
            type="confirm"
            title="退出登录"
            :extra-data="{ message: '退出登录后，需要重新扫码验证才能使用在线功能。确定退出吗？', isDanger: true, confirmText: '退出', cancelText: '取消' }"
            @close="showLogoutModal = false"
            @confirm="(confirmed) => { if(confirmed) handleLogout() }"
          >
            <template #confirm-icon>
              <ArrowRightOnRectangleIcon class="w-12 h-12 text-red-500 mx-auto mb-2" />
            </template>
          </UniversalModal>

          <main class="flex-1 overflow-y-auto p-6 pb-28 scrollbar-thin relative z-10">
             <router-view v-slot="{ Component }">
               <transition :name="settingsStore.settings.uiTransition || 'fade'" mode="out-in">
                 <component :is="Component" />
               </transition>
             </router-view>
          </main>
        </div>

        <!-- 右侧：侧边栏及按钮容器 -->
        <transition name="sidebar-right">
          <div v-if="settingsStore.settings.sidebarPosition === 'right'"
               class="relative w-20 md:w-20 lg:w-56 flex flex-col h-full transition-all duration-300 ease-in-out pointer-events-auto shrink-0">
            <StickerLayer target="sidebar" />
            <Sidebar class="z-10 bg-transparent border-none w-full" />
            <button @click="store.toggleUi"
                    @mouseenter="triggerShimmer"
                    @mouseleave="triggerShimmer"
                    class="relative group/imm h-[90px] mt-auto flex items-center justify-center border-t border-gray-200 dark:border-white/10
                           bg-white/40 dark:bg-white/5 backdrop-blur-md hover:bg-white/80 dark:hover:bg-white/10
                           transition-all duration-500 active:scale-95 overflow-hidden z-10 select-none cursor-pointer"
                    :class="{ 'opacity-0 pointer-events-none': store.isFullImmersive }">
               <div class="absolute inset-0 z-10 pointer-events-none -translate-y-full
                           bg-[linear-gradient(180deg,transparent,rgb(var(--color-primary)/0.5)_10%,rgba(168,85,247,0.5)_30%,rgba(59,130,246,0.5)_50%,transparent)]
                           dark:bg-[linear-gradient(180deg,transparent,rgb(var(--color-primary)/0.6)_10%,rgba(168,85,247,0.6)_30%,rgba(59,130,246,0.6)_50%,transparent)]
                           dark:mix-blend-plus-lighter"
                    :class="{ 'animate-shimmer-down': isShimmering }">
               </div>
               <span class="relative z-20 font-black tracking-[0.2em] uppercase text-[20px] flex items-center gap-3 drop-shadow-md">
                 <SparklesIcon class="w-7 h-7 text-primary-500 group-hover/imm:text-violet-500 transition-colors animate-pulse drop-shadow-md" />
                 <span class="hidden lg:inline bg-gradient-to-br from-primary-500 to-violet-600 bg-clip-text text-transparent group-hover/imm:from-primary-400 group-hover/imm:to-violet-500 transition-all">沉浸模式</span>
               </span>
            </button>
          </div>
        </transition>
      </div>
    </div>

    <!-- 底部播放条 -->
    <PlayerBar class="z-30 transition-all duration-[600ms] ease-in-out"
               :class="[
                 settingsStore.isMiniMode ? 'translate-y-full pointer-events-none' :
                 (store.isFullImmersive
                   ? (isHoveringBottom && !isMouseIdleGlobal ? 'translate-y-0 pointer-events-auto' : 'translate-y-full pointer-events-none')
                   : 'translate-y-0')
               ]"/>

    <!-- 音频频谱层 (位于 UI 之下，背景之上) -->
    <AudioVisualizer />

    <!-- 真实的 Video 标签 -->
    <video ref="videoRef"
           class="hidden"
           preload="auto"
           crossorigin="anonymous"
           playsinline
           webkit-playsinline
           @ended="store.next()"></video>
    
    <!-- 预加载视频元素（用于剪贴板预览缓存） -->
    <video ref="preloadVideoRef"
           class="hidden"
           preload="auto"
           muted
           crossorigin="anonymous"></video>

    <!-- 可视化编辑模式浮层 -->
    <transition name="toast-fade">
      <div v-if="store.isStickerEditMode" class="fixed top-4 left-1/2 -translate-x-1/2 z-[1000] flex items-center gap-4 bg-fuchsia-500/90 backdrop-blur-md px-6 py-3 rounded-2xl shadow-2xl border border-fuchsia-400">
        <SparklesIcon class="w-5 h-5 text-white animate-pulse" />
        <span class="text-white text-sm font-black tracking-widest">贴画编辑模式中</span>
        <span class="text-white/80 text-[10px] uppercase font-bold tracking-tight px-3 border-l border-white/20">拖拽移动 · 滚轮缩放 · Shift+滚轮旋转</span>
        <button @click="store.toggleStickerEditMode" class="ml-2 px-3 py-1 bg-white text-fuchsia-500 rounded-xl text-xs font-black shadow-md hover:scale-105 transition-all active:scale-95">完成</button>
      </div>
    </transition>

    <!-- 剪贴板 BV 号确认弹窗 (使用 VideoPreviewModal 组件) -->
    <VideoPreviewModal
      :show="showClipboardModal"
      :video-info="clipboardVideo"
      @close="handleClipboardDismiss"
      @confirm="handleClipboardConfirm" />

    <!-- 媒体库选择弹窗 -->
    <CollectionSelectModal
      :show="showCollectionSelectModal"
      :video-info="clipboardVideo"
      title="选择媒体库"
      @close="handleCollectionSelectClose"
      @confirm="handleCollectionSelect" />

    <!-- Toast 提示 -->
    <transition name="toast-fade">
      <div v-if="store.toast.show"
           class="fixed top-10 left-1/2 -translate-x-1/2 z-[9999] px-6 py-3 rounded-2xl shadow-2xl backdrop-blur-md border flex items-center gap-3 transition-all duration-300"
           :class="{
             'bg-white/90 dark:bg-gray-900/90 border-gray-200 dark:border-white/10 text-gray-800 dark:text-white': store.toast.type === 'info',
             'bg-red-500/90 border-red-600 text-white': store.toast.type === 'error',
             'bg-green-500/90 border-green-600 text-white': store.toast.type === 'success'
           }">
        <div v-if="store.toast.type === 'error'" class="w-5 h-5 rounded-full bg-white text-red-500 flex items-center justify-center font-bold">!</div>
        <div v-if="store.toast.type === 'success'" class="w-5 h-5 rounded-full bg-white text-green-500 flex items-center justify-center font-bold">✓</div>
        <span class="text-sm font-bold tracking-tight">{{ store.toast.msg }}</span>
      </div>
    </transition>

    <!-- 用户协议弹窗 -->
    <AgreementModal :show="showAgreementModal" @agree="handleAgree" @decline="handleDecline" />

    <!-- 窗口标题栏 (置于最顶层) -->
    <TitleBar v-if="showTitleBar" class="z-[9999]" />
  </div>
</template>

<style>
/* 全局图像优化 - 修复锯齿问题 (还原 1.0.14 版本的修复) */
img {
  /* CSS 抗锯齿属性 */
  image-rendering: -webkit-optimize-contrast;
  image-rendering: crisp-edges;
  
  /* GPU 加速 */
  transform: translateZ(0);
  will-change: transform;
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
  
  /* 平滑渲染 */
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.scrollbar-thin::-webkit-scrollbar { width: 6px; }
.scrollbar-thin::-webkit-scrollbar-track { background: transparent; }
.scrollbar-thin::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.2); border-radius: 3px; }
.scrollbar-thin::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.4); }
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* Slide 过渡 */
.slide-enter-active, .slide-leave-active { transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); }
.slide-enter-from { opacity: 0; transform: translateX(30px); }
.slide-leave-to { opacity: 0; transform: translateX(-30px); }

/* Scale 过渡 */
.scale-enter-active, .scale-leave-active { transition: all 0.3s ease; }
.scale-enter-from { opacity: 0; transform: scale(0.95); }
.scale-leave-to { opacity: 0; transform: scale(1.05); }

.toast-fade-enter-active, .toast-fade-leave-active { transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
.toast-fade-enter-from { opacity: 0; transform: translate(-50%, -20px) scale(0.9); }
.toast-fade-leave-to { opacity: 0; transform: translate(-50%, -20px) scale(0.9); }

/* --- 侧边栏切换动画 --- */
.sidebar-left-enter-active, .sidebar-left-leave-active,
.sidebar-right-enter-active, .sidebar-right-leave-active {
  /* 严格同步时间与曲线 */
  transition: all 0.6s cubic-bezier(0.4, 0, 0.2, 1) !important;
  white-space: nowrap;
  overflow: hidden;
  /* 解决模糊消失：隔离层上下文 */
  isolation: isolate;
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
}

.sidebar-left-enter-from, .sidebar-left-leave-to {
  width: 0 !important;
  min-width: 0 !important;
  opacity: 0;
  transform: translateX(-100%);
}

.sidebar-right-enter-from, .sidebar-right-leave-to {
  width: 0 !important;
  min-width: 0 !important;
  opacity: 0;
  transform: translateX(100%);
}

/* --- 向下的流光动画 --- */
@keyframes shimmer-down {
  0% {
    transform: translateY(-100%) skewY(-15deg);
  }
  100% {
    transform: translateY(200%) skewY(-15deg);
  }
}

.animate-shimmer-down {
  animation: shimmer-down 0.6s cubic-bezier(0.4, 0, 0.2, 1) forwards;
}
</style>
