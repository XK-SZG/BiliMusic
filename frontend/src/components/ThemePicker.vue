# -*- coding: utf-8 -*-
# Path: frontend/src/components/ThemePicker.vue

<script setup>
import { usePlayerStore } from '../stores/playerStore'
import { CheckIcon, SwatchIcon } from '@heroicons/vue/24/solid'

const store = usePlayerStore()

const colors = [
  { name: '暗黑', hex: '#0A0A0A' },
  { name: '纯白', hex: '#FFFFFF' },
  { name: '粉色', hex: '#FF3366' },
  { name: '紫色', hex: '#7000FF' },
  { name: '蓝色', hex: '#0066FF' },
  { name: '青色', hex: '#00F5FF' },
  { name: '绿色', hex: '#00FF88' },
  { name: '橘色', hex: '#FFAB00' }
]

defineEmits(['close'])
</script>

<template>
  <div class="w-72 p-6 rounded-[2.5rem] bg-white/90 dark:bg-gray-900/90 backdrop-blur-2xl border border-white/20 dark:border-white/10 shadow-2xl animate-fade-in">
    <div class="flex items-center gap-3 mb-6">
      <SwatchIcon class="w-5 h-5 text-pink-500" />
      <h3 class="font-black text-sm uppercase tracking-widest text-gray-800 dark:text-white">主题实验室</h3>
    </div>

    <div class="space-y-6">
      <!-- 起始色 -->
      <div>
        <p class="text-[10px] font-bold text-gray-400 uppercase tracking-tighter mb-3 ml-1">起始色彩 (Start)</p>
        <div class="grid grid-cols-4 gap-3">
          <button v-for="c in colors" :key="'s'+c.hex"
                  @click="store.updateTheme({ start: c.hex })"
                  class="w-full aspect-square rounded-2xl transition-all active:scale-90 relative overflow-hidden"
                  :style="{ backgroundColor: c.hex }"
                  :title="c.name">
            <div v-if="store.theme.start === c.hex" class="absolute inset-0 flex items-center justify-center bg-black/20 backdrop-blur-[2px]">
              <CheckIcon class="w-5 h-5 text-white" />
            </div>
          </button>
        </div>
      </div>

      <!-- 结束色 -->
      <div>
        <p class="text-[10px] font-bold text-gray-400 uppercase tracking-tighter mb-3 ml-1">结束色彩 (End)</p>
        <div class="grid grid-cols-4 gap-3">
          <button v-for="c in colors" :key="'e'+c.hex"
                  @click="store.updateTheme({ end: c.hex })"
                  class="w-full aspect-square rounded-2xl transition-all active:scale-90 relative overflow-hidden"
                  :style="{ backgroundColor: c.hex }"
                  :title="c.name">
            <div v-if="store.theme.end === c.hex" class="absolute inset-0 flex items-center justify-center bg-black/20 backdrop-blur-[2px]">
              <CheckIcon class="w-5 h-5 text-white" />
            </div>
          </button>
        </div>
      </div>
    </div>

    <div class="mt-6 pt-4 border-t border-gray-100 dark:border-white/5 flex justify-center">
       <button @click="$emit('close')" class="text-[10px] font-black uppercase tracking-widest text-pink-500 hover:opacity-70 transition-opacity">
         完成配置
       </button>
    </div>
  </div>
</template>
