# -*- coding: utf-8 -*- # Path: frontend/src/components/PlayerBar.vue

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from "vue";
import { usePlayerStore } from "../stores/modules/player";
import { useSettingsStore } from "../stores/modules/settings";
import { useThemeStore } from "../stores/modules/theme";
import StickerLayer from "./StickerLayer.vue";
import {
  PlayIcon,
  PauseIcon,
  BackwardIcon,
  ForwardIcon,
  SpeakerWaveIcon,
  SpeakerXMarkIcon,
  AdjustmentsHorizontalIcon,
  HandThumbUpIcon,
  HandThumbDownIcon,
  PowerIcon,
  ArrowsPointingInIcon,
  MusicalNoteIcon,
  ClockIcon,
  MoonIcon,
} from "@heroicons/vue/24/solid";

const store = usePlayerStore();
const settingsStore = useSettingsStore();
const themeStore = useThemeStore();

// --- 格式化时间 ---
function formatTime(seconds) {
  if (!seconds || isNaN(seconds)) return "00:00";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0)
    return `${h}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

function formatTimeLeft(minutes) {
  if (minutes <= 0) return '00:00';
  const totalSeconds = Math.ceil(minutes * 60);
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  if (m > 60) {
    const h = Math.floor(m / 60);
    const remM = m % 60;
    return `${h}:${remM.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

function onSeek(e) {
  const percent = e.target.value / 100;
  const time = percent * store.duration;
  store.seek(time);
}

let previousVolume = 0.7;
function toggleMute() {
  if (store.volume > 0) {
    previousVolume = store.volume;
    store.setVolume(0);
  } else {
    store.setVolume(
      previousVolume > 0
        ? previousVolume
        : settingsStore.settings.defaultVolume || 0.7,
    );
  }
}

function handleTogglePlay() {
  if (!store.audioElement) return;
  if (!store.currentVideo) {
    if (store.playQueue.length > 0) {
      const resumeIdx = store.queueIndex >= 0 ? store.queueIndex : 0;
      store.queueIndex = resumeIdx;
      store.currentVideo = store.playQueue[resumeIdx];
      store._loadAndPlay();
    } else {
      store.showToast("队列空空如也", "info");
    }
    return;
  }

  // 检查是否是重新加载后的“恢复播放”状态 (src 为空但 currentVideo 有值)
  if (
    !store.audioElement.src ||
    store.audioElement.src === window.location.href
  ) {
    // 仅进行视频层面的续播，不再传入 currentTime 参数
    store._loadAndPlay();
    return;
  }

  if (store.isPlaying) {
    store.audioElement.pause();
    store.isPlaying = false;
  } else {
    store.audioElement
      .play()
      .then(() => {
        store.isPlaying = true;
      })
      .catch(() => {});
  }
}

const showModePopover = ref(false);
const showVolumePopover = ref(false);
const showLengthModal = ref(false);

const tempLengthType = ref("count");
const tempLengthTarget = ref(1);

function openLengthControlModal(e) {
  e.stopPropagation();
  showLengthModal.value = true;
  showModePopover.value = false;
  showVolumePopover.value = false;
  tempLengthType.value = store.lengthControl.type;
  tempLengthTarget.value = store.lengthControl.target;
}

function disableLengthControl() {
  store.lengthControl.enabled = false;
  showLengthModal.value = false;
}

function confirmLengthControl() {
  store.lengthControl.enabled = true;
  store.lengthControl.type = tempLengthType.value;
  let target = tempLengthTarget.value || 1;
  if (tempLengthType.value === 'count') {
    target = Math.max(1, Math.floor(target));
  } else {
    target = Math.max(0.1, target);
  }
  store.lengthControl.target = target;
  store.lengthControl.current = 0;
  showLengthModal.value = false;
  store.showToast("已设置播放长度控制", "success");
}

function toggleAutoAction(action) {
  if (store.autoActionType === action) {
    store.autoActionType = 'none';
  } else {
    store.autoActionType = action;
  }
  localStorage.setItem('player_auto_action', store.autoActionType);
}

let volumeHideTimer = null;
let volumeAutoCloseTimer = null;

watch(
  () => store.volumeShowTrigger,
  () => {
    showVolume();
    if (volumeAutoCloseTimer) clearTimeout(volumeAutoCloseTimer);
    volumeAutoCloseTimer = setTimeout(() => {
      hideVolume();
    }, 2000);
  },
);

function openModePopover(e) {
  e.stopPropagation();
  showModePopover.value = !showModePopover.value;
  showVolumePopover.value = false;
}

function handleScore(delta) {
  if (store.userReacted) {
    store.showToast("此视频本轮已评分", "info");
    return;
  }
  store.updateScoreBatch(delta).catch(() => {});
}

function showVolume() {
  if (volumeHideTimer) clearTimeout(volumeHideTimer);
  showVolumePopover.value = true;
}

function hideVolume() {
  if (volumeHideTimer) clearTimeout(volumeHideTimer);
  volumeHideTimer = setTimeout(() => {
    showVolumePopover.value = false;
    showVolumeInputPopover.value = false;
  }, 300); // 延迟 300ms 隐藏，防误触
}

function handleVolumeWheel(e) {
  e.preventDefault();
  const step = 0.02; // 默认步长 2%
  if (e.deltaY < 0) {
    store.setVolume(Math.min(1, store.volume + step));
  } else {
    store.setVolume(Math.max(0, store.volume - step));
  }
}

const showVolumeInputPopover = ref(false);
const manualVolumeInput = ref("");
const volumeInputRef = ref(null);

function toggleVolumeInput(e) {
  e.stopPropagation();
  showVolumeInputPopover.value = !showVolumeInputPopover.value;
  if (showVolumeInputPopover.value) {
    manualVolumeInput.value = ""; // 清空初始值，直接覆盖
  }
}

function handleNumpadInput(num) {
  if (manualVolumeInput.value.length >= 3) {
    manualVolumeInput.value = num.toString(); // 如果超过长度，重新开始输入
  } else {
    manualVolumeInput.value += num.toString();
  }
  let val = parseInt(manualVolumeInput.value);
  if (!isNaN(val)) {
    val = Math.max(0, Math.min(100, val));
    store.setVolume(val / 100);
  }
}

function handleNumpadClear() {
  manualVolumeInput.value = "";
  store.setVolume(0);
}

function handleVolumeKeydown(e) {
  if (showVolumePopover.value || showVolumeInputPopover.value) {
    if (e.key >= "0" && e.key <= "9") {
      e.preventDefault();
      e.stopPropagation();
      if (!showVolumeInputPopover.value) {
        showVolumeInputPopover.value = true;
        manualVolumeInput.value = "";
      }
      handleNumpadInput(e.key);
    } else if (e.key === "Backspace" || e.key === "c" || e.key === "C") {
      e.preventDefault();
      e.stopPropagation();
      handleNumpadClear();
    } else if (e.key === "Enter" || e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      showVolumeInputPopover.value = false;
      showVolumePopover.value = false;
    }
  }
}

onMounted(() => {
  window.addEventListener("click", closeAll);
  window.addEventListener("keydown", handleVolumeKeydown);
});

onUnmounted(() => {
  window.removeEventListener("click", closeAll);
  window.removeEventListener("keydown", handleVolumeKeydown);
});

const closeAll = () => {
  showModePopover.value = false;
  showVolumePopover.value = false;
  showVolumeInputPopover.value = false;
};

// 动态样式计算
const barStyle = computed(() => ({
  backgroundColor: themeStore.isDarkMode
    ? `rgba(17, 24, 39, ${settingsStore.settings.uiOpacity})` // gray-900
    : `rgba(255, 255, 255, ${settingsStore.settings.uiOpacity})`, // white
  backdropFilter: `blur(${settingsStore.settings.uiBlur}px)`,
  WebkitBackdropFilter: `blur(${settingsStore.settings.uiBlur}px)`,
}));
</script>

<template>
  <div
    class="fixed bottom-0 h-20 flex flex-col z-50 transition-all duration-[600ms] cubic-bezier(0.4, 0, 0.2, 1)"
    :class="
      settingsStore.settings.sidebarPosition === 'right'
        ? 'right-20 md:right-20 lg:right-56 left-0'
        : 'left-20 md:left-20 lg:left-56 right-0'
    "
    :style="barStyle"
  >
    <StickerLayer target="playerBar" />

    <div
      class="absolute top-0 left-0 right-0 h-1.5 group z-10 hover:h-2 transition-all cursor-pointer"
    >
      <div
        class="absolute inset-0 bg-gray-200 dark:bg-white/5 rounded-t-full overflow-hidden"
      >
        <div
          class="absolute top-0 left-0 h-full bg-gray-400/20 transition-all duration-500"
          :style="{ width: (store.buffered / store.duration) * 100 + '%' }"
        ></div>
        <div
          class="absolute top-0 left-0 h-full bg-primary-500"
          :style="{ width: (store.currentTime / store.duration) * 100 + '%' }"
        ></div>

        <!-- 软裁剪视觉遮罩 -->
        <template
          v-if="
            store.currentVideo &&
            (store.currentVideo.trim_start > 0 ||
              (store.currentVideo.trim_end > 0 &&
                store.currentVideo.trim_end < store.duration))
          "
        >
          <!-- Start Mask -->
          <div
            v-if="store.currentVideo.trim_start > 0"
            class="absolute top-0 left-0 h-full bg-black/30 dark:bg-black/50 pointer-events-none"
            :style="{
              width:
                (store.currentVideo.trim_start / store.duration) * 100 + '%',
            }"
          ></div>
          <!-- End Mask -->
          <div
            v-if="store.currentVideo.trim_end > 0"
            class="absolute top-0 right-0 h-full bg-black/30 dark:bg-black/50 pointer-events-none"
            :style="{
              left: (store.currentVideo.trim_end / store.duration) * 100 + '%',
            }"
          ></div>
        </template>
      </div>

      <!-- 小电视滑块 -->
      <div
        class="absolute top-1/2 -translate-y-1/2 w-6 h-6 pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-20"
        :style="{
          left: `calc(${(store.currentTime / store.duration) * 100 || 0}% - 12px)`,
        }"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 18 18"
          width="24"
          height="24"
          class="drop-shadow-lg filter"
        >
          <defs>
            <clipPath id="__lottie_element_55">
              <rect width="18" height="18" x="0" y="0"></rect>
            </clipPath>
          </defs>
          <g clip-path="url(#__lottie_element_55)">
            <g
              transform="matrix(0.98834,-0.72757,0.67759,0.92044,7.3224,-0.76067)"
            >
              <g
                transform="matrix(0.99377,-0.11138,0.11138,0.99377,-2.524,1.385)"
              >
                <path
                  fill="rgb(51,51,51)"
                  d="M0.75,-1.25 C0.75,-1.25 0.75,1.25 0.75,1.25 C0.75,1.66 0.41,2 0,2 C0,2 0,2 0,2 C-0.41,2 -0.75,1.66 -0.75,1.25 C-0.75,1.25 -0.75,-1.25 -0.75,-1.25 C-0.75,-1.66 -0.41,-2 0,-2 C0,-2 0,-2 0,-2 C0.41,-2 0.75,-1.66 0.75,-1.25z"
                ></path>
              </g>
            </g>
            <g
              transform="matrix(1.14366,0.75359,-0.63171,0.95870,16.007,2.90289)"
            >
              <g
                transform="matrix(0.99286,0.11927,-0.11927,0.99286,-2.524,1.385)"
              >
                <path
                  fill="rgb(51,51,51)"
                  d="M0.75,-1.25 C0.75,-1.25 0.75,1.25 0.75,1.25 C0.75,1.66 0.41,2 0,2 C0,2 0,2 0,2 C-0.41,2 -0.75,1.66 -0.75,1.25 C-0.75,1.25 -0.75,-1.25 -0.75,-1.25 C-0.75,-1.66 -0.41,-2 0,-2 C0,-2 0,-2 0,-2 C0.41,-2 0.75,-1.66 0.75,-1.25z"
                ></path>
              </g>
            </g>
            <g transform="matrix(1,0,0,1,8.891,8.406)">
              <g transform="matrix(1,0,0,1,0.091,1.101)">
                <path
                  fill="rgb(255,255,255)"
                  d="M7,-3 C7,-3 7,3 7,3 C7,4.38 5.88,5.5 4.5,5.5 C4.5,5.5 -4.5,5.5 -4.5,5.5 C-5.88,5.5 -7,4.38 -7,3 C-7,3 -7,-3 -7,-3 C-7,-4.38 -5.88,-5.5 -4.5,-5.5 C-4.5,-5.5 4.5,-5.5 4.5,-5.5 C5.88,-5.5 7,-4.38 7,-3z"
                ></path>
                <path
                  fill="none"
                  stroke="rgb(51,51,51)"
                  stroke-width="1.5"
                  d="M7,-3 C7,-3 7,3 7,3 C7,4.38 5.88,5.5 4.5,5.5 C4.5,5.5 -4.5,5.5 -4.5,5.5 C-5.88,5.5 -7,4.38 -7,3 C-7,3 -7,-3 -7,-3 C-7,-4.38 -5.88,-5.5 -4.5,-5.5 C-4.5,-5.5 4.5,-5.5 4.5,-5.5 C5.88,-5.5 7,-4.38 7,-3z"
                ></path>
              </g>
            </g>
            <g transform="matrix(1,0,0,1,8.899,8.084)">
              <g transform="matrix(1,0,0,1,-2.524,1.385)">
                <path
                  fill="rgb(51,51,51)"
                  d="M0.875,-1.125 C0.875,-1.125 0.875,1.125 0.875,1.125 C0.875,1.60 0.48,2 0,2 C0,2 0,2 0,2 C-0.48,2 -0.875,1.60 -0.875,1.125 C-0.875,1.125 -0.875,-1.125 -0.875,-1.125 C-0.875,-1.60 -0.48,-2 0,-2 C0,-2 0,-2 0,-2 C0.48,-2 0.875,-1.60 0.875,-1.125z"
                ></path>
              </g>
            </g>
            <g transform="matrix(1,0,0,1,14.009,8.084)">
              <g transform="matrix(1,0,0,1,-2.524,1.385)">
                <path
                  fill="rgb(51,51,51)"
                  d="M0.9,-1.1 C0.9,-1.1 0.9,1.1 0.9,1.1 C0.9,1.59 0.49,2 0,2 C0,2 0,2 0,2 C-0.49,2 -0.9,1.59 -0.9,1.1 C-0.9,1.1 -0.9,-1.1 -0.9,-1.1 C-0.9,-1.59 -0.49,-2 0,-2 C0,-2 0,-2 0,-2 C0.49,-2 0.9,-1.59 0.9,-1.1z"
                ></path>
              </g>
            </g>
          </g>
        </svg>
      </div>

      <input
        type="range"
        min="0"
        max="100"
        step="0.1"
        :value="(store.currentTime / store.duration) * 100 || 0"
        @input="onSeek"
        class="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-30"
      />
    </div>

    <div class="flex-1 flex items-center justify-between px-2 lg:px-6">
      <div class="flex-1 flex items-center space-x-3 overflow-hidden">
        <div
          v-if="store.currentVideo"
          class="flex items-center space-x-3 animate-fade-in group/info cursor-pointer min-w-0"
          @click="store.toggleUi"
        >
          <div
            class="relative w-16 h-16 rounded-lg overflow-hidden shadow-md border border-white/5 group-hover/info:scale-105 transition-transform shrink-0 image-render-high-quality flex items-center justify-center bg-gray-900"
          >
            <template
              v-if="
                store.currentVideo.pic &&
                store.formatImg(store.currentVideo.pic)
              "
            >
              <img
                :src="
                  store.formatImg(
                    store.currentVideo.pic,
                    '320w_320h_1c_1s.webp',
                  )
                "
                @error="
                  (e) => {
                    if (e.target.src.indexOf('default-cover.svg') === -1)
                      e.target.src = '/default-cover.svg';
                  }
                "
                class="w-full h-full object-cover transform-gpu"
                style="image-rendering: auto; backface-visibility: hidden"
              />
            </template>
            <MusicalNoteIcon
              v-else
              class="w-8 h-8 text-primary-500/50 animate-pulse drop-shadow-md"
            />
          </div>
          <div class="truncate flex flex-col justify-center">
            <div
              class="font-bold text-sm text-gray-800 dark:text-white truncate max-w-[150px] lg:max-w-[250px]"
            >
              {{ store.currentVideo.title }}
            </div>
            <div
              class="text-[12px] font-bold text-gray-500 dark:text-gray-400 truncate"
            >
              @{{ store.currentVideo.owner }}
            </div>
          </div>
        </div>
      </div>

      <div class="flex-1 flex flex-col items-center justify-center min-w-[200px] h-full pt-1">
        <div class="flex items-center space-x-2 lg:space-x-5">
          <button
            @click="handleScore(-0.5)"
            :class="store.userReacted ? 'opacity-10' : 'hover:text-blue-500'"
            class="hidden md:block p-1.5 text-gray-400 transition-all active:scale-90"
          >
            <HandThumbDownIcon class="w-5 h-5" />
          </button>
          <button
            @click="store.prev()"
            class="p-1.5 text-gray-400 hover:text-primary-500 transition-colors transform active:scale-90"
          >
            <BackwardIcon class="w-6 h-6 lg:w-7 lg:h-7" />
          </button>
          <button
            @click="handleTogglePlay"
            class="w-10 h-10 lg:w-12 lg:h-12 bg-primary-500 rounded-full text-white flex items-center justify-center hover:bg-primary-600 shadow-xl transform hover:scale-[1.03] transition active:scale-95"
          >
            <PauseIcon
              v-if="store.isPlaying"
              class="w-6 h-6 lg:w-7 lg:h-7"
            /><PlayIcon v-else class="w-6 h-6 lg:w-7 lg:h-7 ml-0.5" />
          </button>
          <button
            @click="store.next()"
            class="p-1.5 text-gray-400 hover:text-primary-500 transition-colors transform active:scale-90"
          >
            <ForwardIcon class="w-6 h-6 lg:w-7 lg:h-7" />
          </button>
          <button
            @click="handleScore(0.5)"
            :class="store.userReacted ? 'opacity-10' : 'hover:text-primary-500'"
            class="hidden md:block p-1.5 text-gray-400 transition-all active:scale-90"
          >
            <HandThumbUpIcon class="w-5 h-5" />
          </button>
        </div>
        <div
          class="flex items-center justify-center gap-2 text-[10px] lg:text-[11px] font-black text-gray-400 uppercase tracking-tighter tabular-nums mt-1 w-full"
        >
          <div class="flex items-center gap-1">
            <span>{{ formatTime(store.currentTime) }}</span><span class="opacity-30">/</span><span>{{ formatTime(store.duration) }}</span>
          </div>
          
          <button v-if="store.lengthControl.enabled" @click="openLengthControlModal" class="px-1.5 py-0.5 bg-indigo-500/10 text-indigo-500 rounded border border-indigo-500/20 hover:bg-indigo-500/20 transition-colors flex items-center gap-1 shrink-0">
            <ClockIcon class="w-3 h-3" />
            {{ store.lengthControl.type === 'count' ? `剩 ${Math.max(0, store.lengthControl.target - store.lengthControl.current)} 首` : `剩 ${formatTimeLeft(store.lengthControl.target - store.lengthControl.current)}` }}
          </button>
        </div>
      </div>

      <div class="flex-1 flex justify-end items-center space-x-2 lg:space-x-5">
        <button
          @click="settingsStore.toggleMiniMode()"
          class="p-2 text-gray-400 hover:text-primary-500 transition-all active:scale-90"
          title="最小化模式"
        >
          <ArrowsPointingInIcon class="w-5 h-5" />
        </button>
        <div
          class="relative"
          @mouseenter="showVolume"
          @mouseleave="hideVolume"
          @wheel="handleVolumeWheel"
        >
          <div
            class="flex items-center group/vol relative cursor-pointer p-4 -m-2"
          >
            <button
              @click.stop="toggleMute"
              class="text-gray-400 hover:text-primary-500 transition-colors active:scale-90"
            >
              <SpeakerXMarkIcon v-if="store.volume === 0" class="w-5 h-5" />
              <SpeakerWaveIcon v-else class="w-5 h-5" />
            </button>
          </div>
          <!-- 音量悬浮窗 (更紧凑的横向, 靠向屏幕右侧) -->
          <transition name="dropdown-volume">
            <div
              v-if="showVolumePopover"
              class="absolute bottom-[100%] right-0 mb-4 w-64 lg:w-72 h-10 z-[100] bg-white dark:bg-gray-900 rounded-full shadow-xl border border-gray-100 dark:border-white/10 overflow-visible backdrop-blur-2xl flex items-center px-3 gap-3 origin-bottom-right transform translate-x-4 lg:translate-x-12"
            >
              <button
                @click.stop="toggleMute"
                class="text-indigo-500 transition-colors shrink-0 hover:scale-110 active:scale-95"
              >
                <SpeakerXMarkIcon v-if="store.volume === 0" class="w-4 h-4" />
                <SpeakerWaveIcon v-else class="w-4 h-4" />
              </button>

              <div
                class="relative flex-1 h-1.5 bg-gray-100 dark:bg-black/40 rounded-full overflow-hidden flex items-center"
              >
                <!-- 自定义拖拽轨道 -->
                <div
                  class="absolute left-0 h-full bg-gradient-to-r from-indigo-500 to-indigo-400 transition-all duration-75"
                  :style="{ width: store.volume * 100 + '%' }"
                ></div>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  :value="store.volume"
                  @input="(e) => store.setVolume(parseFloat(e.target.value))"
                  class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                />
              </div>

              <div class="relative shrink-0 flex items-center justify-end w-10">
                <button
                  @click.stop="toggleVolumeInput"
                  class="text-[11px] font-black text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-500/20 px-2 py-1 rounded-lg transition-colors tabular-nums"
                >
                  {{ Math.round(store.volume * 100) }}
                </button>

                <!-- 数字键盘弹出层 -->
                <transition name="scale">
                  <div
                    v-if="showVolumeInputPopover"
                    @click.stop
                    class="absolute bottom-[calc(100%+0.5rem)] right-0 w-32 bg-white dark:bg-gray-800 rounded-[1rem] shadow-xl border border-gray-100 dark:border-white/10 p-2 z-[110] origin-bottom-right flex flex-col gap-1.5"
                  >
                    <div class="grid grid-cols-3 gap-1">
                      <button
                        v-for="n in 9"
                        :key="n"
                        @click="handleNumpadInput(n)"
                        class="bg-gray-50 dark:bg-black/20 hover:bg-indigo-50 dark:hover:bg-indigo-500/20 text-gray-700 dark:text-gray-200 text-sm font-bold py-1.5 rounded-lg transition-colors"
                      >
                        {{ n }}
                      </button>
                      <button
                        @click="handleNumpadInput(0)"
                        class="bg-gray-50 dark:bg-black/20 hover:bg-indigo-50 dark:hover:bg-indigo-500/20 text-gray-700 dark:text-gray-200 text-sm font-bold py-1.5 rounded-lg transition-colors col-span-2"
                      >
                        0
                      </button>
                      <button
                        @click="handleNumpadClear"
                        class="bg-red-50 dark:bg-red-500/20 hover:bg-red-100 dark:hover:bg-red-500/30 text-red-500 text-xs font-black py-1.5 rounded-lg transition-colors flex items-center justify-center"
                      >
                        C
                      </button>
                    </div>
                  </div>
                </transition>
              </div>
            </div>
          </transition>
        </div>
        <div class="relative">
          <button
            @click="openModePopover"
            class="flex items-center gap-2 px-2 lg:px-2.5 py-1.5 bg-gray-100 dark:bg-white/5 rounded-lg border border-transparent hover:border-primary-500/30 transition-all group backdrop-blur-[1px]"
          >
            <span
              class="text-[12px] lg:text-[14px] font-black text-gray-500 dark:text-gray-500 uppercase tracking-widest truncate max-w-[4em] lg:max-w-none"
              >{{
                store.playMode === "shuffle"
                  ? "随机"
                  : store.playMode === "shuffle_loop"
                    ? "随循"
                    : store.playMode === "list_loop"
                      ? "列循"
                      : store.playMode === "single_loop"
                        ? "单循"
                        : store.playMode === "weighted"
                          ? "权重"
                          : "顺序"
              }}</span
            >
            <AdjustmentsHorizontalIcon
              class="w-5 h-5 text-gray-500 group-hover:text-primary-500"
            />
          </button>
          <transition name="dropdown">
            <div
              v-if="showModePopover"
              @click.stop
              class="absolute bottom-full right-0 mb-4 w-72 z-[100] bg-white dark:bg-gray-900 rounded-[2rem] shadow-2xl border border-gray-100 dark:border-white/10 overflow-hidden backdrop-blur-2xl p-6"
            >
              <div class="space-y-6">
                <div>
                  <p
                    class="text-[14px] font-black text-gray-400 uppercase tracking-[0.2em] mb-3"
                  >
                    播放模式
                  </p>
                  <div class="grid grid-cols-2 gap-2">
                    <button
                      v-for="m in [
                        { id: 'list', n: '列表顺序' },
                        { id: 'list_loop', n: '列表循环' },
                        { id: 'single_loop', n: '单曲循环' },
                        { id: 'shuffle', n: '无重复随机' },
                        { id: 'shuffle_loop', n: '随机循环' },
                        { id: 'weighted', n: '喜好/权重' },
                      ]"
                      :key="m.id"
                      @click="store.setPlayMode(m.id)"
                      :class="
                        store.playMode === m.id
                          ? 'bg-primary-500 text-white shadow-lg shadow-primary-500/30'
                          : 'bg-gray-50 dark:bg-white/5 text-gray-500'
                      "
                      class="py-2.5 rounded-xl text-[12px] font-bold transition-all"
                    >
                      {{ m.n }}
                    </button>
                  </div>
                  <div
                    v-if="store.playMode === 'weighted'"
                    class="flex mt-2 bg-gray-100 dark:bg-black/20 p-1 rounded-lg"
                  >
                    <button
                      @click="store.weightedMode = 'positive'"
                      :class="
                        store.weightedMode === 'positive'
                          ? 'bg-white dark:bg-gray-700 shadow-sm text-primary-500'
                          : 'text-gray-400'
                      "
                      class="flex-1 py-1 rounded-md text-[11px] font-black uppercase"
                    >
                      高分优先</button
                    ><button
                      @click="store.weightedMode = 'negative'"
                      :class="
                        store.weightedMode === 'negative'
                          ? 'bg-white dark:bg-gray-700 shadow-sm text-blue-500'
                          : 'text-gray-400'
                      "
                      class="flex-1 py-1 rounded-md text-[11px] font-black uppercase"
                    >
                      低分优先
                    </button>
                  </div>
                </div>
                <div class="border-t border-gray-100 dark:border-white/5 pt-4">
                  <button
                    @click="openLengthControlModal"
                    class="w-full py-3 rounded-2xl flex items-center justify-center gap-2 transition-all"
                    :class="store.lengthControl.enabled ? 'bg-indigo-500/10 text-indigo-500' : 'bg-gray-100 dark:bg-white/5 hover:bg-gray-200 dark:hover:bg-white/10 text-gray-700 dark:text-gray-300'"
                  >
                    <ClockIcon class="w-4 h-4" />
                    <span class="text-[14px] font-black uppercase tracking-widest">
                      <template v-if="store.lengthControl.enabled">
                        {{ store.lengthControl.type === 'count' ? `剩 ${Math.max(0, store.lengthControl.target - store.lengthControl.current)} 首` : `剩 ${formatTimeLeft(store.lengthControl.target - store.lengthControl.current)}` }}
                      </template>
                      <template v-else>长度控制</template>
                    </span>
                  </button>
                </div>
                <div class="border-t border-gray-100 dark:border-white/5 pt-4 flex gap-2">
                  <button
                    @click="toggleAutoAction('shutdown')"
                    :class="
                      store.autoActionType === 'shutdown'
                        ? 'text-red-500 bg-red-500/10'
                        : 'text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5'
                    "
                    class="flex-1 py-3 rounded-2xl flex items-center justify-center gap-2 transition-all"
                  >
                    <PowerIcon class="w-4 h-4" /><span
                      class="text-[12px] font-black uppercase tracking-widest"
                      >播完关机</span
                    >
                  </button>
                  <button
                    @click="toggleAutoAction('sleep')"
                    :class="
                      store.autoActionType === 'sleep'
                        ? 'text-orange-500 bg-orange-500/10'
                        : 'text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5'
                    "
                    class="flex-1 py-3 rounded-2xl flex items-center justify-center gap-2 transition-all"
                  >
                    <MoonIcon class="w-4 h-4" /><span
                      class="text-[12px] font-black uppercase tracking-widest"
                      >播完休眠</span
                    >
                  </button>
                </div>
              </div>
            </div></transition
          >
        </div>
      </div>
    </div>
    <!-- 长度控制弹窗 -->
    <Teleport to="body">
      <transition name="fade">
        <div v-if="showLengthModal" class="fixed inset-0 z-[10000] flex items-center justify-center bg-black/60 backdrop-blur-sm" @click.self="showLengthModal = false">
          <div class="bg-white dark:bg-gray-900 rounded-[2rem] shadow-2xl w-full max-w-sm overflow-hidden border border-gray-200 dark:border-white/10 p-6">
            <h3 class="text-xl font-black text-gray-800 dark:text-white mb-4 text-center">播放长度控制</h3>
            
            <div class="flex bg-gray-100 dark:bg-black/20 p-1 rounded-lg mb-4">
              <button @click="tempLengthType = 'count'" :class="tempLengthType === 'count' ? 'bg-white dark:bg-gray-700 shadow-sm text-indigo-500' : 'text-gray-400'" class="flex-1 py-2 rounded-md text-sm font-black">视频个数</button>
              <button @click="tempLengthType = 'time'" :class="tempLengthType === 'time' ? 'bg-white dark:bg-gray-700 shadow-sm text-indigo-500' : 'text-gray-400'" class="flex-1 py-2 rounded-md text-sm font-black">时长(分)</button>
            </div>
            
            <div class="flex items-center gap-3 mb-6">
              <input type="number" :step="tempLengthType === 'count' ? 1 : 0.1" :min="tempLengthType === 'count' ? 1 : 0.1" v-model.number="tempLengthTarget" class="flex-1 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl px-4 py-3 text-lg font-bold text-gray-900 dark:text-white text-center focus:ring-2 focus:ring-indigo-500 outline-none" />
              <span class="text-sm text-gray-500 font-bold">{{ tempLengthType === 'count' ? '个' : '分钟' }}</span>
            </div>
            
            <div class="flex gap-3">
              <button v-if="store.lengthControl.enabled" @click="disableLengthControl" class="flex-1 py-3 bg-red-500/10 text-red-500 hover:bg-red-500 hover:text-white rounded-xl font-bold transition">取消定时</button>
              <button @click="confirmLengthControl" class="flex-1 py-3 bg-indigo-500 hover:bg-indigo-600 text-white rounded-xl font-bold shadow-lg shadow-indigo-500/30 transition">确定</button>
            </div>
          </div>
        </div>
      </transition>
    </Teleport>
  </div>
</template>

<style scoped>
.dropdown-enter-active,
.dropdown-leave-active {
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  transform-origin: bottom right;
}
.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(10px) scale(0.95);
}

.dropdown-volume-enter-active,
.dropdown-volume-leave-active {
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}
.dropdown-volume-enter-from,
.dropdown-volume-leave-to {
  opacity: 0;
  transform: translate(85%, 10px) scale(0.95);
}

/* Numpad Scale 过渡 */
.scale-enter-active,
.scale-leave-active {
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.scale-enter-from,
.scale-leave-to {
  opacity: 0;
  transform: scale(0.95) translateY(10px);
}

input[type="number"]::-webkit-inner-spin-button,
input[type="number"]::-webkit-outer-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
</style>
