<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { DocumentTextIcon } from '@heroicons/vue/24/solid'

const props = defineProps({
  show: Boolean
})

const emit = defineEmits(['agree', 'decline'])

const isScrolledToBottom = ref(false)
const contentRef = ref(null)

function handleScroll(e) {
  if (isScrolledToBottom.value) return
  
  const el = e.target
  // 留一点误差 (10px) 应对缩放等精度问题
  if (el.scrollHeight - el.scrollTop <= el.clientHeight + 10) {
    isScrolledToBottom.value = true
  }
}

// Ensure the scroll logic works well even if content is small (which it shouldn't be, but just in case)
onMounted(async () => {
  await nextTick()
  if (contentRef.value) {
    if (contentRef.value.scrollHeight <= contentRef.value.clientHeight + 10) {
      isScrolledToBottom.value = true
    }
  }
})

function onAgree() {
  if (isScrolledToBottom.value) {
    emit('agree')
  }
}

function onDecline() {
  emit('decline')
}
</script>

<template>
  <transition name="modal-fade">
    <div v-if="show" class="fixed inset-0 z-[99999] flex items-center justify-center p-6" style="-webkit-app-region: no-drag;">
      <!-- 遮罩层 -->
      <div class="absolute inset-0 bg-black/60 backdrop-blur-sm"></div>
      
      <!-- 弹窗内容 -->
      <div class="bg-white dark:bg-gray-900 rounded-3xl shadow-2xl overflow-hidden w-full max-w-3xl flex flex-col max-h-[85vh] border border-gray-200 dark:border-white/10 relative z-10">
        <div class="px-8 py-5 border-b border-gray-100 dark:border-white/5 bg-gray-50/80 dark:bg-black/40 shrink-0 backdrop-blur-md relative z-10 flex items-center justify-between">
          <div>
            <h2 class="text-xl font-black text-gray-800 dark:text-white flex items-center gap-3 tracking-tight">
              <span class="w-10 h-10 rounded-2xl bg-primary-100 dark:bg-primary-900/50 text-primary-600 dark:text-primary-400 flex items-center justify-center shadow-inner border border-primary-200 dark:border-primary-800/50"><DocumentTextIcon class="w-5 h-5" /></span>
              用户协议与隐私政策
            </h2>
            <p class="text-xs text-gray-500 dark:text-gray-400 mt-1.5 font-medium ml-[52px]">阅读完毕即可解锁同意按钮进入 BiliMusic</p>
          </div>
        </div>
        
        <div 
          ref="contentRef"
          class="px-8 py-6 overflow-y-auto flex-1 prose dark:prose-invert prose-sm max-w-none text-gray-600 dark:text-gray-300 scrollbar-thin scroll-smooth"
          @scroll="handleScroll"
        >
          <h3 class="text-lg font-black text-gray-800 dark:text-white mb-4 tracking-tight">BiliMusic 用户协议与隐私政策</h3>
          <p class="mb-1 font-medium"><strong>更新日期：2026年4月16日</strong></p>
          <p class="mb-1"><strong>发布平台：</strong> <a href="https://github.com/XK-SZG/BiliMusic" target="_blank" class="text-primary-500 hover:text-primary-600 hover:underline">GitHub - XK-SZG/BiliMusic</a></p>
          <p class="mb-4"><strong>联系方式：</strong> kangxu346@gmail.com</p>
          
          <p class="leading-relaxed bg-gray-100 dark:bg-gray-800/50 p-4 rounded-xl border border-gray-200 dark:border-white/5">
            欢迎您使用 BiliMusic！在您使用本软件及相关服务之前，请务必审慎阅读、充分理解本《用户协议》与《隐私政策》（以下简称“本协议”）的各项条款。<strong>一旦您安装、打开、或以任何方式使用 BiliMusic，即表示您已阅读并自愿同意接受本协议的所有约束。如果您不同意本协议的任何内容，请立即卸载并停止使用本软件。</strong>
          </p>

          <hr class="my-6 border-gray-200 dark:border-white/10" />

          <h4 class="text-base font-black text-gray-800 dark:text-white mt-6 mb-3 flex items-center gap-2"><span class="w-1.5 h-4 bg-primary-500 rounded-full"></span>第一部分：BiliMusic 用户协议 (User Agreement)</h4>

          <h5 class="font-bold mt-5 text-gray-700 dark:text-gray-200">1. 软件性质与使用授权</h5>
          <p class="leading-relaxed">1.1 <strong>非商业学习性质</strong>：BiliMusic 是一款旨在打通在线流媒体与本地媒体库管理的<strong>开源免费工具</strong>，其开发初衷仅限于代码技术交流与个人学习。<br>
          1.2 <strong>授权范围</strong>：本软件<strong>仅限用户个人进行非商业性质的使用</strong>。您不得将本软件及衍生代码用于任何形式的商业牟利、二次打包分发、企业内部署或搭建公共服务。</p>

          <h5 class="font-bold mt-5 text-gray-700 dark:text-gray-200">2. 第三方平台服务与法律风险提示</h5>
          <p class="leading-relaxed">2.1 <strong>第三方服务条款 (TOS) 冲突</strong>：BiliMusic 作为一个本地播放器与管理客户端，其核心功能（包括流媒体直连代理、请求头规避、离线数据缓存等）需要直接请求 Bilibili（哔哩哔哩）的服务器。这一行为在客观上可能与 Bilibili 官方的服务条款或防盗链策略发生冲突。<br>
          2.2 <strong>用户主导原则</strong>：本软件仅提供“本地媒体播放”和“网络请求工具”的技术外壳，<strong>软件本身不提供、不存储、不分发任何受版权保护的音视频内容</strong>。所有的搜索、播放、缓存、下载等行为均由您（用户）主动触发并完成。<br>
          <span class="text-red-500 dark:text-red-400">2.3 <strong>风险自担</strong>：因您使用本软件（包括但不限于登录个人账号、高频请求接口、下载受保护内容）所引发的一切法律纠纷、账号封禁（封号）、被限制访问或侵犯第三方知识产权的责任，<strong>均由您个人全权承担，开发者对此不承担任何连带法律责任。</strong></span></p>

          <h5 class="font-bold mt-5 text-gray-700 dark:text-gray-200">3. 用户行为规范</h5>
          <p class="leading-relaxed">3.1 您承诺在使用本软件时遵守适用国家和地区的法律法规，尊重他人的知识产权及合法权益。<br>
          3.2 严禁利用本软件批量抓取、盗取第三方平台的付费内容、会员专享内容或受严格数字版权管理（DRM）保护的内容进行非法传播。</p>

          <h5 class="font-bold mt-5 text-gray-700 dark:text-gray-200">4. 免责声明</h5>
          <p class="leading-relaxed">4.1 本软件按“现状”和“现有”提供，开发者不对软件的稳定性、无漏洞性、适用性及对第三方接口的永久兼容性作任何明示或暗示的保证。<br>
          4.2 若因第三方平台（如 Bilibili）接口变更、防爬虫策略升级或业务调整导致本软件部分或全部功能失效，开发者无义务必须提供修复方案。</p>

          <hr class="my-6 border-gray-200 dark:border-white/10" />

          <h4 class="text-base font-black text-gray-800 dark:text-white mt-6 mb-3 flex items-center gap-2"><span class="w-1.5 h-4 bg-primary-500 rounded-full"></span>第二部分：BiliMusic 隐私政策 (Privacy Policy)</h4>

          <p class="leading-relaxed">我们极其重视您的个人隐私与数据安全。基于 BiliMusic 的底层架构设计，我们在此向您做出<strong>“绝对本地化”</strong>的隐私承诺。</p>

          <h5 class="font-bold mt-5 text-gray-700 dark:text-gray-200">1. 绝对本地化的数据处理原则</h5>
          <p class="leading-relaxed"><strong>纯本地，零遥测</strong>：BiliMusic 是一个完全在您的本地设备上运行的客户端程序。<strong>我们没有、也不会部署任何中心化的遥测（Telemetry）服务器，不收集任何用户行为数据、崩溃日志、设备指纹或使用统计。</strong></p>

          <h5 class="font-bold mt-5 text-gray-700 dark:text-gray-200">2. 敏感信息的存储与流转</h5>
          <p class="leading-relaxed">2.1 <strong>账号与授权信息（Cookie）</strong>：<br>
          当您选择在软件内扫码登录 B 站时，获取的身份验证凭证（Cookie）及用户信息（头像、UID、会员状态等）仅会<strong>加密或明文保存在您本机的相对目录或配置文件中</strong>。这些凭证仅用于软件代替您向 B 站请求合法的流媒体数据和播放列表，<strong>绝对不会上传给开发者或任何第三方服务器</strong>。<br>
          2.2 <strong>媒体库与持久化数据</strong>：<br>
          您的播放历史、播放列表、本地收藏夹、主题配置等数据，均仅存储于本地的 SQLite 数据库和浏览器环境的 IndexedDB 中，完全受您本人物理设备的控制。</p>

          <h5 class="font-bold mt-5 text-gray-700 dark:text-gray-200">3. 剪贴板嗅探与监控机制专项声明</h5>
          <p class="leading-relaxed">3.1 <strong>功能原理</strong>：为了提供便捷的“复制链接即解析”的无缝体验，本软件的后台服务（<code>clipboard_service.py</code>）会监听您操作系统的剪贴板动态。<br>
          3.2 <strong>隐私隔离</strong>：<strong>我们郑重承诺，剪贴板的读取与正则表达式匹配完全、彻底地在本地离线内存中进行。</strong> 只有当匹配到合规的“B站视频链接格式”时，软件才会进行后续解析；所有未匹配的其他任何私人剪贴板内容（如密码、聊天记录、私人文件路径）<strong>会被瞬间丢弃，绝不会被存储、记录或外传。</strong> </p>

          <h5 class="font-bold mt-5 text-gray-700 dark:text-gray-200">4. 第三方网络通信说明</h5>
          <p class="leading-relaxed">您在使用 BiliMusic 过程中产生的所有网络流量，均是您的设备直接与 Bilibili 官方服务器，或由于您导入的图片直链而与相关 CDN 服务器之间的点对点通信。本软件不作为任何形式的中间人（MITM）拦截并窃取您的上游通信数据。</p>

          <h5 class="font-bold mt-5 text-gray-700 dark:text-gray-200">5. 数据的删除与控制</h5>
          <p class="leading-relaxed mb-6">由于所有数据均在您的本地设备上，您拥有 100% 的数据控制权。如果您希望删除所有数据，只需清空软件所在目录、删除生成的数据库文件 (<code>backend/data/</code>) 以及清除相应的 AppData/Local Storage 缓存即可实现彻底销毁。</p>

          <div class="p-4 bg-gray-50 dark:bg-white/5 rounded-xl border border-gray-100 dark:border-white/10 mb-2">
            <p class="text-[11px] text-gray-400 dark:text-gray-500 italic m-0">
              *附则：开发者保留在项目发展过程中，因架构演进或法律要求对本协议进行更新的权利。使用本软件即代表您接受当前版本的协议。*
            </p>
          </div>
        </div>

        <div class="px-8 py-5 border-t border-gray-100 dark:border-white/5 bg-gray-50/80 dark:bg-black/40 flex justify-end gap-3 shrink-0 backdrop-blur-md relative z-10">
          <button 
            @click="onDecline"
            class="px-6 py-2.5 rounded-2xl text-sm font-bold text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-800 transition active:scale-95 border border-transparent hover:border-gray-300 dark:hover:border-gray-600"
          >
            不同意并退出
          </button>
          <div class="relative inline-block group">
            <button 
              @click="onAgree"
              :disabled="!isScrolledToBottom"
              class="px-8 py-2.5 rounded-2xl text-sm font-bold text-white transition-all duration-300 shadow-md flex items-center justify-center gap-2 relative overflow-hidden"
              :class="isScrolledToBottom ? 'bg-primary-500 hover:bg-primary-600 shadow-primary-500/40 hover:shadow-primary-500/60 active:scale-95 cursor-pointer' : 'bg-gray-300 dark:bg-gray-700 cursor-not-allowed opacity-80'"
            >
              <!-- 按钮内流光效果 -->
              <div v-if="isScrolledToBottom" class="absolute inset-0 z-0 bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full group-hover:animate-[shimmer_1.5s_infinite]"></div>
              
              <span class="relative z-10">{{ isScrolledToBottom ? '我已阅读并同意' : '请先滚动阅读至底部' }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </transition>
</template>

<style scoped>
@keyframes shimmer {
  100% {
    transform: translateX(100%);
  }
}

/* 模态框淡入淡出动画 */
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.3s ease;
}

.modal-fade-enter-active .bg-white,
.modal-fade-enter-active .dark\:bg-gray-900,
.modal-fade-leave-active .bg-white,
.modal-fade-leave-active .dark\:bg-gray-900 {
  transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}

.modal-fade-enter-from .bg-white,
.modal-fade-enter-from .dark\:bg-gray-900,
.modal-fade-leave-to .bg-white,
.modal-fade-leave-to .dark\:bg-gray-900 {
  transform: scale(0.95);
  opacity: 0;
}
</style>