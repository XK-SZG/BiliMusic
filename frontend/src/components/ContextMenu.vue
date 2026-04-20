<template>
  <teleport to="body">
    <transition name="context-fade">
      <div
        v-if="visible"
        ref="menuRef"
        class="fixed z-[9999] min-w-[180px] rounded-xl shadow-2xl border backdrop-blur-xl overflow-hidden"
        :class="[
          themeStore.isDarkMode 
            ? 'bg-gray-900/95 border-white/10' 
            : 'bg-white/95 border-gray-200'
        ]"
        :style="menuStyle"
        @click.stop
        @contextmenu.prevent
      >
        <div class="py-1">
          <template v-for="(item, index) in items" :key="index">
            <!-- 分隔线 -->
            <div
              v-if="item.type === 'divider'"
              class="h-px my-1 mx-2"
              :class="themeStore.isDarkMode ? 'bg-white/10' : 'bg-gray-200'"
            ></div>
            
            <!-- 菜单项 -->
            <button
              v-else
              :disabled="item.disabled"
              class="w-full px-4 py-2.5 flex items-center gap-3 transition-all duration-150 text-left"
              :class="[
                item.disabled 
                  ? 'opacity-40 cursor-not-allowed' 
                  : themeStore.isDarkMode
                    ? 'hover:bg-white/10 active:bg-white/20'
                    : 'hover:bg-gray-100 active:bg-gray-200',
                item.danger && !item.disabled
                  ? 'text-red-500 hover:text-red-600'
                  : themeStore.isDarkMode
                    ? 'text-gray-200'
                    : 'text-gray-800'
              ]"
              @click="handleItemClick(item)"
            >
              <component
                v-if="item.icon"
                :is="item.icon"
                class="w-5 h-5 shrink-0"
              />
              <span class="flex-1 text-sm font-medium">{{ item.label }}</span>
              <span
                v-if="item.shortcut"
                class="text-xs opacity-60 font-mono"
              >
                {{ item.shortcut }}
              </span>
            </button>
          </template>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useThemeStore } from '../stores/modules/theme'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  x: {
    type: Number,
    default: 0
  },
  y: {
    type: Number,
    default: 0
  },
  items: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['close', 'select'])

const themeStore = useThemeStore()
const menuRef = ref(null)
const menuWidth = ref(180)
const menuHeight = ref(0)

const menuStyle = computed(() => {
  let x = props.x
  let y = props.y
  
  // 防止菜单超出屏幕右侧
  if (x + menuWidth.value > window.innerWidth) {
    x = window.innerWidth - menuWidth.value - 10
  }
  
  // 防止菜单超出屏幕底部
  if (y + menuHeight.value > window.innerHeight) {
    y = window.innerHeight - menuHeight.value - 10
  }
  
  // 防止菜单超出屏幕左侧和顶部
  x = Math.max(10, x)
  y = Math.max(10, y)
  
  return {
    left: `${x}px`,
    top: `${y}px`
  }
})

const handleItemClick = (item) => {
  if (item.disabled) return
  emit('select', item)
  emit('close')
}

const handleClickOutside = (e) => {
  if (menuRef.value && !menuRef.value.contains(e.target)) {
    emit('close')
  }
}

watch(() => props.visible, async (newVal) => {
  if (newVal) {
    await nextTick()
    if (menuRef.value) {
      menuHeight.value = menuRef.value.offsetHeight
      menuWidth.value = menuRef.value.offsetWidth
    }
    // 延迟添加点击监听，避免立即触发关闭
    setTimeout(() => {
      document.addEventListener('click', handleClickOutside)
      document.addEventListener('contextmenu', handleClickOutside)
    }, 100)
  } else {
    document.removeEventListener('click', handleClickOutside)
    document.removeEventListener('contextmenu', handleClickOutside)
  }
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
  document.removeEventListener('contextmenu', handleClickOutside)
})
</script>

<style scoped>
.context-fade-enter-active,
.context-fade-leave-active {
  transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1);
}

.context-fade-enter-from {
  opacity: 0;
  transform: scale(0.95) translateY(-5px);
}

.context-fade-leave-to {
  opacity: 0;
  transform: scale(0.95);
}
</style>
