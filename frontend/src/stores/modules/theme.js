import { defineStore } from 'pinia'
import { generateThemeVariables, applyTheme } from '../../utils/theme.js'
import { useSettingsStore } from './settings.js'
import { usePlayerStore } from './player.js'
import themeApi from '../../api/theme'
import systemApi from '../../api/system'
import { DEFAULT_SETTINGS, BILIBILI_SETTINGS } from './constants'

export { BILIBILI_SETTINGS }

export const useThemeStore = defineStore('theme', {
  state: () => ({
    isDarkMode: localStorage.getItem('theme') === 'dark' || localStorage.getItem('theme') === null,
    themeColor: localStorage.getItem('theme_color') || '#ff6699',
    themes: JSON.parse(localStorage.getItem('bili_themes')) || [
      { id: 'default', name: '默认主题样式', is_default: 1, settings: DEFAULT_SETTINGS },
      { id: 'theme_bilibili', name: 'Bilibili', is_default: 1, settings: BILIBILI_SETTINGS }
    ],
    activeThemeId: localStorage.getItem('bili_active_theme_id') || 'default',
    stickerDataBundle: {},
    isStickerEditMode: false,
    stickerEditingTarget: 'uiBackground',
    customBackgrounds: [],
    customBgUrl: '',
    customBgIndex: parseInt(localStorage.getItem('cache_bg_custom_index') || '0'),
  }),
  actions: {
    applyTheme() {
      if (this.isDarkMode) document.documentElement.classList.add('dark')
      else document.documentElement.classList.remove('dark')
    },
    toggleTheme() {
      this.isDarkMode = !this.isDarkMode
      this.applyTheme()
      localStorage.setItem('theme', this.isDarkMode ? 'dark' : 'light')
    },
    updateThemeColor(hex, save = true) {
      if (!hex) return
      const vars = generateThemeVariables(hex)
      if (vars) {
        applyTheme(vars)
        this.themeColor = hex
        if (save) localStorage.setItem('theme_color', hex)
      }
    },
    async fetchStickersBundle() {
      try {
        const data = await systemApi.getStickersBundle()
        this.stickerDataBundle = data
      } catch (e) { console.warn("Failed to fetch stickers bundle") }
    },
    async fetchCustomBackgrounds() {
      try {
        const data = await systemApi.getBackgrounds()
        this.customBackgrounds = data.backgrounds || []
        if (this.customBackgrounds.length > 0) {
          if (this.customBgIndex >= this.customBackgrounds.length) this.customBgIndex = 0
          this.customBgUrl = this.customBackgrounds[this.customBgIndex].url
        }
      } catch (e) { console.error("Fetch backgrounds failed") }
    },
    rotateCustomBackground() {
      const settingsStore = useSettingsStore()
      if (settingsStore.settings.bgType !== 'custom' || this.customBackgrounds.length === 0) return
      
      if (settingsStore.settings.bgCustomMode === 'shuffle') {
        this.customBgIndex = Math.floor(Math.random() * this.customBackgrounds.length)
      } else {
        this.customBgIndex = (this.customBgIndex + 1) % this.customBackgrounds.length
      }
      
      this.customBgUrl = this.customBackgrounds[this.customBgIndex].url
      localStorage.setItem('cache_bg_custom_index', this.customBgIndex.toString())
    },
    async syncThemes() {
      const settingsStore = useSettingsStore()
      try {
        const localThemes = this.themes;
        if (!localThemes.some(t => t.id === 'theme_bilibili')) {
           localThemes.push({ id: 'theme_bilibili', name: 'Bilibili', is_default: 1, settings: BILIBILI_SETTINGS });
           this.themes = localThemes;
           localStorage.setItem('bili_themes', JSON.stringify(this.themes));
        }

        const data = await themeApi.syncThemes({
          themes: this.themes,
          active_theme_id: this.activeThemeId
        })
        if (data.mismatch) {
          this.themes = data.server_themes
          localStorage.setItem('bili_themes', JSON.stringify(this.themes))
          
          const exists = this.themes.find(t => t.id === this.activeThemeId)
          if (!exists) {
            this.activeThemeId = 'default'
            localStorage.setItem('bili_active_theme_id', 'default')
            const defTheme = this.themes.find(t => t.id === 'default')
            if (defTheme) {
              const visualSettings = { ...defTheme.settings }
              const excludeKeys = ['streamQuality', 'cacheQuality', 'defaultVolume', 'startupPage', 'uiTransition', 'enableVolumeFade', 'idleTimeout', 'weightSensitivity', 'shortcuts']
              excludeKeys.forEach(k => delete visualSettings[k])
              settingsStore.updateSettings(visualSettings)
              this._syncThemeColorToLocalStorage(defTheme.settings)
            }
          } else {
            // 仅当视觉相关设置不一致时才更新
            const visualSettings = { ...exists.settings }
            const excludeKeys = ['streamQuality', 'cacheQuality', 'defaultVolume', 'startupPage', 'uiTransition', 'enableVolumeFade', 'idleTimeout', 'weightSensitivity', 'shortcuts']
            excludeKeys.forEach(k => delete visualSettings[k])
            
            // 简单对比视觉部分
            const currentVisual = { ...settingsStore.settings }
            excludeKeys.forEach(k => delete currentVisual[k])

            if (JSON.stringify(visualSettings) !== JSON.stringify(currentVisual)) {
              settingsStore.updateSettings(visualSettings)
              this._syncThemeColorToLocalStorage(exists.settings)
            }
          }
        }
      } catch (e) { console.error("Theme sync failed", e) }
    },
    async applyThemeById(id) {
      const settingsStore = useSettingsStore()
      const t = this.themes.find(x => x.id === id)
      if (t) {
        this.activeThemeId = id
        localStorage.setItem('bili_active_theme_id', id)
        
        // 仅更新视觉相关的设置，保留全局功能性设置
        const visualSettings = { ...t.settings }
        const excludeKeys = [
          'streamQuality', 'cacheQuality', 'defaultVolume',
          'startupPage', 'uiTransition', 'enableVolumeFade',
          'idleTimeout', 'weightSensitivity', 'shortcuts'
        ]
        excludeKeys.forEach(key => delete visualSettings[key])
        
        settingsStore.updateSettings(visualSettings)
        this._syncThemeColorToLocalStorage(t.settings)
      }
    },
    _syncThemeColorToLocalStorage(settings) {
      const colorMap = { pink: '#ff6699', purple: '#a855f7', blue: '#0087bd', green: '#22c55e', orange: '#f97316', red: '#ef4444' }
      if (settings.visColor !== 'custom' && colorMap[settings.visColor]) {
        localStorage.setItem('theme_color', colorMap[settings.visColor])
        this.updateThemeColor(colorMap[settings.visColor], false)
      } else if (settings.visColor === 'custom' && settings.visColorCustom) {
        localStorage.setItem('theme_color', settings.visColorCustom)
        this.updateThemeColor(settings.visColorCustom, false)
      }
    },
    async addTheme(name) {
      const settingsStore = useSettingsStore()
      const newId = 'theme_' + Math.random().toString(36).substr(2, 9)
      const newTheme = {
        id: newId,
        name,
        is_default: 0,
        settings: JSON.parse(JSON.stringify(settingsStore.settings))
      }
      
      newTheme.settings.cardImage = '/local_stickers/90dfd622_2233.png'
      newTheme.settings.cardImageSize = 50
      newTheme.settings.cardOffsetX = -10
      newTheme.settings.cardOffsetY = 10

      this.themes.push(newTheme)
      localStorage.setItem('bili_themes', JSON.stringify(this.themes))
      try { await themeApi.saveTheme(newTheme) } catch(e){}
      await this.applyThemeById(newId)
    },
    async editThemeCard(id, updates) {
      const settingsStore = useSettingsStore()
      const tIdx = this.themes.findIndex(t => t.id === id)
      if (tIdx !== -1) {
        if (updates.name) this.themes[tIdx].name = updates.name
        if (updates.cardImage !== undefined) this.themes[tIdx].settings.cardImage = updates.cardImage
        if (updates.cardImageSize !== undefined) this.themes[tIdx].settings.cardImageSize = updates.cardImageSize
        if (updates.cardOffsetX !== undefined) this.themes[tIdx].settings.cardOffsetX = updates.cardOffsetX
        if (updates.cardOffsetY !== undefined) this.themes[tIdx].settings.cardOffsetY = updates.cardOffsetY
        
        localStorage.setItem('bili_themes', JSON.stringify(this.themes))
        try { await themeApi.saveTheme(this.themes[tIdx]) } catch(e){}
        
        if (this.activeThemeId === id) {
          const newSettings = {}
          if (updates.cardImage !== undefined) newSettings.cardImage = updates.cardImage
          if (updates.cardImageSize !== undefined) newSettings.cardImageSize = updates.cardImageSize
          if (updates.cardOffsetX !== undefined) newSettings.cardOffsetX = updates.cardOffsetX
          if (updates.cardOffsetY !== undefined) newSettings.cardOffsetY = updates.cardOffsetY
          settingsStore.updateSettings(newSettings)
        }
      }
    },
    async deleteTheme(id) {
      if (id === 'default' || id === 'theme_bilibili') return
      try { await themeApi.deleteTheme(id) } catch(e){}
      this.themes = this.themes.filter(t => t.id !== id)
      localStorage.setItem('bili_themes', JSON.stringify(this.themes))
      if (this.activeThemeId === id) {
        await this.applyThemeById('default')
      }
    },
    toggleStickerEditMode(forceImmersive = false) {
      const playerStore = usePlayerStore()
      this.isStickerEditMode = !this.isStickerEditMode
      if (this.isStickerEditMode) {
        this._prevUiState = {
          collapsed: playerStore.isUiCollapsed,
          immersive: playerStore.isFullImmersive
        }
        if (forceImmersive) {
          playerStore.isUiCollapsed = true
          playerStore.isFullImmersive = true
        }
        playerStore.showToast("已进入贴图编辑模式：拖动移动，滚轮缩放，Shift+滚轮旋转", "info")
      } else {
        playerStore.isUiCollapsed = this._prevUiState.collapsed
        playerStore.isFullImmersive = this._prevUiState.immersive
      }
    }
  }
})
