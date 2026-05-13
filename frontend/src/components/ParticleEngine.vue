# -*- coding: utf-8 -*-
# Path: frontend/src/components/ParticleEngine.vue

<script setup>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { usePlayerStore } from '../stores/modules/player'
import { useSettingsStore } from '../stores/modules/settings'
import { useThemeStore } from '../stores/modules/theme'

const props = defineProps({
  region: { type: String, required: true } // 'left', 'right', 'top'
})

const store = usePlayerStore()
const settingsStore = useSettingsStore()
const themeStore = useThemeStore()
const canvasRef = ref(null)

let animationFrameId = null
let ctx = null
let particles = []
let lastTime = 0
let cw = 0
let ch = 0

// 根据全局或主题色获取颜色
const getParticleColor = () => {
  const mode = settingsStore.settings.particleColorMode || 'theme'
  if (mode === 'random') {
    return `hsl(${Math.random() * 360}, 80%, 60%)`
  }
  return settingsStore.settings.particleColorStart || themeStore.themeColor || '#ff6699'
}

const textOptions = computed(() => {
  return (settingsStore.settings.particleText || '♪,♫,★,✨').split(',').map(s => s.trim()).filter(s => s)
})

// 辅助：Hex 转 RGB
const hexToRgb = (hex) => {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
  return result ? {
    r: parseInt(result[1], 16),
    g: parseInt(result[2], 16),
    b: parseInt(result[3], 16)
  } : { r: 255, g: 102, b: 153 }
}

const svgPaths = {
  svg_star: new Path2D("M0,-5 L1.12,-1.54 L4.75,-1.54 L1.81,0.58 L2.93,4.04 L0,1.92 L-2.93,4.04 L-1.81,0.58 L-4.75,-1.54 L-1.12,-1.54 z"),
  svg_heart: new Path2D("M0,1.5 C-1.5,-1.5 -4,0.5 -4,2.5 C-4,4.5 0,8 0,8 C0,8 4,4.5 4,2.5 C4,0.5 1.5,-1.5 0,1.5 z"),
  svg_music: new Path2D("M1,4 A2,2 0 1,1 -1,4 L-1,-4 L3,-5 L3,-1 L1,0 z")
}

const customImages = []

// --- 预加载复杂的逐帧动画素材 ---
const animatedAssets = {
  svg_petal: null
}

const petalSVGString = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500" width="100%" height="100%">
    <defs>
        <radialGradient id="petalFront" cx="50%" cy="100%" r="100%">
            <stop offset="0%" stop-color="#b31b41" />
            <stop offset="15%" stop-color="#e84a75" />
            <stop offset="50%" stop-color="#ffb7c5" />
            <stop offset="85%" stop-color="#ffe4e8" />
            <stop offset="100%" stop-color="#ffffff" />
        </radialGradient>
        <radialGradient id="petalBack" cx="50%" cy="100%" r="100%">
            <stop offset="0%" stop-color="#991234" />
            <stop offset="20%" stop-color="#d6315d" />
            <stop offset="55%" stop-color="#ff9eb2" />
            <stop offset="90%" stop-color="#ffb7c5" />
            <stop offset="100%" stop-color="#ffe4e8" />
        </radialGradient>
        <linearGradient id="petalEdge" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stop-color="#ffffff" />
            <stop offset="40%" stop-color="#ffb7c5" />
            <stop offset="100%" stop-color="#8a0f2e" />
        </linearGradient>
        <linearGradient id="veinFront" x1="50%" y1="100%" x2="50%" y2="0%">
            <stop offset="0%" stop-color="#8a0f2e" stop-opacity="0.8" />
            <stop offset="30%" stop-color="#d6315d" stop-opacity="0.4" />
            <stop offset="70%" stop-color="#ffb7c5" stop-opacity="0.1" />
            <stop offset="100%" stop-color="#ffffff" stop-opacity="0" />
        </linearGradient>
        <linearGradient id="veinBack" x1="50%" y1="100%" x2="50%" y2="0%">
            <stop offset="0%" stop-color="#61071e" stop-opacity="0.6" />
            <stop offset="40%" stop-color="#d6315d" stop-opacity="0.3" />
            <stop offset="80%" stop-color="#ff9eb2" stop-opacity="0.1" />
            <stop offset="100%" stop-color="#ffb7c5" stop-opacity="0" />
        </linearGradient>
        <radialGradient id="dewShadow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stop-color="#000000" stop-opacity="0.4" />
            <stop offset="100%" stop-color="#000000" stop-opacity="0" />
        </radialGradient>
        <radialGradient id="dewBody" cx="40%" cy="40%" r="60%">
            <stop offset="0%" stop-color="#ffffff" stop-opacity="0.9" />
            <stop offset="50%" stop-color="#ffb7c5" stop-opacity="0.3" />
            <stop offset="100%" stop-color="#e84a75" stop-opacity="0.6" />
        </radialGradient>
    </defs>
    <g>
        <g class="f1" style="display: none;">
            <path d="M 250,410 C 180,350 130,280 140,190 C 150,100 210,90 240,130 C 245,137 250,150 250,150 C 250,150 255,137 260,130 C 290,90 350,100 360,190 C 370,280 320,350 250,410 Z" fill="url(#petalFront)" />
            <g stroke="url(#veinFront)" fill="none" stroke-linecap="round">
                <path d="M 250,400 Q 200,280 160,150" stroke-width="1.5" />
                <path d="M 250,400 Q 300,280 340,150" stroke-width="1.5" />
                <path d="M 250,400 Q 220,260 190,110" stroke-width="1.8" />
                <path d="M 250,400 Q 280,260 310,110" stroke-width="1.8" />
                <path d="M 248,390 Q 240,250 230,140" stroke-width="1.2" />
                <path d="M 252,390 Q 260,250 270,140" stroke-width="1.2" />
                <path d="M 250,400 Q 250,260 250,155" stroke-width="2.5" opacity="0.6"/>
            </g>
            <path d="M 140,190 C 150,100 210,90 240,130" stroke="#ffffff" stroke-width="2.5" fill="none" opacity="0.9" />
            <path d="M 360,190 C 350,100 290,90 260,130" stroke="#ffffff" stroke-width="1" fill="none" opacity="0.6" />
            <g transform="translate(180, 220) rotate(-15)">
                <ellipse cx="0" cy="4" rx="7" ry="10" fill="url(#dewShadow)" />
                <ellipse cx="-1" cy="1" rx="6" ry="8" fill="url(#dewBody)" />
                <path d="M -4,-2 Q -1,-5 2,-2" stroke="#ffffff" stroke-width="1.2" fill="none" stroke-linecap="round" />
                <circle cx="-1" cy="6" r="1.2" fill="#ffffff" opacity="0.8" />
            </g>
        </g>
        <g class="f2" style="display: none;">
            <path d="M 250,410 C 200,350 170,280 180,190 C 190,100 210,90 230,130 C 235,137 240,150 240,150 C 240,150 248,137 255,130 C 280,90 310,100 320,190 C 330,280 300,350 250,410 Z" fill="url(#petalFront)" />
            <g stroke="url(#veinFront)" fill="none" stroke-linecap="round">
                <path d="M 250,400 Q 210,280 190,140" stroke-width="1.5" />
                <path d="M 250,400 Q 280,280 305,140" stroke-width="1.5" />
                <path d="M 248,390 Q 230,260 215,115" stroke-width="1.8" />
                <path d="M 252,390 Q 265,260 285,115" stroke-width="1.8" />
                <path d="M 250,400 Q 240,260 235,155" stroke-width="2.2" opacity="0.6"/>
            </g>
            <path d="M 180,190 C 190,100 210,90 230,130" stroke="#ffffff" stroke-width="2.5" fill="none" opacity="0.9" />
            <g transform="translate(200, 220) rotate(-25)">
                <ellipse cx="0" cy="4" rx="4.5" ry="9" fill="url(#dewShadow)" />
                <ellipse cx="-1" cy="1" rx="3.5" ry="7" fill="url(#dewBody)" />
                <path d="M -2,-2 Q 0,-4 1,-2" stroke="#ffffff" stroke-width="1" fill="none" stroke-linecap="round" />
            </g>
        </g>
        <g class="f3" style="display: none;">
            <path d="M 250,410 C 230,350 210,280 220,190 C 225,130 235,110 240,130 C 242,135 245,140 245,140 C 245,140 248,135 250,130 C 255,110 265,130 260,190 C 250,280 250,350 250,410 Z" fill="url(#petalEdge)" />
            <g stroke="url(#veinFront)" fill="none" stroke-linecap="round">
                <path d="M 250,400 Q 235,280 230,140" stroke-width="1.2" opacity="0.8"/>
                <path d="M 250,400 Q 248,260 255,140" stroke-width="1.2" opacity="0.6"/>
            </g>
            <path d="M 250,410 C 230,350 210,280 220,190 C 225,130 235,110 240,130" stroke="#ffffff" stroke-width="2.5" fill="none" opacity="1" />
        </g>
        <g class="f4" style="display: none;">
            <path d="M 250,410 C 200,350 190,280 180,190 C 170,100 220,90 245,130 C 252,137 260,150 260,150 C 260,150 265,137 270,130 C 290,90 310,100 320,190 C 330,280 300,350 250,410 Z" fill="url(#petalBack)" />
            <g stroke="url(#veinBack)" fill="none" stroke-linecap="round">
                <path d="M 250,400 Q 200,280 195,140" stroke-width="1.5" />
                <path d="M 250,400 Q 280,280 305,140" stroke-width="1.5" />
                <path d="M 248,390 Q 220,260 225,115" stroke-width="1.8" />
                <path d="M 252,390 Q 275,260 285,115" stroke-width="1.8" />
                <path d="M 250,400 Q 255,260 260,155" stroke-width="2.2" opacity="0.6"/>
            </g>
            <path d="M 180,190 C 170,100 220,90 245,130" stroke="#ffb7c5" stroke-width="1.5" fill="none" opacity="0.7" />
        </g>
    </g>
</svg>`

let resizeObserver = null

onMounted(() => {
  // 预渲染 4 帧樱花贴图
  animatedAssets.svg_petal = []
  for (let i = 1; i <= 4; i++) {
    const rawSvg = petalSVGString.replace(`class="f${i}" style="display: none;"`, `class="f${i}" style="display: block;"`)
    const img = new Image()
    img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(rawSvg)))
    animatedAssets.svg_petal.push(img)
  }
  
  window.addEventListener('resize', resize)
  if (canvasRef.value && canvasRef.value.parentElement) {
    resizeObserver = new ResizeObserver(() => resize())
    resizeObserver.observe(canvasRef.value.parentElement)
  }
  resize()
  animationFrameId = requestAnimationFrame(loop)
})

watch(() => settingsStore.settings.particleCustomUrls, (urls) => {
  customImages.length = 0
  if (!urls || urls.length === 0) return
  urls.forEach(url => {
    const img = new Image()
    img.src = url.startsWith('/api') ? `http://127.0.0.1:12180${url}` : url
    customImages.push(img)
  })
}, { immediate: true })

class Particle {
  constructor(x, y, prewarm = false) {
    this.reset(x, y, prewarm)
  }

  reset(x, y, prewarm = false) {
    const s = settingsStore.settings
    const isMini = settingsStore.isMiniMode
    this.x = x
    this.y = y
    
    // Size (最小化模式下缩小粒子)
    const sizeBase = s.particleSize !== undefined ? s.particleSize : 1.0
    const miniSizeFactor = isMini ? 0.6 : 1.0
    this.size = (Math.random() * 8 + 4) * sizeBase * miniSizeFactor
    
    // Velocity (最小化模式下减速，防止“暴风雨”感)
    let speedBase = s.particleSpeedY !== undefined ? s.particleSpeedY : 2.0
    if (isMini) speedBase *= 0.5
    
    const spread = s.particleSpread !== undefined ? s.particleSpread : 1.0
    const isUp = s.particleDirection === 'up'
    
    this.vx = (Math.random() - 0.5) * spread * 2 * (isMini ? 0.7 : 1.0)
    this.vy = (Math.random() * speedBase + speedBase * 0.5) * (isUp ? -1 : 1)
    
    // Wind
    this.wind = s.particleWind !== undefined ? s.particleWind : 0.0
    
    // Physics
    this.friction = s.particleFriction !== undefined ? s.particleFriction : 0.98
    
    // Rotation
    this.angle = Math.random() * Math.PI * 2
    const rotBase = s.particleRotation !== undefined ? s.particleRotation : 1.0
    this.spin = (Math.random() - 0.5) * rotBase * 0.1
    
    // Life
    const lifeBase = s.particleLife !== undefined ? s.particleLife : 5.0
    this.life = lifeBase * 60 * (0.8 + Math.random() * 0.4)
    this.maxLife = this.life
    
    // Visuals
    this.color = getParticleColor()
    this.baseAlpha = s.particleOpacity !== undefined ? s.particleOpacity : 1.0
    this.alpha = this.baseAlpha
    
    // Lifecycle for animation frames (e.g. Petal)
    this.frameIndex = Math.floor(Math.random() * 100) // Random start frame
    
    // Shape selection
    const shapes = s.particleShapes && s.particleShapes.length > 0 ? s.particleShapes : ['circle']
    this.shape = shapes[Math.floor(Math.random() * shapes.length)]
    
    if (this.shape === 'text') {
      const opts = textOptions.value
      this.text = opts[Math.floor(Math.random() * opts.length)]
    } else if (this.shape === 'custom') {
      if (customImages.length > 0) {
        this.image = customImages[Math.floor(Math.random() * customImages.length)]
      } else {
        this.shape = 'circle'
      }
    }

    if (prewarm) {
      let valid = false
      let attempts = 0
      while (!valid && attempts < 10) {
        const startX = this.x
        const startY = this.y
        const startVx = this.vx
        const startVy = this.vy
        const startAngle = this.angle
        
        const targetLife = Math.random() * this.maxLife
        const frames = this.maxLife - targetLife
        
        let isOut = false
        for (let j = 0; j < frames; j++) {
          this.update()
          let isOutX = false
          if (this.wind > 0) isOutX = this.x > cw + 100
          else if (this.wind < 0) isOutX = this.x < -100
          else isOutX = this.x < -100 || this.x > cw + 100
          const isOutY = isUp ? this.y < -50 : this.y > ch + 50
          if (isOutX || isOutY) {
            isOut = true
            break
          }
        }
        
        if (!isOut) {
          valid = true
          this.life = targetLife
        } else {
          this.x = startX
          this.y = startY
          this.vx = startVx
          this.vy = startVy
          this.angle = startAngle
          this.life = this.maxLife
          this.frameIndex = Math.floor(Math.random() * 100)
          attempts++
        }
      }
      if (!valid) {
        this.life = this.maxLife
      }
    }
  }

  update() {
    this.vx += this.wind * 0.05
    this.vx *= this.friction
    this.vy *= this.friction
    
    this.x += this.vx
    this.y += this.vy
    
    this.angle += this.spin
    this.life--
    this.frameIndex++
    this.alpha = Math.max(0, (this.life / this.maxLife) * this.baseAlpha)
    
    // 动态色彩计算 (渐变模式)
    const mode = settingsStore.settings.particleColorMode || 'theme'
    if (mode === 'life_gradient' || mode === 'height_gradient') {
      const startHex = settingsStore.settings.particleColorStart || themeStore.themeColor || '#ff6699'
      const endHex = settingsStore.settings.particleColorEnd || '#a855f7'
      const threshold = settingsStore.settings.particleColorThreshold ?? 0.5
      
      const c1 = hexToRgb(startHex)
      const c2 = hexToRgb(endHex)
      
      let rawRatio = 0
      if (mode === 'life_gradient') {
        rawRatio = 1 - Math.max(0, this.life / this.maxLife)
      } else if (mode === 'height_gradient') {
        rawRatio = Math.max(0, Math.min(1, this.y / ch))
        if (settingsStore.settings.particleDirection === 'up') rawRatio = 1 - rawRatio
      }
      
      // 使用 Threshold 对 ratio 进行非线性调整，使得渐变更明显
      // 如果 threshold < 0.5，渐变向 Start 颜色倾斜；> 0.5 向 End 颜色倾斜
      let ratio = Math.pow(rawRatio, (1 - threshold) * 4) // 映射比例
      
      const r = Math.floor(c1.r * (1 - ratio) + c2.r * ratio)
      const g = Math.floor(c1.g * (1 - ratio) + c2.g * ratio)
      const b = Math.floor(c1.b * (1 - ratio) + c2.b * ratio)
      this.color = `rgb(${r}, ${g}, ${b})`
    }
  }

  draw(context) {
    context.save()
    context.globalAlpha = this.alpha
    context.translate(this.x, this.y)
    context.rotate(this.angle)
    
    if (this.shape === 'circle') {
      context.beginPath()
      context.arc(0, 0, this.size, 0, Math.PI * 2)
      context.fillStyle = this.color
      context.fill()
    } else if (this.shape === 'plexus') {
      // 连线模式不渲染实体节点粒子，仅在后续通过 drawPlexus 绘制线段
    } else if (this.shape === 'square') {
      context.fillStyle = this.color
      context.fillRect(-this.size, -this.size, this.size * 2, this.size * 2)
    } else if (this.shape === 'triangle') {
      context.beginPath()
      context.moveTo(0, -this.size)
      context.lineTo(this.size, this.size)
      context.lineTo(-this.size, this.size)
      context.closePath()
      context.fillStyle = this.color
      context.fill()
    } else if (this.shape === 'text') {
      context.font = `${this.size * 2}px sans-serif`
      context.fillStyle = this.color
      context.textAlign = 'center'
      context.textBaseline = 'middle'
      context.fillText(this.text, 0, 0)
    } else if (this.shape === 'svg_petal' && animatedAssets.svg_petal) {
      // 每 15 帧切换一次动画切片，模拟翻转效果 (4帧循环)
      const currentFrame = Math.floor(this.frameIndex / 15) % 4
      const img = animatedAssets.svg_petal[currentFrame]
      if (img && img.complete && img.naturalWidth > 0) {
        const dim = this.size * 5 // 樱花需要大一点的渲染空间
        context.drawImage(img, -dim/2, -dim/2, dim, dim)
      }
    } else if (this.shape.startsWith('svg_') && svgPaths[this.shape]) {
      context.scale(this.size * 0.4, this.size * 0.4)
      context.fillStyle = this.color
      context.fill(svgPaths[this.shape])
    } else if (this.shape === 'custom' && this.image && this.image.complete && this.image.naturalWidth > 0) {
      const dim = this.size * 4 // 图片可以渲染得稍微大一点
      context.drawImage(this.image, -dim/2, -dim/2, dim, dim)
    }
    
    context.restore()
  }
}

// 连线逻辑 (Plexus)
function drawPlexus() {
  const s = settingsStore.settings
  if (!s.particleShapes?.includes('plexus')) return
  
  // 线段宽度调整：锁定为 3.0px
  ctx.lineWidth = 3.0
  
  // 1. 生成边缘虚拟锚点，确保粒子能连接到发射源
  const isUp = s.particleDirection === 'up'
  const anchorY = isUp ? ch : 0
  const wind = s.particleWind || 0.0
  const comp = wind * 4000
  let minX = 0, maxX = cw
  if (isUp) {
    if (wind > 0) minX -= comp
    else maxX -= comp
  } else {
    if (wind > 0) minX -= comp
    else maxX -= comp
  }
  
  const virtualAnchors = []
  for (let i = 0; i <= 20; i++) {
    virtualAnchors.push({
      x: minX + (maxX - minX) * (i / 20),
      y: anchorY,
      shape: 'anchor',
      alpha: 1.0,
      color: particles.length ? particles[0].color : '#fff'
    })
  }
  
  // 混合真实粒子与虚拟锚点
  const allNodes = particles.filter(p => p.shape === 'plexus').concat(virtualAnchors)
  
  for (let i = 0; i < allNodes.length; i++) {
    const p1 = allNodes[i]
    if (p1.shape === 'anchor') continue // 锚点本身不主动发起连线
    
    // 寻找最近的节点
    let neighbors = []
    
    for (let j = 0; j < allNodes.length; j++) {
      if (i === j) continue
      const p2 = allNodes[j]
      
      const dx = p1.x - p2.x
      const dy = p1.y - p2.y
      const dist = dx * dx + dy * dy
      
      // 距离阈值保持 90000 (300px)
      if (dist < 90000) {
        neighbors.push({ p: p2, dist: dist })
      }
    }
    
    // 排序并仅取最近的 3 个邻居，保持扁平感
    neighbors.sort((a, b) => a.dist - b.dist)
    neighbors = neighbors.slice(0, 3)
    
    for (const neighbor of neighbors) {
      const p2 = neighbor.p
      const dist = neighbor.dist
      
      const lifeFactor = Math.min(p1.alpha, p2.alpha)
      const distAlpha = 1 - (dist / 90000)
      
      ctx.strokeStyle = p1.color
      // 强制不透明度以确保线条清晰
      ctx.globalAlpha = lifeFactor * distAlpha * 0.95
      
      ctx.beginPath()
      ctx.moveTo(p1.x, p1.y)
      ctx.lineTo(p2.x, p2.y)
      ctx.stroke()
    }
  }
  ctx.globalAlpha = 1.0
}

function resize() {
  if (!canvasRef.value) return
  // 获取父容器实际尺寸，如果获取不到则使用窗口尺寸作为后备
  const rect = canvasRef.value.parentElement?.getBoundingClientRect()
  cw = rect?.width || window.innerWidth
  ch = rect?.height || window.innerHeight
  canvasRef.value.width = cw
  canvasRef.value.height = ch
}

// 自动补偿风力导致的发射区偏移 (真空区消除)
const getLaunchX = () => {
  const wind = settingsStore.settings.particleWind || 0.0
  const isUp = settingsStore.settings.particleDirection === 'up'
  
  // 终极狂风补偿：放大 4000 倍，彻底填平真空区
  const compensation = wind * 4000
  
  let minX = 0
  let maxX = cw
  
  if (isUp) {
    if (wind > 0) minX -= compensation // 在左侧预发
    else maxX -= compensation // 在右侧预发
  } else {
    // 向下发
    if (wind > 0) minX -= compensation
    else maxX -= compensation
  }
  
  return minX + Math.random() * (maxX - minX)
}

function loop(timestamp) {
  // 当粒子引擎关闭或页面处于后台时，跳过密集渲染以优化性能
  if (!settingsStore.settings.particleEnabled || document.hidden) {
    if (ctx) ctx.clearRect(0, 0, cw, ch)
    particles = []
    animationFrameId = requestAnimationFrame(loop)
    return
  }

  if (!ctx) ctx = canvasRef.value.getContext('2d')
  ctx.clearRect(0, 0, cw, ch)
  
  // 如果容器尺寸尚未初始化，尝试重新获取
  if (cw === 0 || ch === 0) {
    resize()
    if (cw === 0 || ch === 0) {
      animationFrameId = requestAnimationFrame(loop)
      return
    }
  }
  
  // 最小化模式下减弱效果：数量减半，且最大限制为 30
  let targetCount = settingsStore.settings.particleCount || 50
  if (settingsStore.isMiniMode) {
    targetCount = Math.min(30, Math.floor(targetCount / 2.5))
  }

  const isUp = settingsStore.settings.particleDirection === 'up'
  const wind = settingsStore.settings.particleWind || 0.0
  
  // 保持粒子总数恒定：一旦开启播放，瞬间补齐目标数量的粒子（附带预热以铺满屏幕）
  if (store.isPlaying) {
    while (particles.length < targetCount) {
      particles.push(new Particle(getLaunchX(), isUp ? ch : 0, true))
    }
  }
  
  // 更新和绘制
  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i]
    p.update()
    
    // 修复真空区 Bug：粒子在被风吹偏时，不应过早被 x 边界剔除
    let isOutX = false
    if (wind > 0) isOutX = p.x > cw + 100 // 风向右，仅在右侧越界时销毁
    else if (wind < 0) isOutX = p.x < -100 // 风向左，仅在左侧越界时销毁
    else isOutX = p.x < -100 || p.x > cw + 100 // 无风，两侧限制
    
    const isOutY = isUp ? p.y < -50 : p.y > ch + 50
    const isOut = isOutX || isOutY
    
    if (p.life <= 0 || isOut) {
      // 粒子死亡或越界时，无缝在发射点重生
      if (store.isPlaying && particles.length <= targetCount) {
        p.reset(getLaunchX(), isUp ? ch : 0)
      } else {
        particles.splice(i, 1)
      }
    } else {
      p.draw(ctx)
    }
  }
  
  drawPlexus()
  animationFrameId = requestAnimationFrame(loop)
}

onUnmounted(() => {
  window.removeEventListener('resize', resize)
  if (resizeObserver) resizeObserver.disconnect()
  if (animationFrameId) cancelAnimationFrame(animationFrameId)
})

watch(() => [settingsStore.settings.particleDirection, props.region, settingsStore.settings.particleEnabled], () => {
  // 容器、方向或开关改变时，清空当前粒子防止瞬间乱飞或闪烁
  particles = []
})
</script>

<template>
  <canvas ref="canvasRef" class="w-full h-full"></canvas>
</template>
