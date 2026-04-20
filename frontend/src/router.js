import { createRouter, createWebHashHistory } from 'vue-router'
const routes = [
  { path: '/', component: () => import('./views/Home.vue') },
  { path: '/bili', component: () => import('./views/BiliLibrary.vue') },
  { path: '/local', component: () => import('./views/LocalLibrary.vue') },
  { path: '/queue', component: () => import('./views/PlayQueue.vue') },
  { path: '/statistics', component: () => import('./views/Statistics.vue') },
  { path: '/settings', component: () => import('./views/Settings.vue') }
]

export default createRouter({
  history: createWebHashHistory(),
  routes
})