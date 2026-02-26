# -*- coding: utf-8 -*-
# Path: frontend/src/components/Sidebar.vue

<script setup>
import { useRouter } from 'vue-router'
import { usePlayerStore } from '../stores/modules/player'
import { useThemeStore } from '../stores/modules/theme'
import { ref, computed } from 'vue'
import {
  HomeIcon,
  CloudIcon,
  FolderIcon,
  QueueListIcon,
  Cog6ToothIcon,
  MoonIcon,
  SunIcon
} from '@heroicons/vue/24/solid'

const store = usePlayerStore()
const themeStore = useThemeStore()
const router = useRouter()

function handleLogoClick() {
  if (store.isUiCollapsed) {
    store.isUiCollapsed = false
    router.push(store.lastRoute || '/')
  } else {
    router.push('/')
  }
}
const isShimmering = ref(false)
let shimmerTimer = null

function triggerShimmer() {
  isShimmering.value = false
  if (shimmerTimer) clearTimeout(shimmerTimer)

  setTimeout(() => {
    isShimmering.value = true
    shimmerTimer = setTimeout(() => {
      isShimmering.value = false
    }, 600)
  }, 0)
}

function goHome() {
  store.isUiCollapsed = false
  router.push('/')
}
</script>

<template>
  <div class="flex flex-col transition-all duration-300 ease-in-out h-full w-20 md:w-20 lg:w-56">

    <div class="h-[90px]">
      <div @click="handleLogoClick"
           @mouseenter="triggerShimmer"
           @mouseleave="triggerShimmer"
           class="relative group/title cursor-pointer select-none overflow-hidden
                  transition-all duration-500 ease-out border-b border-gray-200 dark:border-white/10
                  active:scale-95 hover:bg-white/60 dark:hover:bg-white/10
                  bg-white/40 dark:bg-white/5 backdrop-blur-md h-full flex flex-col justify-center">
        
        <div class="absolute inset-0 z-10 pointer-events-none -translate-x-full
                    bg-[linear-gradient(90deg,transparent,rgb(var(--color-primary)/0.5)_10%,rgba(168,85,247,0.5)_30%,rgba(59,130,246,0.5)_50%,transparent)]
                    dark:bg-[linear-gradient(90deg,transparent,rgb(var(--color-primary)/0.6)_10%,rgba(168,85,247,0.6)_30%,rgba(59,130,246,0.6)_50%,transparent)]
                    dark:mix-blend-plus-lighter"
             :class="{ 'animate-shimmer-slide': isShimmering }">
        </div>

        <div class="relative z-20 p-4 flex justify-center lg:block">
          <div class="text-[32px] font-black tracking-widest text-center
                      bg-gradient-to-br from-primary-500 to-violet-600 bg-clip-text text-transparent
                      group-hover/title:from-primary-400 group-hover/title:to-violet-500 transition-all
                      hidden lg:block">
            BiliMusic
          </div>
          <div class="lg:hidden text-3xl font-black text-primary-500">
            <span class="relative top-[4px]">BM</span>
          </div>
        </div>
      </div>
    </div>

    <nav class="flex-1 px-2 lg:px-4 space-y-2 mt-2 mb-2 flex flex-col items-center lg:items-stretch">
      <router-link to="/" class="nav-item group/nav" title="概览与登录">
        <HomeIcon class="w-6 h-6 lg:w-5 lg:h-5 lg:mr-3 text-gray-200 group-hover/nav:text-primary-500 transition-colors" />
        <span class="hidden lg:inline">概览与登录</span>
      </router-link>
      <router-link to="/bili" class="nav-item group/nav" title="B站收藏夹">
        <CloudIcon class="w-6 h-6 lg:w-5 lg:h-5 lg:mr-3 text-gray-200 group-hover/nav:text-primary-500 transition-colors" />
        <span class="hidden lg:inline">B站收藏夹</span>
      </router-link>
      <router-link to="/local" class="nav-item group/nav" title="本地媒体库">
        <FolderIcon class="w-6 h-6 lg:w-5 lg:h-5 lg:mr-3 text-gray-200 group-hover/nav:text-primary-500 transition-colors" />
        <span class="hidden lg:inline">本地媒体库</span>
      </router-link>
      <router-link to="/queue" class="nav-item group/nav relative" title="播放队列">
        <QueueListIcon class="w-6 h-6 lg:w-5 lg:h-5 lg:mr-3 text-gray-200 group-hover/nav:text-primary-500 transition-colors" />
        <span class="hidden lg:inline">播放队列</span>
        <span v-if="store.playQueue.length" 
              class="absolute top-1 right-1 lg:static lg:ml-auto text-[10px] font-black text-white bg-red-500 shadow-lg shadow-red-500/20 text-center transition-all duration-300"
              :class="store.playQueue.length < 10 ? 'w-5 h-5 flex items-center justify-center rounded-full' : 'px-2 py-0.5 rounded-full min-w-[1.2em]'">
          {{ store.playQueue.length }}
        </span>
      </router-link>
      <router-link to="/settings" class="nav-item group/nav" title="系统设置">
        <Cog6ToothIcon class="w-6 h-6 lg:w-5 lg:h-5 lg:mr-3 text-gray-200 group-hover/nav:text-primary-500 transition-colors" />
        <span class="hidden lg:inline">系统设置</span>
      </router-link>
    </nav>

    <div class="p-2 lg:p-4">
      <button @click="themeStore.toggleTheme"
              class="flex items-center justify-center w-full py-3 rounded-xl font-bold transition-all duration-200 active:scale-95
                     bg-white/40 dark:bg-white/5 backdrop-blur-md border border-white/50 dark:border-white/10 shadow-sm
                     text-gray-700 hover:bg-white/80 hover:text-primary-600 hover:shadow-md hover:-translate-y-0.5
                     dark:text-gray-300 dark:hover:bg-white/10 dark:hover:text-white"
              title="切换主题">
        <template v-if="themeStore.isDarkMode">
          <MoonIcon class="w-5 h-5 lg:w-4 lg:h-4 lg:mr-2" />
          <span class="hidden lg:inline">暗色模式</span>
        </template>
        <template v-else>
          <SunIcon class="w-5 h-5 lg:w-4 lg:h-4 text-yellow-500 lg:mr-2" />
          <span class="hidden lg:inline">亮色模式</span>
        </template>
      </button>
    </div>
  </div>
</template>

<style scoped>
.nav-item {
  @apply flex items-center justify-center lg:justify-start px-2 lg:px-4 py-3 rounded-xl transition-all font-bold
         bg-white/40 dark:bg-white/5 backdrop-blur-[5px] border border-white/50 dark:border-white/10 shadow-sm
         text-gray-700 hover:bg-white/80 hover:text-primary-600 hover:shadow-md hover:-translate-y-0.5
         dark:text-gray-100 dark:hover:bg-white/10 dark:hover:text-white;
}
.router-link-active {
  @apply bg-white/90 text-primary-600 shadow-md border-primary-500/30
         dark:bg-primary-600/40 dark:text-primary-300 dark:border-primary-500/30;
}

@keyframes shimmer-slide {
  0% {
    transform: translateX(-100%) skewX(-15deg);
  }
  100% {
    transform: translateX(100%) skewX(-15deg);
  }
}

.animate-shimmer-slide {
  animation: shimmer-slide 0.6s cubic-bezier(0.4, 0, 0.2, 1) forwards;
}
</style>
