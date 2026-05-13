<script setup>
import { ref, watch, reactive } from 'vue'

const props = defineProps({
  show: Boolean,
  type: String, // 'input' | 'score' | 'tags' | 'confirm' | 'checklist' | 'range' | 'title_filter' | 'edit_metadata'
  title: String,
  initialValue: [String, Number, Array, Object],
  extraData: Object
})

import { XMarkIcon, CheckIcon, ArrowsRightLeftIcon, PlusIcon } from '@heroicons/vue/24/solid'

const emit = defineEmits(['close', 'confirm', 'remove-tag', 'create-collection'])

// 状态定义
const inputValue = ref('')
const scoreValue = ref(5.0)
const newTag = ref('')
const selectedOptions = ref([])
const showCreateCollection = ref(false)
const newCollectionName = ref('')

// Range 模式
const rangeStart = ref(0)
const rangeEnd = ref(0)

// 标题过滤模式
const titleText = ref('')
const isStrict = ref(false)

// 元数据编辑模式
const editData = reactive({ title: '', owner: '', cover: null })

// 弹窗打开时初始化数据
watch(() => props.show, (isShowing) => {
  if (isShowing) {
    if (props.type === 'input') inputValue.value = props.initialValue || ''
    if (props.type === 'score') scoreValue.value = Math.max(0.5, Number(props.initialValue) || 5.0)
    if (props.type === 'tags') {
      newTag.value = ''
    }
    if (props.type === 'checklist') {
      selectedOptions.value = Array.isArray(props.initialValue) ? [...props.initialValue] : []
      showCreateCollection.value = false
      newCollectionName.value = ''
    }
    if (props.type === 'range') {
      rangeStart.value = props.initialValue?.start || 0
      rangeEnd.value = props.initialValue?.end || 0
    }
    if (props.type === 'title_filter') {
      titleText.value = props.initialValue?.text || ''
      isStrict.value = props.initialValue?.isStrict || false
    }
    if (props.type === 'edit_metadata') {
      editData.title = props.initialValue?.title || ''
      editData.owner = props.initialValue?.owner || ''
      editData.cover = null
    }
  }
})

// 时长/评分自动填充逻辑
watch(rangeStart, (newVal) => {
  if (props.type === 'range' && rangeEnd.value < newVal) {
    rangeEnd.value = newVal
  }
})

function handleCoverChange(e) {
  editData.cover = e.target.files[0] || null
}

function handleCancel() {
  if (props.type === 'confirm') {
    // 如果设置了 requireConfirm，点击取消或遮罩层应该传递 null 表示取消操作
    if (props.extraData?.requireConfirm) {
      emit('confirm', null)
      // 延迟emit close，确保confirm事件先被处理
      setTimeout(() => {
        emit('close')
      }, 0)
      return
    }
  }
  emit('close')
}

function handleCancelButton() {
  if (props.type === 'confirm' && props.extraData?.requireConfirm) {
    // 点击取消按钮时传递 false 表示"仅播放"
    emit('confirm', false)
    setTimeout(() => {
      emit('close')
    }, 0)
    return
  }
  emit('close')
}

function handleConfirm() {
  let val = null
  if (props.type === 'input') val = inputValue.value
  if (props.type === 'score') val = scoreValue.value
  if (props.type === 'checklist') val = selectedOptions.value
  if (props.type === 'confirm') val = true
  if (props.type === 'range') {
    if (rangeEnd.value < rangeStart.value) rangeEnd.value = rangeStart.value
    val = { start: rangeStart.value, end: rangeEnd.value }
  }
  if (props.type === 'title_filter') {
    val = { text: titleText.value, isStrict: isStrict.value }
  }
  if (props.type === 'edit_metadata') {
    val = { ...editData }
  }

  if (props.type === 'tags') {
    if (!newTag.value.trim()) {
      emit('close')
      return
    }
    emit('confirm', newTag.value.trim())
    newTag.value = ''
    return
  }

  emit('confirm', val)
  emit('close')
}

function toggleOption(id) {
  const idx = selectedOptions.value.indexOf(id)
  if (idx > -1) selectedOptions.value.splice(idx, 1)
  else selectedOptions.value.push(id)
}

async function handleCreateCollection() {
  if (!newCollectionName.value.trim()) return
  
  emit('create-collection', newCollectionName.value.trim())
  newCollectionName.value = ''
  showCreateCollection.value = false
}
</script>

<template>
  <Teleport to="body">
    <transition name="fade">
      <div v-if="show" class="fixed inset-0 z-[9999] flex items-center justify-center p-4">
        <div class="absolute inset-0 bg-black/70 backdrop-blur-md" @click.self="handleCancel"></div>

      <div class="relative bg-white dark:bg-gray-900 w-full max-w-sm rounded-3xl shadow-2xl overflow-hidden border border-gray-100 dark:border-white/10 p-8 transform transition-all"
           :class="{'border-red-500/50': extraData?.isDanger}">

        <div class="flex flex-col items-center mb-6">
          <slot name="confirm-icon"></slot>
          <h3 class="text-xl font-black text-gray-800 dark:text-white text-center tracking-tight">{{ title }}</h3>
        </div>

        <!-- 1. 普通输入模式 -->
        <div v-if="type === 'input'">
          <input v-model="inputValue" @keyup.enter="handleConfirm"
                 class="w-full bg-gray-100 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-2xl px-5 py-4 outline-none focus:ring-2 focus:ring-pink-500 font-medium text-gray-800 dark:text-white placeholder-gray-400 dark:placeholder-gray-500"
                 autofocus />
        </div>

        <!-- 2. 评分模式 -->
        <div v-if="type === 'score'" class="space-y-6">
          <div class="text-center text-5xl font-black text-pink-500 tabular-nums">{{ scoreValue.toFixed(1) }}</div>
          <input type="range" min="0.5" max="10" step="0.5" v-model.number="scoreValue"
                 class="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer accent-pink-500" />
        </div>

        <!-- 3. 标签/UP/BV 管理模式 -->
        <div v-if="type === 'tags'" class="space-y-4">
          <div v-if="extraData?.existingTags?.length > 0" class="flex flex-wrap gap-2 mb-4 p-3 bg-gray-50 dark:bg-white/5 rounded-2xl max-h-40 overflow-y-auto">
            <span v-for="tag in extraData.existingTags" :key="tag.id || tag"
                  class="px-2 py-1 bg-pink-500/10 text-pink-500 rounded-lg text-xs font-bold flex items-center gap-1">
              #{{ tag.name || tag }}
              <button @click="$emit('remove-tag', tag.id || tag)" class="hover:text-red-500 transition-colors">
                <XMarkIcon class="w-3 h-3" />
              </button>
            </span>
          </div>
          <div class="flex gap-2">
            <input v-model="newTag" :placeholder="extraData?.placeholder || '输入内容...'" @keyup.enter="handleConfirm"
                   class="flex-1 bg-gray-100 dark:bg-white/5 border-none rounded-xl px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-pink-500 text-gray-800 dark:text-white placeholder-gray-400 dark:placeholder-gray-500" />
            <button @click="handleConfirm" class="px-4 py-2 bg-pink-500 text-white rounded-xl font-bold">添加</button>
          </div>
        </div>

        <!-- 4. 范围模式 (时长/评分) -->
        <div v-if="type === 'range'" class="space-y-4">
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-1">
              <label class="text-[10px] font-black text-gray-400 uppercase tracking-widest ml-1">起始</label>
              <input type="number" v-model.number="rangeStart" step="any"
                     class="w-full bg-gray-100 dark:bg-white/5 border-none rounded-xl px-4 py-3 text-sm focus:ring-2 focus:ring-pink-500 text-gray-800 dark:text-white" />
            </div>
            <div class="space-y-1">
              <label class="text-[10px] font-black text-gray-400 uppercase tracking-widest ml-1">结束</label>
              <input type="number" v-model.number="rangeEnd" step="any"
                     class="w-full bg-gray-100 dark:bg-white/5 border-none rounded-xl px-4 py-3 text-sm focus:ring-2 focus:ring-pink-500 text-gray-800 dark:text-white" />
            </div>
          </div>
          <p class="text-[10px] text-gray-400 text-center italic">{{ extraData?.unit || '' }}</p>
        </div>

        <!-- 5. 标题过滤模式 -->
        <div v-if="type === 'title_filter'" class="space-y-4">
          <input v-model="titleText" placeholder="关键词..."
                 class="w-full bg-gray-100 dark:bg-white/5 border-none rounded-xl px-4 py-3 text-sm focus:ring-2 focus:ring-pink-500 text-gray-800 dark:text-white placeholder-gray-400 dark:placeholder-gray-500" />
          <button @click="isStrict = !isStrict" 
                  class="w-full py-3 rounded-xl text-xs font-black transition-all flex items-center justify-center gap-2"
                  :class="isStrict ? 'bg-pink-500 text-white shadow-lg' : 'bg-gray-100 dark:bg-white/5 text-gray-500'">
            <ArrowsRightLeftIcon class="w-4 h-4" />
            {{ isStrict ? '严格匹配 (绝对同名)' : '模糊匹配 (包含关键词)' }}
          </button>
        </div>

        <!-- 6. 多选列表模式 (Checklist) -->
        <div v-if="type === 'checklist'" class="space-y-3">
          <div class="space-y-2 max-h-64 overflow-y-auto scrollbar-thin pr-1">
            <div v-for="opt in (extraData?.options || [])" :key="opt.id"
                 @click="toggleOption(opt.id)"
                 class="flex items-center justify-between p-4 rounded-2xl cursor-pointer transition-all border"
                 :class="selectedOptions.includes(opt.id)
                   ? 'bg-pink-500/10 border-pink-500/50 text-pink-500'
                   : 'bg-gray-50 dark:bg-white/5 border-transparent text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10'">
              <span class="font-bold text-sm">{{ opt.label }}</span>
              <div class="w-6 h-6 rounded-full border-2 flex items-center justify-center transition-all"
                   :class="selectedOptions.includes(opt.id) ? 'bg-pink-500 border-pink-500 scale-110' : 'border-gray-300 dark:border-gray-600'">
                 <CheckIcon v-if="selectedOptions.includes(opt.id)" class="w-4 h-4 text-white" />
              </div>
            </div>
          </div>
          
          <!-- 新建媒体库区域 -->
          <div v-if="extraData?.allowCreate" class="border-t border-gray-200 dark:border-white/10 pt-3">
            <transition name="expand">
              <div v-if="showCreateCollection" class="mb-3 space-y-2">
                <input
                  v-model="newCollectionName"
                  type="text"
                  placeholder="输入媒体库名称"
                  class="w-full px-3 py-2 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-white/20 rounded-lg text-sm text-gray-800 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-pink-500"
                  @keyup.enter="handleCreateCollection"
                  @keyup.esc="showCreateCollection = false" />
                <div class="flex gap-2">
                  <button @click="handleCreateCollection" class="flex-1 px-3 py-2 bg-pink-500 text-white rounded-lg text-xs font-bold hover:bg-pink-600 transition active:scale-95">
                    创建
                  </button>
                  <button @click="showCreateCollection = false; newCollectionName = ''" class="px-3 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg text-xs font-bold hover:bg-gray-300 dark:hover:bg-gray-600 transition active:scale-95">
                    取消
                  </button>
                </div>
              </div>
            </transition>
            
            <button
              v-if="!showCreateCollection"
              @click="showCreateCollection = true"
              class="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-gray-100 dark:bg-white/5 text-gray-700 dark:text-gray-300 rounded-xl text-sm font-bold hover:bg-gray-200 dark:hover:bg-white/10 transition active:scale-95">
              <PlusIcon class="w-5 h-5" />
              <span>新建本地媒体库</span>
            </button>
          </div>
        </div>

        <!-- 7. 确认模式 -->
        <div v-if="type === 'confirm'" class="text-center text-gray-500 dark:text-gray-400 font-medium px-2">
          {{ extraData?.message || '此操作无法撤销，请确认。' }}
        </div>

        <!-- 8. 元数据编辑模式 -->
        <div v-if="type === 'edit_metadata'" class="space-y-4">
          <div class="flex flex-col gap-1">
            <label class="text-[10px] font-black text-gray-400 uppercase tracking-widest ml-1">标题</label>
            <input v-model="editData.title" class="w-full bg-gray-100 dark:bg-white/5 border-none rounded-xl px-4 py-3 text-sm focus:ring-2 focus:ring-pink-500 text-gray-800 dark:text-white" />
          </div>
          <div class="flex flex-col gap-1">
            <label class="text-[10px] font-black text-gray-400 uppercase tracking-widest ml-1">作者/UP主</label>
            <input v-model="editData.owner" class="w-full bg-gray-100 dark:bg-white/5 border-none rounded-xl px-4 py-3 text-sm focus:ring-2 focus:ring-pink-500 text-gray-800 dark:text-white" />
          </div>
          <div class="flex flex-col gap-1 mt-2">
            <label class="text-[10px] font-black text-gray-400 uppercase tracking-widest ml-1">封面图片 (留空则不修改)</label>
            <input type="file" accept="image/*" @change="handleCoverChange" class="text-xs text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-black file:bg-pink-500/10 file:text-pink-500 hover:file:bg-pink-500/20 transition-all cursor-pointer" />
          </div>
        </div>

        <!-- 底部按钮 -->
        <div class="mt-8 flex gap-3">
          <button @click="handleCancelButton" class="flex-1 py-3 text-gray-400 font-bold hover:text-gray-600 dark:hover:text-white transition">
            {{ extraData?.cancelText || '取消' }}
          </button>
          <button @click="handleConfirm"
                  class="flex-1 py-3 text-white rounded-2xl font-black shadow-lg transition transform active:scale-95"
                  :class="extraData?.isDanger ? 'bg-red-500 shadow-red-500/30 hover:bg-red-600' : 'bg-pink-500 shadow-pink-500/30 hover:bg-pink-600'">
            {{ extraData?.confirmText || (type === 'tags' ? '添加' : '确定') }}
          </button>
        </div>

        </div>
      </div>
    </transition>
  </Teleport>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
input[type=number]::-webkit-inner-spin-button,
input[type=number]::-webkit-outer-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.expand-enter-active, .expand-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}

.expand-enter-from, .expand-leave-to {
  opacity: 0;
  max-height: 0;
}

.expand-enter-to, .expand-leave-from {
  opacity: 1;
  max-height: 200px;
}

.scrollbar-thin::-webkit-scrollbar { width: 4px; }
.scrollbar-thin::-webkit-scrollbar-thumb { background: rgba(156, 163, 175, 0.2); border-radius: 10px; }
</style>
