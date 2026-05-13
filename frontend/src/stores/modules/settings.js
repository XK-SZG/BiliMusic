import { defineStore } from 'pinia'
import { usePlayerStore } from './player'
import { useThemeStore } from './theme'
import themeApi from '../../api/theme'
import { DEFAULT_SETTINGS } from './constants'

export { DEFAULT_SETTINGS }

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    settings: JSON.parse(localStorage.getItem('bili_settings')) || DEFAULT_SETTINGS,
    isMiniMode: localStorage.getItem('is_mini_mode') === 'true',
    idleTimeout: 3,
    isExportingLibrary: false,
  }),
  actions: {
    updateSettings(newSettings) {
      const playerStore = usePlayerStore()
      const themeStore = useThemeStore()
      const oldQuality = this.settings.streamQuality
      
      this.settings = { ...this.settings, ...newSettings }
      localStorage.setItem('bili_settings', JSON.stringify(this.settings))
      
      const tIdx = themeStore.themes.findIndex(t => t.id === themeStore.activeThemeId)
      if (tIdx !== -1) {
        themeStore.themes[tIdx].settings = this.settings
        localStorage.setItem('bili_themes', JSON.stringify(themeStore.themes))
        if (this._themeSaveTimeout) clearTimeout(this._themeSaveTimeout)
        this._themeSaveTimeout = setTimeout(() => {
          themeApi.saveTheme(themeStore.themes[tIdx]).catch(()=>{})
        }, 1000)
      }

      if (newSettings.defaultVolume !== undefined) playerStore.setVolume(newSettings.defaultVolume)
      if (playerStore.isPlaying && playerStore.currentVideo && playerStore.currentVideo.download_status !== 'completed' && newSettings.streamQuality && newSettings.streamQuality !== oldQuality) {
        playerStore._switchStreamingQuality()
      }
    },
    toggleMiniMode() {
      this.isMiniMode = !this.isMiniMode
      localStorage.setItem('is_mini_mode', this.isMiniMode.toString())
      if (window.require) {
        const { ipcRenderer } = window.require('electron')
        ipcRenderer.send('toggle-mini-mode', this.isMiniMode)
      }
    }
  }
})
