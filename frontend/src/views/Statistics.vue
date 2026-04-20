<template>
  <div class="h-full overflow-y-auto bg-gray-50 dark:bg-gray-900 p-6">
    <div class="max-w-7xl mx-auto space-y-6">
      <!-- 页面标题 -->
      <div class="flex items-center justify-between">
        <h1 class="text-3xl font-bold text-gray-900 dark:text-white">数据统计</h1>
        <button 
          @click="refreshData" 
          class="px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-colors flex items-center gap-2"
          :disabled="loading"
        >
          <svg v-if="loading" class="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <span>{{ loading ? '加载中...' : '刷新数据' }}</span>
        </button>
      </div>

      <!-- 用户信息卡片 -->
      <div v-if="store.user" class="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-6">
        <h2 class="text-xl font-semibold text-gray-900 dark:text-white mb-4">用户信息</h2>
        <div class="flex items-center justify-between gap-4">
          <div class="flex items-center gap-4">
            <img
              :src="store.user.face"
              class="w-16 h-16 rounded-full"
              draggable="false"
            />
            <div>
              <div class="flex items-center gap-2">
                <span class="text-lg font-medium text-gray-900 dark:text-white">{{ store.user.uname }}</span>
                <img
                  v-if="store.user.vip_label"
                  :src="store.user.vip_label"
                  class="h-5"
                  draggable="false"
                />
              </div>
              <p class="text-sm text-gray-500 dark:text-gray-400">UID: {{ store.user.mid }}</p>
            </div>
          </div>
          <!-- 优化标语布局 - 靠右对齐，放大字体，增强视觉效果 -->
          <div class="text-right">
            <p class="text-1xl font-bold italic">{{ intelligentComment }}</p>
          </div>
        </div>
      </div>

      <!-- 统计概览卡片组 -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <!-- 视频总数 -->
        <div class="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-6">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm text-gray-500 dark:text-gray-400">视频总数</p>
              <p class="text-3xl font-bold text-gray-900 dark:text-white mt-2">{{ overview.total_videos }}</p>
            </div>
            <div class="w-12 h-12 bg-blue-100 dark:bg-blue-900 rounded-lg flex items-center justify-center">
              <svg class="w-6 h-6 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4M4 20h16a1 1 0 001-1V5a1 1 0 00-1-1H4a1 1 0 00-1 1v14a1 1 0 001 1z" />
              </svg>
            </div>
          </div>
          <div class="mt-4 flex gap-4 text-sm">
            <span class="text-green-600 dark:text-green-400">已缓存: {{ overview.cached_videos }}</span>
            <span class="text-orange-600 dark:text-orange-400">未缓存: {{ overview.uncached_videos }}</span>
          </div>
        </div>

        <!-- 播放次数 -->
        <div class="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-6">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm text-gray-500 dark:text-gray-400">总播放次数</p>
              <p class="text-3xl font-bold text-gray-900 dark:text-white mt-2">{{ overview.total_plays }}</p>
            </div>
            <div class="w-12 h-12 bg-purple-100 dark:bg-purple-900 rounded-lg flex items-center justify-center">
              <svg class="w-6 h-6 text-purple-600 dark:text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
          </div>
          <div class="mt-4 flex gap-4 text-sm">
            <span class="text-green-600 dark:text-green-400">已缓存: {{ overview.cached_plays || 0 }}</span>
            <span class="text-orange-600 dark:text-orange-400">未缓存: {{ overview.uncached_plays || 0 }}</span>
          </div>
        </div>

        <!-- 使用时长 -->
        <div class="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-6">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm text-gray-500 dark:text-gray-400">软件使用时长</p>
              <p class="text-3xl font-bold text-gray-900 dark:text-white mt-2">{{ formatDuration(overview.total_app_usage) }}</p>
            </div>
            <div class="w-12 h-12 bg-green-100 dark:bg-green-900 rounded-lg flex items-center justify-center">
              <svg class="w-6 h-6 text-green-600 dark:text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
          </div>
          <div class="mt-4 flex gap-4 text-sm">
            <span class="text-green-600 dark:text-green-400">已缓存: {{ formatDuration(overview.cached_play_time || 0) }}</span>
            <span class="text-orange-600 dark:text-orange-400">未缓存: {{ formatDuration(overview.uncached_play_time || 0) }}</span>
          </div>
        </div>

        <!-- 网络流量 -->
        <div class="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-6">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm text-gray-500 dark:text-gray-400">网络流量消耗</p>
              <p class="text-3xl font-bold text-gray-900 dark:text-white mt-2">{{ formatBytes(overview.total_traffic) }}</p>
            </div>
            <div class="w-12 h-12 bg-red-100 dark:bg-red-900 rounded-lg flex items-center justify-center">
              <svg class="w-6 h-6 text-red-600 dark:text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
            </div>
          </div>
          <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">未缓存流量: {{ formatBytes(overview.total_uncached_traffic) }}</p>
        </div>
      </div>

      <!-- 播放作息曲线图 -->
      <div class="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-6">
        <div class="flex justify-between items-center mb-2">
          <h2 class="text-xl font-semibold text-gray-900 dark:text-white">播放作息曲线</h2>
          <!-- 任务 3.2：智能分析结果 -->
          <div v-if="scheduleAnalysis" class="flex items-center gap-2">
            <span class="text-2xl">{{ scheduleAnalysis.icon }}</span>
            <p class="text-sm text-gray-600 dark:text-gray-300 font-medium">{{ scheduleAnalysis.message }}</p>
          </div>
        </div>
        <div class="h-64 mt-4">
          <div ref="chartCanvas" class="w-full h-full"></div>
        </div>
      </div>

      <!-- 排行榜 -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <!-- 播放次数排行 -->
        <div class="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-6">
          <h2 class="text-xl font-semibold text-gray-900 dark:text-white mb-4">播放次数排行</h2>
          <div class="space-y-3">
            <div
              v-for="(video, index) in rankings.play_count"
              :key="video.bvid"
              class="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            >
              <span class="text-lg font-bold w-6" :class="getRankColor(index)">{{ index + 1 }}</span>
              <img
                :src="getCoverUrl(video.pic, '160w_100h')"
                @error="handleImageError($event, video.pic)"
                class="w-12 h-12 rounded object-cover bg-gray-200 dark:bg-gray-700"
                draggable="false"
              />
              <div class="flex-1 min-w-0">
                <p class="text-sm font-medium text-gray-900 dark:text-white truncate">{{ video.title }}</p>
                <p class="text-xs text-gray-500 dark:text-gray-400">播放 {{ video.play_count }} 次</p>
              </div>
            </div>
            <p v-if="rankings.play_count.length === 0" class="text-center text-gray-500 dark:text-gray-400 py-8">暂无数据</p>
          </div>
        </div>

        <!-- 播放时长排行 -->
        <div class="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-6">
          <h2 class="text-xl font-semibold text-gray-900 dark:text-white mb-4">播放时长排行</h2>
          <div class="space-y-3">
            <div
              v-for="(video, index) in rankings.play_duration"
              :key="video.bvid"
              class="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            >
              <span class="text-lg font-bold w-6" :class="getRankColor(index)">{{ index + 1 }}</span>
              <img
                :src="getCoverUrl(video.pic, '160w_100h')"
                @error="handleImageError($event, video.pic)"
                class="w-12 h-12 rounded object-cover bg-gray-200 dark:bg-gray-700"
                draggable="false"
              />
              <div class="flex-1 min-w-0">
                <p class="text-sm font-medium text-gray-900 dark:text-white truncate">{{ video.title }}</p>
                <p class="text-xs text-gray-500 dark:text-gray-400">{{ formatDuration(video.total_duration) }}</p>
              </div>
            </div>
            <p v-if="rankings.play_duration.length === 0" class="text-center text-gray-500 dark:text-gray-400 py-8">暂无数据</p>
          </div>
        </div>

        <!-- 评分排行 -->
        <div class="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-6">
          <h2 class="text-xl font-semibold text-gray-900 dark:text-white mb-4">评分排行</h2>
          <div class="space-y-3">
            <div
              v-for="(video, index) in rankings.score"
              :key="video.bvid"
              class="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            >
              <span class="text-lg font-bold w-6" :class="getRankColor(index)">{{ index + 1 }}</span>
              <img
                :src="getCoverUrl(video.pic, '160w_100h')"
                @error="handleImageError($event, video.pic)"
                class="w-12 h-12 rounded object-cover bg-gray-200 dark:bg-gray-700"
                draggable="false"
              />
              <div class="flex-1 min-w-0">
                <p class="text-sm font-medium text-gray-900 dark:text-white truncate">{{ video.title }}</p>
                <p class="text-xs text-gray-500 dark:text-gray-400">评分 {{ video.score.toFixed(1) }}</p>
              </div>
            </div>
            <p v-if="rankings.score.length === 0" class="text-center text-gray-500 dark:text-gray-400 py-8">暂无数据</p>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed, shallowRef } from 'vue'
import { usePlayerStore } from '../stores/modules/player'
import statsApi from '../api/stats'
import * as echarts from 'echarts'

const store = usePlayerStore()
const loading = ref(false)
const chartCanvas = ref(null)
const chartInstance = shallowRef(null)

const overview = ref({
  total_videos: 0,
  cached_videos: 0,
  uncached_videos: 0,
  total_plays: 0,
  cached_plays: 0,
  uncached_plays: 0,
  total_app_usage: 0,
  total_video_play_time: 0,
  cached_play_time: 0,
  uncached_play_time: 0,
  total_traffic: 0,
  total_uncached_traffic: 0
})

// 任务 3.2：智能分析数据
const scheduleAnalysis = ref(null)

let rawPlayData = []
let currentBucketSize = 5 * 60 * 1000

function aggregateData(rawData, bucketSizeMs) {
  if (bucketSizeMs <= 5 * 60 * 1000) return rawData;
  const map = new Map();
  for (let i = 0; i < rawData.length; i++) {
    const ts = rawData[i][0];
    const val = rawData[i][1];
    const bucket = ts - (ts % bucketSizeMs);
    map.set(bucket, (map.get(bucket) || 0) + val);
  }
  return Array.from(map.entries()).sort((a, b) => a[0] - b[0]);
}

async function loadPlaySchedule() {
  try {
    const scheduleRes = await statsApi.getPlaySchedule()
    if (scheduleRes.code === 0) {
      rawPlayData = scheduleRes.data
      renderChart()
    }
    
    // 任务 3.2：加载智能分析
    const analysisRes = await statsApi.getPlayScheduleAnalysis()
    console.log('[Statistics] 智能分析接口返回:', analysisRes)
    if (analysisRes.code === 0) {
      scheduleAnalysis.value = analysisRes.data
      console.log('[Statistics] 智能分析数据已设置:', scheduleAnalysis.value)
    } else {
      console.error('[Statistics] 智能分析接口返回错误:', analysisRes)
    }
  } catch (error) {
    console.error('加载作息曲线失败:', error)
  }
}

const rankings = ref({
  play_count: [],
  play_duration: [],
  score: []
})

// 格式化时长（秒 -> 小时/分钟）
function formatDuration(seconds) {
  if (!seconds) return '0分钟'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (hours > 0) {
    return `${hours}小时${minutes}分钟`
  }
  return `${minutes}分钟`
}

// 格式化字节数
function formatBytes(bytes) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
}

// 获取排名颜色
function getRankColor(index) {
  if (index === 0) return 'text-yellow-500'
  if (index === 1) return 'text-gray-400'
  if (index === 2) return 'text-orange-600'
  return 'text-gray-500 dark:text-gray-400'
}

// 图片重试计数和下载状态
const imageRetryCount = ref({})
const imageDownloading = ref({})
const DEFAULT_COVER = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="160" height="100" viewBox="0 0 160 100"%3E%3Crect fill="%23e5e7eb" width="160" height="100"/%3E%3Ctext x="50%25" y="50%25" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="14" fill="%239ca3af"%3E封面加载失败%3C/text%3E%3C/svg%3E'

function getCoverUrl(pic, size = '160w_100h') {
  if (!pic) return DEFAULT_COVER
  return store.formatImg(pic, size)
}

async function downloadCover(originalPic) {
  try {
    // 调用后端代理接口下载/缓存封面
    // formatImg内部其实就是调用的 /api/proxy/image 接口（如果是外网URL的话）
    // 为了强制后端重新去下，我们在URL后面加个时间戳来防一下浏览器本地缓存，
    // 但是对于后端来说，依然会去拿对应的图片，如果在缓存服务里没有，后端就会去真的下载
    const proxyUrl = store.formatImg(originalPic, '640w_360h')
    const noCacheUrl = proxyUrl.includes('?') ? `${proxyUrl}&_t=${Date.now()}` : `${proxyUrl}?_t=${Date.now()}`
    
    const response = await fetch(noCacheUrl, { method: 'GET' })
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    return true
  } catch (error) {
    console.error('[Statistics] 封面下载失败:', error)
    return false
  }
}

async function handleImageError(event, originalPic) {
  const img = event.target
  const key = originalPic || img.src
  
  if (imageDownloading.value[key]) return
  
  if (!imageRetryCount.value[key]) {
    imageRetryCount.value[key] = 0
  }
  
  if (imageRetryCount.value[key] < 3) {
    imageRetryCount.value[key]++
    imageDownloading.value[key] = true
    
    console.log(`[Statistics] 封面加载失败，第 ${imageRetryCount.value[key]} 次尝试让后端下载:`, key)
    
    const success = await downloadCover(originalPic)
    imageDownloading.value[key] = false
    
    if (success) {
      // 后端缓存成功，前端重新渲染
      setTimeout(() => {
        img.src = getCoverUrl(originalPic, '160w_100h') + '&_retry=' + Date.now()
      }, 500)
    } else {
      if (imageRetryCount.value[key] >= 3) {
        console.log('[Statistics] 封面下载重试3次均失败，使用默认封面:', key)
        img.src = DEFAULT_COVER
      } else {
         // 没成功，但还没到3次，让它再次触发 error 事件
         setTimeout(() => {
           img.src = getCoverUrl(originalPic, '160w_100h') + '&_retry=' + Date.now()
         }, 1000)
      }
    }
  } else {
    console.log('[Statistics] 封面下载失败，使用默认封面:', key)
    img.src = DEFAULT_COVER
  }
}

// 智能评价
const intelligentComment = computed(() => {
  const totalHours = overview.value.total_app_usage / 3600
  const avgPlayTime = overview.value.total_plays > 0 
    ? overview.value.total_video_play_time / overview.value.total_plays 
    : 0

  if (totalHours < 1) {
      return 'BiliMusic欢迎你！期待与你共同开启这场奇妙的音乐之旅~'
    } else if (totalHours < 10) {
      return '旋律悄然潜入心扉，愿BiliMusic为你带来更多不期而遇的小美好！'
    } else if (totalHours < 20) {
      return '每一个跳动的音符，都是我们在你耳边的温柔轻语。请沉醉在音乐的世界里吧~'
    } else if (totalHours < 30) {
      return '一首首藏着故事的歌，是我们彼此间最懂的默契。BiliMusic愿做你最贴心的知音！'
    } else if (totalHours < 40) {
      return '不论开心还是失落，别忘了还有这些温暖的歌声拥抱着你。BiliMusic与你同在！'
    } else if (totalHours < 50) {
      return '耳机里流淌的不仅是歌声，更是我们紧紧相连的心。感谢你让BiliMusic住在你的世界里~'
    } else if (totalHours < 60) {
      return '你的每一次聆听，都赋予了旋律最特别的意义。愿这些动人的歌声能化作你最坚实的依靠！'
    } else if (totalHours < 70) {
      return '音符交织成了一张温暖的网，把我们紧紧系在一起。BiliMusic彻底沦陷在你的好品味里啦~'
    } else if (totalHours < 80) {
      return '我们在无数次旋律的起伏中共鸣，这些闪闪发亮的音乐片段，是属于我们最珍贵的宝藏！'
    } else if (totalHours < 90) {
      return '懂你的欢喜，也懂你的叹息。BiliMusic愿化作漫天星光，照亮你内心最柔软的角落~'
    } else if (totalHours < 100) {
      return '音乐如春风化雨般融入了你的生命。只要戴上耳机，整个宇宙都会为你唱歌！'
    } else {
      return '灵魂伴侣，形影不离！感谢你的满分偏爱，BiliMusic誓做你最忠诚的播放器！'
    }
})

// 加载数据
async function loadData() {
  loading.value = true
  try {
    // 加载概览数据
    const overviewRes = await statsApi.getOverview()
    if (overviewRes.code === 0) {
      overview.value = overviewRes.data
    }

    // 加载播放作息曲线
    await loadPlaySchedule()

    // 加载排行榜
    const rankingsRes = await statsApi.getRankings()
    if (rankingsRes.code === 0) {
      rankings.value = rankingsRes.data
    }
  } catch (error) {
    console.error('加载统计数据失败:', error)
    store.showToast('加载统计数据失败', 'error')
  } finally {
    loading.value = false
  }
}

// 渲染图表
function renderChart() {
  if (!chartCanvas.value) return

  if (!chartInstance.value) {
    chartInstance.value = echarts.init(chartCanvas.value)
    
    chartInstance.value.on('dataZoom', () => {
      updateAggregation()
      updateTimeLabel() // 任务 2.2：更新时间标签
    })
    
    window.addEventListener('resize', handleResize)
  }

  const now = Date.now()
  // 默认显示最近24小时
  const start = now - 24 * 3600 * 1000
  
  currentBucketSize = 5 * 60 * 1000
  const initialData = aggregateData(rawPlayData, currentBucketSize)

  const option = {
    tooltip: {
      trigger: 'axis',
      formatter: function (params) {
        if (!params || !params.length || !params[0] || !params[0].value) return ''
        
        // 兼容不同的数据格式
        const value = params[0].value
        const timestamp = Array.isArray(value) ? value[0] : value
        const duration = Array.isArray(value) ? value[1] : 0
        
        if (!timestamp) return ''
        
        const date = new Date(timestamp)
        const mins = Math.round(duration / 60)
        let formatStr = date.toLocaleString()
        
        // 根据不同步长显示不同精度的 tooltip
        if (currentBucketSize >= 24 * 3600 * 1000) {
          formatStr = `${date.getFullYear()}-${date.getMonth()+1}-${date.getDate()}`
        } else if (currentBucketSize >= 3600 * 1000) {
          formatStr = `${date.getMonth()+1}-${date.getDate()} ${date.getHours()}:00`
        }
        
        return `${formatStr}<br/>播放时长: ${mins} 分钟`
      }
    },
    grid: { left: 40, right: 20, top: 20, bottom: 60 }, // 增加底部空间以容纳时间标签
    dataZoom: [
      {
        type: 'slider',
        show: true,
        xAxisIndex: [0],
        startValue: start,
        endValue: now,
        minValueSpan: 3600 * 1000, // 严格限制最小区间为1小时(毫秒)
        filterMode: 'none', // 任务 2.1：不过滤数据，只调整视图，避免边界裁剪
        showDetail: false, // 任务 2.2：关闭默认标签显示
        bottom: 30, // 为自定义时间标签预留空间
        height: 20
      },
      {
        type: 'inside',
        xAxisIndex: [0],
        zoomOnMouseWheel: true,
        moveOnMouseMove: true,
        minValueSpan: 3600 * 1000, // 严格限制最小区间为1小时(毫秒)
        filterMode: 'none' // 任务 2.1：不过滤数据，只调整视图
      }
    ],
    graphic: [
      {
        type: 'text',
        left: 'center',
        bottom: 5,
        style: {
          text: '', // 初始为空，将在 dataZoom 事件中动态更新
          fill: '#9ca3af',
          fontSize: 12
        },
        z: 100
      }
    ],
    xAxis: {
      type: 'time',
      boundaryGap: false,
      axisLabel: { color: '#9ca3af' },
      splitLine: { show: false }
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        color: '#9ca3af',
        formatter: (val) => Math.round(val / 60) + '分'
      },
      splitLine: { lineStyle: { color: 'rgba(156, 163, 175, 0.2)' } }
    },
    series: [
      {
        name: '播放时长',
        type: 'line',
        smooth: true,
        showSymbol: false,
        itemStyle: { color: 'rgb(59, 130, 246)' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(59, 130, 246, 0.5)' },
            { offset: 1, color: 'rgba(59, 130, 246, 0.05)' }
          ])
        },
        data: initialData
      }
    ]
  }

  chartInstance.value.setOption(option, true)
  updateAggregation()
  updateTimeLabel() // 任务 2.2：初始化时间标签
}

// 任务 2.2：更新时间标签显示
function updateTimeLabel() {
  if (!chartInstance.value) return
  
  const option = chartInstance.value.getOption()
  if (!option || !option.dataZoom || !option.dataZoom[0]) return
  
  const start = option.dataZoom[0].startValue || option.xAxis[0].min
  const end = option.dataZoom[0].endValue || option.xAxis[0].max
  
  // 格式化时间标签
  const startDate = new Date(start)
  const endDate = new Date(end)
  const rangeMs = end - start
  
  let timeLabel = ''
  
  // 根据时间跨度选择合适的格式（最小范围1小时）
  if (rangeMs > 30 * 24 * 3600 * 1000) {
    // 超过30天：显示年月日
    timeLabel = `${startDate.getFullYear()}-${(startDate.getMonth()+1).toString().padStart(2,'0')}-${startDate.getDate().toString().padStart(2,'0')} ~ ${endDate.getFullYear()}-${(endDate.getMonth()+1).toString().padStart(2,'0')}-${endDate.getDate().toString().padStart(2,'0')}`
  } else if (rangeMs > 24 * 3600 * 1000) {
    // 1-30天：显示月日
    timeLabel = `${(startDate.getMonth()+1)}月${startDate.getDate()}日 ~ ${(endDate.getMonth()+1)}月${endDate.getDate()}日`
  } else if (rangeMs >= 3600 * 1000) {
    // 1小时-1天：显示月日时分
    timeLabel = `${(startDate.getMonth()+1)}月${startDate.getDate()}日 ${startDate.getHours().toString().padStart(2,'0')}:${startDate.getMinutes().toString().padStart(2,'0')} ~ ${(endDate.getMonth()+1)}月${endDate.getDate()}日 ${endDate.getHours().toString().padStart(2,'0')}:${endDate.getMinutes().toString().padStart(2,'0')}`
  } else {
    // 小于1小时：显示"最小范围1小时"提示
    timeLabel = `时间范围: ${Math.round(rangeMs / 60000)} 分钟 (最小范围1小时)`
  }
  
  // 更新 graphic 组件的文本
  chartInstance.value.setOption({
    graphic: [{
      style: {
        text: timeLabel
      }
    }]
  })
}

let updateTimer = null
function updateAggregation() {
  if (!chartInstance.value) return
  if (updateTimer) clearTimeout(updateTimer)
  
  // 防抖，避免缩放时卡顿
  updateTimer = setTimeout(() => {
    const option = chartInstance.value.getOption()
    if (!option || !option.dataZoom || !option.dataZoom[0]) return
    
    const start = option.dataZoom[0].startValue || option.xAxis[0].min
    const end = option.dataZoom[0].endValue || option.xAxis[0].max
    const rangeMs = end - start
    
    let newBucketSize = 5 * 60 * 1000 // 默认 < 3 天视口: 聚合为 5分钟
    
    // 如果视口跨度很大（越宏观），我们就应该把底层柱子切得越粗，否则 ECharts 会卡死
    if (rangeMs > 60 * 24 * 3600 * 1000) {
      newBucketSize = 24 * 3600 * 1000 // > 60 天: 每天 1 根柱子
    } else if (rangeMs > 14 * 24 * 3600 * 1000) {
      newBucketSize = 12 * 3600 * 1000 // > 14 天: 聚合为半天 1 根柱子
    } else if (rangeMs > 3 * 24 * 3600 * 1000) {
      newBucketSize = 3600 * 1000      // > 3 天: 聚合为 1小时 1 根柱子
    }
    // <= 3 天: 保持最细粒度的 5分钟 1 根柱子，提供极高的查看精度
    
    if (newBucketSize !== currentBucketSize) {
      currentBucketSize = newBucketSize
      chartInstance.value.setOption({
        series: [{
          data: aggregateData(rawPlayData, currentBucketSize)
        }]
      })
    }
  }, 100)
}

function handleResize() {
  if (chartInstance.value) chartInstance.value.resize()
}

// 刷新数据
function refreshData() {
  loadData()
}

let refreshInterval = null

onMounted(() => {
  loadData()
  // 每30秒自动刷新一次数据
  refreshInterval = setInterval(() => {
    loadData()
  }, 30000)
})

onUnmounted(() => {
  if (chartInstance.value) {
    chartInstance.value.dispose()
  }
  window.removeEventListener('resize', handleResize)
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})
</script>
