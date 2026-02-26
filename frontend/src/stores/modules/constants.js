export const DEFAULT_SETTINGS = {
  streamQuality: 64, cacheQuality: 80, defaultVolume: 0.7, bgEffects: ['float'],
  videoScale: 1.0, bgBlur: 100, bgOpacity: 0.6, visualizerStyle: 'bars',
  visSensitivity: 1.0, visCount: 64, visColor: 'pink', visDirection: 'forward',
  visHeightLimit: 0.8, visGain: 1.0, visColorCustom: '#ff6699', visColorCustomSec: '#a855f7',
  visCutoffLow: 0, visCutoffHigh: 75, visPosition: 'bottom', visSmoothing: 0.8,
  visGravity: 2.0, visEnabled: false, uiOpacity: 0.85, uiBlur: 20, uiFontFamily: 'sans',
  uiFontSize: 1.0, uiFontCustom: '', sidebarPosition: 'left', videoFitMode: 'contain',
  bgType: 'cover', bgCustomMode: 'list', immersiveOverlay: 'all', immersiveVideoFloat: true,
  particleAboveVideo: true, bgAnimationSpeed: 1.0, bgAnimationAmplitude: 1.0, startupPage: 'home',
  uiTransition: 'fade', enableVolumeFade: true, idleTimeout: 3, weightSensitivity: 2.0,
  particleEnabled: false, particleDirection: 'up', particleShapes: ['circle'],
  particleText: '♪,♫,★,✨', particleCount: 50, particleColorMode: 'theme',
  particleColorStart: '', particleColorEnd: '', particleSpeedY: 2.0, particleSpread: 1.0,
  particleWind: 0.0, particleFriction: 0.98, particleRotation: 1.0, particleLife: 5.0,
  particleSize: 1.0, particleOpacity: 1.0, particleColorThreshold: 0.5,
  particleCustomUrls: [], stickersEnabled: false,
  stickers: { uiBackground: [], sidebar: [], mainView: [], playerBar: [], immersive: [] },
  customBackgrounds: [],
  shortcuts: {
    play: 'Space', prev: 'BracketLeft', next: 'BracketRight', volumeUp: 'ArrowUp',
    volumeDown: 'ArrowDown', seekForward: 'ArrowRight', seekBackward: 'ArrowLeft',
    mute: 'KeyM', fullscreen: 'KeyF', immersive: 'KeyI', toggleUi: 'Enter', toggleTheme: 'KeyT'
  },
  cardImage: '',
  cardImageSize: 50,
  cardOffsetX: -10,
  cardOffsetY: 10
}

export const BILIBILI_SETTINGS = {
  streamQuality: 64, cacheQuality: 80, defaultVolume: 0.7, 
  bgEffects: ["float", "ripple", "rotate", "drift", "zoom", "glitch", "wave", "pulse", "color"],
  videoScale: 1, bgBlur: 2, bgOpacity: 0.6, visualizerStyle: "curve",
  visSensitivity: 1.5, visCount: 160, visColor: "pink", visDirection: "reverse_symmetric",
  visHeightLimit: 1, visColorCustom: "#ff6699", visColorCustomSec: "#a855f7",
  visCutoffLow: 0, visCutoffHigh: 70, visPosition: "double", visSmoothing: 0.9,
  visGravity: 2, visEnabled: true, uiOpacity: 0.5, uiBlur: 5, uiFontFamily: "sans",
  uiFontSize: 1, uiFontCustom: "", sidebarPosition: "left", videoFitMode: "contain",
  bgType: "cover", bgCustomMode: "list", immersiveOverlay: "all", immersiveVideoFloat: true,
  particleAboveVideo: true, bgAnimationSpeed: 1, bgAnimationAmplitude: 1, startupPage: "home",
  uiTransition: "fade", enableVolumeFade: true, idleTimeout: 3, weightSensitivity: 2,
  particleEnabled: true, particleDirection: "down", particleShapes: ["svg_petal", "circle", "custom"],
  particleText: "♪,♫,★,✨", particleCount: 100, particleColorMode: "life_gradient",
  particleColorStart: "", particleColorEnd: "#0087bd", particleSpeedY: 6, particleSpread: 2,
  particleWind: -2, particleFriction: 0.9975, particleRotation: 2.5, particleLife: 5,
  particleSize: 1, particleOpacity: 1, particleColorThreshold: 0.85,
  particleCustomUrls: ["/api/system/particles/raw/b194e8d6_SmallTV.svg"], stickersEnabled: true,
  stickers: {
    uiBackground: [
      { id: "tdy6ztn6a", url: "/local_stickers/99bfcba9_22-画板背景.png", x: 8.1, y: 87.3, width: 26, opacity: 0.65, rotate: 0 },
      { id: "q06aje8i2", url: "/local_stickers/a4ee1bba_33-画板背景.png", x: 94, y: 78.2, width: 20, opacity: 0.65, rotate: 0 }
    ],
    sidebar: [
      { id: "e7i07cp86", url: "/local_stickers/fcf9ce47_小电视-侧边栏背景.png", x: 9.3, y: 28.2, width: 140, opacity: 0.5, rotate: 45 }
    ],
    mainView: [
      { id: "ed2nb5vbk", url: "/local_stickers/21d6643f_22-主视图背景.png", x: 0.8, y: 17.7, width: 16, opacity: 0.65, rotate: 40 },
      { id: "zx0za3ors", url: "/local_stickers/1c0054d1_33-主视图背景.png", x: 97.4, y: 24.6, width: 14, opacity: 0.65, rotate: -55 },
      { id: "pmoba0esy", url: "/local_stickers/2fc4f03e_2233-主视图背景.png", x: 12.2, y: 85.7, width: 14, opacity: 0.55, rotate: 0 }
    ],
    playerBar: [
      { id: "ltwfxn9jf", url: "/local_stickers/d1d27b25_2233-播放栏背景.png", x: 73.5, y: 78.8, width: 20, opacity: 0.8, rotate: 0 }
    ],
    immersive: [
      { id: "fxe1r78yu", url: "/local_stickers/8fa85d0a_22-沉浸播放界面.png", x: 9.8, y: 72.8, width: 36, opacity: 0.8, rotate: 0 },
      { id: "pox9rgl6c", url: "/local_stickers/bc41a97f_33-沉浸播放界面.png", x: 87.8, y: 74.6, width: 40, opacity: 0.8, rotate: 0 }
    ]
  },
  customBackgrounds: [],
  shortcuts: { play: "Space", prev: "BracketLeft", next: "BracketRight", volumeUp: "ArrowUp", volumeDown: "ArrowDown", seekForward: "ArrowRight", seekBackward: "ArrowLeft", mute: "KeyM", fullscreen: "KeyF", immersive: "KeyI", toggleUi: "Enter", toggleTheme: "KeyT" },
  cardImage: "/local_stickers/9e9ad747_2233-图标.png",
  cardImageSize: 100,
  cardOffsetX: -25,
  cardOffsetY: 10,
  visGain: 1
}
