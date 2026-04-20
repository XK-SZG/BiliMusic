<script setup>
import { ref, watch } from 'vue'
import { XMarkIcon, LinkIcon } from '@heroicons/vue/24/solid'
import systemApi from '../api/system'

const props = defineProps({
  show: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['close', 'confirm'])

const inputText = ref('')

// 监听弹窗显示状态，控制剪贴板监听
watch(() => props.show, async (newVal) => {
  if (newVal) {
    // 弹窗打开时暂停剪贴板监听
    try {
      await systemApi.pauseClipboard()
      console.log('剪贴板监听已暂停')
    } catch (e) {
      console.error('暂停剪贴板监听失败:', e)
    }
  } else {
    // 弹窗关闭时恢复剪贴板监听
    try {
      await systemApi.resumeClipboard()
      console.log('剪贴板监听已恢复')
    } catch (e) {
      console.error('恢复剪贴板监听失败:', e)
    }
  }
})

function handleConfirm() {
  if (!inputText.value.trim()) {
    return
  }
  emit('confirm', inputText.value.trim())
  inputText.value = ''
}

function handleClose() {
  inputText.value = ''
  emit('close')
}

function handleKeydown(e) {
  if (e.key === 'Enter') {
    handleConfirm()
  } else if (e.key === 'Escape') {
    handleClose()
  }
}
</script>

<template>
  <transition name="modal-fade">
    <div v-if="show" class="fixed inset-0 z-[300] flex items-center justify-center p-4" @click.self="handleClose">
      <!-- 背景遮罩 -->
      <div class="absolute inset-0 bg-black/50 backdrop-blur-sm"></div>
      
      <!-- 弹窗内容 -->
      <div class="relative bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-white/10 w-full max-w-md overflow-hidden">
        <!-- 头部 -->
        <div class="flex items-center justify-between p-6 border-b border-gray-200 dark:border-white/10">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-xl bg-primary-100 dark:bg-primary-500/20 flex items-center justify-center">
              <LinkIcon class="w-6 h-6 text-primary-500" />
            </div>
            <h3 class="text-lg font-black text-gray-800 dark:text-white">添加视频</h3>
          </div>
          <button @click="handleClose" class="p-2 hover:bg-gray-100 dark:hover:bg-white/5 rounded-lg transition-colors">
            <XMarkIcon class="w-5 h-5 text-gray-500" />
          </button>
        </div>
        
        <!-- 内容 -->
        <div class="p-6 space-y-4">
          <div>
            <label class="block text-sm font-bold text-gray-700 dark:text-gray-300 mb-2">
              输入 B 站视频链接或 BV 号
            </label>
            <textarea
              v-model="inputText"
              @keydown="handleKeydown"
              placeholder="支持以下格式：&#10;• https://www.bilibili.com/video/BV1xx...&#10;• BV1xx4y1x7xx&#10;• BV1xx4y1x7xx?p=2&#10;• 包含 BV 号的任意文本"
              class="w-full px-4 py-3 bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-white/20 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none"
              rows="5"
              autofocus></textarea>
          </div>
          
          <div class="bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20 rounded-xl p-3">
            <div class="text-xs text-blue-700 dark:text-blue-300 space-y-1">
              <div class="font-bold mb-1">💡 提示</div>
              <div>• 支持分集视频（如 ?p=2）</div>
              <div>• 可以粘贴完整链接或纯 BV 号</div>
              <div>• 系统会自动提取第一个匹配的 BV 号</div>
            </div>
          </div>
        </div>
        
        <!-- 底部按钮 -->
        <div class="flex gap-3 p-6 border-t border-gray-200 dark:border-white/10">
          <button @click="handleClose" class="flex-1 px-4 py-2.5 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-xl text-sm font-bold hover:bg-gray-300 dark:hover:bg-gray-600 transition active:scale-95">
            取消
          </button>
          <button @click="handleConfirm" :disabled="!inputText.trim()" class="flex-1 px-4 py-2.5 bg-primary-500 text-white rounded-xl text-sm font-bold hover:bg-primary-600 transition shadow-lg shadow-primary-500/30 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed">
            下一步
          </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.modal-fade-enter-active, .modal-fade-leave-active {
  transition: opacity 0.3s ease;
}

.modal-fade-enter-active > div:last-child,
.modal-fade-leave-active > div:last-child {
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.modal-fade-enter-from, .modal-fade-leave-to {
  opacity: 0;
}

.modal-fade-enter-from > div:last-child,
.modal-fade-leave-to > div:last-child {
  transform: scale(0.95) translateY(20px);
}
</style>
