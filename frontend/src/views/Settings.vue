# -*- coding: utf-8 -*-
# Path: frontend/src/views/Settings.vue

<script setup>
import { ref, onMounted, onUnmounted, watch, computed, reactive } from 'vue'
import { usePlayerStore } from '../stores/modules/player'
import { useSettingsStore } from '../stores/modules/settings'
import { useThemeStore } from '../stores/modules/theme'
import systemApi from '../api/system'
// 日志系统接口独立在 api/logs.js 中（initLogStream 为同文件的具名导出）
import logsApi, { initLogStream } from '../api/logs'
import themeApi from '../api/theme'
import UniversalModal from '../components/UniversalModal.vue'
import AgreementModal from '../components/AgreementModal.vue'
import { saveAs, copyText } from '../utils/download'
import {
  TvIcon,
  ArrowDownTrayIcon,
  SpeakerWaveIcon,
  LockClosedIcon,
  ChevronDownIcon,
  CheckIcon,
  SparklesIcon,
  PhotoIcon,
  ArrowsPointingOutIcon,
  SparklesIcon as SparklesOutlineIcon,
  ArrowsRightLeftIcon,
  LanguageIcon,
  ArrowUpTrayIcon,
  ArrowPathIcon,
  ViewColumnsIcon,
  ArrowsUpDownIcon,
  CommandLineIcon,
  XMarkIcon as XMarkSolidIcon,
  RocketLaunchIcon,
  ArrowPathRoundedSquareIcon,
  ScaleIcon,
  PaintBrushIcon,
  RectangleGroupIcon,
  TrashIcon,
  SunIcon,
  SwatchIcon,
  PencilSquareIcon,
  CloudArrowUpIcon,
  CloudArrowDownIcon,
  CircleStackIcon,
  CheckCircleIcon,
  XCircleIcon,
  ExclamationTriangleIcon,
  PowerIcon,
  InformationCircleIcon,
  MagnifyingGlassIcon,
  FolderOpenIcon,
  PlayIcon,
  PauseIcon,
  ClipboardDocumentIcon,
  FunnelIcon,
  DocumentArrowDownIcon,
  ShieldCheckIcon,
  BugAntIcon,
  KeyIcon,
  EyeIcon,
  EyeSlashIcon,
  ServerStackIcon
} from '@heroicons/vue/24/solid'

const store = usePlayerStore()
const settingsStore = useSettingsStore()
const themeStore = useThemeStore()

const modalState_themeName = reactive({ show: false, value: '' })
const modalState_themeDel = reactive({ show: false, targetId: null })
const modalState_themeEdit = reactive({ show: false, targetId: null })

// 用户协议弹窗状态
const showAgreementModal = ref(false)

// 应用版本号（从 Vite 环境变量注入）
const appVersion = __APP_VERSION__

const systemFonts = ref([])
const isScanningFonts = ref(false)

// ============================================================
// 日志系统（实时推送 / 多条件叠加筛选 / 物理日志管理 / 复制下载）
// ============================================================

const systemLogs = ref([])          // 当前展示的日志（筛选后）
const logStats = ref({})            // 日志系统状态（内存占用 / 物理文件 / 保留上限）
const logMeta = ref({})             // 筛选器可选项（级别 / 记录器 / 时间范围）
const logFiles = ref([])            // 物理日志文件列表
const isFetchingLogs = ref(false)
const isDownloadingLogs = ref(false)
const isOpeningLogDir = ref(false)
const isLiveTail = ref(false)
const isLogStreamConnected = ref(false)
const LIVE_LOG_LIMIT = 3000

// 筛选条件（可任意叠加）
const logFilter = reactive({
  keyword: '',
  exclude: '',
  hideHeartbeat: true,        // 默认屏蔽心跳噪声，界面清爽
  heartbeatCategories: ['request', 'login', 'polling'],  // 被屏蔽的心跳类别
  levels: [],                 // 空数组 = 全部级别
  loggerContains: '',
  startTime: '',
  endTime: ''
})

// 心跳类别：可分别屏蔽「请求 / 登录验证 / 前端轮询」
const LOG_HEARTBEAT_CATEGORIES = [
  { id: 'request', label: 'HTTP 请求', desc: '[请求]、urllib3 等逐条 HTTP 访问日志' },
  { id: 'login', label: '登录验证', desc: 'B 站导航接口验证、登录验证成功、API 缓存清除' },
  { id: 'polling', label: '前端轮询', desc: '/download/status、/system/events 等高频轮询' }
]

// 日志系统运行状态（界面自检用，出现异常时能一眼看出）
const logStatus = reactive({ lastAction: '', lastError: '', lastTime: '' })

// 物理日志保留策略（与后端同步）
const logRetention = reactive({ maxFiles: 5, maxFileMB: 5, maxTotalMB: 25 })
const isSavingRetention = ref(false)

// 后端返回的日志时间形如 "2026-10-08 20:39:08"（本地时间，无时区后缀）。
// 若直接用 new Date() 解析，部分环境会因缺少时区而出现偏差，
// 这里手工解析，确保展示时间与系统时间完全一致。
function formatLogTime(timeStr, ts) {
  try {
    if (typeof timeStr === 'string' && timeStr) {
      const m = timeStr.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/)
      if (m) {
        return `${m[2]}-${m[3]} ${m[4]}:${m[5]}:${m[6]}`
      }
      return timeStr
    }
    if (typeof ts === 'number') {
      const d = new Date(ts * 1000)
      const pad = (n) => String(n).padStart(2, '0')
      return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
    }
    return '-'
  } catch (e) {
    return String(timeStr || '-')
  }
}

function formatBytes(bytes) {
  const n = Number(bytes) || 0
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(2)} MB`
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`
}

/** 统一提取后端返回的错误说明（用于把失败原因明确告诉用户） */
function errText(e, fallback = '操作失败') {
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string' && detail) return detail
  if (e?.message) return `${fallback}：${e.message}`
  return fallback
}

/** 记录日志面板的操作结果，便于用户与开发者定位问题 */
function markLogStatus(action, error) {
  logStatus.lastAction = action
  logStatus.lastTime = new Date().toLocaleTimeString()
  logStatus.lastError = error ? String(error) : ''
  if (error) {
    console.error(`[日志系统] ${action} 失败:`, error)
  }
}

/** 把界面筛选条件转换成后端查询参数 */
function buildLogParams(extra = {}) {
  const params = { ...extra }
  if (logFilter.keyword.trim()) params.keyword = logFilter.keyword.trim()
  if (logFilter.exclude.trim()) params.exclude = logFilter.exclude.trim()
  if (logFilter.loggerContains.trim()) params.logger_contains = logFilter.loggerContains.trim()
  if (logFilter.hideHeartbeat) {
    const cats = logFilter.heartbeatCategories
    // 三类全选时用简单开关；部分选择时按类别精确屏蔽
    if (cats.length >= LOG_HEARTBEAT_CATEGORIES.length) {
      params.hide_heartbeat = true
    } else if (cats.length > 0) {
      params.hide_heartbeat = true
      params.hide_heartbeat_categories = cats.join(',')
    }
  }
  if (logFilter.levels.length > 0 && logFilter.levels.length < LOG_LEVELS.length) {
    params.levels = logFilter.levels.join(',')
  }
  if (logFilter.startTime) {
    const t = new Date(logFilter.startTime).getTime()
    if (!isNaN(t)) params.start_time = t / 1000
  }
  if (logFilter.endTime) {
    const t = new Date(logFilter.endTime).getTime()
    if (!isNaN(t)) params.end_time = t / 1000
  }
  return params
}

/** 拉取日志（应用当前筛选条件） */
async function fetchSystemLogs() {
  isFetchingLogs.value = true
  try {
    const data = await logsApi.getLogs(buildLogParams({ limit: 1500, newest_first: true }))
    systemLogs.value = data.logs || []
    markLogStatus(`拉取日志（${systemLogs.value.length} 条）`)
  } catch (e) {
    markLogStatus('拉取日志', errText(e))
    store.showToast(errText(e, '获取日志失败'), 'error')
  } finally {
    isFetchingLogs.value = false
  }
}

/** 拉取日志系统状态与筛选元数据 */
async function fetchLogStats() {
  try {
    const [stats, meta, files] = await Promise.all([
      logsApi.getStats(),
      logsApi.getMeta(),
      logsApi.getLogFiles()
    ])
    logStats.value = stats || {}
    logMeta.value = meta || {}
    logFiles.value = files?.files || []
    if (stats?.max_files) logRetention.maxFiles = stats.max_files
    if (stats?.max_file_bytes) logRetention.maxFileMB = Math.round(stats.max_file_bytes / 1024 / 1024)
    if (stats?.max_total_bytes) logRetention.maxTotalMB = Math.round(stats.max_total_bytes / 1024 / 1024)
  } catch (e) {
    // 状态获取失败不阻塞主流程，但要把原因暴露出来
    markLogStatus('拉取日志状态', errText(e))
  }
}

/** 一键刷新（状态 + 日志） */
async function refreshLogs() {
  await Promise.all([fetchSystemLogs(), fetchLogStats()])
}

// ---------- 实时日志（SSE，无需手动刷新）----------

let logStream = null

function startLiveLog() {
  if (logStream) stopLiveLog()
  const params = buildLogParams()
  const sseFilters = {
    hide_heartbeat: params.hide_heartbeat,
    hide_heartbeat_categories: params.hide_heartbeat_categories,
    levels: params.levels,
    keyword: params.keyword,
    exclude: params.exclude
  }
  Object.keys(sseFilters).forEach((k) => {
    if (sseFilters[k] === undefined || sseFilters[k] === null || sseFilters[k] === '') {
      delete sseFilters[k]
    }
  })

  try {
    logStream = initLogStream(
      (record) => {
        // 实时追加，超出上限时丢弃最旧的记录
        systemLogs.value.unshift(record)
        if (systemLogs.value.length > LIVE_LOG_LIMIT) {
          systemLogs.value.length = LIVE_LOG_LIMIT
        }
      },
      () => {
        isLogStreamConnected.value = true
        markLogStatus('实时日志已连接')
      },
      sseFilters
    )
    logStream.onerror = () => { isLogStreamConnected.value = false }
    isLiveTail.value = true
    markLogStatus('正在建立实时日志连接...')
  } catch (e) {
    isLiveTail.value = false
    markLogStatus('启动实时日志', errText(e))
    store.showToast(errText(e, '启动实时日志失败'), 'error')
  }
}

function stopLiveLog() {
  if (logStream) {
    try { logStream.close() } catch (e) { /* 忽略 */ }
    logStream = null
  }
  isLogStreamConnected.value = false
  isLiveTail.value = false
}

/** 筛选条件变化：实时模式下重连，否则重新拉取 */
async function onLogFilterChange() {
  if (isLiveTail.value) {
    startLiveLog()
  } else {
    await fetchSystemLogs()
  }
}

function resetLogFilter() {
  logFilter.keyword = ''
  logFilter.exclude = ''
  logFilter.hideHeartbeat = true
  logFilter.heartbeatCategories = ['request', 'login', 'polling']
  logFilter.levels = []
  logFilter.loggerContains = ''
  logFilter.startTime = ''
  logFilter.endTime = ''
  onLogFilterChange()
}

/**
 * 日志级别筛选。
 * 交互约定：点击某个级别 = 「只看这一级」；再次点击同一级别 = 恢复「全部级别」。
 * （旧实现是纯粹的勾选切换，默认全部勾选的组合下点击无任何视觉变化，容易被误判为“筛选没生效”。）
 */
function toggleLogLevel(level) {
  const isOnlyThis = logFilter.levels.length === 1 && logFilter.levels[0] === level
  if (isOnlyThis) {
    logFilter.levels = []
  } else {
    logFilter.levels = [level]
  }
  onLogFilterChange()
}

function showAllLogLevels() {
  logFilter.levels = []
  onLogFilterChange()
}

/** 切换某个心跳类别的屏蔽状态 */
function toggleHeartbeatCategory(id) {
  logFilter.hideHeartbeat = true
  const idx = logFilter.heartbeatCategories.indexOf(id)
  if (idx > -1) logFilter.heartbeatCategories.splice(idx, 1)
  else logFilter.heartbeatCategories.push(id)
  onLogFilterChange()
}

const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

const activeFilterCount = computed(() => {
  let n = 0
  if (logFilter.keyword.trim()) n++
  if (logFilter.exclude.trim()) n++
  if (logFilter.loggerContains.trim()) n++
  if (logFilter.hideHeartbeat && logFilter.heartbeatCategories.length > 0) n++
  if (logFilter.levels.length > 0 && logFilter.levels.length < LOG_LEVELS.length) n++
  if (logFilter.startTime) n++
  if (logFilter.endTime) n++
  return n
})

const logLevelCounts = computed(() => {
  const counts = {}
  for (const log of systemLogs.value) {
    counts[log.level] = (counts[log.level] || 0) + 1
  }
  return counts
})

// ---------- 复制 / 下载 ----------

async function copyAllLogs() {
  try {
    const text = await logsApi.exportLogs(buildLogParams({ fmt: 'txt', limit: 100000 }))
    const payload = typeof text === 'string' ? text : String(text ?? '')
    if (!payload.trim()) {
      store.showToast('当前筛选条件下没有可复制的日志', 'info')
      return
    }
    const ok = await copyText(payload)
    if (ok) {
      markLogStatus(`已复制 ${payload.split('\n').length} 行日志`)
      store.showToast('日志已复制到剪贴板', 'success')
    } else {
      markLogStatus('复制日志', '剪贴板写入被拒绝')
      store.showToast('复制失败：剪贴板不可用，请改用「下载」', 'error')
    }
  } catch (e) {
    markLogStatus('复制日志', errText(e))
    store.showToast(errText(e, '复制日志失败'), 'error')
  }
}

async function downloadLogs(fmt = 'txt') {
  isDownloadingLogs.value = true
  try {
    const blob = await logsApi.downloadLogs(buildLogParams({ fmt, limit: 100000 }))
    const size = blob instanceof Blob ? blob.size : 0
    if (!size) {
      markLogStatus('下载日志', '服务端返回空内容')
      store.showToast('当前筛选条件下没有可下载的日志', 'info')
      return
    }
    const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
    const filename = `BiliMusic-logs-${stamp}.${fmt}`
    const result = await saveAs(blob, filename, 'text/plain;charset=utf-8')
    if (result.saved) {
      markLogStatus(`已保存日志（${formatBytes(size)}）`)
      store.showToast(result.path ? `日志已保存到 ${result.path}` : '日志已开始下载', 'success')
    } else {
      markLogStatus('下载日志', '本地保存失败')
      store.showToast('日志下载失败：无法写入本地文件', 'error')
    }
  } catch (e) {
    markLogStatus('下载日志', errText(e))
    store.showToast(errText(e, '日志下载失败'), 'error')
  } finally {
    isDownloadingLogs.value = false
  }
}

// ---------- 物理日志管理 ----------

async function openLogDirectory() {
  isOpeningLogDir.value = true
  const dir = logStats.value?.log_dir || ''
  try {
    // 路径 1：Electron 主进程（最稳妥，不受后端隐藏窗口限制）
    const ipc = getElectronIpc()
    if (ipc && dir) {
      const res = await ipc.invoke('open-directory', dir)
      if (res && res.ok) {
        markLogStatus(`已打开日志目录 ${dir}`)
        store.showToast('已打开日志目录', 'success')
        return
      }
      console.warn('[日志系统] Electron 打开目录失败，回退到后端接口：', res && res.error)
    }

    // 路径 2：后端接口
    const res = await logsApi.openLogDir()
    markLogStatus(`已打开日志目录 ${res.log_dir || dir}`)
    store.showToast('已打开日志目录', 'success')
  } catch (e) {
    const detail = errText(e, '打开日志目录失败')
    markLogStatus('打开日志目录', detail)
    if (dir) {
      await copyText(dir)
      store.showToast(`${detail}（目录路径已复制到剪贴板：${dir}）`, 'error')
    } else {
      store.showToast(detail, 'error')
    }
  } finally {
    isOpeningLogDir.value = false
  }
}

async function saveLogRetention() {
  isSavingRetention.value = true
  try {
    const stats = await logsApi.setRetention({
      max_files: Math.max(1, Number(logRetention.maxFiles) || 5),
      max_file_mb: Math.max(0.1, Number(logRetention.maxFileMB) || 5),
      max_total_mb: Math.max(0.5, Number(logRetention.maxTotalMB) || 25)
    })
    logStats.value = stats || logStats.value
    await fetchLogStats()
    markLogStatus('已保存日志保留策略')
    store.showToast('日志保留策略已保存并立即生效', 'success')
  } catch (e) {
    markLogStatus('保存保留策略', errText(e))
    store.showToast(errText(e, '保存日志保留策略失败'), 'error')
  } finally {
    isSavingRetention.value = false
  }
}

async function clearMemoryLogs() {
  try {
    await logsApi.clearLogs(true)
    systemLogs.value = []
    await fetchLogStats()
    markLogStatus('已清空内存日志')
    store.showToast('内存日志已清空（磁盘日志文件保留）', 'success')
  } catch (e) {
    markLogStatus('清空日志', errText(e))
    store.showToast(errText(e, '清空日志失败'), 'error')
  }
}

const purgeLogState = reactive({ show: false })
const isPurgingLogs = ref(false)

async function executePurgeLogFiles() {
  isPurgingLogs.value = true
  try {
    const res = await logsApi.purgeLogFiles(true)
    purgeLogState.show = false
    await Promise.all([fetchSystemLogs(), fetchLogStats()])
    markLogStatus(`已删除 ${res.removed_files} 个日志文件`)
    store.showToast(`已删除 ${res.removed_files} 个物理日志文件`, 'success')
  } catch (e) {
    markLogStatus('删除日志文件', errText(e))
    store.showToast(errText(e, '删除日志文件失败'), 'error')
  } finally {
    isPurgingLogs.value = false
  }
}

// ============================================================
// 调试系统（协议闸门 + 远程调试组件）
// ============================================================

const debugStatus = ref({ enabled: false, consent: { confirmed: false, checklist: [] } })
const debugAgreementText = ref('')
const debugChecklist = ref([])
const debugChecked = ref([])
const debugAllowPython = ref(false)
const debugAllowShell = ref(false)
const debugToken = ref('')
const isTokenRevealed = ref(false)
const isDebugBusy = ref(false)
const debugAudit = ref([])
const showDebugAgreement = ref(false)
const debugLoaded = ref(false)
const debugTab = ref('console')      // console | audit | api
const debugConsoleInput = ref('platform.python_version()')
const debugConsoleOutput = ref('')
const isDebugConsoleRunning = ref(false)
const debugCopyState = ref('')

// 控制台常用示例表达式（放在 script 中避免模板引号转义问题）
const debugSamples = [
  'platform.python_version()',
  'sys.getsizeof(sys.modules)',
  'len(threading.enumerate())',
  'json.dumps(collections.Counter(["a", "b", "a"]))'
]

const isElectronEnv = computed(() => {
  try {
    return !!(window.require && window.require('process')?.versions?.electron)
  } catch (e) {
    return false
  }
})

/** 获取 Electron 的 ipcRenderer（非 Electron 环境返回 null） */
function getElectronIpc() {
  try {
    if (!window.require) return null
    const { ipcRenderer } = window.require('electron')
    return ipcRenderer && typeof ipcRenderer.invoke === 'function' ? ipcRenderer : null
  } catch (e) {
    return null
  }
}

const debugAgreementError = ref('')

async function fetchDebugStatus() {
  try {
    const data = await systemApi.getDebugStatus(true)
    debugStatus.value = data || {}
    if (data?.token) debugToken.value = data.token
    if (!data?.enabled) debugToken.value = ''
    debugLoaded.value = true
  } catch (e) {
    debugLoaded.value = false
    debugAgreementError.value = errText(e, '无法读取调试系统状态')
    console.error('[调试系统] 读取状态失败:', e)
  }
}

async function loadDebugAgreement() {
  debugAgreementError.value = ''
  try {
    const data = await systemApi.getDebugAgreement()
    debugAgreementText.value = data.agreement || ''
    debugChecklist.value = data.checklist || []
    // 每次都要求重新逐项勾选：协议闸门的意义在于「本次主动确认」，
    // 而不是复用上一次的勾选状态。
    debugChecked.value = []
    if (!debugAgreementText.value) {
      debugAgreementError.value = '后端返回的协议内容为空，请检查后端版本是否为 v1.0.21 及以上'
    }
  } catch (e) {
    debugAgreementError.value = errText(e, '获取调试协议失败')
    console.error('[调试系统] 获取协议失败:', e)
    store.showToast(debugAgreementError.value, 'error')
  }
}

function openDebugAgreement() {
  showDebugAgreement.value = true
  // 每次都重新拉取，避免拿到过期内容
  loadDebugAgreement()
}

function toggleDebugCheck(id) {
  const idx = debugChecked.value.indexOf(id)
  if (idx > -1) debugChecked.value.splice(idx, 1)
  else debugChecked.value.push(id)
}

const debugAllChecked = computed(() =>
  debugChecklist.value.length > 0 &&
  debugChecklist.value.every(i => debugChecked.value.includes(i.id)))

async function handleEnableDebug() {
  if (!debugAllChecked.value) {
    store.showToast('请先逐项确认协议中的所有条款', 'error')
    return
  }
  isDebugBusy.value = true
  try {
    await systemApi.acceptDebugConsent(debugChecked.value)
    const res = await systemApi.enableDebug(debugAllowPython.value, debugAllowShell.value)
    debugToken.value = res.token || ''
    showDebugAgreement.value = false
    isTokenRevealed.value = true
    await fetchDebugStatus()
    store.showToast('调试模式已开启，请妥善保管访问令牌', 'success')
  } catch (e) {
    store.showToast(e.response?.data?.detail || '开启调试模式失败', 'error')
  } finally {
    isDebugBusy.value = false
  }
}

async function handleDisableDebug() {
  isDebugBusy.value = true
  try {
    await systemApi.disableDebug('用户在设置中关闭')
    debugToken.value = ''
    isTokenRevealed.value = false
    await fetchDebugStatus()
    store.showToast('调试模式已关闭，访问令牌已销毁', 'success')
  } catch (e) {
    store.showToast('关闭调试模式失败', 'error')
  } finally {
    isDebugBusy.value = false
  }
}

async function handleRotateDebugToken() {
  try {
    const res = await systemApi.rotateDebugToken()
    debugToken.value = res.token || ''
    isTokenRevealed.value = true
    store.showToast('访问令牌已轮换', 'success')
  } catch (e) {
    store.showToast('轮换令牌失败', 'error')
  }
}

async function handleRevokeDebugConsent() {
  try {
    await systemApi.revokeDebugConsent()
    debugChecked.value = []
    debugToken.value = ''
    await fetchDebugStatus()
    store.showToast('已撤回协议确认', 'success')
  } catch (e) {
    store.showToast('撤回失败', 'error')
  }
}

async function copyDebugValue(text, label) {
  const ok = await copyText(text)
  if (ok) {
    debugCopyState.value = label
    setTimeout(() => { debugCopyState.value = '' }, 1500)
  }
  store.showToast(ok ? `${label} 已复制` : '复制失败', ok ? 'success' : 'error')
}

const curlExample = computed(() => {
  const token = debugToken.value || '<你的访问令牌>'
  return [
    `# 1. 连通性与能力探测`,
    `curl -H "X-Debug-Token: ${token}" http://127.0.0.1:12180/api/debug/ping`,
    ``,
    `# 2. 运行场景快照`,
    `curl -H "X-Debug-Token: ${token}" http://127.0.0.1:12180/api/debug/scene`,
    ``,
    `# 3. 读取最近错误日志`,
    `curl -H "X-Debug-Token: ${token}" "http://127.0.0.1:12180/api/debug/logs?levels=ERROR&limit=50"`,
    ``,
    `# 4. 执行受限表达式`,
    `curl -X POST -H "X-Debug-Token: ${token}" -H "Content-Type: application/json" \\`,
    `  -d '{"action":"python","payload":{"expression":"platform.python_version()"}}' \\`,
    `  http://127.0.0.1:12180/api/debug/action`,
    ``,
    `# 5. 只读 SQL 查询`,
    `curl -X POST -H "X-Debug-Token: ${token}" -H "Content-Type: application/json" \\`,
    `  -d '{"action":"db_query","payload":{"sql":"SELECT bvid, download_status FROM videos LIMIT 10"}}' \\`,
    `  http://127.0.0.1:12180/api/debug/action`
  ].join('\n')
})

async function runDebugConsole() {
  if (!debugToken.value) {
    store.showToast('请先开启调试模式以获取访问令牌', 'error')
    return
  }
  isDebugConsoleRunning.value = true
  debugConsoleOutput.value = ''
  try {
    const res = await systemApi.debugAction(debugToken.value, 'python', {
      expression: debugConsoleInput.value
    })
    debugConsoleOutput.value = JSON.stringify(res.result, null, 2)
  } catch (e) {
    const detail = errText(e, '执行失败')
    debugConsoleOutput.value = `执行失败：${detail}`
    // 令牌失效时同步一次调试状态，避免界面显示「已开启」但实际已不可用
    if (e?.response?.status === 403) {
      await fetchDebugStatus()
      debugConsoleOutput.value += (debugStatus.value?.enabled
        ? '\n\n提示：令牌无效，可点击「轮换令牌」获取新令牌。'
        : '\n\n提示：调试模式已关闭，请重新开启。')
    }
  } finally {
    isDebugConsoleRunning.value = false
  }
}

const isDebugAuditLoading = ref(false)
const debugAuditError = ref('')

async function fetchDebugAudit() {
  debugAuditError.value = ''
  if (!debugToken.value) {
    debugAuditError.value = '当前没有可用的调试令牌，请先关闭并重新开启调试模式'
    return
  }
  isDebugAuditLoading.value = true
  try {
    // [修复] 该接口在后端受 require_debug_token 保护，必须携带令牌，
    // 否则后端会记录 auth_failed 并返回 403「令牌校验失败」
    const res = await systemApi.getDebugAudit(debugToken.value, 100)
    debugAudit.value = res.audit || []
  } catch (e) {
    debugAuditError.value = errText(e, '读取审计日志失败')
    // 令牌失效（被轮换 / 调试已关闭）时同步一次状态，避免界面显示与实际不符
    if (e?.response?.status === 403) {
      await fetchDebugStatus()
      if (!debugStatus.value?.enabled) {
        debugAuditError.value = '调试模式已关闭，审计日志不可读取'
      }
    }
  } finally {
    isDebugAuditLoading.value = false
  }
}

async function clearDebugAuditLog() {
  if (!debugToken.value) {
    store.showToast('当前没有可用的调试令牌', 'error')
    return
  }
  try {
    await systemApi.clearDebugAudit(debugToken.value)
    debugAudit.value = []
    debugAuditError.value = ''
    store.showToast('审计日志已清空', 'success')
  } catch (e) {
    store.showToast(errText(e, '清空审计日志失败'), 'error')
  }
}

watch(debugTab, (tab) => {
  if (tab === 'audit') fetchDebugAudit()
})

// 搜索功能
const searchQuery = ref('')
const searchResults = ref([])

// 导航配置（添加关键词用于搜索）
const navItems = [
  { name: '主题样式', id: 'section-themes', icon: SwatchIcon, keywords: ['主题', '样式', '外观', '皮肤', 'theme', 'style'] },
  { name: '主题色彩', id: 'section-theme', icon: PaintBrushIcon, keywords: ['颜色', '色彩', '主题色', '配色', 'color', 'theme'] },
  { name: '排版字体', id: 'section-font', icon: LanguageIcon, keywords: ['字体', '文字', '排版', 'font', 'text'] },
  { name: '界面贴画', id: 'section-stickers', icon: RectangleGroupIcon, keywords: ['贴画', '贴纸', '装饰', 'sticker', 'decoration'] },
  { name: '全景粒子', id: 'section-particles', icon: SunIcon, keywords: ['粒子', '特效', '动画', 'particle', 'effect'] },
  { name: '频谱呈现', id: 'section-visualizer', icon: SparklesOutlineIcon, keywords: ['频谱', '可视化', '音频', 'visualizer', 'audio'] },
  { name: '视觉实验室', id: 'section-visual-lab', icon: ArrowsPointingOutIcon, keywords: ['视觉', '实验', '效果', 'visual', 'effect'] },
  { name: '背景视觉', id: 'section-background', icon: PhotoIcon, keywords: ['背景', '壁纸', '图片', 'background', 'wallpaper'] },
  { name: '快捷键', id: 'section-shortcuts', icon: CommandLineIcon, keywords: ['快捷键', '键盘', '热键', 'shortcut', 'hotkey'] },
  { name: '交互过渡', id: 'section-interaction', icon: ArrowPathRoundedSquareIcon, keywords: ['过渡', '动画', '交互', 'transition', 'animation'] },
  { name: '启动行为', id: 'section-startup', icon: RocketLaunchIcon, keywords: ['启动', '开机', '自动', 'startup', 'boot'] },
  { name: '媒体质量', id: 'section-quality', icon: TvIcon, keywords: ['质量', '清晰度', '画质', 'quality', 'resolution'] },
  { name: '算法实验室', id: 'section-algorithm', icon: ScaleIcon, keywords: ['算法', '播放', '模式', 'algorithm', 'mode'] },
  { name: '基础音量', id: 'section-volume', icon: SpeakerWaveIcon, keywords: ['音量', '声音', '音频', 'volume', 'sound'] },
  { name: '数据同步', id: 'section-sync', icon: CircleStackIcon, keywords: ['同步', '备份', '数据', 'sync', 'backup'] },
  { name: '系统日志', id: 'section-logs', icon: CommandLineIcon, keywords: ['日志', '控制台', '错误', 'log', 'console', 'error', '筛选', '实时'] },
  { name: '调试系统', id: 'section-debug', icon: BugAntIcon, keywords: ['调试', '开发', 'debug', '远程', 'token', '令牌', 'vibe', 'api'] },
  { name: '关于软件', id: 'section-about', icon: InformationCircleIcon, keywords: ['关于', '版本', '信息', 'about', 'version'] }
]

// 搜索逻辑
watch(searchQuery, (newQuery) => {
  const query = newQuery.trim().toLowerCase()
  if (!query) {
    searchResults.value = []
    return
  }
  
  searchResults.value = navItems.filter(item => {
    // 匹配名称或关键词
    return item.name.toLowerCase().includes(query) ||
           item.keywords.some(keyword => keyword.toLowerCase().includes(query))
  })
})

// 清除搜索
function clearSearch() {
  searchQuery.value = ''
  searchResults.value = []
}

// 搜索结果点击
function handleSearchResultClick(item) {
  scrollToSection(item.id)
  clearSearch()
}

const activeSection = ref(navItems[0].id)
const scrollContainer = ref(null)
let isManualScrolling = false

function scrollToSection(id) {
  const el = document.getElementById(id)
  const container = scrollContainer.value
  if (el && container) {
    isManualScrolling = true
    activeSection.value = id
    
    // 计算相对于容器的偏移量
    const targetScrollTop = el.offsetTop - 20
    
    container.scrollTo({
      top: targetScrollTop,
      behavior: 'smooth'
    })
    
    setTimeout(() => { isManualScrolling = false }, 800)
  }
}

// 监听滚动以更新激活状态
function handleScroll(e) {
  if (isManualScrolling) return
  const scrollPos = e.target.scrollTop + 150
  for (const item of navItems) {
    const el = document.getElementById(item.id)
    if (el) {
      const top = el.offsetTop
      const bottom = top + el.offsetHeight
      if (scrollPos >= top && scrollPos < bottom) {
        activeSection.value = item.id
      }
    }
  }
}

async function fetchSystemFonts() {
  if (systemFonts.value.length > 0) return
  isScanningFonts.value = true
  try {
    const data = await systemApi.getFonts()
    if (data.fonts) systemFonts.value = data.fonts
    if (data.error) store.showToast(data.error, "info")
  } catch (e) { console.error(e) }
  isScanningFonts.value = false
}

async function handleFontUpload(e) {
  const file = e.target.files[0]
  if (!file) return
  const formData = new FormData()
  formData.append('file', file)
  try {
    store.showToast("正在上传字体...", "info")
    const data = await systemApi.uploadFont(formData)
    if (data.status === 'success') {
      const fontName = data.filename.split('.')[0]
      const fontFace = new FontFace(fontName, `url(http://127.0.0.1:12180${data.url})`)
      await fontFace.load()
      document.fonts.add(fontFace)
      settingsStore.updateSettings({ uiFontFamily: 'custom', uiFontCustom: fontName })
      store.showToast("字体上传并应用成功", "success")
    }
  } catch (e) { store.showToast("上传失败", "error") }
}

// 粒子本地上传
async function handleParticleUpload(e) {
  const file = e.target.files[0]
  if (!file) return
  const formData = new FormData()
  formData.append('file', file)
  try {
    store.showToast("正在上传自定义粒子...", "info")
    const data = await systemApi.uploadParticle(formData)
    if (data.status === 'success') {
      const urls = [...(settingsStore.settings.particleCustomUrls || [])]
      if (!urls.includes(data.url)) {
         urls.push(data.url)
         settingsStore.updateSettings({particleCustomUrls: urls})
      }
      store.showToast("粒子素材上传成功", "success")
    }
  } catch (e) { store.showToast("上传失败", "error") }
}

const qualities = [
  { val: 16, label: '360P', desc: '省流模式', member: false },
  { val: 32, label: '480P', desc: '标准画质', member: false },
  { val: 64, label: '720P', desc: '高清视频', member: false },
  { val: 80, label: '1080P', desc: '全高清', member: false },
  { val: 112, label: '1080P+', desc: '高码率 (会员)', member: true },
  { val: 116, label: '1080P 60帧', desc: '流畅丝滑 (会员)', member: true },
  { val: 120, label: '4K', desc: '极致超清 (会员)', member: true }
]

const bgEffects = [
  { id: 'float', label: '律动浮动', desc: '微弱的呼吸式位移' },
  { id: 'ripple', label: '色彩波纹', desc: '柔和的缩放脉冲' },
  { id: 'rotate', label: '极光旋转', desc: '动态几何覆盖旋转' },
  { id: 'drift', label: '流云漂移', desc: '对角线平滑滑动' },
  { id: 'zoom', label: '深空变焦', desc: '缓慢的推拉镜头感' },
  { id: 'glitch', label: '霓虹闪动', desc: '增强型色偏反馈' },
  { id: 'wave', label: '极简扭曲', desc: '轻微的液化拉伸感' },
  { id: 'pulse', label: '节拍跳动', desc: '随呼吸频率起伏' },
  { id: 'color', label: '梦幻色移', desc: '全色谱缓慢循环' }
]

const directions = [
  { id: 'forward', label: '正向', desc: '低频至高频 (左->右)' },
  { id: 'reverse', label: '反向', desc: '高频至低频 (左->右)' },
  { id: 'symmetric', label: '对称', desc: '中心对称扩散' },
  { id: 'reverse_symmetric', label: '反向对称', desc: '两侧低频向中心高频' }
]

const colors = [
  { id: 'pink', label: '哔哩粉', class: 'text-[#ff6699] bg-[#ff6699]' },
  { id: 'blue', label: '哔哩蓝', class: 'text-[#0087bd] bg-[#0087bd]' },
  { id: 'purple', label: '罗兰紫', class: 'text-purple-500 bg-purple-500' },
  { id: 'green', label: '清新绿', class: 'text-green-500 bg-green-500' },
  { id: 'orange', label: '活力橙', class: 'text-orange-500 bg-orange-500' },
  { id: 'red', label: '热情红', class: 'text-red-500 bg-red-500' },
  { id: 'custom', label: '自定义', class: 'text-gray-500 bg-gray-500' }
]

const fonts = [
  { id: 'sans', label: '默认无衬线', desc: 'Modern Sans' },
  { id: 'serif', label: '典雅衬线', desc: 'Elegant Serif' },
  { id: 'mono', label: '极客等宽', desc: 'Geek Mono' },
  { id: 'rounded', label: '可爱圆体', desc: 'Rounded' },
  { id: 'custom', label: '本地字体', desc: 'Custom Local' }
]

const openDropdown = ref(null) 

function isMember() { return store.user && store.user.vip_status === 1 }
function toggleDropdown(type, e) { e.stopPropagation(); openDropdown.value = openDropdown.value === type ? null : type }

function selectQuality(type, q) {
  if (q.member && !isMember()) { store.showToast("该清晰度仅限大会员使用", "error"); return }
  if (type === 'stream') settingsStore.updateSettings({ streamQuality: q.val })
  else settingsStore.updateSettings({ cacheQuality: q.val })
  openDropdown.value = null
}

function toggleBgEffect(id) {
  let effects = [...(settingsStore.settings.bgEffects || [])]
  if (effects.includes(id)) effects = effects.filter(e => e !== id)
  else effects.push(id)
  settingsStore.updateSettings({ bgEffects: effects })
}

function handleVolumeChange(e) { store.setVolume(parseFloat(e.target.value)) }

function selectThemeColor(c) {
  settingsStore.updateSettings({ visColor: c.id })
  const colorMap = { pink: '#ff6699', purple: '#a855f7', blue: '#0087bd', green: '#22c55e', orange: '#f97316', red: '#ef4444' }
  if (c.id !== 'custom' && colorMap[c.id]) { themeStore.updateThemeColor(colorMap[c.id]) }
}

const closeAll = () => { openDropdown.value = null }
onMounted(() => window.addEventListener('click', closeAll))
onUnmounted(() => window.removeEventListener('click', closeAll))

// 日志系统与调试系统的初始化 / 资源释放
onMounted(async () => {
  await refreshLogs()
  fetchDebugStatus()
})

onUnmounted(() => {
  stopLiveLog()
})

const editThemeData = reactive({ name: '', cardImage: '', cardImageSize: 50, cardOffsetX: -10, cardOffsetY: 10 })

async function handleThemeCardImageUpload(e) {
  const file = e.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  store.showToast('上传中...', 'info');
  try {
    const data = await systemApi.uploadSticker(fd);
    if(data.status === 'success') {
      editThemeData.cardImage = data.url;
      store.showToast('上传成功', 'success');
    }
  } catch(err) { store.showToast('上传失败', 'error') }
  e.target.value = '';
}

function openEditTheme(t) {
  editThemeData.name = t.name
  editThemeData.cardImage = t.settings.cardImage || ''
  editThemeData.cardImageSize = t.settings.cardImageSize || 50
  editThemeData.cardOffsetX = t.settings.cardOffsetX !== undefined ? t.settings.cardOffsetX : -10
  editThemeData.cardOffsetY = t.settings.cardOffsetY !== undefined ? t.settings.cardOffsetY : 10
  modalState_themeEdit.show = true
  modalState_themeEdit.targetId = t.id
}

async function handleThemeImport(e) {
  const file = e.target.files[0]
  if (!file) return
  const fd = new FormData()
  fd.append('file', file)
  store.showToast('正在解包导入主题...', 'info')
  try {
    const data = await themeApi.importTheme(fd)
    if (data.status === 'success') {
      const newTheme = data.theme
      themeStore.themes.push(newTheme)
      localStorage.setItem('bili_themes', JSON.stringify(themeStore.themes))
      await themeStore.applyThemeById(newTheme.id)
      store.showToast('导入成功，正在应用...', 'success')
    }
  } catch (e) { store.showToast('导入失败', 'error') }
  e.target.value = ''
}

function exportTheme(id) {
  store.showToast('正在打包主题资源...', 'info')
  window.open(`http://127.0.0.1:12180/api/themes/export/${id}`, '_blank')
}

function getThemeColor(t) {
  const colorMap = { pink: '#ff6699', purple: '#a855f7', blue: '#0087bd', green: '#22c55e', orange: '#f97316', red: '#ef4444' }
  if (t.settings.visColor === 'custom') return t.settings.visColorCustom || '#ff6699'
  return colorMap[t.settings.visColor] || '#ff6699'
}

// 贴画管理
const activeStickerTab = ref('uiBackground')
watch(activeStickerTab, (newTab) => {
  themeStore.stickerEditingTarget = newTab
}, { immediate: true })

// 背景图多选状态
const selectedBgNames = ref([])
const isAllBgSelected = computed(() => 
  themeStore.customBackgrounds.length > 0 && selectedBgNames.value.length === themeStore.customBackgrounds.length
)

function toggleBgSelection(name) {
  const idx = selectedBgNames.value.indexOf(name)
  if (idx > -1) selectedBgNames.value.splice(idx, 1)
  else selectedBgNames.value.push(name)
}

function selectAllBgs() {
  if (isAllBgSelected.value) selectedBgNames.value = []
  else selectedBgNames.value = themeStore.customBackgrounds.map(bg => bg.name)
}

async function handleBulkDeleteBgs() {
  if (selectedBgNames.value.length === 0) return
  if (!confirm(`确定要删除选中的 ${selectedBgNames.value.length} 张背景图吗？`)) return
  
  store.showToast(`正在删除...`, "info")
  let successCount = 0
  for (const name of selectedBgNames.value) {
    try {
      await systemApi.deleteBackground(name)
      successCount++
    } catch (e) { console.error("删除失败:", name) }
  }
  
  selectedBgNames.value = []
  await themeStore.fetchCustomBackgrounds()
  store.showToast(`成功删除 ${successCount} 张背景图`, "success")
}

const stickerTabs = [
  { id: 'uiBackground', label: '面板背景' },
  { id: 'mainView', label: '主视图背景' },
  { id: 'sidebar', label: '侧边栏背景' },
  { id: 'playerBar', label: '播放栏背景' },
  { id: 'immersive', label: '沉浸播放界面' }
]

async function handleStickerUpload(e) {
  const file = e.target.files[0]
  if (!file) return
  const formData = new FormData()
  formData.append('file', file)
  
  // 重置 input 的 value，允许连续上传同一张图
  e.target.value = ''

  try {
    store.showToast("正在上传贴画...", "info")
    const data = await systemApi.uploadSticker(formData)
    if (data.status === 'success') {
      const newSticker = {
        id: Math.random().toString(36).substr(2, 9),
        url: data.url,
        x: 50,
        y: 50,
        width: 50,
        opacity: 0.8,
        rotate: 0
      }
      const newStickers = JSON.parse(JSON.stringify(settingsStore.settings.stickers || { uiBackground: [], sidebar: [], mainView: [], playerBar: [], immersive: [] }))
      if (!newStickers[activeStickerTab.value]) newStickers[activeStickerTab.value] = []
      newStickers[activeStickerTab.value].push(newSticker)
      settingsStore.updateSettings({ stickers: newStickers })
      store.showToast("贴画上传成功", "success")
    }
  } catch (e) { store.showToast("上传失败", "error") }
}

async function handleBackgroundUpload(e) {
  const files = e.target.files
  if (!files || files.length === 0) return
  
  store.showToast(`正在上传 ${files.length} 张背景图...`, "info")
  let successCount = 0

  for (let i = 0; i < files.length; i++) {
    const fd = new FormData()
    fd.append('file', files[i])
    try {
      const data = await systemApi.uploadBackground(fd)
      if (data.status === 'success') {
        successCount++
      }
    } catch (e) {
      console.error("上传背景图失败:", files[i].name)
    }
  }

  if (successCount > 0) {
    await themeStore.fetchCustomBackgrounds()
    store.showToast(`成功上传 ${successCount} 张背景图`, "success")
  } else {
    store.showToast("上传失败", "error")
  }
  
  e.target.value = ''
}

function removeSticker(target, index) {
  const newStickers = JSON.parse(JSON.stringify(settingsStore.settings.stickers || {}))
  newStickers[target].splice(index, 1)
  settingsStore.updateSettings({ stickers: newStickers })
}

function updateStickerProp(target, index, prop, val) {
  const newStickers = JSON.parse(JSON.stringify(settingsStore.settings.stickers || {}))
  newStickers[target][index][prop] = val
  settingsStore.updateSettings({ stickers: newStickers })
}

const getLabel = (val) => qualities.find(q => q.val === val)?.label || '未知'

// 快捷键录制
const recordingKey = ref(null)
const recordingListener = (e) => {
  e.preventDefault(); e.stopPropagation()
  if (recordingKey.value) {
    const newShortcuts = { ...settingsStore.settings.shortcuts }
    newShortcuts[recordingKey.value] = e.code
    settingsStore.updateSettings({ shortcuts: newShortcuts })
    stopRecording()
  }
}
function startRecording(keyId) { recordingKey.value = keyId; window.addEventListener('keydown', recordingListener, true) }
function stopRecording() { recordingKey.value = null; window.removeEventListener('keydown', recordingListener, true) }

const shortcutLabels = {
  play: '播放 / 暂停', prev: '上一首', next: '下一首',
  volumeUp: '增大音量', volumeDown: '减小音量',
  seekForward: '快进 5s', seekBackward: '后退 5s',
  mute: '静音切换', fullscreen: '网页全屏',
  immersive: '沉浸全屏', toggleUi: '展开/收起 UI',
  toggleTheme: '切换深浅主题'
}

const keyCodeMap = { 'Space': '空格', 'Enter': '回车', 'ArrowUp': '↑', 'ArrowDown': '↓', 'ArrowLeft': '←', 'ArrowRight': '→', 'BracketLeft': '[', 'BracketRight': ']', 'Backquote': '`', 'Minus': '-', 'Equal': '=', 'Backspace': '退格', 'Tab': 'Tab', 'CapsLock': '大写锁定', 'ShiftLeft': '左 Shift', 'ShiftRight': '右 Shift', 'ControlLeft': '左 Ctrl', 'ControlRight': '右 Ctrl', 'AltLeft': '左 Alt', 'AltRight': '右 Alt', 'Escape': 'Esc', 'Delete': 'Del', 'Insert': 'Ins', 'Home': 'Home', 'End': 'End', 'PageUp': 'PgUp', 'PageDown': 'PgDn', 'Numpad0': '0(小)', 'NumpadDecimal': '.(小)', 'NumpadEnter': '回车(小)' }

function formatKeyCode(code) {
  if (!code) return '未设置'
  if (code.startsWith('Key')) return code.slice(3)
  if (code.startsWith('Digit')) return code.slice(5)
  if (code.startsWith('F') && code.length <= 3) return code
  return keyCodeMap[code] || code
}

// ---------------- 媒体库同步逻辑 ----------------
const exportSettings = reactive({
  exportLibrary: true,
  exportQueue: true,
  type: 'data', // data, full
  selectedCollections: []
})

async function handleExportLibrary() {
  if (!exportSettings.exportLibrary && !exportSettings.exportQueue) {
    store.showToast('请至少选择一项要导出的内容', 'error')
    return
  }
  
  const payload = {
    export_library: exportSettings.exportLibrary,
    collection_ids: exportSettings.selectedCollections.length === 0 ? ['all'] : exportSettings.selectedCollections,
    export_type: exportSettings.type,
    export_queue: exportSettings.exportQueue,
    queue_data: exportSettings.exportQueue ? store.playQueue : []
  }

  if (window.require) {
    const { ipcRenderer } = window.require('electron')
    try {
      const savePath = await ipcRenderer.invoke('show-save-dialog', {
        title: '导出媒体库',
        defaultPath: 'BiliMusic_Backup.zip',
        filters: [{ name: 'ZIP Archives', extensions: ['zip'] }]
      })
      if (!savePath) {
        return // 用户取消了保存
      }
      payload.save_path = savePath
    } catch (e) {
      console.error('获取保存路径失败:', e)
    }
  }

  settingsStore.isExportingLibrary = true
  store.showToast('正在打包资源，大型图库可能需要较长时间，请耐心等待...', 'info')
  
  systemApi.exportLibrary(payload)
    .then(data => {
      if (payload.save_path) {
        store.showToast('媒体库导出成功', 'success')
      } else {
        const url = window.URL.createObjectURL(new Blob([data]))
        const link = document.createElement('a')
        link.href = url
        link.setAttribute('download', `BiliMusic_Backup.zip`)
        document.body.appendChild(link)
        link.click()
        link.remove()
        store.showToast('媒体库导出成功', 'success')
      }
    })
    .catch(err => store.showToast('导出失败', 'error'))
    .finally(() => { settingsStore.isExportingLibrary = false })
}

const importState = reactive({
  showModal: false,
  sessionId: '',
  collections: [],
  newVideos: [],
  conflicts: [],
  hasQueue: false,
  resolutions: {},
  importQueue: true,
  isUploading: false,
  uploadProgress: 0,
  isExecuting: false
})

async function handleLibraryImport(e) {
  const file = e.target.files[0]
  if (!file) return
  const fd = new FormData()
  fd.append('file', file)
  
  importState.isUploading = true
  importState.uploadProgress = 0
  
  try {
    const data = await systemApi.analyzeImport(fd)
    importState.sessionId = data.session_id
    importState.collections = data.collections
    importState.newVideos = data.new_videos
    importState.conflicts = data.conflicts
    importState.hasQueue = data.has_queue
    importState.importQueue = data.has_queue
    importState.resolutions = {}
    
    data.conflicts.forEach(v => importState.resolutions[v.bvid] = 'skip')
    
    importState.showModal = true
  } catch (err) {
    store.showToast('解析失败，请检查文件格式或重试', 'error')
  } finally {
    importState.isUploading = false
    e.target.value = ''
  }
}

async function executeLibraryImport() {
  importState.isExecuting = true
  store.showToast('正在执行导入并解压迁移文件，请勿刷新页面...', 'info')
  try {
    const data = await systemApi.executeImport({
      session_id: importState.sessionId,
      resolutions: importState.resolutions,
      import_queue: importState.importQueue
    })
    
    if (data.queue_data && data.queue_data.length > 0) {
       store.playQueue = data.queue_data
       store.queueIndex = 0
       store._saveQueue()
    }
    
    await store.fetchLocalCollections()
    await store.fetchLocalVideos()
    
    store.showToast('导入成功', 'success')
    importState.showModal = false
  } catch (err) {
    store.showToast('导入执行失败', 'error')
  } finally {
    importState.isExecuting = false
  }
}

// ---------------- 重置软件逻辑 ----------------
const resetState = reactive({
  step: 0,
  showModal: false
})

function handleFactoryResetClick() {
  resetState.step = 1
  resetState.showModal = true
}

function createDesktopShortcut() {
  if (window.require) {
    const { ipcRenderer } = window.require('electron')
    ipcRenderer.send('create-desktop-shortcut')
    store.showToast("已尝试创建桌面快捷方式", "success")
  } else {
    store.showToast("仅在客户端环境下支持此功能", "error")
  }
}

const uninstallState = reactive({
  step: 0,
  showModal: false
})

function handleUninstallClick() {
  if (!window.require) {
    store.showToast("网页端无需卸载，直接关闭标签页即可", "info")
    return
  }
  uninstallState.step = 1
  uninstallState.showModal = true
}

function confirmUninstallStep() {
  if (uninstallState.step < 3) {
    uninstallState.step++
  } else {
    executeUninstall()
  }
}

function executeUninstall() {
  uninstallState.showModal = false
  const { ipcRenderer } = window.require('electron')
  ipcRenderer.send('uninstall-app')
}

function confirmResetStep() {
  if (resetState.step === 1) {
    resetState.step = 2
  } else if (resetState.step === 2) {
    resetState.step = 3
  } else if (resetState.step === 3) {
    executeFactoryReset()
  }
}

async function executeFactoryReset() {
  resetState.showModal = false
  store.showToast('正在执行重置软件，请稍候...', 'info')
  try {
    await systemApi.factoryReset()
    
    // 清除本地缓存
    localStorage.clear()
    sessionStorage.clear()
    
    // 清除所有的 cookies
    document.cookie.split(";").forEach((c) => {
      document.cookie = c.replace(/^ +/, "").replace(/=.*/, "=;expires=" + new Date().toUTCString() + ";path=/");
    })
    
    // 清除 IndexedDB
    try {
      if (window.indexedDB && window.indexedDB.databases) {
        const dbs = await window.indexedDB.databases()
        for (const db of dbs) {
          window.indexedDB.deleteDatabase(db.name)
        }
      } else {
        window.indexedDB.deleteDatabase('BiliMusicDB')
      }
    } catch (e) {
      console.warn("IndexedDB 清理失败", e)
    }

    // 延迟确保数据都已清理后刷新
    setTimeout(() => {
      window.location.reload()
    }, 500)
  } catch (e) {
    store.showToast('重置失败，请查看控制台日志', 'error')
  }
}
</script>

<template>
  <div class="max-w-6xl mx-auto h-full flex flex-col lg:flex-row gap-8 p-4 lg:p-6 animate-fade-in lg:pb-10">
    
    <!-- 左侧快捷导航 (仅桌面端显示) -->
    <aside class="hidden lg:flex w-64 flex-col gap-1 sticky top-6 self-start shrink-0 max-h-[calc(100vh-14rem)]">
      <div class="px-4 mb-4 shrink-0">
        <h2 class="text-3xl font-black text-gray-800 dark:text-white tracking-tight">系统设置</h2>
      </div>
      
      <!-- 搜索框 -->
      <div class="relative mb-4 px-4">
        <MagnifyingGlassIcon class="w-4 h-4 absolute left-7 top-3 text-gray-400" />
        <input
          v-model="searchQuery"
          placeholder="搜索设置项..."
          class="w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-white/10 rounded-xl pl-10 pr-10 py-2.5 text-sm font-bold focus:outline-none focus:ring-2 focus:ring-primary-500 transition-all text-gray-800 dark:text-white"
        />
        <button
          v-if="searchQuery"
          @click="clearSearch"
          class="absolute right-7 top-3 text-gray-400 hover:text-gray-600 transition-colors"
        >
          <XMarkSolidIcon class="w-4 h-4" />
        </button>
      </div>
      
      <!-- 搜索结果 -->
      <div v-if="searchResults.length > 0" class="mb-4 mx-4 p-3 bg-primary-50 dark:bg-primary-500/10 rounded-xl border border-primary-200 dark:border-primary-500/20">
        <div class="text-xs font-black text-primary-600 dark:text-primary-400 uppercase tracking-widest mb-2">
          搜索结果 ({{ searchResults.length }})
        </div>
        <div class="space-y-1">
          <button
            v-for="item in searchResults"
            :key="item.id"
            @click="handleSearchResultClick(item)"
            class="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left transition-all hover:bg-primary-100 dark:hover:bg-primary-500/20 text-sm font-bold text-gray-700 dark:text-gray-200"
          >
            <component :is="item.icon" class="w-4 h-4 text-primary-500" />
            <span>{{ item.name }}</span>
          </button>
        </div>
      </div>
      
      <nav class="space-y-1 overflow-y-auto scrollbar-none pb-4">
        <button v-for="item in navItems" :key="item.id"
                @click="scrollToSection(item.id)"
                :class="activeSection === item.id ? 'bg-primary-500 text-white shadow-lg shadow-primary-500/20' : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5'"
                class="w-full flex items-center gap-3 px-4 py-3 rounded-2xl text-sm font-bold transition-all group">
          <component :is="item.icon" class="w-5 h-5" :class="activeSection === item.id ? 'text-white' : 'text-gray-400 group-hover:text-primary-500'" />
          {{ item.name }}
        </button>
      </nav>
    </aside>

    <!-- 右侧滚动内容 -->
    <div ref="scrollContainer" class="flex-1 space-y-10 overflow-y-auto pr-2 scroll-smooth no-scrollbar" @scroll="handleScroll">
      
      <!-- 重置软件警告弹窗 -->
      <UniversalModal :show="resetState.showModal" type="confirm"
        :title="resetState.step === 1 ? '第一次警告' : resetState.step === 2 ? '第二次警告' : '最终警告'"
        :extra-data="{
          message: resetState.step === 1 ? '您正在尝试重置软件。这会清空所有媒体库和设置，确定要继续吗？' :
                   resetState.step === 2 ? '所有下载的音视频缓存、收藏数据都会被永久删除，请问是否继续？' :
                   '这是最后一次机会。一旦点击确认，所有数据将灰飞烟灭。确定吗？',
          isDanger: true,
          confirmText: resetState.step === 3 ? '确认销毁' : '继续',
          cancelText: '取消',
          requireConfirm: true  // 修复：添加 requireConfirm 标志
        }"
        @confirm="(confirmed) => {
          if(confirmed) {
            confirmResetStep()
          } else {
            resetState.showModal = false;
            resetState.step = 0;
          }
        }" />

      <!-- 卸载软件警告弹窗 -->
      <UniversalModal :show="uninstallState.showModal" type="confirm"
        :title="uninstallState.step === 1 ? '卸载确认' : uninstallState.step === 2 ? '再次确认' : '最后一次确认'"
        :extra-data="{
          message: uninstallState.step === 1 ? '您确定要卸载 BiliMusic 吗？' :
                   uninstallState.step === 2 ? '卸载将删除程序文件，您可以选择是否保留数据。确定继续？' :
                   '点击确认后，程序将立即关闭并启动卸载向导。确定卸载？',
          isDanger: true,
          confirmText: uninstallState.step === 3 ? '立即卸载' : '继续',
          cancelText: '取消',
          requireConfirm: true  // 修复：添加 requireConfirm 标志
        }"
        @confirm="(confirmed) => {
          if(confirmed) {
            confirmUninstallStep()
          } else {
            uninstallState.showModal = false;
            uninstallState.step = 0;
          }
        }" />

      <!-- 主题命名输入弹窗 -->
      <UniversalModal :show="modalState_themeName?.show || false" type="input" title="新主题名称"
        :initial-value="modalState_themeName?.value || ''"
        @close="modalState_themeName.show = false; modalState_themeName.value = ''"
        @confirm="(name) => { 
          if(name && name.trim()) themeStore.addTheme(name.trim());
          modalState_themeName.show = false; modalState_themeName.value = ''
        }" />

      <!-- 主题删除确认弹窗 -->
      <UniversalModal :show="modalState_themeDel?.show || false" type="confirm" title="删除主题"
        :extra-data="{ message: '删除后不可恢复，确定要删除此主题吗？' }"
        @close="modalState_themeDel.show = false; modalState_themeDel.targetId = null"
        @confirm="(confirmed) => { 
          if(confirmed && modalState_themeDel?.targetId) {
             themeStore.deleteTheme(modalState_themeDel.targetId)
          }
          modalState_themeDel.show = false; modalState_themeDel.targetId = null
        }" />

      <!-- 导入解析结果弹窗 -->
      <transition name="fade">
        <div v-if="importState.showModal" class="fixed inset-0 z-[1000] flex items-center justify-center p-4">
          <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" @click="importState.showModal = false"></div>
          <div class="relative w-full max-w-xl bg-white dark:bg-gray-800 rounded-3xl shadow-2xl p-6 flex flex-col gap-6 max-h-[85vh]">
            <h3 class="text-xl font-black text-gray-800 dark:text-white flex items-center gap-2"><CheckCircleIcon class="w-6 h-6 text-green-500" /> 解析完成</h3>
            
            <div class="flex gap-4">
               <div class="flex-1 bg-green-50 dark:bg-green-500/10 p-3 rounded-2xl border border-green-200 dark:border-green-500/20 text-center">
                 <div class="text-2xl font-black text-green-600">{{ importState.newVideos.length }}</div>
                 <div class="text-[10px] text-green-500 uppercase font-bold mt-1">新视频</div>
               </div>
               <div class="flex-1 bg-blue-50 dark:bg-blue-500/10 p-3 rounded-2xl border border-blue-200 dark:border-blue-500/20 text-center">
                 <div class="text-2xl font-black text-blue-600">{{ importState.collections.length }}</div>
                 <div class="text-[10px] text-blue-500 uppercase font-bold mt-1">媒体夹</div>
               </div>
               <div class="flex-1 bg-orange-50 dark:bg-orange-500/10 p-3 rounded-2xl border border-orange-200 dark:border-orange-500/20 text-center">
                 <div class="text-2xl font-black text-orange-600">{{ importState.conflicts.length }}</div>
                 <div class="text-[10px] text-orange-500 uppercase font-bold mt-1">重复冲突</div>
               </div>
            </div>

            <div v-if="importState.hasQueue" class="flex items-center justify-between bg-gray-50 dark:bg-black/20 p-4 rounded-2xl border border-gray-100 dark:border-white/5 shrink-0">
               <span class="text-xs font-bold text-gray-700 dark:text-gray-300">检测到包含播放队列快照，是否覆盖当前队列？</span>
               <input type="checkbox" v-model="importState.importQueue" class="accent-indigo-500 w-5 h-5 cursor-pointer" />
            </div>

            <div v-if="importState.conflicts.length > 0" class="flex flex-col flex-1 overflow-hidden min-h-[150px]">
              <div class="flex items-center justify-between mb-3 shrink-0">
                 <span class="text-[10px] font-bold text-gray-500 uppercase">处理已存在的视频记录</span>
                 <div class="flex gap-2">
                   <button @click="importState.conflicts.forEach(v => importState.resolutions[v.bvid] = 'skip')" class="text-[10px] bg-gray-100 dark:bg-white/10 px-2.5 py-1 rounded-md font-black hover:text-indigo-500 transition">全部跳过</button>
                   <button @click="importState.conflicts.forEach(v => importState.resolutions[v.bvid] = 'overwrite')" class="text-[10px] bg-red-50 text-red-500 dark:bg-red-500/10 px-2.5 py-1 rounded-md font-black hover:bg-red-500 hover:text-white transition">全部覆盖</button>
                 </div>
              </div>
              <div class="flex-1 overflow-y-auto scrollbar-thin space-y-2 pr-2">
                 <div v-for="v in importState.conflicts" :key="v.bvid" class="flex items-center justify-between p-3 bg-gray-50 dark:bg-black/20 rounded-xl border border-gray-100 dark:border-white/5">
                    <span class="text-xs font-bold text-gray-700 dark:text-gray-300 truncate max-w-[55%]">{{ v.title }}</span>
                    <select v-model="importState.resolutions[v.bvid]" class="bg-white dark:bg-gray-800 text-[10px] font-black rounded-lg px-2 py-1.5 border border-gray-200 dark:border-white/10 focus:ring-0 focus:border-indigo-500">
                       <option value="skip">跳过并保留原版</option>
                       <option value="overwrite">覆盖并合并信息</option>
                    </select>
                 </div>
              </div>
            </div>
            
            <div class="flex items-center gap-3 mt-2 shrink-0">
               <button @click="importState.showModal = false" :disabled="importState.isExecuting" class="flex-1 py-3 bg-gray-100 hover:bg-gray-200 dark:bg-white/10 dark:hover:bg-white/20 text-gray-600 dark:text-white rounded-2xl font-bold text-sm transition active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed">取消</button>
               <button @click="executeLibraryImport" :disabled="importState.isExecuting" class="flex-1 py-3 bg-indigo-500 hover:bg-indigo-600 text-white rounded-2xl font-bold text-sm shadow-md shadow-indigo-500/30 transition active:scale-95 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed">
                 <ArrowPathIcon v-if="importState.isExecuting" class="w-5 h-5 animate-spin" />
                 {{ importState.isExecuting ? '正在搬运文件...' : '确认执行' }}
               </button>
             </div>
          </div>
        </div>
      </transition>

      <div class="lg:hidden mb-8">
        <h2 class="text-4xl font-black text-gray-800 dark:text-white">系统设置</h2>
      </div>

      <!-- 编辑主题弹窗 -->
      <transition name="fade">
        <div v-if="modalState_themeEdit?.show" class="fixed inset-0 z-[1000] flex items-center justify-center p-4">
          <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" @click="modalState_themeEdit.show = false; modalState_themeEdit.targetId = null"></div>
          <div class="relative w-full max-w-sm bg-white dark:bg-gray-800 rounded-3xl shadow-2xl p-6 flex flex-col gap-6">
             <h3 class="text-xl font-black text-gray-800 dark:text-white">编辑主题卡片</h3>
             <div class="flex flex-col gap-4">
               <div>
                 <span class="text-xs font-bold text-gray-500 uppercase">主题名称</span>
                 <input v-model="editThemeData.name" class="w-full mt-1 px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-white/10 rounded-xl font-bold text-sm text-gray-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-all" />
               </div>
               <div>
                 <span class="text-xs font-bold text-gray-500 uppercase flex justify-between items-center">
                   <span>左下角卡片图标</span>
                   <label class="text-[10px] text-indigo-500 hover:text-indigo-600 font-black cursor-pointer bg-indigo-500/10 px-2 py-0.5 rounded">
                     上传新图
                     <input type="file" class="hidden" accept=".png,.jpg,.jpeg,.gif,.webp" @change="handleThemeCardImageUpload" />
                   </label>
                 </span>
                 <div class="mt-2 h-20 bg-gray-50 dark:bg-black/20 rounded-xl flex items-center justify-center border border-gray-200 dark:border-white/10 relative overflow-hidden">
                   <img v-if="editThemeData.cardImage" :src="`http://127.0.0.1:12180${editThemeData.cardImage}`" @error="(e) => e.target.style.display='none'" class="h-full object-contain drop-shadow-md" />
                   <div v-else class="text-[10px] text-gray-400 font-bold uppercase tracking-widest">使用默认样式</div>
                   <button v-if="editThemeData.cardImage" @click="editThemeData.cardImage = ''" class="absolute right-2 top-2 p-1 bg-red-500 text-white rounded-md shadow hover:bg-red-600 transition"><TrashIcon class="w-3 h-3" /></button>
                 </div>
               </div>
               <div v-if="editThemeData.cardImage">
                 <span class="text-xs font-bold text-gray-500 uppercase flex justify-between">
                   <span>图像大小 (%)</span>
                   <span>{{ editThemeData.cardImageSize }}%</span>
                 </span>
                 <input type="range" min="10" max="150" step="1" v-model.number="editThemeData.cardImageSize" class="w-full mt-2 accent-indigo-500" />
                 
                 <div class="flex gap-4 mt-3">
                   <div class="flex-1">
                     <span class="text-[10px] font-bold text-gray-500 uppercase flex justify-between"><span>X 偏移</span><span>{{ editThemeData.cardOffsetX }}%</span></span>
                     <input type="range" min="-150" max="150" step="1" v-model.number="editThemeData.cardOffsetX" class="w-full mt-1 accent-indigo-500" />
                   </div>
                   <div class="flex-1">
                     <span class="text-[10px] font-bold text-gray-500 uppercase flex justify-between"><span>Y 偏移</span><span>{{ editThemeData.cardOffsetY }}%</span></span>
                     <input type="range" min="-150" max="150" step="1" v-model.number="editThemeData.cardOffsetY" class="w-full mt-1 accent-indigo-500" />
                   </div>
                 </div>
               </div>
             </div>
             <div class="flex items-center gap-3 mt-2">
               <button @click="modalState_themeEdit.show = false; modalState_themeEdit.targetId = null" class="flex-1 py-2 bg-gray-100 hover:bg-gray-200 dark:bg-white/10 dark:hover:bg-white/20 text-gray-600 dark:text-white rounded-xl font-bold text-sm transition active:scale-95">取消</button>
               <button @click="() => {
                 themeStore.editThemeCard(modalState_themeEdit.targetId, editThemeData);
                 modalState_themeEdit.show = false; modalState_themeEdit.targetId = null;
               }" class="flex-1 py-2 bg-indigo-500 hover:bg-indigo-600 text-white rounded-xl font-bold text-sm shadow-md shadow-indigo-500/30 transition active:scale-95">保存更改</button>
             </div>
          </div>
        </div>
      </transition>

      <!-- 0. 主题样式 -->
      <section id="section-themes" class="bg-white/50 dark:bg-gray-900/40 backdrop-blur-md rounded-[2.5rem] p-8 border border-gray-100 dark:border-white/5 shadow-sm">
        <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-6 mb-8">
          <div class="flex items-center gap-5">
            <div class="p-4 bg-indigo-500/10 text-indigo-500 rounded-[1.5rem]"><SwatchIcon class="w-7 h-7" /></div>
            <div><h3 class="text-xl font-bold text-gray-800 dark:text-white">主题样式与资源库</h3><p class="text-sm text-gray-400 mt-1">一键应用或分享您精心调配的视觉系统</p></div>
          </div>
          <div class="flex flex-wrap items-center gap-3">
            <button @click="() => { 
                modalState_themeName.show = true; modalState_themeName.value = '' 
              }" class="px-4 py-2 bg-indigo-500 hover:bg-indigo-600 text-white rounded-xl text-xs font-bold transition shadow-md shadow-indigo-500/30 active:scale-95">当前设置另存为</button>
            <label class="px-4 py-2 bg-purple-500 hover:bg-purple-600 text-white rounded-xl text-xs font-bold cursor-pointer transition shadow-md shadow-purple-500/30 active:scale-95">
              导入主题包
              <input type="file" class="hidden" accept=".zip" @change="handleThemeImport" />
            </label>
          </div>
        </div>
        
        <div class="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4 max-h-[360px] overflow-y-auto pr-2 scrollbar-thin">
          <div v-for="t in themeStore.themes" :key="t.id"
               @click="themeStore.applyThemeById(t.id)"
               class="group relative flex flex-col p-5 bg-white dark:bg-gray-800 rounded-2xl border-[3px] transition-all cursor-pointer overflow-hidden aspect-square"
               :class="themeStore.activeThemeId === t.id ? 'shadow-xl scale-[1.02]' : 'border-transparent hover:border-gray-200 dark:hover:border-white/10 hover:scale-[1.01]'"
               :style="themeStore.activeThemeId === t.id ? { borderColor: getThemeColor(t), boxShadow: `0 20px 25px -5px ${getThemeColor(t)}33` } : {}">
            
            <!-- 卡片右上角装饰性点缀 -->
            <div class="absolute -right-6 -top-6 w-24 h-24 rounded-full transition-transform group-hover:scale-150 pointer-events-none opacity-20"
                 :style="{ backgroundColor: getThemeColor(t) }"></div>

            <!-- 卡片左下角图像 -->
            <img v-if="t.settings.cardImage" :src="`http://127.0.0.1:12180${t.settings.cardImage}`"
                 @error="(e) => e.target.style.display = 'none'"
                 class="absolute bottom-0 left-0 object-contain drop-shadow-lg opacity-40 group-hover:opacity-100 transition-all pointer-events-none"
                 :style="{ width: `${t.settings.cardImageSize || 50}%`, transform: `translate(${t.settings.cardOffsetX ?? -10}%, ${t.settings.cardOffsetY ?? 10}%)` }" />
            
            <div v-else class="absolute -bottom-16 -left-16 w-32 h-32 rounded-full transition-all pointer-events-none opacity-10"
                 :style="{ backgroundColor: getThemeColor(t) }"></div>

            <div class="flex items-start justify-between mb-8 relative z-10 gap-3">
              <span class="font-black text-sm break-words line-clamp-2 drop-shadow-sm" :class="themeStore.activeThemeId === t.id ? '' : 'text-gray-800 dark:text-white'"
                    :style="themeStore.activeThemeId === t.id ? { color: getThemeColor(t) } : {}">{{ t.name }}</span>
              <div class="flex flex-col gap-1 items-end shrink-0">
                 <span v-if="t.is_default" class="text-[8px] bg-gray-100 dark:bg-white/10 text-gray-500 px-2 py-0.5 rounded uppercase font-black">系统默认</span>
                 <span v-if="themeStore.activeThemeId === t.id" class="text-[8px] text-white px-2 py-0.5 rounded uppercase font-black shadow-sm"
                       :style="{ backgroundColor: getThemeColor(t) }">使用中</span>
              </div>
            </div>

            <div class="mt-auto flex flex-wrap items-center justify-end gap-1.5 pt-4 border-t border-gray-100 dark:border-white/5 opacity-0 group-hover:opacity-100 transition-opacity relative z-10">
               <button @click.stop="openEditTheme(t)" class="whitespace-nowrap px-2.5 py-1 bg-white/80 dark:bg-black/50 backdrop-blur-md text-gray-700 dark:text-gray-200 rounded-lg text-[10px] font-black hover:bg-gray-200 dark:hover:bg-white/20 transition active:scale-95"><PencilSquareIcon class="w-3 h-3 inline-block mr-1 -mt-0.5"/>编辑</button>
               <button @click.stop="exportTheme(t.id)" class="whitespace-nowrap px-2.5 py-1 bg-blue-50/80 dark:bg-blue-500/20 backdrop-blur-md text-blue-600 dark:text-blue-300 rounded-lg text-[10px] font-black hover:bg-blue-500 hover:text-white transition active:scale-95">导出</button>
               <button v-if="!t.is_default" @click.stop="() => { modalState_themeDel.show = true; modalState_themeDel.targetId = t.id }" class="whitespace-nowrap px-2.5 py-1 bg-red-50/80 dark:bg-red-500/20 backdrop-blur-md text-red-600 dark:text-red-300 rounded-lg text-[10px] font-black hover:bg-red-500 hover:text-white transition active:scale-95">删除</button>
            </div>
          </div>
        </div>
      </section>

      <!-- 1. 主题色彩 -->
      <section id="section-theme" class="bg-white/50 dark:bg-gray-900/40 backdrop-blur-md rounded-[2.5rem] p-8 border border-gray-100 dark:border-white/5 shadow-sm">
        <div class="flex items-center gap-5 mb-8">
          <div class="p-4 bg-primary-500/10 text-primary-500 rounded-[1.5rem]"><PaintBrushIcon class="w-7 h-7" /></div>
          <div><h3 class="text-xl font-bold text-gray-800 dark:text-white">个性化主题</h3><p class="text-sm text-gray-400 mt-1">自定义全局强调色与频谱渐变</p></div>
        </div>
        <div class="flex flex-col gap-6">
           <div class="flex flex-col gap-3">
             <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">预设方案</span>
             <div class="flex flex-wrap gap-4 items-center">
               <button v-for="c in colors.filter(x => x.id !== 'custom')" :key="c.id" @click="selectThemeColor(c)"
                       class="flex items-center gap-2 px-6 py-2 rounded-xl border-2 transition-all"
                       :class="settingsStore.settings.visColor === c.id ? 'border-primary-500 bg-primary-50 dark:bg-primary-500/20' : 'border-transparent bg-gray-50 dark:bg-white/5'">
                  <div class="w-3 h-3 rounded-full shadow-sm" :class="c.class"></div>
                  <span class="text-xs font-bold" :class="settingsStore.settings.visColor === c.id ? 'text-gray-800 dark:text-white' : 'text-gray-400'">{{ c.label }}</span>
               </button>
             </div>
           </div>
           <div class="flex flex-col gap-3">
             <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">深度定制</span>
             <div class="flex flex-wrap gap-4 items-center p-4 bg-gray-50 dark:bg-white/5 rounded-2xl border border-gray-100 dark:border-white/5">
                <button @click="settingsStore.updateSettings({visColor: 'custom'})" class="flex items-center gap-2 px-3 py-2 rounded-xl border-2 transition-all shrink-0"
                       :class="settingsStore.settings.visColor === 'custom' ? 'border-primary-500 bg-primary-50 dark:bg-primary-500/20' : 'border-transparent bg-white dark:bg-white/10'">
                  <div class="w-3 h-3 rounded-full shadow-sm" :style="settingsStore.settings.visColor === 'custom' ? { background: `linear-gradient(to right, ${settingsStore.settings.visColorCustom}, ${settingsStore.settings.visColorCustomSec || '#a855f7'})` } : { backgroundColor: '#9ca3af' }"></div>
                  <span class="text-xs font-bold" :class="settingsStore.settings.visColor === 'custom' ? 'text-gray-800 dark:text-white' : 'text-gray-400'">开启自定义</span>
               </button>
               <template v-if="settingsStore.settings.visColor === 'custom'">
                 <div class="h-8 w-px bg-gray-200 dark:bg-white/10 mx-2 hidden sm:block"></div>
                 <div class="animate-fade-in flex flex-wrap items-center gap-6">
                   <div class="flex items-center gap-3">
                     <span class="text-[10px] font-bold text-gray-400 uppercase leading-tight">全局主题<br />频谱底部</span>
                     <div class="relative w-10 h-10 rounded-full overflow-hidden border-2 border-white dark:border-gray-600 shadow-sm cursor-pointer hover:scale-110 transition-transform">
                       <input type="color" :value="settingsStore.settings.visColorCustom" @input="(e) => { settingsStore.updateSettings({visColorCustom: e.target.value}); themeStore.updateThemeColor(e.target.value); }" class="absolute -top-1/2 -left-1/2 w-[200%] h-[200%] p-0 m-0 cursor-pointer" />
                     </div>
                   </div>
                   <ArrowsRightLeftIcon class="w-4 h-4 text-gray-300 hidden sm:block" />
                   <div class="flex items-center gap-3">
                     <span class="text-[10px] font-bold text-gray-400 uppercase leading-tight">频谱顶部<br />辅助色</span>
                     <div class="relative w-10 h-10 rounded-full overflow-hidden border-2 border-white dark:border-gray-600 shadow-sm cursor-pointer hover:scale-110 transition-transform">
                       <input type="color" :value="settingsStore.settings.visColorCustomSec || '#a855f7'" @input="(e) => settingsStore.updateSettings({visColorCustomSec: e.target.value})" class="absolute -top-1/2 -left-1/2 w-[200%] h-[200%] p-0 m-0 cursor-pointer" />
                     </div>
                   </div>
                 </div>
               </template>
             </div>
           </div>
        </div>
      </section>

      <!-- 2. 字体与排版 -->
      <section id="section-font" class="bg-white/50 dark:bg-gray-900/40 backdrop-blur-md rounded-[2.5rem] p-8 border border-gray-100 dark:border-white/5 shadow-sm">
        <div class="flex items-center gap-5 mb-8">
          <div class="p-4 bg-teal-500/10 text-teal-500 rounded-[1.5rem]"><LanguageIcon class="w-7 h-7" /></div>
          <div><h3 class="text-xl font-bold text-gray-800 dark:text-white">排版与字体</h3><p class="text-sm text-gray-400 mt-1">选择最适合阅读的字形</p></div>
        </div>
        <div class="space-y-6">
          <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
            <button v-for="f in fonts" :key="f.id" @click="settingsStore.updateSettings({uiFontFamily: f.id})"
                    :class="settingsStore.settings.uiFontFamily === f.id ? 'border-primary-500 bg-primary-50 dark:bg-primary-500/20' : 'border-transparent bg-gray-50 dark:bg-white/5 text-gray-500'"
                    class="flex flex-col p-3 rounded-2xl border-2 transition-all text-center">
              <span class="font-bold text-xs">{{ f.label }}</span>
              <span class="text-[8px] opacity-50 mt-1">{{ f.desc }}</span>
            </button>
          </div>
          <div v-if="settingsStore.settings.uiFontFamily === 'custom'" class="animate-fade-in flex flex-col gap-4 bg-gray-50 dark:bg-white/5 p-4 rounded-2xl border border-gray-100 dark:border-white/5">
             <div class="flex items-center justify-between">
               <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">字体配置</span>
               <button @click="fetchSystemFonts" class="text-[10px] font-bold text-teal-500 hover:underline flex items-center gap-1">
                 <ArrowPathIcon class="w-3 h-3" :class="{'animate-spin': isScanningFonts}" /> 扫描系统字体
               </button>
             </div>
             <div class="flex gap-2">
               <input :value="settingsStore.settings.uiFontCustom" @input="(e) => settingsStore.updateSettings({uiFontCustom: e.target.value})" placeholder="输入名称或从下方选择" class="flex-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-white/10 rounded-xl px-4 py-2 text-sm font-bold focus:outline-none focus:ring-2 focus:ring-teal-500 transition-all text-gray-800 dark:text-white" />
               <label class="p-2 bg-gray-200 dark:bg-white/10 rounded-xl cursor-pointer hover:bg-gray-300 dark:hover:bg-white/20 transition-colors shadow-sm" title="上传字体文件">
                 <ArrowUpTrayIcon class="w-5 h-5 text-gray-600 dark:text-gray-300" /><input type="file" class="hidden" accept=".ttf,.woff,.woff2,.otf" @change="handleFontUpload" />
               </label>
             </div>
             <div v-if="systemFonts.length > 0" class="flex flex-wrap gap-2 max-h-32 overflow-y-auto pr-2 scrollbar-thin">
               <button v-for="font in systemFonts" :key="font.path" @click="settingsStore.updateSettings({uiFontCustom: font.name})" class="px-2 py-1 bg-white dark:bg-gray-700 border border-gray-100 dark:border-white/5 rounded-lg text-[10px] font-medium text-gray-600 dark:text-gray-300 hover:border-teal-500 transition-all">{{ font.name }}</button>
             </div>
          </div>
          <div class="flex flex-col gap-4">
            <div class="flex justify-between items-center"><span class="text-sm font-bold text-gray-600 dark:text-gray-300">全局字号缩放 ({{ (settingsStore.settings.uiFontSize || 1.0).toFixed(2) }}x)</span></div>
            <input type="range" min="0.8" max="1.3" step="0.05" :value="settingsStore.settings.uiFontSize || 1.0" @input="(e) => settingsStore.updateSettings({uiFontSize: parseFloat(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-primary-500" />
          </div>
        </div>
      </section>

      <!-- 3. 界面贴画 -->
      <section id="section-stickers" class="bg-white/50 dark:bg-gray-900/40 backdrop-blur-md rounded-[2.5rem] p-8 border border-gray-100 dark:border-white/5 shadow-sm">
        <div class="flex items-center justify-between mb-8">
          <div class="flex items-center gap-5">
            <div class="p-4 bg-fuchsia-500/10 text-fuchsia-500 rounded-[1.5rem]"><RectangleGroupIcon class="w-7 h-7" /></div>
            <div><h3 class="text-xl font-bold text-gray-800 dark:text-white">界面贴画</h3><p class="text-sm text-gray-400 mt-1">在任意角落贴上您的专属背景图</p></div>
          </div>
          <!-- 总开关 -->
          <button @click="settingsStore.updateSettings({stickersEnabled: !settingsStore.settings.stickersEnabled})" 
                  :class="settingsStore.settings.stickersEnabled !== false ? 'bg-fuchsia-500 shadow-fuchsia-500/30' : 'bg-gray-300 dark:bg-white/10'" 
                  class="w-12 h-6 rounded-full transition-all relative flex items-center shrink-0">
            <div class="absolute w-4 h-4 bg-white rounded-full transition-all shadow-sm" :class="settingsStore.settings.stickersEnabled !== false ? 'left-7' : 'left-1'"></div>
          </button>
        </div>
        <div class="flex flex-col gap-6" v-if="settingsStore.settings.stickersEnabled !== false">
          <!-- Tab 切换 -->
          <div class="flex gap-2 bg-gray-100 dark:bg-black/20 p-1.5 rounded-2xl w-full overflow-x-auto scrollbar-none">
            <button v-for="tab in stickerTabs" :key="tab.id" @click="activeStickerTab = tab.id"
                    :class="activeStickerTab === tab.id ? 'bg-white dark:bg-gray-700 shadow-sm text-fuchsia-500' : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'"
                    class="flex-1 py-3 px-4 rounded-xl text-xs font-black transition-all whitespace-nowrap">{{ tab.label }}</button>
          </div>
          
          <div class="bg-gray-50/50 dark:bg-white/5 p-4 rounded-2xl border border-gray-100 dark:border-white/5">
            <div class="flex justify-between items-center mb-6">
              <span class="text-xs font-bold text-gray-500 uppercase tracking-widest flex items-center gap-2">
                当前容器贴图 ({{ settingsStore.settings.stickers?.[activeStickerTab]?.length || 0 }})
                <button @click="themeStore.toggleStickerEditMode(activeStickerTab === 'immersive')" :class="themeStore.isStickerEditMode ? 'bg-fuchsia-500 text-white shadow-md shadow-fuchsia-500/30' : 'bg-fuchsia-500/10 text-fuchsia-500'" class="px-3 py-1 rounded-lg text-[10px] uppercase font-black hover:scale-105 transition-all ml-2 active:scale-95 flex items-center gap-1">
                  <ArrowsPointingOutIcon class="w-3 h-3" />
                  {{ themeStore.isStickerEditMode ? '退出可视化编辑' : '进入可视化编辑' }}
                </button>
              </span>
              <label class="px-4 py-2 bg-fuchsia-500 hover:bg-fuchsia-600 text-white rounded-xl text-xs font-bold cursor-pointer transition shadow-md shadow-fuchsia-500/30 active:scale-95">
                上传新贴图
                <input type="file" class="hidden" accept=".png,.jpg,.jpeg,.gif,.webp" @change="handleStickerUpload" />
              </label>
            </div>
            
            <div class="space-y-4">
              <div v-for="(s, idx) in settingsStore.settings.stickers?.[activeStickerTab] || []" :key="s.id" class="flex flex-col gap-3 p-4 bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-white/5 shadow-sm">
                <div class="flex flex-col lg:flex-row lg:items-center gap-6">
                  <!-- 缩略图 -->
                  <div class="w-full lg:w-24 h-24 bg-gray-100 dark:bg-black/40 rounded-lg overflow-hidden shrink-0 flex items-center justify-center p-2 border border-gray-200 dark:border-white/5">
                    <img :src="`http://127.0.0.1:12180${s.url}`" @error="(e) => e.target.style.display='none'" class="max-w-full max-h-full object-contain drop-shadow-md" />
                  </div>
                  <!-- 控制器：改为垂直排列以支持输入框 -->
                  <div class="flex-1 flex flex-col gap-4 w-full">
                    <!-- X 轴 -->
                    <div class="flex items-center gap-4">
                      <span class="w-16 text-[10px] font-bold text-gray-400 uppercase shrink-0">X 轴</span>
                      <input type="range" min="-200" max="200" step="0.1" :value="s.x" @input="(e) => updateStickerProp(activeStickerTab, idx, 'x', parseFloat(e.target.value))" class="flex-1 accent-fuchsia-500 min-w-[100px]" />
                      <input type="number" :value="s.x" @input="(e) => updateStickerProp(activeStickerTab, idx, 'x', parseFloat(e.target.value) || 0)" class="w-16 bg-gray-100 dark:bg-black/20 border-none rounded-lg px-2 py-1 text-xs font-bold text-center shrink-0 text-gray-700 dark:text-gray-300" />
                    </div>
                    <!-- Y 轴 -->
                    <div class="flex items-center gap-4">
                      <span class="w-16 text-[10px] font-bold text-gray-400 uppercase shrink-0">Y 轴</span>
                      <input type="range" min="-200" max="200" step="0.1" :value="s.y" @input="(e) => updateStickerProp(activeStickerTab, idx, 'y', parseFloat(e.target.value))" class="flex-1 accent-fuchsia-500 min-w-[100px]" />
                      <input type="number" :value="s.y" @input="(e) => updateStickerProp(activeStickerTab, idx, 'y', parseFloat(e.target.value) || 0)" class="w-16 bg-gray-100 dark:bg-black/20 border-none rounded-lg px-2 py-1 text-xs font-bold text-center shrink-0 text-gray-700 dark:text-gray-300" />
                    </div>
                    <!-- 宽度 -->
                    <div class="flex items-center gap-4">
                      <span class="w-16 text-[10px] font-bold text-gray-400 uppercase shrink-0">大小 (%)</span>
                      <input type="range" min="1" max="500" step="0.5" :value="s.width" @input="(e) => updateStickerProp(activeStickerTab, idx, 'width', parseFloat(e.target.value))" class="flex-1 accent-fuchsia-500 min-w-[100px]" />
                      <input type="number" :value="s.width" @input="(e) => updateStickerProp(activeStickerTab, idx, 'width', parseFloat(e.target.value) || 1)" class="w-16 bg-gray-100 dark:bg-black/20 border-none rounded-lg px-2 py-1 text-xs font-bold text-center shrink-0 text-gray-700 dark:text-gray-300" />
                    </div>
                    <!-- 旋转 -->
                    <div class="flex items-center gap-4">
                      <span class="w-16 text-[10px] font-bold text-gray-400 uppercase shrink-0">旋转 (°)</span>
                      <input type="range" min="-180" max="180" step="0.5" :value="s.rotate" @input="(e) => updateStickerProp(activeStickerTab, idx, 'rotate', parseFloat(e.target.value))" class="flex-1 accent-fuchsia-500 min-w-[100px]" />
                      <input type="number" :value="s.rotate" @input="(e) => updateStickerProp(activeStickerTab, idx, 'rotate', parseFloat(e.target.value) || 0)" class="w-16 bg-gray-100 dark:bg-black/20 border-none rounded-lg px-2 py-1 text-xs font-bold text-center shrink-0 text-gray-700 dark:text-gray-300" />
                    </div>
                    <!-- 透明度 -->
                    <div class="flex items-center gap-4">
                      <span class="w-16 text-[10px] font-bold text-gray-400 uppercase shrink-0">透明度</span>
                      <input type="range" min="0" max="1" step="0.01" :value="s.opacity" @input="(e) => updateStickerProp(activeStickerTab, idx, 'opacity', parseFloat(e.target.value))" class="flex-1 accent-fuchsia-500 min-w-[100px]" />
                      <input type="number" :value="s.opacity" step="0.01" @input="(e) => updateStickerProp(activeStickerTab, idx, 'opacity', parseFloat(e.target.value) || 0)" class="w-16 bg-gray-100 dark:bg-black/20 border-none rounded-lg px-2 py-1 text-xs font-bold text-center shrink-0 text-gray-700 dark:text-gray-300" />
                    </div>
                  </div>
                  <!-- 删除 -->
                  <div class="flex items-center justify-end">
                    <button @click="removeSticker(activeStickerTab, idx)" class="p-3 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-xl transition" title="删除贴图">
                      <TrashIcon class="w-5 h-5" />
                    </button>
                  </div>
                </div>
              </div>
              <div v-if="(settingsStore.settings.stickers?.[activeStickerTab] || []).length === 0" class="text-center py-10 opacity-30">
                <RectangleGroupIcon class="w-10 h-10 mx-auto mb-2" />
                <p class="text-xs font-bold uppercase tracking-widest">该容器暂无贴画</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 4. 全局粒子引擎 -->
      <section id="section-particles" class="bg-white/50 dark:bg-gray-900/40 backdrop-blur-md rounded-[2.5rem] p-8 border border-gray-100 dark:border-white/5 shadow-sm">
        <div class="flex items-center justify-between mb-8">
          <div class="flex items-center gap-5">
            <div class="p-4 bg-yellow-500/10 text-yellow-500 rounded-[1.5rem]"><SunIcon class="w-7 h-7" /></div>
            <div><h3 class="text-xl font-bold text-gray-800 dark:text-white">全景粒子引擎</h3><p class="text-sm text-gray-400 mt-1">沉浸模式下的次世代视觉补偿系统</p></div>
          </div>
          <!-- 总开关 -->
          <button @click="settingsStore.updateSettings({particleEnabled: !settingsStore.settings.particleEnabled})" 
                  :class="settingsStore.settings.particleEnabled ? 'bg-yellow-500 shadow-yellow-500/30' : 'bg-gray-300 dark:bg-white/10'" 
                  class="w-12 h-6 rounded-full transition-all relative flex items-center shrink-0">
            <div class="absolute w-4 h-4 bg-white rounded-full transition-all shadow-sm" :class="settingsStore.settings.particleEnabled ? 'left-7' : 'left-1'"></div>
          </button>
        </div>

        <div class="space-y-8" v-if="settingsStore.settings.particleEnabled">
          
          <!-- 粒子形态选择 (多选) -->
          <div class="flex flex-col gap-3">
             <span class="text-xs font-bold text-gray-500 uppercase tracking-widest flex justify-between">
               <span>形态混合池</span>
               <span class="text-[10px] text-yellow-500">支持多选混合</span>
             </span>
             <div class="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-2 bg-gray-100 dark:bg-black/20 p-2 rounded-2xl w-full">
               <button v-for="s in [{id:'circle', l:'圆形'}, {id:'square', l:'方形'}, {id:'triangle', l:'三角'}, {id:'plexus', l:'星图连线'}, {id:'svg_star', l:'星星'}, {id:'svg_heart', l:'心形'}, {id:'svg_music', l:'音符'}, {id:'svg_petal', l:'樱花'}, {id:'text', l:'字符'}, {id:'custom', l:'自定义图'}]" :key="s.id"
                       @click="() => {
                         let shapes = [...(settingsStore.settings.particleShapes || [])];
                         if (shapes.includes(s.id)) shapes = shapes.filter(x => x !== s.id);
                         else shapes.push(s.id);
                         if (shapes.length === 0) shapes = ['circle'];
                         settingsStore.updateSettings({particleShapes: shapes});
                       }"
                       :class="settingsStore.settings.particleShapes?.includes(s.id) ? 'bg-white dark:bg-gray-700 shadow-sm text-yellow-500 border-yellow-500/50' : 'text-gray-400 border-transparent'"
                       class="py-2 px-1 rounded-xl text-xs font-black transition-all border text-center">{{ s.l }}</button>
             </div>
          </div>

          <!-- 文本粒子配置 -->
          <div v-if="settingsStore.settings.particleShapes?.includes('text')" class="animate-fade-in flex flex-col gap-2 bg-gray-50 dark:bg-white/5 p-4 rounded-2xl border border-gray-100 dark:border-white/5">
             <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">注入字符序列 (英文逗号分隔)</span>
             <input :value="settingsStore.settings.particleText" @input="(e) => settingsStore.updateSettings({particleText: e.target.value})"
                    placeholder="例如: ♪,♫,★,✨,A,B" 
                    class="w-full bg-transparent border-b border-gray-300 dark:border-gray-600 py-2 text-sm font-bold focus:outline-none focus:border-yellow-500 transition-colors text-gray-800 dark:text-white placeholder-gray-400" />
          </div>

          <!-- 自定义图片输入 -->
          <div v-if="settingsStore.settings.particleShapes?.includes('custom')" class="animate-fade-in flex flex-col gap-2 bg-gray-50 dark:bg-white/5 p-4 rounded-2xl border border-gray-100 dark:border-white/5">
             <span class="text-xs font-bold text-gray-500 uppercase tracking-widest flex justify-between items-center">
                <span>绑定自定义图元 (支持网络 URL 或本地上传)</span>
                <label class="text-[9px] bg-yellow-500/10 text-yellow-600 hover:bg-yellow-500 hover:text-white px-2 py-0.5 rounded-md cursor-pointer transition">
                  本地上传
                  <input type="file" class="hidden" accept=".png,.jpg,.jpeg,.gif,.webp,.svg" @change="handleParticleUpload" />
                </label>
             </span>
             
             <!-- 这里的 input 我们简化处理，监听回车将输入的 URL 推入数组 -->
             <input placeholder="https://example.com/icon.png (回车添加)"
                    @keyup.enter="(e) => {
                      const v = e.target.value.trim();
                      if (v) {
                        const urls = [...(settingsStore.settings.particleCustomUrls || [])];
                        if (!urls.includes(v)) {
                           urls.push(v);
                           settingsStore.updateSettings({particleCustomUrls: urls});
                        }
                        e.target.value = '';
                      }
                    }"
                    class="w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-white/10 rounded-xl px-4 py-2 text-sm font-bold focus:outline-none focus:ring-2 focus:ring-yellow-500 transition-all text-gray-800 dark:text-white" />
             
             <div class="flex flex-wrap gap-2 mt-2">
                <div v-for="(url, idx) in settingsStore.settings.particleCustomUrls || []" :key="idx" 
                     class="flex items-center gap-1 bg-yellow-500/10 text-yellow-600 border border-yellow-500/20 px-2 py-1 rounded-lg text-[10px] font-mono group">
                  <span class="max-w-[150px] truncate" :title="url">{{ url }}</span>
                  <XMarkSolidIcon @click="() => {
                    const urls = [...(settingsStore.settings.particleCustomUrls || [])];
                    urls.splice(idx, 1);
                    settingsStore.updateSettings({particleCustomUrls: urls});
                  }" class="w-3 h-3 cursor-pointer hover:text-red-500" />
                </div>
             </div>
          </div>

          <!-- 发射方向 -->
          <div class="flex flex-col gap-3">
             <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">引力方向</span>
             <div class="flex bg-gray-100 dark:bg-black/20 p-1.5 rounded-2xl w-full">
               <button @click="settingsStore.updateSettings({particleDirection: 'up'})"
                       :class="settingsStore.settings.particleDirection !== 'down' ? 'bg-white dark:bg-gray-700 shadow-sm text-yellow-500' : 'text-gray-400'"
                       class="flex-1 py-3 rounded-xl text-xs font-black transition-all flex items-center justify-center gap-2">
                 喷泉 (上升)
               </button>
               <button @click="settingsStore.updateSettings({particleDirection: 'down'})"
                       :class="settingsStore.settings.particleDirection === 'down' ? 'bg-white dark:bg-gray-700 shadow-sm text-yellow-500' : 'text-gray-400'"
                       class="flex-1 py-3 rounded-xl text-xs font-black transition-all flex items-center justify-center gap-2">
                 瀑布 (下落)
               </button>
             </div>
          </div>

          <!-- 粒子颜色设置 -->
          <div class="flex flex-col gap-3">
             <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">粒子色彩模式</span>
             <div class="flex bg-gray-100 dark:bg-black/20 p-1.5 rounded-2xl w-full">
               <button v-for="m in [{id:'theme',l:'随主题色'}, {id:'random',l:'随机缤纷'}, {id:'life_gradient',l:'寿命渐变'}, {id:'height_gradient',l:'高度渐变'}]" :key="m.id"
                       @click="settingsStore.updateSettings({particleColorMode: m.id})"
                       :class="(settingsStore.settings.particleColorMode || 'theme') === m.id ? 'bg-white dark:bg-gray-700 shadow-sm text-yellow-500' : 'text-gray-400'"
                       class="flex-1 py-3 rounded-xl text-xs font-black transition-all">{{ m.l }}</button>
             </div>
          </div>
          
          <div v-if="['theme', 'life_gradient', 'height_gradient'].includes(settingsStore.settings.particleColorMode || 'theme')" class="animate-fade-in flex flex-col gap-2 bg-gray-50 dark:bg-white/5 p-4 rounded-2xl border border-gray-100 dark:border-white/5">
             <span class="text-xs font-bold text-gray-500 uppercase tracking-widest flex justify-between items-center">
                <span>自定义色彩 (选填，不填则默认主题色)</span>
             </span>
             <div class="flex items-center gap-6 mt-2">
                <div class="flex items-center gap-3">
                   <span class="text-[10px] font-bold text-gray-400 uppercase leading-tight">基础色 / 起点</span>
                   <div class="relative w-10 h-10 rounded-full overflow-hidden border-2 border-white dark:border-gray-600 shadow-sm cursor-pointer hover:scale-110 transition-transform">
                     <input type="color" :value="settingsStore.settings.particleColorStart || themeStore.themeColor || '#ff6699'" @input="(e) => settingsStore.updateSettings({particleColorStart: e.target.value})" class="absolute -top-1/2 -left-1/2 w-[200%] h-[200%] p-0 m-0 cursor-pointer" />
                   </div>
                </div>
                <template v-if="['life_gradient', 'height_gradient'].includes(settingsStore.settings.particleColorMode)">
                   <ArrowsRightLeftIcon class="w-4 h-4 text-gray-300 hidden sm:block" />
                   <div class="flex items-center gap-3">
                     <span class="text-[10px] font-bold text-gray-400 uppercase leading-tight">渐变终点</span>
                     <div class="relative w-10 h-10 rounded-full overflow-hidden border-2 border-white dark:border-gray-600 shadow-sm cursor-pointer hover:scale-110 transition-transform">
                       <input type="color" :value="settingsStore.settings.particleColorEnd || '#a855f7'" @input="(e) => settingsStore.updateSettings({particleColorEnd: e.target.value})" class="absolute -top-1/2 -left-1/2 w-[200%] h-[200%] p-0 m-0 cursor-pointer" />
                     </div>
                   </div>
                   
                   <!-- 渐变平衡阈值 -->
                   <div class="flex-1 flex flex-col gap-1 ml-4">
                     <span class="text-[9px] font-bold text-gray-400 uppercase tracking-tighter">渐变平衡 ({{ (settingsStore.settings.particleColorThreshold ?? 0.5).toFixed(2) }})</span>
                     <input type="range" min="0.01" max="0.99" step="0.01" :value="settingsStore.settings.particleColorThreshold ?? 0.5" @input="(e) => settingsStore.updateSettings({particleColorThreshold: parseFloat(e.target.value)})" class="w-full h-1 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-yellow-500" />
                   </div>
                </template>
                <button @click="settingsStore.updateSettings({particleColorStart: '', particleColorEnd: ''})" class="px-3 py-1 bg-gray-200 dark:bg-white/10 rounded-lg text-[10px] font-bold text-gray-500 hover:text-yellow-500 transition-all ml-auto">清空</button>
             </div>
          </div>

          <!-- 物理参数引擎 -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-8 p-6 bg-gray-50 dark:bg-white/5 rounded-[2rem] border border-gray-100 dark:border-white/5">
            <div class="col-span-full mb-2"><span class="text-sm font-black text-gray-800 dark:text-white">力学与流体参数</span></div>
            
            <div class="flex flex-col gap-4">
              <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">环境风力 X-Axis ({{ (settingsStore.settings.particleWind ?? 0).toFixed(1) }})</span>
              <input type="range" min="-5.0" max="5.0" step="0.1" :value="settingsStore.settings.particleWind ?? 0" @input="(e) => settingsStore.updateSettings({particleWind: parseFloat(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-yellow-500" />
            </div>
            
            <div class="flex flex-col gap-4">
              <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">介质阻力 ({{ (settingsStore.settings.particleFriction ?? 0.9800).toFixed(4) }})</span>
              <input type="range" min="0.9000" max="1.0000" step="0.0025" :value="settingsStore.settings.particleFriction ?? 0.98" @input="(e) => settingsStore.updateSettings({particleFriction: parseFloat(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-yellow-500" />
              <p class="text-[9px] text-gray-400 mt-1">1.0 为无阻力真空环境，值越小阻力越大，易产生悬停滞空效果。</p>
            </div>

            <div class="flex flex-col gap-4">
              <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">粒子基础尺寸 ({{ (settingsStore.settings.particleSize ?? 1.0).toFixed(1) }}x)</span>
              <input type="range" min="0.1" max="5.0" step="0.1" :value="settingsStore.settings.particleSize ?? 1.0" @input="(e) => settingsStore.updateSettings({particleSize: parseFloat(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-yellow-500" />
            </div>

            <div class="flex flex-col gap-4">
              <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">粒子基础透明度 ({{ (settingsStore.settings.particleOpacity ?? 1.0).toFixed(2) }})</span>
              <input type="range" min="0.1" max="1.0" step="0.05" :value="settingsStore.settings.particleOpacity ?? 1.0" @input="(e) => settingsStore.updateSettings({particleOpacity: parseFloat(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-yellow-500" />
            </div>

            <div class="flex flex-col gap-4">
              <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">发射初速度 ({{ (settingsStore.settings.particleSpeedY ?? 2.0).toFixed(1) }})</span>
              <input type="range" min="0.5" max="10.0" step="0.5" :value="settingsStore.settings.particleSpeedY ?? 2.0" @input="(e) => settingsStore.updateSettings({particleSpeedY: parseFloat(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-yellow-500" />
            </div>

            <div class="flex flex-col gap-4">
              <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">扇形发散角 ({{ (settingsStore.settings.particleSpread ?? 1.0).toFixed(1) }})</span>
              <input type="range" min="0.0" max="5.0" step="0.1" :value="settingsStore.settings.particleSpread ?? 1.0" @input="(e) => settingsStore.updateSettings({particleSpread: parseFloat(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-yellow-500" />
            </div>

            <div class="flex flex-col gap-4">
              <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">自转扭矩角 ({{ (settingsStore.settings.particleRotation ?? 1.0).toFixed(1) }})</span>
              <input type="range" min="0.0" max="5.0" step="0.1" :value="settingsStore.settings.particleRotation ?? 1.0" @input="(e) => settingsStore.updateSettings({particleRotation: parseFloat(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-yellow-500" />
            </div>
            
            <div class="flex flex-col gap-4">
              <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">同屏密度配额 ({{ settingsStore.settings.particleCount ?? 50 }})</span>
              <input type="range" min="10" max="200" step="10" :value="settingsStore.settings.particleCount ?? 50" @input="(e) => settingsStore.updateSettings({particleCount: parseInt(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-yellow-500" />
            </div>
          </div>
          
        </div>
      </section>

      <!-- 5. 频谱呈现 (原 4.) -->
      <section id="section-visualizer" class="bg-white/50 dark:bg-gray-900/40 backdrop-blur-md rounded-[2.5rem] p-8 border border-gray-100 dark:border-white/5 shadow-sm">
        <div class="flex items-center justify-between mb-8">
          <div class="flex items-center gap-5">
            <div class="p-4 bg-primary-500/10 text-primary-500 rounded-[1.5rem]"><SparklesOutlineIcon class="w-7 h-7" /></div>
            <div><h3 class="text-xl font-bold text-gray-800 dark:text-white">频谱呈现</h3><p class="text-sm text-gray-400 mt-1">音频可视化的风格与物理反馈</p></div>
          </div>
          <button @click="settingsStore.updateSettings({visEnabled: !settingsStore.settings.visEnabled})" :class="settingsStore.settings.visEnabled !== false ? 'bg-primary-500 shadow-primary-500/30' : 'bg-gray-300 dark:bg-white/10'" class="w-12 h-6 rounded-full transition-all relative flex items-center shrink-0">
            <div class="absolute w-4 h-4 bg-white rounded-full transition-all shadow-sm" :class="settingsStore.settings.visEnabled !== false ? 'left-7' : 'left-1'"></div>
          </button>
        </div>
        <div class="space-y-8" v-if="settingsStore.settings.visEnabled !== false">
          <div class="flex gap-2 bg-gray-100 dark:bg-black/20 p-1.5 rounded-2xl overflow-x-auto scrollbar-none">
            <button v-for="s in [{v:'bars',l:'能量柱'}, {v:'line',l:'折线图'}, {v:'curve',l:'平滑曲线'}, {v:'particles',l:'灵动粒子'}]" :key="s.v" @click="settingsStore.updateSettings({visualizerStyle: s.v})" :class="settingsStore.settings.visualizerStyle === s.v ? 'bg-white dark:bg-gray-700 shadow-sm text-primary-500' : 'text-gray-400'" class="flex-1 py-3 px-4 rounded-xl text-xs font-black transition-all">{{ s.l }}</button>
          </div>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
            <button v-for="d in directions" :key="d.id" @click="settingsStore.updateSettings({visDirection: d.id})" :class="settingsStore.settings.visDirection === d.id ? 'border-primary-500 bg-primary-500/10 text-primary-600 dark:text-primary-400' : 'border-transparent bg-gray-50 dark:bg-white/5 text-gray-500'" class="flex flex-col p-4 rounded-2xl border-2 transition-all text-center items-center justify-center"><span class="font-bold text-xs">{{ d.label }}</span><span class="text-[8px] opacity-50 mt-1">{{ d.desc }}</span></button>
          </div>
          <div class="flex flex-col gap-3">
             <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">位置布局</span>
             <div class="flex bg-gray-100 dark:bg-black/20 p-1.5 rounded-2xl w-full">
               <button @click="settingsStore.updateSettings({visPosition: 'bottom'})" :class="settingsStore.settings.visPosition !== 'top' && settingsStore.settings.visPosition !== 'double' ? 'bg-white dark:bg-gray-700 shadow-sm text-primary-500' : 'text-gray-400'" class="flex-1 py-3 rounded-xl text-xs font-black transition-all flex items-center justify-center gap-2"><ArrowDownTrayIcon class="w-4 h-4" /> 底部</button>
               <button @click="settingsStore.updateSettings({visPosition: 'top'})" :class="settingsStore.settings.visPosition === 'top' ? 'bg-white dark:bg-gray-700 shadow-sm text-primary-500' : 'text-gray-400'" class="flex-1 py-3 rounded-xl text-xs font-black transition-all flex items-center justify-center gap-2"><ArrowUpTrayIcon class="w-4 h-4" /> 顶部</button>
               <button @click="settingsStore.updateSettings({visPosition: 'double'})" :class="settingsStore.settings.visPosition === 'double' ? 'bg-white dark:bg-gray-700 shadow-sm text-primary-500' : 'text-gray-400'" class="flex-1 py-3 rounded-xl text-xs font-black transition-all flex items-center justify-center gap-2"><ArrowsUpDownIcon class="w-4 h-4" /> 镜像</button>
             </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div class="flex flex-col gap-4">
              <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">灵敏度 ({{ (settingsStore.settings.visSensitivity ?? 1.0).toFixed(1) }}x)</span>
              <input type="range" min="0.5" max="3.0" step="0.1" :value="settingsStore.settings.visSensitivity ?? 1.0" @input="(e) => settingsStore.updateSettings({visSensitivity: parseFloat(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-primary-500" />
            </div>
            <div class="flex flex-col gap-4">
              <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">采样单元 ({{ settingsStore.settings.visCount ?? 64 }})</span>
              <input type="range" min="32" max="256" step="32" :value="settingsStore.settings.visCount ?? 64" @input="(e) => settingsStore.updateSettings({visCount: parseInt(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-primary-500" />
            </div>
            <div class="flex flex-col gap-4"><span class="text-xs font-bold text-gray-500 uppercase tracking-widest">平滑度 ({{ settingsStore.settings.visSmoothing ?? 0.8 }})</span><input type="range" min="0.1" max="0.99" step="0.01" :value="settingsStore.settings.visSmoothing ?? 0.8" @input="(e) => settingsStore.updateSettings({visSmoothing: parseFloat(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-primary-500" /></div>
            <div class="flex flex-col gap-4"><span class="text-xs font-bold text-gray-500 uppercase tracking-widest">重力 ({{ settingsStore.settings.visGravity ?? 2.0 }})</span><input type="range" min="0.5" max="5.0" step="0.1" :value="settingsStore.settings.visGravity ?? 2.0" @input="(e) => settingsStore.updateSettings({visGravity: parseFloat(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-primary-500" /></div>
            <div class="flex flex-col gap-4">
              <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">高度限制 ({{ Math.round((settingsStore.settings.visHeightLimit ?? 0.8) * 100) }}%)</span>
              <input type="range" min="0.1" max="1.0" step="0.05" :value="settingsStore.settings.visHeightLimit ?? 0.8" @input="(e) => settingsStore.updateSettings({visHeightLimit: parseFloat(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-primary-500" />
            </div>
            <div class="flex flex-col gap-4">
              <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">增幅倍率 ({{ (settingsStore.settings.visGain ?? 1.0).toFixed(1) }}x)</span>
              <input type="range" min="0.1" max="5.0" step="0.1" :value="settingsStore.settings.visGain ?? 1.0" @input="(e) => settingsStore.updateSettings({visGain: parseFloat(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-primary-500" />
            </div>
            <div class="flex flex-col gap-4">
              <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">低频裁剪 ({{ settingsStore.settings.visCutoffLow ?? 0 }}%)</span>
              <input type="range" min="0" max="100" step="1" :value="settingsStore.settings.visCutoffLow ?? 0" @input="(e) => settingsStore.updateSettings({visCutoffLow: parseInt(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-primary-500" />
            </div>
            <div class="flex flex-col gap-4">
              <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">高频裁剪 ({{ settingsStore.settings.visCutoffHigh ?? 75 }}%)</span>
              <input type="range" min="0" max="100" step="1" :value="settingsStore.settings.visCutoffHigh ?? 75" @input="(e) => settingsStore.updateSettings({visCutoffHigh: parseInt(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-primary-500" />
            </div>
          </div>
        </div>
      </section>

      <!-- 4. 视觉实验室 -->
      <section id="section-visual-lab" class="bg-white/50 dark:bg-gray-900/40 backdrop-blur-md rounded-[2.5rem] p-8 border border-gray-100 dark:border-white/5 shadow-sm">
        <div class="flex items-center gap-5 mb-8">
          <div class="p-4 bg-amber-500/10 text-amber-500 rounded-[1.5rem]"><ArrowsPointingOutIcon class="w-7 h-7" /></div>
          <div><h3 class="text-xl font-bold text-gray-800 dark:text-white">视觉实验室</h3><p class="text-sm text-gray-400 mt-1">调控沉浸模式组件尺寸与布局细节</p></div>
        </div>
        <div class="space-y-8">
          <div class="flex flex-col gap-3">
             <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">侧边栏位置</span>
             <div class="flex bg-gray-100 dark:bg-black/20 p-1.5 rounded-2xl w-full">
               <button @click="settingsStore.updateSettings({sidebarPosition: 'left'})" :class="settingsStore.settings.sidebarPosition !== 'right' ? 'bg-white dark:bg-gray-700 shadow-sm text-amber-500' : 'text-gray-400'" class="flex-1 py-3 rounded-xl text-xs font-black transition-all flex items-center justify-center gap-2"><ViewColumnsIcon class="w-4 h-4" /> 靠左</button>
               <button @click="settingsStore.updateSettings({sidebarPosition: 'right'})" :class="settingsStore.settings.sidebarPosition === 'right' ? 'bg-white dark:bg-gray-700 shadow-sm text-amber-500' : 'text-gray-400'" class="flex-1 py-3 rounded-xl text-xs font-black transition-all flex items-center justify-center gap-2"><ViewColumnsIcon class="w-4 h-4 rotate-180" /> 靠右</button>
             </div>
          </div>
          <div class="flex flex-col gap-3">
             <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">画面填充</span>
             <div class="flex bg-gray-100 dark:bg-black/20 p-1.5 rounded-2xl w-full">
               <button v-for="m in [{id:'contain',l:'比例'}, {id:'cover',l:'裁剪'}, {id:'fill',l:'拉伸'}]" :key="m.id" @click="settingsStore.updateSettings({videoFitMode: m.id})" :class="settingsStore.settings.videoFitMode === m.id ? 'bg-white dark:bg-gray-700 shadow-sm text-amber-500' : 'text-gray-400'" class="flex-1 py-3 rounded-xl text-xs font-black transition-all">{{ m.l }}</button>
             </div>
          </div>
          <div class="flex flex-col gap-3">
             <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">叠加信息</span>
             <div class="flex bg-gray-100 dark:bg-black/20 p-1.5 rounded-2xl w-full">
               <button v-for="o in [{id:'all',l:'全部'}, {id:'title_only',l:'仅标题'}, {id:'none',l:'隐藏'}]" :key="o.id" @click="settingsStore.updateSettings({immersiveOverlay: o.id})" :class="settingsStore.settings.immersiveOverlay === o.id ? 'bg-white dark:bg-gray-700 shadow-sm text-amber-500' : 'text-gray-400'" class="flex-1 py-3 rounded-xl text-xs font-black transition-all">{{ o.l }}</button>
             </div>
          </div>
          
          <div class="flex items-center justify-between p-4 bg-gray-50/50 dark:bg-white/5 rounded-2xl border border-transparent hover:border-amber-500/20 transition-all">
            <div>
              <h4 class="text-sm font-bold text-gray-700 dark:text-gray-200">视频容器悬浮动画</h4>
              <p class="text-[10px] text-gray-400 mt-1">关闭后视频在沉浸模式下保持绝对静止</p>
            </div>
            <button @click="settingsStore.updateSettings({immersiveVideoFloat: settingsStore.settings.immersiveVideoFloat === false ? true : false})" 
                    :class="settingsStore.settings.immersiveVideoFloat !== false ? 'bg-amber-500 shadow-amber-500/30' : 'bg-gray-300 dark:bg-white/10'" 
                    class="w-12 h-6 rounded-full transition-all relative flex items-center shrink-0">
              <div class="absolute w-4 h-4 bg-white rounded-full transition-all shadow-sm" :class="settingsStore.settings.immersiveVideoFloat !== false ? 'left-7' : 'left-1'"></div>
            </button>
          </div>

          <!-- 粒子层置顶开关 -->
          <div class="flex items-center justify-between p-4 bg-gray-50/50 dark:bg-white/5 rounded-2xl border border-transparent hover:border-amber-500/20 transition-all">
            <div>
              <h4 class="text-sm font-bold text-gray-700 dark:text-gray-200">粒子层置顶</h4>
              <p class="text-[10px] text-gray-400 mt-1">开启后粒子将漂浮在视频画面之上，关闭则被视频遮挡</p>
            </div>
            <button @click="settingsStore.updateSettings({particleAboveVideo: settingsStore.settings.particleAboveVideo !== false ? false : true})" 
                    :class="settingsStore.settings.particleAboveVideo !== false ? 'bg-amber-500 shadow-amber-500/30' : 'bg-gray-300 dark:bg-white/10'" 
                    class="w-12 h-6 rounded-full transition-all relative flex items-center shrink-0">
              <div class="absolute w-4 h-4 bg-white rounded-full transition-all shadow-sm" :class="settingsStore.settings.particleAboveVideo !== false ? 'left-7' : 'left-1'"></div>
            </button>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div class="flex flex-col gap-4"><div><span class="text-xs font-bold text-gray-500 uppercase">组件大小 ({{ Math.round(settingsStore.settings.videoScale * 100) }}%)</span></div><input type="range" min="0.5" max="1.5" step="0.05" :value="settingsStore.settings.videoScale" @input="(e) => settingsStore.updateSettings({videoScale: parseFloat(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-amber-500" /></div>
            <div class="flex flex-col gap-4"><div><span class="text-xs font-bold text-gray-500 uppercase">背景虚化 ({{ settingsStore.settings.bgBlur }}px)</span></div><input type="range" min="0" max="50" step="1" :value="settingsStore.settings.bgBlur" @input="(e) => settingsStore.updateSettings({bgBlur: parseInt(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-amber-500" /></div>
            <div class="flex flex-col gap-4"><div><span class="text-xs font-bold text-gray-500 uppercase">面板透明度 ({{ Math.round(settingsStore.settings.uiOpacity * 100) }}%)</span></div><input type="range" min="0.0" max="1.0" step="0.05" :value="settingsStore.settings.uiOpacity" @input="(e) => settingsStore.updateSettings({uiOpacity: parseFloat(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-amber-500" /></div>
            <div class="flex flex-col gap-4"><div><span class="text-xs font-bold text-gray-500 uppercase">UI 模糊 ({{ settingsStore.settings.uiBlur }}px)</span></div><input type="range" min="0" max="50" step="1" :value="settingsStore.settings.uiBlur" @input="(e) => settingsStore.updateSettings({uiBlur: parseInt(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-amber-500" /></div>
          </div>
        </div>
      </section>

      <!-- 5. 背景视觉系统 -->
      <section id="section-background" class="bg-white/50 dark:bg-gray-900/40 backdrop-blur-md rounded-[2.5rem] p-8 border border-gray-100 dark:border-white/5 shadow-sm">
        <div class="flex items-center justify-between mb-8">
          <div class="flex items-center gap-5">
            <div class="p-4 bg-emerald-500/10 text-emerald-500 rounded-[1.5rem]"><PhotoIcon class="w-7 h-7" /></div>
            <div><h3 class="text-xl font-bold text-gray-800 dark:text-white">背景视觉系统</h3><p class="text-sm text-gray-400 mt-1">定制播放界面的背景底图与动态交互效果</p></div>
          </div>
        </div>

        <div class="space-y-10">
          <!-- 背景模式与切换逻辑 -->
          <div class="grid grid-cols-1 xl:grid-cols-2 gap-8">
            <div class="flex flex-col gap-3">
               <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">渲染源模式</span>
               <div class="flex bg-gray-100 dark:bg-black/20 p-1.5 rounded-2xl w-full">
                 <button @click="settingsStore.updateSettings({bgType: 'cover'})"
                         :class="settingsStore.settings.bgType === 'cover' ? 'bg-white dark:bg-gray-700 shadow-sm text-emerald-500' : 'text-gray-400'"
                         class="flex-1 py-3 rounded-xl text-xs font-black transition-all">跟随视频封面</button>
                 <button @click="settingsStore.updateSettings({bgType: 'custom'})"
                         :class="settingsStore.settings.bgType === 'custom' ? 'bg-white dark:bg-gray-700 shadow-sm text-emerald-500' : 'text-gray-400'"
                         class="flex-1 py-3 rounded-xl text-xs font-black transition-all">使用自定义图库</button>
               </div>
            </div>

            <div v-if="settingsStore.settings.bgType === 'custom'" class="flex flex-col gap-3 animate-fade-in">
               <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">图库轮换算法</span>
               <div class="flex bg-gray-100 dark:bg-black/20 p-1.5 rounded-2xl w-full">
                 <button @click="settingsStore.updateSettings({bgCustomMode: 'list'})"
                         :class="settingsStore.settings.bgCustomMode === 'list' ? 'bg-white dark:bg-gray-700 shadow-sm text-emerald-500' : 'text-gray-400'"
                         class="flex-1 py-3 rounded-xl text-xs font-black transition-all">顺序轮换</button>
                 <button @click="settingsStore.updateSettings({bgCustomMode: 'shuffle'})"
                         :class="settingsStore.settings.bgCustomMode === 'shuffle' ? 'bg-white dark:bg-gray-700 shadow-sm text-emerald-500' : 'text-gray-400'"
                         class="flex-1 py-3 rounded-xl text-xs font-black transition-all">随机挑选</button>
               </div>
            </div>
          </div>

          <!-- 动态动效叠加层 -->
          <div class="space-y-4">
            <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">物理动效叠加 (支持多选混合)</span>
            <div class="grid grid-cols-3 gap-3">
              <button v-for="eff in bgEffects" :key="eff.id" @click="toggleBgEffect(eff.id)" 
                      :class="settingsStore.settings.bgEffects?.includes(eff.id) ? 'border-emerald-500 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 shadow-lg shadow-emerald-500/10' : 'border-gray-100 dark:border-white/5 text-gray-500 hover:border-gray-300 dark:hover:border-white/20'" 
                      class="flex flex-col p-5 rounded-2xl border-2 transition-all text-center items-center justify-center gap-2">
                <span class="font-black text-[14px] lg:text-[16px] leading-tight uppercase">{{ eff.label }}</span>
                <p class="text-[10px] lg:text-[12px] opacity-50 leading-tight hidden sm:block">{{ eff.desc }}</p>
              </button>
            </div>
          </div>

          <!-- 自定义库管理器 -->
          <div v-if="settingsStore.settings.bgType === 'custom'" class="animate-fade-in bg-gray-50/50 dark:bg-white/5 p-6 rounded-[2rem] border border-gray-100 dark:border-white/5">
              <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
                <div class="flex items-center gap-4">
                  <span class="text-xs font-bold text-gray-500 uppercase tracking-widest">背景素材 ({{ themeStore.customBackgrounds.length }})</span>
                  <div v-if="themeStore.customBackgrounds.length > 0" class="flex items-center gap-2 border-l border-gray-200 dark:border-white/10 pl-4">
                    <button @click="selectAllBgs" class="text-[10px] font-black uppercase tracking-tight text-gray-400 hover:text-emerald-500 transition-colors">
                      {{ isAllBgSelected ? '清空' : '全选' }}
                    </button>
                    <button v-if="selectedBgNames.length > 0" @click="handleBulkDeleteBgs" 
                            class="flex items-center gap-1 px-3 py-1 bg-red-500 hover:bg-red-600 text-white rounded-lg text-[10px] font-black uppercase transition-all shadow-md active:scale-95">
                      <TrashIcon class="w-3 h-3" /> 删除 ({{ selectedBgNames.length }})
                    </button>
                  </div>
                </div>
                <label class="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-xl text-xs font-bold cursor-pointer transition shadow-md shadow-emerald-500/30 active:scale-95">
                  上传图片
                  <input type="file" class="hidden" accept=".png,.jpg,.jpeg,.webp" multiple @change="handleBackgroundUpload" />
                </label>
              </div>

              <div class="max-h-[380px] overflow-y-auto pr-2 scrollbar-thin">
                <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-4 pb-4">
                  <div v-for="bg in themeStore.customBackgrounds" :key="bg.name"
                       @click="toggleBgSelection(bg.name)"
                       class="group relative aspect-video rounded-2xl overflow-hidden border-2 transition-all cursor-pointer bg-black min-w-[120px]"
                       :class="selectedBgNames.includes(bg.name) ? 'border-emerald-500 ring-4 ring-emerald-500/20' : 'border-gray-200 dark:border-white/5'">
                    <img :src="`http://127.0.0.1:12180${bg.url}`" @error="(e) => e.target.style.display='none'" class="w-full h-full object-cover transition-all duration-500"
                         :class="selectedBgNames.includes(bg.name) ? 'scale-110 opacity-100' : 'opacity-70 group-hover:opacity-100'" />
                    <div class="absolute top-2 left-2 w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all"
                         :class="selectedBgNames.includes(bg.name) ? 'bg-emerald-500 border-emerald-500' : 'bg-black/20 border-white/50'">
                      <CheckIcon v-if="selectedBgNames.includes(bg.name)" class="w-3 h-3 text-white font-black" />
                    </div>
                    <div v-if="themeStore.customBgUrl === bg.url" class="absolute top-2 right-2 px-2 py-0.5 bg-emerald-500 text-white rounded-md text-[8px] font-black uppercase shadow-lg z-10">使用中</div>
                  </div>
                </div>
                <div v-if="themeStore.customBackgrounds.length === 0" class="text-center py-20 opacity-30">
                  <PhotoIcon class="w-12 h-12 mx-auto mb-2" />
                  <p class="text-xs font-bold uppercase tracking-widest">请上传素材</p>
                </div>
              </div>
          </div>

          <!-- 物理动力学参数 -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-8 pt-6 border-t border-gray-100 dark:border-white/5">
            <div class="flex flex-col gap-4">
              <div class="flex justify-between items-center">
                <span class="text-xs font-bold text-gray-500 uppercase">动效频率 ({{ (settingsStore.settings.bgAnimationSpeed || 1.0).toFixed(1) }}x)</span>
              </div>
              <input type="range" min="0.1" max="5.0" step="0.1" :value="settingsStore.settings.bgAnimationSpeed || 1.0" @input="(e) => settingsStore.updateSettings({bgAnimationSpeed: parseFloat(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-emerald-500" />
            </div>
            <div class="flex flex-col gap-4">
              <div class="flex justify-between items-center">
                <span class="text-xs font-bold text-gray-500 uppercase">动效幅度 ({{ (settingsStore.settings.bgAnimationAmplitude || 1.0).toFixed(1) }}x)</span>
              </div>
              <input type="range" min="0.1" max="2.0" step="0.1" :value="settingsStore.settings.bgAnimationAmplitude || 1.0" @input="(e) => settingsStore.updateSettings({bgAnimationAmplitude: parseFloat(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-emerald-500" />
            </div>
          </div>
        </div>
      </section>

      <!-- 6. 快捷键 -->
      <section id="section-shortcuts" class="bg-white/50 dark:bg-gray-900/40 backdrop-blur-md rounded-[2.5rem] p-8 border border-gray-100 dark:border-white/5 shadow-sm">
        <div class="flex items-center gap-5 mb-8"><div class="p-4 bg-slate-500/10 text-slate-500 rounded-[1.5rem]"><CommandLineIcon class="w-7 h-7" /></div><h3 class="text-xl font-bold text-gray-800 dark:text-white">快捷键控制</h3></div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div v-for="(label, keyId) in shortcutLabels" :key="keyId" class="flex items-center justify-between p-4 bg-gray-50/50 dark:bg-white/5 rounded-2xl border border-transparent hover:border-slate-500/20 transition-all"><span class="text-xs font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider">{{ label }}</span><button @click="startRecording(keyId)" :class="recordingKey === keyId ? 'ring-2 ring-primary-500 bg-primary-500 text-white' : 'bg-white dark:bg-gray-800 text-slate-500 border border-gray-200 dark:border-white/10 shadow-sm'" class="min-w-[100px] px-4 py-2 rounded-xl text-[10px] font-black uppercase transition-all flex items-center justify-center gap-2"><template v-if="recordingKey === keyId"><span class="animate-pulse">按下按键...</span><XMarkSolidIcon @click.stop="stopRecording" class="w-3 h-3 hover:scale-125" /></template><template v-else>{{ formatKeyCode(settingsStore.settings.shortcuts[keyId]) }}</template></button></div>
        </div>
      </section>

      <!-- 7. 交互过渡 -->
      <section id="section-interaction" class="bg-white/50 dark:bg-gray-900/40 backdrop-blur-md rounded-[2.5rem] p-8 border border-gray-100 dark:border-white/5 shadow-sm">
        <div class="flex items-center gap-5 mb-8"><div class="p-4 bg-rose-500/10 text-rose-500 rounded-[1.5rem]"><ArrowPathRoundedSquareIcon class="w-7 h-7" /></div><h3 class="text-xl font-bold text-gray-800 dark:text-white">交互过渡</h3></div>
        <div class="space-y-8">
          <div class="flex flex-col gap-3"><span class="text-xs font-bold text-gray-500 uppercase tracking-widest">路由切换动画</span><div class="flex bg-gray-100 dark:bg-black/20 p-1.5 rounded-2xl w-full"><button v-for="t in [{id:'fade',l:'淡入'}, {id:'slide',l:'推移'}, {id:'scale',l:'缩放'}, {id:'none',l:'无'}]" :key="t.id" @click="settingsStore.updateSettings({uiTransition: t.id})" :class="settingsStore.settings.uiTransition === t.id ? 'bg-white dark:bg-gray-700 shadow-sm text-rose-500' : 'text-gray-400'" class="flex-1 py-3 rounded-xl text-xs font-black transition-all">{{ t.l }}</button></div></div>
          
          <div class="flex items-center justify-between p-4 bg-gray-50/50 dark:bg-white/5 rounded-2xl border border-transparent hover:border-rose-500/20 transition-all"><div><h4 class="text-sm font-bold text-gray-700 dark:text-gray-200">切歌音量淡入</h4></div><button @click="settingsStore.updateSettings({enableVolumeFade: !settingsStore.settings.enableVolumeFade})" :class="settingsStore.settings.enableVolumeFade !== false ? 'bg-rose-500 shadow-rose-500/30' : 'bg-gray-300 dark:bg-white/10'" class="w-12 h-6 rounded-full transition-all relative flex items-center shrink-0"><div class="absolute w-4 h-4 bg-white rounded-full transition-all shadow-sm" :class="settingsStore.settings.enableVolumeFade !== false ? 'left-7' : 'left-1'"></div></button></div>
          
          <!-- 沉浸模式自动隐藏 UI 计时 -->
          <div class="flex flex-col gap-4">
            <div class="flex justify-between items-center"><span class="text-sm font-bold text-gray-600 dark:text-gray-300">沉浸模式自动隐藏 UI 延迟 ({{ settingsStore.settings.idleTimeout || 3 }}s)</span></div>
            <input type="range" min="1" max="10" step="1" :value="settingsStore.settings.idleTimeout || 3" @input="(e) => settingsStore.updateSettings({idleTimeout: parseInt(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-rose-500" />
            <p class="text-[10px] text-gray-400 italic">控制鼠标空闲多久后自动隐藏光标与控件</p>
          </div>

          <!-- 自动关机/休眠倒计时 -->
          <div class="flex flex-col gap-4">
            <div class="flex justify-between items-center"><span class="text-sm font-bold text-gray-600 dark:text-gray-300">自动关机/休眠倒计时 ({{ Math.floor((settingsStore.settings.autoActionTimeout || 180) / 60) }} 分钟)</span></div>
            <input type="range" min="60" max="1800" step="60" :value="settingsStore.settings.autoActionTimeout || 180" @input="(e) => {
              const val = parseInt(e.target.value);
              settingsStore.updateSettings({autoActionTimeout: val});
              localStorage.setItem('player_auto_action_timeout', val.toString());
            }" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-rose-500" />
            <p class="text-[10px] text-gray-400 italic">触发自动关机或休眠时的确认倒计时长度</p>
          </div>
        </div>
      </section>

      <!-- 8. 启动行为 -->
      <section id="section-startup" class="bg-white/50 dark:bg-gray-900/40 backdrop-blur-md rounded-[2.5rem] p-8 border border-gray-100 dark:border-white/5 shadow-sm">
        <div class="flex items-center gap-5 mb-8"><div class="p-4 bg-orange-500/10 text-orange-500 rounded-[1.5rem]"><RocketLaunchIcon class="w-7 h-7" /></div><h3 class="text-xl font-bold text-gray-800 dark:text-white">启动行为</h3></div>
        <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
          <button v-for="p in [{id:'home',l:'登录页'}, {id:'bili',l:'B站收藏'}, {id:'local',l:'本地库'}, {id:'queue',l:'队列'}, {id:'last',l:'记忆'}]" :key="p.id" @click="settingsStore.updateSettings({startupPage: p.id})" :class="settingsStore.settings.startupPage === p.id ? 'border-orange-500 bg-orange-500/10 text-orange-600 dark:text-orange-400' : 'border-transparent bg-gray-50 dark:bg-white/5 text-gray-500'" class="flex flex-col p-4 rounded-2xl border-2 transition-all text-center items-center justify-center font-bold text-xs">{{ p.l }}</button>
        </div>
        <div class="mt-6 pt-6 border-t border-gray-100 dark:border-white/5 flex items-center justify-between">
          <div>
            <h4 class="text-sm font-bold text-gray-700 dark:text-gray-200">桌面快捷方式</h4>
            <p class="text-[10px] text-gray-400 mt-1">如果桌面快捷方式丢失，可以点击重新创建</p>
          </div>
          <button @click="createDesktopShortcut" class="px-4 py-2 bg-orange-500 hover:bg-orange-600 text-white rounded-xl text-xs font-bold transition shadow-md shadow-orange-500/30 active:scale-95">
            创建快捷方式
          </button>
        </div>
      </section>

      <!-- 9. 媒体质量 -->
      <section id="section-quality" class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div class="bg-white/50 dark:bg-gray-900/40 backdrop-blur-md rounded-[2.5rem] p-6 border border-gray-100 dark:border-white/5 shadow-sm" :class="{'z-30': openDropdown === 'stream'}">
          <div class="flex items-center gap-4 mb-6"><div class="p-3 bg-blue-500/10 text-blue-500 rounded-2xl"><TvIcon class="w-6 h-6" /></div><h3 class="font-bold text-gray-800 dark:text-white text-sm uppercase tracking-wider">视频流质量</h3></div>
          <div class="relative"><div @click="toggleDropdown('stream', $event)" class="w-full flex items-center justify-between px-5 py-4 bg-gray-50 dark:bg-white/5 rounded-2xl cursor-pointer border border-transparent dark:border-white/5 font-black text-blue-500 text-sm">{{ getLabel(settingsStore.settings.streamQuality) }}<ChevronDownIcon class="w-4 h-4 text-gray-400" /></div><transition name="dropdown"><div v-if="openDropdown === 'stream'" class="absolute top-full left-0 right-0 mt-3 z-[60] bg-white dark:bg-gray-800 rounded-3xl shadow-2xl border border-gray-100 dark:border-white/10 overflow-hidden"><div class="p-2 max-h-60 overflow-y-auto scrollbar-thin"><div v-for="q in qualities" :key="'s'+q.val" @click.stop="selectQuality('stream', q)" class="flex items-center justify-between px-4 py-3 rounded-xl cursor-pointer" :class="[settingsStore.settings.streamQuality === q.val ? 'bg-blue-500 text-white' : 'hover:bg-gray-50 dark:hover:bg-white/5 text-gray-700 dark:text-gray-300']"><span class="font-bold text-xs">{{ q.label }}</span><LockClosedIcon v-if="q.member && !isMember()" class="w-3 h-3 text-gray-400" /></div></div></div></transition></div>
        </div>
        <div class="bg-white/50 dark:bg-gray-900/40 backdrop-blur-md rounded-[2.5rem] p-6 border border-gray-100 dark:border-white/5 shadow-sm" :class="{'z-30': openDropdown === 'cache'}">
          <div class="flex items-center gap-4 mb-6"><div class="p-3 bg-pink-500/10 text-pink-500 rounded-2xl"><ArrowDownTrayIcon class="w-6 h-6" /></div><h3 class="font-bold text-gray-800 dark:text-white text-sm uppercase tracking-wider">缓存质量</h3></div>
          <div class="relative"><div @click="toggleDropdown('cache', $event)" class="w-full flex items-center justify-between px-5 py-4 bg-gray-50 dark:bg-white/5 rounded-2xl cursor-pointer border border-transparent dark:border-white/5 font-black text-pink-500 text-sm">{{ getLabel(settingsStore.settings.cacheQuality) }}<ChevronDownIcon class="w-4 h-4 text-gray-400" /></div><transition name="dropdown"><div v-if="openDropdown === 'cache'" class="absolute top-full left-0 right-0 mt-3 z-[60] bg-white dark:bg-gray-800 rounded-3xl shadow-2xl border border-gray-100 dark:border-white/10 overflow-hidden"><div class="p-2 max-h-60 overflow-y-auto scrollbar-thin"><div v-for="q in qualities" :key="'c'+q.val" @click.stop="selectQuality('cache', q)" class="flex items-center justify-between px-4 py-3 rounded-xl cursor-pointer" :class="[settingsStore.settings.cacheQuality === q.val ? 'bg-pink-500 text-white' : 'hover:bg-gray-50 dark:hover:bg-white/5 text-gray-700 dark:text-gray-300']"><span class="font-bold text-xs">{{ q.label }}</span><LockClosedIcon v-if="q.member && !isMember()" class="w-3 h-3 text-gray-400" /></div></div></div></transition></div>
        </div>
      </section>

      <!-- 10. 算法实验室 -->
      <section id="section-algorithm" class="bg-white/50 dark:bg-gray-900/40 backdrop-blur-md rounded-[2.5rem] p-8 border border-gray-100 dark:border-white/5 shadow-sm">
        <div class="flex items-center gap-5 mb-8"><div class="p-4 bg-indigo-500/10 text-indigo-500 rounded-[1.5rem]"><ScaleIcon class="w-7 h-7" /></div><div><h3 class="text-xl font-bold text-gray-800 dark:text-white">算法实验室</h3><p class="text-sm text-gray-400 mt-1">控制随机播放的权重倾向</p></div></div>
        <div class="flex flex-col gap-4"><div><span class="text-xs font-bold text-gray-500 uppercase tracking-widest">权重偏好强度 ({{ (settingsStore.settings.weightSensitivity || 2.0).toFixed(1) }})</span></div><input type="range" min="1.0" max="5.0" step="0.1" :value="settingsStore.settings.weightSensitivity || 2.0" @input="(e) => settingsStore.updateSettings({weightSensitivity: parseFloat(e.target.value)})" class="w-full h-1.5 bg-gray-200 dark:bg-white/10 rounded-full appearance-none accent-indigo-500" /></div>
      </section>

      <!-- 11. 基础音量 -->
      <section id="section-volume" class="bg-white/50 dark:bg-gray-900/40 backdrop-blur-md rounded-[2.5rem] p-8 border border-gray-100 dark:border-white/5 shadow-sm">
        <div class="flex items-center gap-5 mb-8"><div class="p-4 bg-purple-500/10 text-purple-500 rounded-[1.5rem]"><SpeakerWaveIcon class="w-7 h-7" /></div><div><h3 class="text-xl font-bold text-gray-800 dark:text-white">基础音量</h3></div></div>
        <div class="flex items-center gap-8 bg-gray-50/50 dark:bg-white/5 p-8 rounded-[2rem]"><div class="flex flex-col items-center gap-1 w-24 shrink-0"><span class="text-4xl font-black text-purple-500 tabular-nums">{{ Math.round(store.volume * 100) }}</span></div><div class="flex-1 relative h-6 flex items-center"><input type="range" min="0" max="1" step="0.01" :value="store.volume" @input="handleVolumeChange" class="w-full h-2 bg-gray-200 dark:bg-white/10 rounded-full appearance-none cursor-pointer accent-purple-500" /></div></div>
      </section>

      <!-- 12. 数据同步与备份 -->
      <section id="section-sync" class="bg-white/50 dark:bg-gray-900/40 backdrop-blur-md rounded-[2.5rem] p-8 border border-gray-100 dark:border-white/5 shadow-sm">
        

        <div class="flex items-center gap-5 mb-8">
          <div class="p-4 bg-cyan-500/10 text-cyan-500 rounded-[1.5rem]"><CircleStackIcon class="w-7 h-7" /></div>
          <div><h3 class="text-xl font-bold text-gray-800 dark:text-white">数据同步与备份</h3><p class="text-sm text-gray-400 mt-1">跨端同步媒体库及物理缓存文件</p></div>
        </div>
        
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <!-- 导出面板 -->
          <div class="flex flex-col gap-6 bg-gray-50/50 dark:bg-white/5 p-6 rounded-[2rem] border border-gray-100 dark:border-white/5">
             <div class="flex items-center gap-3 border-b border-gray-200 dark:border-white/10 pb-4">
                <CloudArrowUpIcon class="w-6 h-6 text-cyan-500" />
                <h4 class="font-black text-gray-800 dark:text-white">创建备份 (Export)</h4>
             </div>
             <div class="flex flex-col gap-4">
                <div class="flex items-center justify-between p-3 bg-white dark:bg-black/20 rounded-xl border border-gray-100 dark:border-white/5">
                  <span class="text-xs font-bold text-gray-600 dark:text-gray-300">导出本地媒体库</span>
                  <input type="checkbox" v-model="exportSettings.exportLibrary" class="accent-cyan-500 w-4 h-4 cursor-pointer" />
                </div>
                
                <div v-if="exportSettings.exportLibrary" class="flex flex-col gap-2">
                   <span class="text-[10px] font-bold text-gray-500 uppercase">选择媒体夹 (留空则全选)</span>
                   <div class="flex flex-wrap gap-2 max-h-32 overflow-y-auto scrollbar-thin">
                     <button v-for="c in store.localCollections" :key="c.id"
                             @click="() => {
                               const idx = exportSettings.selectedCollections.indexOf(c.id);
                               if(idx > -1) exportSettings.selectedCollections.splice(idx, 1);
                               else exportSettings.selectedCollections.push(c.id);
                             }"
                             :class="exportSettings.selectedCollections.includes(c.id) ? 'bg-cyan-500 text-white shadow-md' : 'bg-white dark:bg-gray-800 text-gray-500 border-gray-200 dark:border-white/10'"
                             class="px-3 py-1.5 rounded-lg text-[10px] font-bold transition-all border">
                       {{ c.title }}
                     </button>
                   </div>
                </div>
                
                <div class="flex items-center justify-between p-3 bg-white dark:bg-black/20 rounded-xl border border-gray-100 dark:border-white/5">
                  <span class="text-xs font-bold text-gray-600 dark:text-gray-300">导出当前播放队列</span>
                  <input type="checkbox" v-model="exportSettings.exportQueue" class="accent-cyan-500 w-4 h-4 cursor-pointer" />
                </div>
                
                <div class="flex flex-col gap-2 pt-2 border-t border-gray-200 dark:border-white/10">
                  <span class="text-[10px] font-bold text-gray-500 uppercase">打包内容策略</span>
                  <div class="flex gap-2 bg-gray-100 dark:bg-black/20 p-1.5 rounded-2xl">
                    <button @click="exportSettings.type = 'data'" :class="exportSettings.type === 'data' ? 'bg-white dark:bg-gray-700 shadow-sm text-cyan-500' : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'" class="flex-1 py-2.5 rounded-xl text-xs font-black transition">仅元数据 (连带本地文件)</button>
                    <button @click="exportSettings.type = 'full'" :class="exportSettings.type === 'full' ? 'bg-white dark:bg-gray-700 shadow-sm text-cyan-500' : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'" class="flex-1 py-2.5 rounded-xl text-xs font-black transition">全量包 (含所有缓存)</button>
                  </div>
                </div>
                
                <button @click="handleExportLibrary" :disabled="settingsStore.isExportingLibrary" class="mt-2 w-full py-3 bg-cyan-500 hover:bg-cyan-600 text-white rounded-2xl font-black shadow-lg shadow-cyan-500/30 transition active:scale-95 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed">
                  <ArrowPathIcon v-if="settingsStore.isExportingLibrary" class="w-5 h-5 animate-spin" />
                  <ArrowDownTrayIcon v-else class="w-5 h-5" />
                  {{ settingsStore.isExportingLibrary ? '正在打包压缩 (可能需要数分钟)...' : '立即生成并下载 ZIP' }}
                </button>
             </div>
          </div>
          
          <!-- 导入面板 -->
          <div class="flex flex-col gap-6 bg-gray-50/50 dark:bg-white/5 p-6 rounded-[2rem] border border-gray-100 dark:border-white/5">
             <div class="flex items-center gap-3 border-b border-gray-200 dark:border-white/10 pb-4">
                <CloudArrowDownIcon class="w-6 h-6 text-indigo-500" />
                <h4 class="font-black text-gray-800 dark:text-white">恢复备份 (Import)</h4>
             </div>
             
             <div class="flex-1 flex flex-col items-center justify-center gap-4 w-full">
                <p class="text-xs text-gray-400 text-center px-4 leading-relaxed">
                  选择之前生成的 ZIP 备份包，系统会自动分析文件变化并提供冲突解决选项。
                </p>
                <div v-if="importState.isUploading" class="w-full max-w-sm mt-2 flex flex-col gap-2">
                  <div class="flex justify-between text-[10px] font-black text-indigo-500 uppercase tracking-widest">
                    <span>正在上传解析备份包...</span>
                    <span>{{ importState.uploadProgress }}%</span>
                  </div>
                  <div class="w-full h-1.5 bg-indigo-500/20 rounded-full overflow-hidden">
                    <div class="h-full bg-indigo-500 transition-all duration-300" :style="{ width: importState.uploadProgress + '%' }"></div>
                  </div>
                </div>
                <label v-else class="px-6 py-3 bg-indigo-500 hover:bg-indigo-600 text-white rounded-2xl font-black shadow-lg shadow-indigo-500/30 transition active:scale-95 cursor-pointer flex items-center gap-2 mt-2">
                  <ArrowUpTrayIcon class="w-5 h-5" /> 解析 ZIP 文件
                  <input type="file" class="hidden" accept=".zip" @change="handleLibraryImport" />
                </label>
             </div>
          </div>
        </div>

        <!-- 危险操作面板 -->
        <div class="flex flex-col gap-6 bg-red-50/50 dark:bg-red-500/5 p-6 rounded-[2rem] border border-red-100 dark:border-red-500/10 col-span-1 lg:col-span-2 mt-2">
           <div class="flex items-center gap-3 border-b border-red-200 dark:border-red-500/10 pb-4">
              <ExclamationTriangleIcon class="w-6 h-6 text-red-500" />
              <h4 class="font-black text-red-600 dark:text-red-400">危险操作 (Danger Zone)</h4>
           </div>
           <p class="text-xs text-red-500/80 dark:text-red-400/80 leading-relaxed text-center px-4">
             重置软件将清空所有本地数据，包括媒体库、播放队列、系统设置以及所有的音视频缓存文件（系统及默认主题的静态资源除外）。<br/><b>此操作不可逆！</b>
           </p>
           <button @click="handleFactoryResetClick" class="w-full py-3 bg-red-500 hover:bg-red-600 text-white rounded-2xl font-black shadow-lg shadow-red-500/30 transition active:scale-95 flex items-center justify-center gap-2">
             <TrashIcon class="w-5 h-5" /> 重置软件
           </button>

           <button @click="handleUninstallClick" class="w-full py-3 mt-4 bg-gray-800 dark:bg-white text-white dark:text-black hover:bg-black dark:hover:bg-gray-200 rounded-2xl font-black shadow-lg transition active:scale-95 flex items-center justify-center gap-2">
             <PowerIcon class="w-5 h-5" /> 卸载软件
           </button>
        </div>
      </section>

      <!-- 13. 系统日志 -->
      <section id="section-logs" class="bg-white/50 dark:bg-gray-900/40 backdrop-blur-md rounded-[2.5rem] p-8 border border-gray-100 dark:border-white/5 shadow-sm">
        <!-- 标题栏 -->
        <div class="flex flex-wrap items-center justify-between gap-4 mb-6">
          <div class="flex items-center gap-5">
            <div class="p-4 bg-gray-500/10 text-gray-500 rounded-[1.5rem]"><CommandLineIcon class="w-7 h-7" /></div>
            <div>
              <h3 class="text-xl font-bold text-gray-800 dark:text-white flex items-center gap-3">
                系统日志
                <span v-if="isLiveTail"
                      class="px-2 py-0.5 rounded-lg text-[10px] font-black flex items-center gap-1"
                      :class="isLogStreamConnected ? 'bg-emerald-500/15 text-emerald-500' : 'bg-amber-500/15 text-amber-500'">
                  <span class="w-1.5 h-1.5 rounded-full animate-pulse"
                        :class="isLogStreamConnected ? 'bg-emerald-500' : 'bg-amber-500'"></span>
                  {{ isLogStreamConnected ? '实时连接中' : '连接中...' }}
                </span>
              </h3>
              <p class="text-sm text-gray-400 mt-1">
                实时日志 · 多条件筛选 · 物理日志管理
                <span v-if="logStats.time" class="ml-2 font-mono text-[11px] text-gray-400">
                  服务端时间 {{ logStats.time }}
                </span>
              </p>
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <button @click="isLiveTail ? stopLiveLog() : startLiveLog()"
                    class="px-3.5 py-2 rounded-xl text-xs font-bold transition shadow-md active:scale-95 flex items-center gap-2"
                    :class="isLiveTail
                      ? 'bg-amber-500 hover:bg-amber-600 text-white shadow-amber-500/30'
                      : 'bg-emerald-500 hover:bg-emerald-600 text-white shadow-emerald-500/30'">
              <component :is="isLiveTail ? PauseIcon : PlayIcon" class="w-4 h-4" />
              {{ isLiveTail ? '暂停实时' : '实时日志' }}
            </button>
            <button @click="refreshLogs" :disabled="isFetchingLogs"
                    class="px-3.5 py-2 bg-gray-500 hover:bg-gray-600 text-white rounded-xl text-xs font-bold transition shadow-md shadow-gray-500/30 active:scale-95 flex items-center gap-2 disabled:opacity-50">
              <ArrowPathIcon class="w-4 h-4" :class="{ 'animate-spin': isFetchingLogs }" />
              刷新
            </button>
          </div>
        </div>

        <!-- 日志统计 -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
          <div class="p-3.5 rounded-2xl bg-gray-50/70 dark:bg-white/5 border border-gray-100 dark:border-white/5">
            <div class="text-[10px] font-black text-gray-400 uppercase tracking-widest">内存日志</div>
            <div class="text-sm font-black text-gray-700 dark:text-gray-200 mt-1">
              {{ logStats.memory_count ?? 0 }} <span class="text-[10px] text-gray-400">/ {{ logStats.memory_capacity ?? 0 }}</span>
            </div>
          </div>
          <div class="p-3.5 rounded-2xl bg-gray-50/70 dark:bg-white/5 border border-gray-100 dark:border-white/5">
            <div class="text-[10px] font-black text-gray-400 uppercase tracking-widest">磁盘占用</div>
            <div class="text-sm font-black text-gray-700 dark:text-gray-200 mt-1">
              {{ formatBytes(logStats.total_bytes) }}
              <span class="text-[10px] text-gray-400">/ {{ formatBytes(logStats.max_total_bytes) }}</span>
            </div>
          </div>
          <div class="p-3.5 rounded-2xl bg-gray-50/70 dark:bg-white/5 border border-gray-100 dark:border-white/5">
            <div class="text-[10px] font-black text-gray-400 uppercase tracking-widest">日志文件</div>
            <div class="text-sm font-black text-gray-700 dark:text-gray-200 mt-1">
              {{ logStats.file_count ?? 0 }} <span class="text-[10px] text-gray-400">/ {{ logStats.max_files ?? 0 }} 个</span>
            </div>
          </div>
          <div class="p-3.5 rounded-2xl bg-gray-50/70 dark:bg-white/5 border border-gray-100 dark:border-white/5">
            <div class="text-[10px] font-black text-gray-400 uppercase tracking-widest">当前筛选</div>
            <div class="text-sm font-black text-gray-700 dark:text-gray-200 mt-1">
              {{ systemLogs.length }} 条
              <span v-if="activeFilterCount > 0" class="text-[10px] text-primary-500">· {{ activeFilterCount }} 项条件</span>
            </div>
          </div>
        </div>

        <!-- 操作状态栏：任一步骤失败都会在这里明确显示原因 -->
        <div v-if="logStatus.lastTime"
             class="mb-4 px-4 py-2.5 rounded-2xl text-[11px] font-bold flex flex-wrap items-center gap-x-3 gap-y-1 border"
             :class="logStatus.lastError
               ? 'bg-red-50 dark:bg-red-500/10 border-red-200 dark:border-red-500/20 text-red-600 dark:text-red-400'
               : 'bg-emerald-50/70 dark:bg-emerald-500/5 border-emerald-100 dark:border-emerald-500/10 text-emerald-700 dark:text-emerald-400'">
          <component :is="logStatus.lastError ? XCircleIcon : CheckCircleIcon" class="w-4 h-4 shrink-0" />
          <span>{{ logStatus.lastAction || '就绪' }}</span>
          <span v-if="logStatus.lastError" class="font-mono break-all">{{ logStatus.lastError }}</span>
          <span class="ml-auto text-gray-400 font-mono">{{ logStatus.lastTime }}</span>
        </div>

        <!-- 筛选器 -->
        <div class="p-5 rounded-[2rem] bg-gray-50/60 dark:bg-white/5 border border-gray-100 dark:border-white/5 mb-4 space-y-4">
          <div class="flex items-center gap-2">
            <FunnelIcon class="w-4 h-4 text-primary-500" />
            <span class="text-xs font-black text-gray-700 dark:text-gray-200 tracking-wide">日志筛选（各条件可叠加）</span>
            <button @click="resetLogFilter"
                    class="ml-auto text-[10px] font-black text-gray-400 hover:text-primary-500 transition">重置全部条件</button>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label class="text-[10px] font-black text-gray-400 uppercase tracking-widest ml-1">包含关键字（用 | 分隔多个）</label>
              <input v-model="logFilter.keyword" @keyup.enter="onLogFilterChange" @change="onLogFilterChange"
                     placeholder="例如：下载失败|Errno"
                     class="mt-1 w-full bg-white dark:bg-black/20 border border-gray-200 dark:border-white/10 rounded-xl px-3 py-2 text-xs font-bold text-gray-800 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500" />
            </div>
            <div>
              <label class="text-[10px] font-black text-gray-400 uppercase tracking-widest ml-1">屏蔽关键字（用 | 分隔多个）</label>
              <input v-model="logFilter.exclude" @keyup.enter="onLogFilterChange" @change="onLogFilterChange"
                     placeholder="例如：请求|轮询"
                     class="mt-1 w-full bg-white dark:bg-black/20 border border-gray-200 dark:border-white/10 rounded-xl px-3 py-2 text-xs font-bold text-gray-800 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500" />
            </div>
            <div>
              <label class="text-[10px] font-black text-gray-400 uppercase tracking-widest ml-1">模块名包含</label>
              <input v-model="logFilter.loggerContains" @keyup.enter="onLogFilterChange" @change="onLogFilterChange"
                     placeholder="例如：download_service"
                     class="mt-1 w-full bg-white dark:bg-black/20 border border-gray-200 dark:border-white/10 rounded-xl px-3 py-2 text-xs font-bold text-gray-800 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500" />
            </div>
          </div>

          <div class="flex flex-wrap items-center gap-3">
            <span class="text-[10px] font-black text-gray-400 uppercase tracking-widest">日志级别</span>
            <button @click="showAllLogLevels()"
                    class="px-3 py-1.5 rounded-xl text-[10px] font-black transition border"
                    :class="logFilter.levels.length === 0
                      ? 'bg-primary-500 text-white border-primary-500 shadow-md shadow-primary-500/20'
                      : 'bg-white dark:bg-black/20 text-gray-400 border-gray-200 dark:border-white/10 hover:border-primary-300'">
              全部
            </button>
            <button v-for="level in LOG_LEVELS" :key="level"
                    @click="toggleLogLevel(level)"
                    class="px-3 py-1.5 rounded-xl text-[10px] font-black transition border"
                    :class="logFilter.levels.includes(level)
                      ? 'bg-primary-500 text-white border-primary-500 shadow-md shadow-primary-500/20'
                      : 'bg-white dark:bg-black/20 text-gray-400 border-gray-200 dark:border-white/10 hover:border-primary-300'">
              {{ level }}
              <span class="opacity-70">({{ logLevelCounts[level] || 0 }})</span>
            </button>
            <span class="text-[10px] text-gray-400 italic">点击单个级别 = 只看这一级；再点一次 = 恢复全部</span>
          </div>

          <!-- 心跳/噪声日志屏蔽（分类可分别开关） -->
          <div class="flex flex-wrap items-center gap-3">
            <span class="text-[10px] font-black text-gray-400 uppercase tracking-widest">心跳日志屏蔽</span>
            <button v-for="cat in LOG_HEARTBEAT_CATEGORIES" :key="cat.id"
                    @click="toggleHeartbeatCategory(cat.id)"
                    :title="cat.desc"
                    class="px-3 py-1.5 rounded-xl text-[10px] font-black transition border flex items-center gap-1.5"
                    :class="logFilter.hideHeartbeat && logFilter.heartbeatCategories.includes(cat.id)
                      ? 'bg-emerald-500 text-white border-emerald-500'
                      : 'bg-white dark:bg-black/20 text-gray-400 border-gray-200 dark:border-white/10 hover:border-emerald-300'">
              <component :is="logFilter.hideHeartbeat && logFilter.heartbeatCategories.includes(cat.id) ? EyeSlashIcon : EyeIcon" class="w-3.5 h-3.5" />
              {{ cat.label }}
              <span class="opacity-70">({{ (logMeta.heartbeat_categories || {})[cat.id] || 0 }})</span>
            </button>
            <span class="text-[10px] text-gray-400 italic">
              登录验证噪声（导航接口校验、登录成功、API 缓存清除）已归入「登录验证」，可单独屏蔽
            </span>
          </div>

          <div class="flex flex-wrap items-center gap-3">
            <span class="text-[10px] font-black text-gray-400 uppercase tracking-widest">时间区间</span>
            <input type="datetime-local" v-model="logFilter.startTime" @change="onLogFilterChange"
                   class="bg-white dark:bg-black/20 border border-gray-200 dark:border-white/10 rounded-xl px-3 py-2 text-xs font-bold text-gray-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500" />
            <span class="text-xs text-gray-400 font-bold">至</span>
            <input type="datetime-local" v-model="logFilter.endTime" @change="onLogFilterChange"
                   class="bg-white dark:bg-black/20 border border-gray-200 dark:border-white/10 rounded-xl px-3 py-2 text-xs font-bold text-gray-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500" />
            <span class="text-[10px] text-gray-400 italic">留空表示不限</span>
          </div>
        </div>

        <!-- 日志内容 -->
        <div class="bg-gray-900 rounded-2xl overflow-hidden flex flex-col h-[420px]">
          <div class="px-4 py-2.5 border-b border-white/10 flex items-center gap-3 shrink-0">
            <span class="text-[10px] font-black text-gray-400 uppercase tracking-widest">日志输出</span>
            <span class="text-[10px] text-gray-500">
              最新在上 · 共 {{ systemLogs.length }} 条
            </span>
            <div class="ml-auto flex items-center gap-2">
              <button @click="copyAllLogs"
                      class="px-2.5 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white text-[10px] font-black transition flex items-center gap-1.5">
                <ClipboardDocumentIcon class="w-3.5 h-3.5" /> 一键复制
              </button>
              <button @click="downloadLogs('txt')" :disabled="isDownloadingLogs"
                      class="px-2.5 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white text-[10px] font-black transition flex items-center gap-1.5 disabled:opacity-50">
                <DocumentArrowDownIcon class="w-3.5 h-3.5" :class="{ 'animate-bounce': isDownloadingLogs }" /> 下载 TXT
              </button>
              <button @click="downloadLogs('json')" :disabled="isDownloadingLogs"
                      class="px-2.5 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white text-[10px] font-black transition flex items-center gap-1.5 disabled:opacity-50">
                <DocumentArrowDownIcon class="w-3.5 h-3.5" /> JSON
              </button>
              <button @click="clearMemoryLogs"
                      class="px-2.5 py-1.5 rounded-lg bg-white/10 hover:bg-red-500/60 text-white text-[10px] font-black transition flex items-center gap-1.5">
                <TrashIcon class="w-3.5 h-3.5" /> 清屏
              </button>
            </div>
          </div>

          <div v-if="systemLogs.length === 0" class="flex-1 flex items-center justify-center text-gray-500 text-sm font-bold">
            {{ isFetchingLogs ? '正在加载日志...' : '当前筛选条件下没有日志' }}
          </div>
          <div v-else ref="logViewport" class="flex-1 overflow-y-auto scrollbar-thin font-mono text-[11px] py-2">
            <div v-for="(log, idx) in systemLogs" :key="log.seq || idx"
                 class="flex gap-3 px-4 py-1 hover:bg-white/5">
              <span class="text-gray-500 shrink-0 tabular-nums">{{ formatLogTime(log.time, log.ts) }}</span>
              <span class="shrink-0 w-[68px] font-black" :class="{
                'text-red-400': log.level === 'ERROR' || log.level === 'CRITICAL',
                'text-amber-400': log.level === 'WARNING',
                'text-blue-400': log.level === 'INFO',
                'text-gray-500': log.level === 'DEBUG'
              }">{{ log.level }}</span>
              <span class="text-gray-300 break-all whitespace-pre-wrap flex-1">{{ log.message }}</span>
            </div>
          </div>
        </div>

        <!-- 物理日志管理 -->
        <div class="mt-5 p-5 rounded-[2rem] bg-gray-50/60 dark:bg-white/5 border border-gray-100 dark:border-white/5 space-y-4">
          <div class="flex flex-wrap items-center gap-3">
            <ServerStackIcon class="w-4 h-4 text-cyan-500" />
            <span class="text-xs font-black text-gray-700 dark:text-gray-200 tracking-wide">物理日志管理</span>
            <span class="text-[10px] font-mono text-gray-400 break-all">{{ logStats.log_dir || '（未初始化）' }}</span>
            <div class="ml-auto flex flex-wrap items-center gap-2">
              <button @click="openLogDirectory" :disabled="isOpeningLogDir"
                      class="px-3.5 py-2 bg-cyan-500 hover:bg-cyan-600 text-white rounded-xl text-xs font-bold transition shadow-md shadow-cyan-500/30 active:scale-95 flex items-center gap-2 disabled:opacity-50">
                <FolderOpenIcon class="w-4 h-4" />
                打开日志目录
              </button>
              <button @click="purgeLogState.show = true"
                      class="px-3.5 py-2 bg-white dark:bg-black/20 border border-red-200 dark:border-red-500/20 text-red-500 rounded-xl text-xs font-bold transition active:scale-95 flex items-center gap-2">
                <TrashIcon class="w-4 h-4" /> 删除全部日志文件
              </button>
            </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label class="text-[10px] font-black text-gray-400 uppercase tracking-widest ml-1">文件数量上限</label>
              <input type="number" min="1" max="200" v-model.number="logRetention.maxFiles"
                     class="mt-1 w-full bg-white dark:bg-black/20 border border-gray-200 dark:border-white/10 rounded-xl px-3 py-2 text-xs font-bold text-gray-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-cyan-500" />
              <p class="text-[10px] text-gray-400 mt-1 ml-1">超出后自动删除最旧的文件</p>
            </div>
            <div>
              <label class="text-[10px] font-black text-gray-400 uppercase tracking-widest ml-1">单文件体积上限 (MB)</label>
              <input type="number" min="0.1" max="1024" step="0.5" v-model.number="logRetention.maxFileMB"
                     class="mt-1 w-full bg-white dark:bg-black/20 border border-gray-200 dark:border-white/10 rounded-xl px-3 py-2 text-xs font-bold text-gray-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-cyan-500" />
              <p class="text-[10px] text-gray-400 mt-1 ml-1">写满后自动轮转为归档文件</p>
            </div>
            <div>
              <label class="text-[10px] font-black text-gray-400 uppercase tracking-widest ml-1">日志总占用上限 (MB)</label>
              <input type="number" min="0.5" max="10240" step="1" v-model.number="logRetention.maxTotalMB"
                     class="mt-1 w-full bg-white dark:bg-black/20 border border-gray-200 dark:border-white/10 rounded-xl px-3 py-2 text-xs font-bold text-gray-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-cyan-500" />
              <p class="text-[10px] text-gray-400 mt-1 ml-1">超出后按最旧优先回收</p>
            </div>
          </div>

          <div class="flex items-center gap-3">
            <button @click="saveLogRetention" :disabled="isSavingRetention"
                    class="px-4 py-2 bg-gray-800 dark:bg-white text-white dark:text-black rounded-xl text-xs font-black transition active:scale-95 flex items-center gap-2 disabled:opacity-50">
              <ArrowPathIcon class="w-4 h-4" :class="{ 'animate-spin': isSavingRetention }" />
              保存保留策略
            </button>
            <span class="text-[10px] text-gray-400">保存后立即回收超限文件，无需重启</span>
          </div>

          <div v-if="logFiles.length > 0" class="space-y-1.5 pt-1">
            <div v-for="file in logFiles" :key="file.name"
                 class="flex items-center gap-3 px-3 py-2 rounded-xl bg-white/70 dark:bg-black/20 border border-gray-100 dark:border-white/5">
              <span class="text-[11px] font-mono font-bold text-gray-600 dark:text-gray-300 break-all">{{ file.name }}</span>
              <span v-if="file.is_active"
                    class="px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-500 text-[9px] font-black shrink-0">写入中</span>
              <span class="ml-auto text-[10px] font-mono text-gray-400 shrink-0">{{ formatBytes(file.size) }}</span>
              <span class="text-[10px] font-mono text-gray-400 shrink-0 hidden sm:inline">{{ file.modified }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- 14. 调试系统 -->
      <section id="section-debug" class="bg-white/50 dark:bg-gray-900/40 backdrop-blur-md rounded-[2.5rem] p-8 border border-gray-100 dark:border-white/5 shadow-sm">
        <div class="flex flex-wrap items-center justify-between gap-4 mb-6">
          <div class="flex items-center gap-5">
            <div class="p-4 rounded-[1.5rem]"
                 :class="debugStatus.enabled ? 'bg-purple-500/10 text-purple-500' : 'bg-gray-500/10 text-gray-500'">
              <BugAntIcon class="w-7 h-7" />
            </div>
            <div>
              <h3 class="text-xl font-bold text-gray-800 dark:text-white flex items-center gap-3">
                调试系统
                <span class="px-2 py-0.5 rounded-lg text-[10px] font-black"
                      :class="debugStatus.enabled ? 'bg-purple-500/15 text-purple-500' : 'bg-gray-500/15 text-gray-400'">
                  {{ debugStatus.enabled ? '已开启' : '未开启' }}
                </span>
              </h3>
              <p class="text-sm text-gray-400 mt-1">面向开发者与 Vibe Coding 的远程调试组件（需先阅读并确认协议）</p>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <button v-if="!debugStatus.enabled" @click="openDebugAgreement"
                    class="px-4 py-2.5 bg-purple-500 hover:bg-purple-600 text-white rounded-xl text-xs font-black transition shadow-md shadow-purple-500/30 active:scale-95 flex items-center gap-2">
              <ShieldCheckIcon class="w-4 h-4" /> 阅读协议并开启
            </button>
            <template v-else>
              <button @click="handleRotateDebugToken"
                      class="px-3.5 py-2.5 bg-white dark:bg-black/20 border border-gray-200 dark:border-white/10 text-gray-600 dark:text-gray-300 rounded-xl text-xs font-black transition active:scale-95 flex items-center gap-2">
                <ArrowPathIcon class="w-4 h-4" /> 轮换令牌
              </button>
              <button @click="handleDisableDebug" :disabled="isDebugBusy"
                      class="px-4 py-2.5 bg-red-500 hover:bg-red-600 text-white rounded-xl text-xs font-black transition shadow-md shadow-red-500/30 active:scale-95 flex items-center gap-2 disabled:opacity-50">
                <PowerIcon class="w-4 h-4" /> 关闭调试模式
              </button>
            </template>
          </div>
        </div>

        <!-- 未开启时的说明 -->
        <div v-if="!debugStatus.enabled" class="p-6 rounded-[2rem] bg-amber-50/60 dark:bg-amber-500/5 border border-amber-100 dark:border-amber-500/10 space-y-3">
          <div class="flex items-start gap-3">
            <ExclamationTriangleIcon class="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
            <div class="text-xs leading-relaxed text-gray-600 dark:text-gray-300 space-y-2">
              <p><b class="text-amber-600 dark:text-amber-400">开启调试模式前请务必知悉：</b></p>
              <ul class="list-disc ml-4 space-y-1">
                <li>调试模式会在本机开放一组调试接口，可读取运行状态、日志并执行受限指令；</li>
                <li>持有访问令牌的任何程序都可以调用这些接口，存在本机数据暴露与数据损坏风险；</li>
                <li>由此产生的一切后果由使用者本人承担，<b>开发者不承担连带或赔偿责任</b>；</li>
                <li>调试系统<b>不会上传任何数据</b>，审计记录仅保存在你的本机。</li>
              </ul>
            </div>
          </div>
          <button @click="openDebugAgreement"
                  class="w-full py-3 bg-purple-500 hover:bg-purple-600 text-white rounded-2xl font-black text-xs shadow-lg shadow-purple-500/30 transition active:scale-95">
            阅读《调试模式使用协议 / 风险说明书 / 责任划分书》
          </button>
        </div>

        <!-- 已开启时的控制台 -->
        <div v-else class="space-y-4">
          <!-- 访问令牌 -->
          <div class="p-5 rounded-[2rem] bg-gray-50/70 dark:bg-white/5 border border-gray-100 dark:border-white/5 space-y-3">
            <div class="flex items-center gap-2">
              <KeyIcon class="w-4 h-4 text-purple-500" />
              <span class="text-xs font-black text-gray-700 dark:text-gray-200">访问令牌</span>
              <span class="text-[10px] text-gray-400">（所有调试接口都需要请求头 X-Debug-Token）</span>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <code class="flex-1 min-w-[240px] px-3 py-2.5 rounded-xl bg-gray-900 text-emerald-400 text-[11px] font-mono break-all">
                {{ isTokenRevealed ? debugToken : '•'.repeat(Math.min(48, debugToken.length || 48)) }}
              </code>
              <button @click="isTokenRevealed = !isTokenRevealed"
                      class="px-3 py-2.5 rounded-xl bg-white dark:bg-black/20 border border-gray-200 dark:border-white/10 text-gray-600 dark:text-gray-300 text-[11px] font-black transition active:scale-95 flex items-center gap-1.5">
                <component :is="isTokenRevealed ? EyeSlashIcon : EyeIcon" class="w-4 h-4" />
                {{ isTokenRevealed ? '隐藏' : '显示' }}
              </button>
              <button @click="copyDebugValue(debugToken, '访问令牌')"
                      class="px-3 py-2.5 rounded-xl bg-white dark:bg-black/20 border border-gray-200 dark:border-white/10 text-gray-600 dark:text-gray-300 text-[11px] font-black transition active:scale-95 flex items-center gap-1.5">
                <ClipboardDocumentIcon class="w-4 h-4" />
                {{ debugCopyState === '访问令牌' ? '已复制' : '复制' }}
              </button>
            </div>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-3 pt-1">
              <div>
                <div class="text-[10px] font-black text-gray-400 uppercase tracking-widest">开启时间</div>
                <div class="text-[11px] font-bold text-gray-600 dark:text-gray-300 mt-0.5">{{ debugStatus.enabled_at || '-' }}</div>
              </div>
              <div>
                <div class="text-[10px] font-black text-gray-400 uppercase tracking-widest">调试请求数</div>
                <div class="text-[11px] font-bold text-gray-600 dark:text-gray-300 mt-0.5">{{ debugStatus.request_count || 0 }}</div>
              </div>
              <div>
                <div class="text-[10px] font-black text-gray-400 uppercase tracking-widest">表达式执行</div>
                <div class="text-[11px] font-bold mt-0.5"
                     :class="debugStatus.allow_python ? 'text-emerald-500' : 'text-gray-400'">
                  {{ debugStatus.allow_python ? '已允许' : '未允许' }}
                </div>
              </div>
              <div>
                <div class="text-[10px] font-black text-gray-400 uppercase tracking-widest">命令执行</div>
                <div class="text-[11px] font-bold mt-0.5"
                     :class="debugStatus.allow_shell ? 'text-emerald-500' : 'text-gray-400'">
                  {{ debugStatus.allow_shell ? '已允许' : '未允许' }}
                </div>
              </div>
            </div>
          </div>

          <!-- 页签 -->
          <div class="flex gap-2 p-1.5 rounded-2xl bg-gray-100 dark:bg-black/20">
            <button v-for="tab in [
                      { id: 'console', name: '表达式控制台' },
                      { id: 'api', name: 'API 接入说明' },
                      { id: 'audit', name: '审计日志' }
                    ]" :key="tab.id"
                    @click="debugTab = tab.id"
                    class="flex-1 py-2.5 rounded-xl text-xs font-black transition"
                    :class="debugTab === tab.id
                      ? 'bg-white dark:bg-gray-700 shadow-sm text-purple-500'
                      : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'">
              {{ tab.name }}
            </button>
          </div>

          <!-- 表达式控制台 -->
          <div v-if="debugTab === 'console'" class="space-y-3">
            <div class="flex flex-wrap gap-2">
              <button v-for="sample in debugSamples" :key="sample"
                      @click="debugConsoleInput = sample"
                      class="px-2.5 py-1.5 rounded-lg bg-gray-100 dark:bg-white/5 text-[10px] font-mono text-gray-500 hover:text-purple-500 transition">
                {{ sample }}
              </button>
            </div>
            <textarea v-model="debugConsoleInput" rows="3"
                      placeholder="输入受限 Python 表达式（仅允许白名单模块，禁止私有属性访问）"
                      class="w-full bg-gray-900 text-emerald-400 font-mono text-xs rounded-2xl p-4 outline-none focus:ring-2 focus:ring-purple-500"
                      :disabled="!debugStatus.allow_python"></textarea>
            <div class="flex items-center gap-3">
              <button @click="runDebugConsole" :disabled="isDebugConsoleRunning || !debugStatus.allow_python"
                      class="px-4 py-2.5 bg-purple-500 hover:bg-purple-600 text-white rounded-xl text-xs font-black transition active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2">
                <PlayIcon class="w-4 h-4" :class="{ 'animate-pulse': isDebugConsoleRunning }" />
                执行表达式
              </button>
              <span v-if="!debugStatus.allow_python" class="text-[10px] text-amber-500 font-bold">
                未开启「表达式执行」能力，请关闭调试模式后重新开启并勾选该能力
              </span>
            </div>
            <pre v-if="debugConsoleOutput"
                 class="bg-gray-900 rounded-2xl p-4 text-[11px] font-mono text-gray-300 whitespace-pre-wrap break-all max-h-64 overflow-y-auto scrollbar-thin">{{ debugConsoleOutput }}</pre>
          </div>

          <!-- API 接入说明 -->
          <div v-else-if="debugTab === 'api'" class="space-y-3">
            <p class="text-xs leading-relaxed text-gray-500 dark:text-gray-400">
              把下面的命令粘贴给你的 AI 编码助手（或直接在终端执行），即可让它读取运行状态、日志并执行受限调试动作。
              接口默认监听 <code class="px-1 rounded bg-gray-100 dark:bg-white/10 font-mono">{{ debugStatus.endpoint || 'http://127.0.0.1:12180/api/debug' }}</code>。
            </p>
            <div class="relative">
              <pre class="bg-gray-900 rounded-2xl p-4 text-[10px] leading-relaxed font-mono text-gray-300 whitespace-pre-wrap break-all max-h-72 overflow-y-auto scrollbar-thin">{{ curlExample }}</pre>
              <button @click="copyDebugValue(curlExample, 'API 示例')"
                      class="absolute top-3 right-3 px-2.5 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white text-[10px] font-black transition flex items-center gap-1.5">
                <ClipboardDocumentIcon class="w-3.5 h-3.5" />
                {{ debugCopyState === 'API 示例' ? '已复制' : '复制' }}
              </button>
            </div>
          </div>

          <!-- 审计日志 -->
          <div v-else class="space-y-3">
            <div class="flex items-center gap-3">
              <span class="text-xs font-black text-gray-700 dark:text-gray-200">调试操作审计（仅保存在本机）</span>
              <div class="ml-auto flex gap-2">
                <button @click="fetchDebugAudit" :disabled="isDebugAuditLoading"
                        class="px-3 py-2 rounded-xl bg-white dark:bg-black/20 border border-gray-200 dark:border-white/10 text-[11px] font-black text-gray-600 dark:text-gray-300 transition active:scale-95 disabled:opacity-50 flex items-center gap-1.5">
                  <ArrowPathIcon class="w-3.5 h-3.5" :class="{ 'animate-spin': isDebugAuditLoading }" />
                  {{ isDebugAuditLoading ? '读取中...' : '刷新' }}
                </button>
                <button @click="clearDebugAuditLog"
                        class="px-3 py-2 rounded-xl bg-white dark:bg-black/20 border border-red-200 dark:border-red-500/20 text-[11px] font-black text-red-500 transition active:scale-95">清空</button>
              </div>
            </div>

            <!-- 读取失败时明确说明原因（例如令牌校验失败） -->
            <div v-if="debugAuditError"
                 class="p-3.5 rounded-2xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20">
              <p class="text-[11px] font-black text-red-600 dark:text-red-400">审计日志读取失败</p>
              <p class="text-[11px] font-mono text-red-500/80 dark:text-red-400/80 mt-1 break-all">{{ debugAuditError }}</p>
              <p class="text-[10px] text-red-500/70 dark:text-red-400/70 mt-1">
                提示：调试令牌在「轮换令牌」或「关闭调试模式」后会立即失效，需重新开启调试模式获取新令牌。
              </p>
            </div>

            <div v-if="debugAudit.length === 0 && !debugAuditError"
                 class="text-center text-xs text-gray-400 py-8">
              {{ isDebugAuditLoading ? '正在读取审计日志...' : '暂无审计记录' }}
            </div>
            <div v-else-if="debugAudit.length > 0"
                 class="bg-gray-900 rounded-2xl p-3 max-h-72 overflow-y-auto scrollbar-thin space-y-1">
              <div v-for="(item, idx) in debugAudit" :key="idx"
                   class="flex gap-3 px-2 py-1.5 rounded hover:bg-white/5 font-mono text-[10px]">
                <span class="text-gray-500 shrink-0">{{ item.time }}</span>
                <span class="shrink-0 font-black" :class="item.ok ? 'text-emerald-400' : 'text-red-400'">{{ item.action }}</span>
                <span class="text-gray-300 break-all">{{ item.detail }}</span>
              </div>
            </div>
          </div>

          <!-- 撤回协议 -->
          <div class="flex items-center gap-3 pt-2 border-t border-gray-100 dark:border-white/5">
            <span class="text-[10px] text-gray-400">
              协议确认版本 {{ debugStatus.consent?.version }} ·
              {{ debugStatus.consent?.confirmed ? `已于 ${debugStatus.consent?.confirmed_at} 确认` : '尚未确认' }}
            </span>
            <button @click="handleRevokeDebugConsent"
                    class="ml-auto text-[10px] font-black text-gray-400 hover:text-red-500 transition">撤回协议确认</button>
          </div>
        </div>

        <!-- 调试协议弹窗 -->
        <Teleport to="body">
          <transition name="modal-fade">
            <div v-if="showDebugAgreement" class="fixed inset-0 z-[99997] flex items-center justify-center p-6" style="-webkit-app-region: no-drag;">
              <div class="absolute inset-0 bg-black/70 backdrop-blur-sm"></div>
              <div class="relative bg-white dark:bg-gray-900 w-full max-w-3xl rounded-3xl shadow-2xl overflow-hidden border border-purple-200 dark:border-purple-500/20 flex flex-col max-h-[88vh]">
                <div class="px-7 py-5 border-b border-gray-100 dark:border-white/5 bg-purple-50/70 dark:bg-purple-500/5 shrink-0 flex items-center gap-4">
                  <div class="p-3 rounded-2xl bg-purple-500 text-white shadow-lg">
                    <ShieldCheckIcon class="w-6 h-6" />
                  </div>
                  <div>
                    <h3 class="text-lg font-black text-gray-800 dark:text-white">调试模式使用协议 / 风险说明书 / 责任划分书</h3>
                    <p class="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">
                      请完整阅读，并逐项勾选确认后才能开启调试模式
                    </p>
                  </div>
                  <button @click="showDebugAgreement = false"
                          class="ml-auto p-1.5 rounded-xl text-gray-400 hover:text-gray-600 dark:hover:text-white transition">
                    <XMarkSolidIcon class="w-5 h-5" />
                  </button>
                </div>

                <div class="px-7 py-5 overflow-y-auto scrollbar-thin flex-1">
                  <!-- 协议拉取失败：明确提示并提供重试 -->
                  <div v-if="debugAgreementError"
                       class="mb-4 p-4 rounded-2xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20">
                    <p class="text-xs font-black text-red-600 dark:text-red-400">协议内容未能加载</p>
                    <p class="text-[11px] font-mono text-red-500/80 dark:text-red-400/80 mt-1 break-all">{{ debugAgreementError }}</p>
                    <button @click="loadDebugAgreement"
                            class="mt-3 px-3.5 py-2 rounded-xl bg-red-500 hover:bg-red-600 text-white text-[11px] font-black transition active:scale-95 flex items-center gap-2">
                      <ArrowPathIcon class="w-4 h-4" /> 重新拉取协议
                    </button>
                  </div>

                  <pre v-if="debugAgreementText" class="text-[11px] leading-relaxed font-mono text-gray-600 dark:text-gray-300 whitespace-pre-wrap">{{ debugAgreementText }}</pre>
                  <p v-else-if="!debugAgreementError" class="text-xs text-gray-400 text-center py-10">正在拉取协议内容...</p>

                  <div class="mt-6 space-y-2.5">
                    <div v-for="item in debugChecklist" :key="item.id"
                         @click="toggleDebugCheck(item.id)"
                         class="flex items-start gap-3 p-3.5 rounded-2xl cursor-pointer transition-all border"
                         :class="debugChecked.includes(item.id)
                           ? 'bg-purple-500/10 border-purple-500/40'
                           : 'bg-gray-50 dark:bg-white/5 border-transparent hover:bg-gray-100 dark:hover:bg-white/10'">
                      <div class="w-5 h-5 rounded-md border-2 flex items-center justify-center transition-all shrink-0 mt-0.5"
                           :class="debugChecked.includes(item.id)
                             ? 'bg-purple-500 border-purple-500'
                             : 'border-gray-300 dark:border-gray-600'">
                        <CheckIcon v-if="debugChecked.includes(item.id)" class="w-3.5 h-3.5 text-white" />
                      </div>
                      <span class="text-xs leading-relaxed text-gray-600 dark:text-gray-300">{{ item.text }}</span>
                    </div>
                  </div>

                  <div class="mt-6 p-4 rounded-2xl bg-gray-50 dark:bg-white/5 border border-gray-100 dark:border-white/10 space-y-3">
                    <div class="text-xs font-black text-gray-700 dark:text-gray-200">可选能力（默认关闭，按需开启）</div>
                    <label class="flex items-center gap-3 cursor-pointer select-none">
                      <input type="checkbox" v-model="debugAllowPython" class="accent-purple-500 w-4 h-4" />
                      <span class="text-xs text-gray-600 dark:text-gray-300">
                        允许<b>表达式执行</b>（受限 Python 表达式，仅白名单模块）
                      </span>
                    </label>
                    <label class="flex items-center gap-3 cursor-pointer select-none">
                      <input type="checkbox" v-model="debugAllowShell" class="accent-purple-500 w-4 h-4" />
                      <span class="text-xs text-gray-600 dark:text-gray-300">
                        允许<b>命令执行</b>（仅只读诊断命令白名单，最长 20 秒）
                      </span>
                    </label>
                  </div>
                </div>

                <div class="px-7 py-4 border-t border-gray-100 dark:border-white/5 bg-gray-50/70 dark:bg-black/30 shrink-0 flex items-center gap-3">
                  <span class="text-[10px] font-black" :class="debugAllChecked ? 'text-emerald-500' : 'text-amber-500'">
                    {{ debugAllChecked ? '已逐项确认，可以开启' : `还需确认 ${debugChecklist.length - debugChecked.length} 项` }}
                  </span>
                  <div class="ml-auto flex gap-2">
                    <button @click="showDebugAgreement = false"
                            class="px-4 py-2.5 rounded-2xl text-xs font-black text-gray-500 hover:bg-gray-200 dark:hover:bg-white/10 transition">
                      取消
                    </button>
                    <button @click="handleEnableDebug" :disabled="!debugAllChecked || isDebugBusy"
                            class="px-5 py-2.5 rounded-2xl text-xs font-black text-white transition active:scale-95 flex items-center gap-2"
                            :class="debugAllChecked
                              ? 'bg-purple-500 hover:bg-purple-600 shadow-lg shadow-purple-500/30'
                              : 'bg-gray-300 dark:bg-gray-700 cursor-not-allowed'">
                      <BugAntIcon class="w-4 h-4" :class="{ 'animate-pulse': isDebugBusy }" />
                      我已理解全部风险，开启调试模式
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </transition>
        </Teleport>

        <!-- 删除物理日志确认 -->
        <UniversalModal
          :show="purgeLogState.show"
          type="confirm"
          title="删除全部日志文件"
          :extra-data="{
            message: '该操作会立即删除磁盘上的所有日志文件（含当前正在写入的文件），删除后无法恢复。确定继续吗？',
            isDanger: true,
            confirmText: isPurgingLogs ? '正在删除...' : '确认删除',
            cancelText: '取消'
          }"
          @close="purgeLogState.show = false"
          @confirm="(confirmed) => { if (confirmed) executePurgeLogFiles() }"
        >
          <template #confirm-icon>
            <ExclamationTriangleIcon class="w-12 h-12 text-red-500 mx-auto mb-2" />
          </template>
        </UniversalModal>
      </section>


      <!-- 14. 关于软件 -->
      <section id="section-about" class="bg-white/50 dark:bg-gray-900/40 backdrop-blur-md rounded-[2.5rem] p-8 border border-gray-100 dark:border-white/5 shadow-sm mb-12">
        <div class="flex items-center gap-5 mb-8">
          <div class="p-4 bg-emerald-500/10 text-emerald-500 rounded-[1.5rem]"><InformationCircleIcon class="w-7 h-7" /></div>
          <div>
            <h3 class="text-xl font-bold text-gray-800 dark:text-white">关于软件</h3>
            <p class="text-sm text-gray-400 mt-1">软件信息与法律声明</p>
          </div>
        </div>

        <div class="flex flex-col md:flex-row gap-8 items-center md:items-start">
          <div class="w-24 h-24 rounded-[2rem] shadow-xl overflow-hidden shrink-0 bg-white dark:bg-gray-800 flex items-center justify-center">
            <img src="/icon.png" class="w-full h-full object-contain p-3" alt="BiliMusic Icon" />
          </div>
          
          <div class="flex-1 space-y-6 text-center md:text-left">
            <div>
              <h4 class="text-2xl font-black text-gray-800 dark:text-white tracking-tight">BiliMusic</h4>
              <p class="text-xs font-bold text-primary-500 uppercase tracking-[0.2em] mt-1">Version {{ appVersion }}</p>
            </div>

            <p class="text-sm text-gray-500 dark:text-gray-400 leading-relaxed max-w-2xl">
              BiliMusic 是一款基于 Vue 3、Electron 和 Python FastAPI 构建的开源 Bilibili 音乐播放器。
              旨在为用户提供极致的 B 站音频收听体验，支持沉浸式视觉效果与高效的媒体管理。
            </p>

            <div class="grid grid-cols-2 sm:grid-cols-3 gap-4 pt-4">
              <div class="flex flex-col gap-1">
                <span class="text-[10px] font-bold text-gray-400 uppercase tracking-widest">开发者</span>
                <span class="text-sm font-bold text-gray-700 dark:text-gray-200">XK-SZG</span>
              </div>
              <div class="flex flex-col gap-1">
                <span class="text-[10px] font-bold text-gray-400 uppercase tracking-widest">开源协议</span>
                <span class="text-sm font-bold text-gray-700 dark:text-gray-200">MIT License</span>
              </div>
              <div class="flex flex-col gap-1">
                <span class="text-[10px] font-bold text-gray-400 uppercase tracking-widest">技术栈</span>
                <span class="text-sm font-bold text-gray-700 dark:text-gray-200">Vue / FastAPI</span>
              </div>
            </div>

            <!-- 用户协议与隐私政策按钮 -->
            <div class="pt-4">
              <button
                @click="showAgreementModal = true"
                class="inline-flex items-center gap-2 px-6 py-3 bg-primary-500/10 hover:bg-primary-500/20 text-primary-600 dark:text-primary-400 rounded-2xl font-bold text-sm transition-all duration-300 hover:scale-105 active:scale-95 border border-primary-200 dark:border-primary-800/50"
              >
                <LockClosedIcon class="w-4 h-4" />
                查看用户协议与隐私政策
              </button>
            </div>
          </div>
        </div>
      </section>

    </div>

    <!-- 用户协议弹窗 -->
    <AgreementModal
      :show="showAgreementModal"
      @agree="showAgreementModal = false"
      @decline="showAgreementModal = false"
    />
  </div>
</template>

<style scoped>
.scroll-smooth { scroll-behavior: smooth; }
.no-scrollbar::-webkit-scrollbar { display: none; }
input[type=range]::-webkit-slider-thumb { -webkit-appearance: none; height: 20px; width: 20px; border-radius: 50%; background: currentColor; cursor: pointer; border: 3px solid white; box-shadow: 0 0 10px rgba(0,0,0,0.1); transition: transform 0.2s; }
input[type=range]::-webkit-slider-thumb:hover { transform: scale(1.2); }
.dropdown-enter-active, .dropdown-leave-active { transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1); transform-origin: top; }
.dropdown-enter-from, .dropdown-leave-to { opacity: 0; transform: translateY(-10px) scale(0.95); }
.animate-fade-in { animation: fadeIn 0.6s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
</style>
