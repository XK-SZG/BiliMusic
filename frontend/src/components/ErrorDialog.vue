<script setup>
/**
 * 错误弹窗（错误系统的人机界面）
 *
 * 当后端产生「会导致业务逻辑终止」的错误（例如下载失败）时，
 * 通过 SSE 推送过来，由本组件负责：
 *   1. 用大白话说明「这是什么 / 可能由什么引起 / 可能可以怎么解决」；
 *   2. 提供「一键修复」尝试自动修复、「绕过并继续」跳过该错误；
 *   3. 提供「下载诊断包（ZIP）」，内含错误详情 + 环境快照 + 最近日志（已脱敏），
 *      便于分发给技术客服与开发者。
 */
import { ref, computed, watch } from 'vue'
import { usePlayerStore } from '../stores/modules/player'
import systemApi from '../api/system'
import { saveAs, copyText } from '../utils/download'
import {
  ExclamationTriangleIcon,
  WrenchScrewdriverIcon,
  ArrowDownTrayIcon,
  ArrowRightIcon,
  ClipboardDocumentIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  XMarkIcon,
  ShieldExclamationIcon,
  LightBulbIcon,
  BugAntIcon
} from '@heroicons/vue/24/solid'

const store = usePlayerStore()

const current = computed(() => store.pendingErrors[0] || null)
const show = computed(() => !!current.value)
const totalPending = computed(() => store.pendingErrors.length)

const isRepairing = ref(false)
const isDownloading = ref(false)
const isBypassing = ref(false)
const showTech = ref(false)
const suppressNext = ref(false)
const lastResult = ref(null)

// 切换错误时重置交互状态
watch(current, () => {
  showTech.value = false
  lastResult.value = null
  suppressNext.value = false
})

const spec = computed(() => current.value?.spec || {})

const levelClass = computed(() => {
  const severity = current.value?.severity || 'error'
  if (severity === 'critical') return 'bg-red-600'
  if (severity === 'warning') return 'bg-amber-500'
  return 'bg-red-500'
})

/** 技术细节文本（可复制 / 可折叠） */
const techText = computed(() => {
  const err = current.value
  if (!err) return ''
  const lines = []
  lines.push(`错误编号: ${err.id}`)
  lines.push(`错误码  : ${err.code}`)
  lines.push(`标题    : ${err.title}`)
  lines.push(`时间    : ${err.time}`)
  lines.push(`消息    : ${err.message}`)
  if (err.detail) lines.push(`详情    : ${err.detail}`)
  if (err.context && Object.keys(err.context).length) {
    lines.push('上下文  : ' + JSON.stringify(err.context, null, 2))
  }
  if (err.traceback) {
    lines.push('调用栈  :')
    lines.push(err.traceback)
  }
  return lines.join('\n')
})

function close() {
  store.dismissCurrentError()
}

async function handleRepair() {
  if (!current.value) return
  isRepairing.value = true
  lastResult.value = null
  try {
    const res = await systemApi.repairError(current.value.id)
    lastResult.value = { ok: res.status === 'success', message: res.message }
    store.showToast(res.status === 'success' ? '一键修复已执行' : '修复未成功，请查看提示', res.status === 'success' ? 'success' : 'error')
    if (res.status === 'success') {
      store.removePendingError(current.value.id)
      // 修复后刷新媒体库，让下载状态即时回显
      try { await store.fetchLocalVideos(true) } catch (e) { /* 忽略 */ }
    }
  } catch (e) {
    lastResult.value = { ok: false, message: e.response?.data?.detail || e.message || '修复请求失败' }
  } finally {
    isRepairing.value = false
  }
}

async function handleBypass() {
  if (!current.value) return
  isBypassing.value = true
  try {
    if (suppressNext.value) {
      try { await systemApi.suppressError(current.value.id, true) } catch (e) { /* 忽略 */ }
    }
    await systemApi.bypassError(current.value.id, '用户在错误弹窗中选择绕过')
    store.removePendingError(current.value.id)
    store.showToast('已绕过该错误，业务逻辑继续执行', 'info')
  } catch (e) {
    store.showToast(e.response?.data?.detail || '绕过失败', 'error')
  } finally {
    isBypassing.value = false
  }
}

async function handleDownloadPackage() {
  if (!current.value) return
  isDownloading.value = true
  try {
    const blob = await systemApi.downloadErrorPackage(current.value.id, true)
    const filename = `BiliMusic-diagnostic-${current.value.code}-${current.value.id}.zip`
    const result = await saveAs(blob, filename, 'application/zip')
    if (result.saved) {
      store.showToast(result.path ? `诊断包已保存到 ${result.path}` : '诊断包已开始下载', 'success')
    } else {
      store.showToast('诊断包保存失败', 'error')
    }
  } catch (e) {
    store.showToast(e.response?.data?.detail || '生成诊断包失败', 'error')
  } finally {
    isDownloading.value = false
  }
}

async function handleCopy() {
  const ok = await copyText(techText.value)
  store.showToast(ok ? '错误详情已复制到剪贴板' : '复制失败', ok ? 'success' : 'error')
}
</script>

<template>
  <Teleport to="body">
    <transition name="modal-fade">
      <div v-if="show" class="fixed inset-0 z-[99998] flex items-center justify-center p-6" style="-webkit-app-region: no-drag;">
        <div class="absolute inset-0 bg-black/70 backdrop-blur-sm"></div>

        <div class="relative bg-white dark:bg-gray-900 w-full max-w-2xl rounded-3xl shadow-2xl overflow-hidden border border-red-200 dark:border-red-500/20 flex flex-col max-h-[88vh]">
          <!-- 头部 -->
          <div class="px-7 py-5 border-b border-gray-100 dark:border-white/5 bg-red-50/70 dark:bg-red-500/5 shrink-0 flex items-start gap-4">
            <div class="p-3 rounded-2xl text-white shrink-0 shadow-lg" :class="levelClass">
              <ExclamationTriangleIcon class="w-6 h-6" />
            </div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <h2 class="text-lg font-black text-gray-800 dark:text-white tracking-tight">
                  {{ current?.title || '发生错误' }}
                </h2>
                <span v-if="totalPending > 1"
                      class="px-2 py-0.5 rounded-lg bg-gray-200 dark:bg-white/10 text-[10px] font-black text-gray-500 dark:text-gray-300">
                  另有 {{ totalPending - 1 }} 条待处理
                </span>
              </div>
              <p class="text-xs text-gray-500 dark:text-gray-400 mt-1 font-medium break-all">
                {{ current?.message }}
              </p>
              <p class="text-[10px] text-gray-400 mt-1 font-mono">
                {{ current?.code }} · {{ current?.time }}
              </p>
            </div>
            <button @click="close" class="p-1.5 rounded-xl text-gray-400 hover:text-gray-600 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/5 transition shrink-0">
              <XMarkIcon class="w-5 h-5" />
            </button>
          </div>

          <!-- 内容 -->
          <div class="px-7 py-5 overflow-y-auto scrollbar-thin flex-1 space-y-5">
            <!-- 这是什么 -->
            <div class="p-4 rounded-2xl bg-gray-50 dark:bg-white/5 border border-gray-100 dark:border-white/5">
              <div class="flex items-center gap-2 mb-2 text-gray-700 dark:text-gray-200">
                <BugAntIcon class="w-4 h-4 text-gray-400" />
                <span class="text-xs font-black tracking-wide">这是什么问题？</span>
              </div>
              <p class="text-xs leading-relaxed text-gray-600 dark:text-gray-300">
                {{ spec.summary || '软件在执行该操作时遇到异常，相关业务逻辑已被终止。' }}
              </p>
            </div>

            <!-- 可能的原因 -->
            <div v-if="spec.causes?.length" class="p-4 rounded-2xl bg-amber-50/60 dark:bg-amber-500/5 border border-amber-100 dark:border-amber-500/10">
              <div class="flex items-center gap-2 mb-2 text-amber-700 dark:text-amber-400">
                <ShieldExclamationIcon class="w-4 h-4" />
                <span class="text-xs font-black tracking-wide">可能是什么引起的？</span>
              </div>
              <ul class="space-y-1.5">
                <li v-for="(cause, idx) in spec.causes" :key="idx"
                    class="text-xs leading-relaxed text-gray-600 dark:text-gray-300 flex gap-2">
                  <span class="text-amber-500 font-black shrink-0">{{ idx + 1 }}.</span>
                  <span>{{ cause }}</span>
                </li>
              </ul>
            </div>

            <!-- 可以怎么解决 -->
            <div v-if="spec.solutions?.length" class="p-4 rounded-2xl bg-emerald-50/60 dark:bg-emerald-500/5 border border-emerald-100 dark:border-emerald-500/10">
              <div class="flex items-center gap-2 mb-2 text-emerald-700 dark:text-emerald-400">
                <LightBulbIcon class="w-4 h-4" />
                <span class="text-xs font-black tracking-wide">可能可以怎么解决？</span>
              </div>
              <ul class="space-y-1.5">
                <li v-for="(solution, idx) in spec.solutions" :key="idx"
                    class="text-xs leading-relaxed text-gray-600 dark:text-gray-300 flex gap-2">
                  <span class="text-emerald-500 font-black shrink-0">{{ idx + 1 }}.</span>
                  <span>{{ solution }}</span>
                </li>
              </ul>
            </div>

            <!-- 技术细节（折叠） -->
            <div class="rounded-2xl border border-gray-100 dark:border-white/5 overflow-hidden">
              <button @click="showTech = !showTech"
                      class="w-full px-4 py-3 flex items-center justify-between bg-gray-50 dark:bg-white/5 hover:bg-gray-100 dark:hover:bg-white/10 transition">
                <span class="text-xs font-black text-gray-600 dark:text-gray-300">专业且详细的技术内容（供开发者 / 客服分析）</span>
                <component :is="showTech ? ChevronUpIcon : ChevronDownIcon" class="w-4 h-4 text-gray-400" />
              </button>
              <div v-if="showTech" class="p-4 bg-gray-900 dark:bg-black/60 space-y-3">
                <pre class="text-[10px] leading-relaxed font-mono text-gray-300 whitespace-pre-wrap break-all max-h-64 overflow-y-auto scrollbar-thin">{{ techText }}</pre>
                <button @click="handleCopy"
                        class="w-full py-2 rounded-xl bg-white/10 hover:bg-white/20 text-white text-[11px] font-black transition flex items-center justify-center gap-2">
                  <ClipboardDocumentIcon class="w-4 h-4" /> 一键复制技术内容
                </button>
              </div>
            </div>

            <!-- 修复结果提示 -->
            <div v-if="lastResult"
                 class="p-3 rounded-2xl text-xs font-bold flex items-start gap-2"
                 :class="lastResult.ok
                   ? 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/20'
                   : 'bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-500/20'">
              <span>{{ lastResult.ok ? '✓' : '✕' }}</span>
              <span class="flex-1">{{ lastResult.message }}</span>
            </div>

            <!-- 不再提示 -->
            <label class="flex items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400 cursor-pointer select-none">
              <input type="checkbox" v-model="suppressNext" class="accent-primary-500 w-3.5 h-3.5 cursor-pointer" />
              下次出现「{{ current?.title }}」时不再弹窗（仍会记录到日志与错误列表）
            </label>
          </div>

          <!-- 底部操作 -->
          <div class="px-7 py-4 border-t border-gray-100 dark:border-white/5 bg-gray-50/70 dark:bg-black/30 shrink-0 flex flex-wrap items-center gap-2">
            <button @click="handleDownloadPackage" :disabled="isDownloading"
                    class="px-3.5 py-2.5 rounded-2xl text-[11px] font-black text-gray-600 dark:text-gray-300 bg-white dark:bg-white/5 border border-gray-200 dark:border-white/10 hover:border-gray-300 dark:hover:border-white/20 transition active:scale-95 flex items-center gap-2 disabled:opacity-50">
              <ArrowDownTrayIcon class="w-4 h-4" :class="{ 'animate-bounce': isDownloading }" />
              {{ isDownloading ? '正在打包...' : '下载诊断包 (ZIP)' }}
            </button>

            <div class="flex-1"></div>

            <button @click="handleBypass" :disabled="isBypassing"
                    class="px-4 py-2.5 rounded-2xl text-[11px] font-black text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-white/10 transition active:scale-95 flex items-center gap-2 disabled:opacity-50">
              <ArrowRightIcon class="w-4 h-4" />
              {{ spec.bypass_label || '绕过并继续' }}
            </button>

            <button v-if="spec.repairable" @click="handleRepair" :disabled="isRepairing"
                    class="px-5 py-2.5 rounded-2xl text-[11px] font-black text-white bg-primary-500 hover:bg-primary-600 shadow-lg shadow-primary-500/30 transition active:scale-95 flex items-center gap-2 disabled:opacity-50">
              <WrenchScrewdriverIcon class="w-4 h-4" :class="{ 'animate-spin': isRepairing }" />
              {{ isRepairing ? '正在修复...' : (spec.repair_label || '一键修复') }}
            </button>
            <button v-else @click="close"
                    class="px-5 py-2.5 rounded-2xl text-[11px] font-black text-white bg-gray-700 hover:bg-gray-800 transition active:scale-95">
              我知道了
            </button>
          </div>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<style scoped>
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.3s ease;
}
.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
.scrollbar-thin::-webkit-scrollbar { width: 6px; }
.scrollbar-thin::-webkit-scrollbar-thumb { background: rgba(156, 163, 175, 0.3); border-radius: 3px; }
</style>
