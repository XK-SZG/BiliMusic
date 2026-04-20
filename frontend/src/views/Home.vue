<!-- frontend/src/views/Home.vue -->
<script setup>
import { ref, onMounted, onUnmounted } from 'vue' // 引入生命周期钩子
import authApi from '../api/auth'
import { usePlayerStore } from '../stores/modules/player'
import { ExclamationTriangleIcon } from '@heroicons/vue/24/solid'

const store = usePlayerStore()
const qrImg = ref('')
const qrKey = ref('')
const msg = ref('请点击获取二维码')

// --- 二维码缩放设置 ---
const qrSize = ref(128) // 默认 128px

function changeSize(delta) {
  const newSize = qrSize.value + delta
  // 限制最小 64px，最大 512px
  if (newSize >= 64 && newSize <= 512) {
    qrSize.value = newSize
  }
}

// --- 随机欢迎语逻辑 ---
const welcomeList = [
  '哔哩哔哩 (゜-゜)つロ 干杯~',
  '歌单掺了金坷垃，能吸收三百首神中曲！',
  '歌单掺了金坷垃，一曲能抵两曲听！',
  'B友这什么啊？好好听哦',
  '歌单中，突然窜出来首歌\n哇！神曲！',
  '蓝蓝路！',
  '我听歌发自真心！',
  '你指尖跃动的歌单，是我此生不变的信仰',
  'Only My Music',
  '集齐十三首神曲，完成人生之愿景',
  '歌单？哈给马森！',
  '磨刀不误砍柴工，听完音乐再开工',
  '曼波曼波，该听哈基歌啦曼波~',
  '呵呵…啊哈哈哈！歌单来咯！',
  '我晒干了歌单，悔得很冲动~',
  '消除恐惧的最好办法就是听歌单，加油，奥利给！',
  '歌你太美~',
  '你这歌保神吗？不神我听了它！',
  '萨日朗！火红的萨日朗~',
  '打开音乐播放键，于是转身向床缝走去',
  '人生的意义是什么？去歌单淘几首好曲',
  '唱这么好听，你就是歌姬吧！',
  '艹，走，忽略！歌单等你敖',
  '时间停止吧！歌是多么好听',
  '纵使疾风起，听歌不言弃',
  '身在异乡为异客，每逢此时倍思歌',
  '饭后走一走，活到九十九\n饭后听一曲，烦恼全撵走',
  '笑一笑，十年少\n听一听，好心情',
  '书中自有黄金屋，曲中自有颜如玉',
  '一年之计在于春，一日之计在于晨，一时之计在于BGM',
  '冰冻三尺非一日之寒，歌单千首非一日加完',
  '路遥知马力，日久见人心。\n此曲怎么样？听了就知道！',
  '吃一堑，长一智\n听一首，长一姿',
  '三个臭皮匠，顶个诸葛亮。\n耳机双声道，顶个Live现场！',
  '工欲善其事，必先备好曲',
  '百闻不如一见，百见不如听首好曲',
  '一日不见，如隔三秋\n一曲不听，如隔三周',
  '近水楼台先得月，向阳花木易为春\n戴上耳机听首歌，心情立马就升温',
  '有心栽花花不开，无心插柳柳成荫\n随意点开一首歌，也许就是你的菜',
  '少壮不努力，老大徒伤悲\n现在不听歌，以后没得追',
  '读书破万卷，下笔如有神\n听歌千百首，开口就是神',
  '海内存知己，天涯若比邻\n只要音乐起，处处是知音',
  '春眠不觉晓，处处闻啼鸟\n夜来风雨声，不如听歌好',
  '床前明月光，疑是地上霜\n举头望明月，低头听歌忙',
  '锄禾日当午，汗滴禾下土\n谁知盘中餐，听歌补一补',
  '好雨知时节，当听乃发生\n戴上耳机听，心情润无声',
  '神曲生歌单，每日发几首\n愿君多收藏，此曲最解忧',
  '手机电量尽，耳机还放流\n欲听更多曲，再往下划楼',
  '代表歌单消灭你！',
  '教练，我想听歌单',
  '为了歌单！',
  '大吉大利，今晚听歌',
  '早上起来第一句，先给歌单打个气',
  '拜拜坏心情，烦恼全忘记',
  '好运来祝你好运来，好歌来祝你心情嗨~',
  '今天是个听歌日，天天都是听歌日',
  '听歌一时爽，一直听歌一直爽',
  '歌单千万条，好听第一条\n收藏不规范，日后两行泪',
  '耳机一戴，谁也不爱\n音乐响起，世界是我的',
  '没有什么是一首歌解决不了的\n如果有，那就两首',
  '歌单在手，天下我有',
]

const currentWelcome = ref('')
let playlist = [] // 当前轮次的待播放池
let welcomeTimer = null

// 大会员小图标 Base64
const ICON_ANNUAL_VIP = "data:image/png;base64,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"

// Fisher-Yates 洗牌算法：将数组顺序打乱
function shuffle(array) {
  const newArr = [...array]
  for (let i = newArr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [newArr[i], newArr[j]] = [newArr[j], newArr[i]]
  }
  return newArr
}

function updateWelcome() {
  // 如果播放池空了，重新洗牌
  if (playlist.length === 0) {
    playlist = shuffle(welcomeList)
    
    // 特殊处理：防止上一轮最后一句和新一轮第一句正好相同
    if (playlist[playlist.length - 1] === currentWelcome.value && playlist.length > 1) {
      playlist.unshift(playlist.pop()) // 把最后一句挪到最前面
    }
  }
  
  // 从池子里弹出一个
  currentWelcome.value = playlist.pop()
}

onMounted(() => {
  updateWelcome() // 初始化显示第一句
  welcomeTimer = setInterval(updateWelcome, 10000) // 每10秒切换
})

onUnmounted(() => {
  if (welcomeTimer) clearInterval(welcomeTimer)
})
// -------------------------

const pollTimer = ref(null)

onUnmounted(() => {
  if (welcomeTimer) clearInterval(welcomeTimer)
  if (pollTimer.value) clearInterval(pollTimer.value)
})

async function getQr() {
  try {
    const res = await authApi.getQR()
    qrImg.value = res.qr_img
    qrKey.value = res.qr_key
    msg.value = '请使用 Bilibili App 扫码'
    
    if (pollTimer.value) clearInterval(pollTimer.value)
    
    pollTimer.value = setInterval(async () => {
      try {
        const check = await authApi.checkLogin(qrKey.value)
        if (check.code === 0) {
          clearInterval(pollTimer.value)
          pollTimer.value = null
          store.checkLogin()
          msg.value = '登录成功！'
        } else if (check.code === 86038) { // 二维码失效
          clearInterval(pollTimer.value)
          pollTimer.value = null
          msg.value = '二维码已失效，请重新获取'
        }
      } catch (e) {
        clearInterval(pollTimer.value)
        pollTimer.value = null
      }
    }, 1500)
  } catch (err) {
    console.error(err)
  }
}
</script>

<template>
  <div class="h-full flex items-center justify-center p-4 lg:p-10">
    <div class="w-full max-w-2xl p-10 rounded-2xl shadow-xl text-center transition-all duration-300
                bg-white/50 dark:bg-gray-800/40 backdrop-blur-xl border border-white/20 dark:border-white/5
                text-gray-800 dark:text-white">
      
      <!-- 标题 -->
      <div class="h-20 mb-6 flex items-center justify-center overflow-hidden">
        <h2 class="text-2xl font-bold w-full">
          <span v-if="!store.user">海内存知己，请君先登录</span>
          
          <Transition name="fade-slide" mode="out-in" v-else>
            <!-- whitespace-pre-wrap 识别 \n 换行 -->
            <span :key="currentWelcome" 
                  class="block whitespace-pre-wrap leading-tight px-4">
              {{ currentWelcome }}
            </span>
          </Transition>
        </h2>
      </div>

      <!-- 离线提示 -->
      <div v-if="store.isOffline" class="mx-auto mb-6 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-xl p-4 flex flex-col sm:flex-row items-center justify-center gap-3 text-red-500 shadow-sm animate-pulse">
        <ExclamationTriangleIcon class="w-8 h-8 shrink-0" />
        <div class="text-left">
          <p class="text-sm font-black">无法连接到核心服务</p>
          <p class="text-xs font-bold opacity-80 mt-0.5">网络异常或本地服务端未启动，部分功能受限，正在持续重连...</p>
        </div>
      </div>
      
      <div v-else-if="store.isBiliOffline" class="mx-auto mb-6 bg-orange-50 dark:bg-orange-500/10 border border-orange-200 dark:border-orange-500/20 rounded-xl p-4 flex flex-col sm:flex-row items-center justify-center gap-3 text-orange-500 shadow-sm">
        <ExclamationTriangleIcon class="w-8 h-8 shrink-0" />
        <div class="text-left">
          <p class="text-sm font-black">账号处于离线模式</p>
          <p class="text-xs font-bold opacity-80 mt-0.5">无法连接到 Bilibili，在线播放与同步受限，本地库可正常使用。</p>
        </div>
      </div>
      
      <div v-if="store.user" class="space-y-6">
        <div class="flex justify-center relative">
          <div class="relative group/avatar p-4"> 
            <div class="absolute inset-0 bg-primary-500 rounded-full blur-3xl opacity-0 group-hover/avatar:opacity-20 transition-opacity duration-700"></div>
            <a :href="`https://space.bilibili.com/${store.user.mid}`" target="_blank" class="block relative z-10">
              <img v-if="store.user.face" :src="store.user.face" @error="(e) => e.target.style.display='none'" draggable="false" class="w-28 h-28 rounded-full border-4 border-white dark:border-gray-700 shadow-2xl object-cover transition-transform duration-500 group-hover/avatar:scale-105" />
              <!-- 直接在前端使用内置图标 -->
              <img v-if="store.user.vip_status === 1" :src="ICON_ANNUAL_VIP" @error="(e) => e.target.style.display='none'" draggable="false"
                  class="absolute bottom-0 right-0 w-9 h-9 z-20 drop-shadow-2xl animate-bounce-slow object-contain" />
            </a>
          </div>
        </div>
        <div>
          <p class="text-xl font-black tracking-tight">
            欢迎回来, 
            <span class="text-primary-600 dark:text-primary-500">
              {{ store.user.uname }}
            </span>
          </p>
          <p class="text-xs font-bold text-gray-400 mt-1 uppercase tracking-widest">UID: {{ store.user.mid }}</p>
        </div>
      </div>

      <div v-else class="space-y-6">
        <button @click="getQr" 
                :disabled="store.isOffline || store.isBiliOffline"
                class="px-6 py-2 rounded-full transition text-white"
                :class="(store.isOffline || store.isBiliOffline) ? 'bg-gray-400 cursor-not-allowed opacity-50' : 'bg-primary-500 hover:bg-primary-600'">
          {{ (store.isOffline || store.isBiliOffline) ? '离线状态无法获取' : '获取登录二维码' }}
        </button>
        <div v-if="qrImg" class="flex flex-col items-center animate-fade-in">
          <!-- 缩放控制按钮 -->
          <div class="flex gap-4">
            <button @click="changeSize(-64)" 
                    class="w-8 h-8 rounded-full bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 flex items-center justify-center transition"
                    title="缩小" :disabled="qrSize <= 64">
              <span class="text-lg font-bold select-none text-gray-600 dark:text-gray-300">-</span>
            </button>
            <span class="text-xs text-gray-400 self-center select-none">{{ qrSize }}px</span>
            <button @click="changeSize(64)" 
                    class="w-8 h-8 rounded-full bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 flex items-center justify-center transition"
                    title="放大" :disabled="qrSize >= 512">
              <span class="text-lg font-bold select-none text-gray-600 dark:text-gray-300">+</span>
            </button>
          </div>

          <div class="bg-white p-2 rounded-lg shadow-inner mt-3">
             <!-- 动态绑定宽高，添加 transition-all 实现平滑缩放 -->
             <img :src="`data:image/png;base64,${qrImg}`" 
                  class="rounded-lg object-contain transition-all duration-300 ease-out"
                  :style="{ width: qrSize + 'px', height: qrSize + 'px' }" />
          </div>

          <p class="mt-4 animate-pulse text-gray-500 dark:text-gray-400">
            {{ msg }}
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<!-- 新增样式部分，用于处理动画 -->
<style scoped>
/* 定义进入和离开的过渡状态 */
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.5s ease;
}

/* 元素进入前和离开后的状态 */
.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(10px); /* 稍微向下偏移进入 */
}

.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-10px); /* 稍微向上偏移离开 */
}

.animate-fade-in {
  animation: fadeIn 0.5s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(5px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>