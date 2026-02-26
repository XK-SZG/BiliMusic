import { onMounted, onUnmounted } from 'vue'
import { usePlayerStore } from '../stores/modules/player'
import { useSettingsStore } from '../stores/modules/settings'
import { useThemeStore } from '../stores/modules/theme'

export function useShortcuts() {
  const store = usePlayerStore()
  const settingsStore = useSettingsStore()
  const themeStore = useThemeStore()

  function handleGlobalKeyDown(e) {
    const activeEl = document.activeElement
    if (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.isContentEditable) return

    // 最小化模式下禁用除基础播放控制外的所有快捷键
    const key = e.code
    const s = settingsStore.settings.shortcuts || {}
    const isMini = settingsStore.isMiniMode

    if (isMini && ![s.play, s.prev, s.next, s.volumeUp, s.volumeDown, s.mute].includes(key)) return

    // 统一阻止这些功能键的默认行为
    if ([s.play, s.volumeUp, s.volumeDown].includes(key)) e.preventDefault()

    if (key === s.play) {
      if (store.audioElement) {
        if (!store.currentVideo) {
          if (store.playQueue.length > 0) {
            const resumeIdx = store.queueIndex >= 0 ? store.queueIndex : 0
            store.playFromQueue(resumeIdx)
          } else { store.showToast("队列空空如也", "info") }
        } else {
          // 核心修复：检查是否是重新加载后的“恢复播放”状态 (src 为空但 currentVideo 有值)
          if (!store.audioElement.src || store.audioElement.src === window.location.href) {
            store._loadAndPlay()
            return
          }

          if (store.isPlaying) store.audioElement.pause()
          else store.audioElement.play().catch(()=>{})
        }
      }
    } else if (key === s.volumeUp) {
      store.setVolume(store.volume + 0.02, true)
    } else if (key === s.volumeDown) {
      store.setVolume(store.volume - 0.02, true)
    } else if (key === s.seekBackward) {
      store.seek(store.currentTime - 3)
    } else if (key === s.seekForward) {
      store.seek(store.currentTime + 3)
    } else if (key === s.mute) {
      store.setVolume(store.volume > 0 ? 0 : (settingsStore.settings.defaultVolume || 0.7))
    } else if (key === s.fullscreen) {
      const videoEl = document.getElementById('video-mount-point')
      if (videoEl) {
        if (!document.fullscreenElement) videoEl.requestFullscreen().catch(() => {})
        else document.exitFullscreen()
      }
    } else if (key === s.immersive) {
      if (store.isFullImmersive) { 
        store.isFullImmersive = false 
      } else { 
        store.isUiCollapsed = true
        store.isFullImmersive = true 
      }
    } else if (key === s.toggleUi) {
      if (store.isFullImmersive) { 
        store.isFullImmersive = false
        store.isUiCollapsed = false 
      } else { 
        store.toggleUi() 
      }
    } else if (key === s.prev) {
      store.prev()
    } else if (key === s.next) {
      store.next()
    } else if (key === s.toggleTheme) {
      themeStore.toggleTheme()
    }
  }

  onMounted(() => {
    window.addEventListener('keydown', handleGlobalKeyDown)
  })

  onUnmounted(() => {
    window.removeEventListener('keydown', handleGlobalKeyDown)
  })
}
