import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './style.css'
import App from './App.vue'
import router from './router'

// 彻底禁用原生同步阻塞弹窗，根除浏览器回弹与任务栏闪烁
window.alert = () => {}
window.confirm = () => true
window.prompt = () => null

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)

// [修复历史遗留问题] 必须在路由逻辑执行前初始化 Store，确保持久化索引不被视图覆盖
import { usePlayerStore } from './stores/modules/player'
const playerStore = usePlayerStore()

// 启动路由策略
const settings = JSON.parse(localStorage.getItem('bili_settings') || '{}')
const startupPage = settings.startupPage || 'home'
const lastRoute = localStorage.getItem('last_route') || '/'

if (startupPage !== 'home') {
  const routeMap = {
    bili: '/bili',
    local: '/local',
    queue: '/queue',
    last: lastRoute
  }
  const target = routeMap[startupPage]
  if (target && target !== '/') {
    // 延迟跳转，确保路由已就绪
    router.isReady().then(() => {
      router.push(target)
    })
  }
}

// 注册全局指令 v-click-outside
app.directive('click-outside', {
  mounted(el, binding) {
    el.clickOutsideEvent = function(event) {
      if (!(el === event.target || el.contains(event.target))) {
        binding.value(event, el);
      }
    };
    document.addEventListener('click', el.clickOutsideEvent);
  },
  unmounted(el) {
    document.removeEventListener('click', el.clickOutsideEvent);
  },
});

app.mount('#app')
