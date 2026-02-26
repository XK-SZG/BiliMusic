export function hexToRgb(hex) {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
  return result ? {
    r: parseInt(result[1], 16),
    g: parseInt(result[2], 16),
    b: parseInt(result[3], 16)
  } : null
}

export function mixColor(c1, c2, weight) {
  const w1 = weight
  const w2 = 1 - w1
  const rgb = {
    r: Math.round(c1.r * w1 + c2.r * w2),
    g: Math.round(c1.g * w1 + c2.g * w2),
    b: Math.round(c1.b * w1 + c2.b * w2)
  }
  return rgb
}

export function generateThemeVariables(hexColor) {
  const base = hexToRgb(hexColor)
  if (!base) return null
  
  const white = { r: 255, g: 255, b: 255 }
  const black = { r: 0, g: 0, b: 0 }

  // 生成色阶 (Tailwind 默认风格)
  // 50: 非常浅
  // 100: 浅
  // 200: 较浅
  // 300: ...
  // 400: ...
  // 500: Base
  // 600: Slightly Darker
  // 700: Darker
  // 800: ...
  // 900: Very Dark

  // 简单算法：与白/黑混合
  const shades = {
    50: mixColor(white, base, 0.95),
    100: mixColor(white, base, 0.9),
    200: mixColor(white, base, 0.75),
    300: mixColor(white, base, 0.6),
    400: mixColor(white, base, 0.3),
    500: base,
    600: mixColor(black, base, 0.1),
    700: mixColor(black, base, 0.3),
    800: mixColor(black, base, 0.5),
    900: mixColor(black, base, 0.7),
  }

  const vars = {}
  for (const [key, value] of Object.entries(shades)) {
    vars[`--color-primary-${key}`] = `${value.r} ${value.g} ${value.b}`
  }
  
  // 同时也定义一个通用的 --color-primary 指向 500
  vars['--color-primary'] = `${base.r} ${base.g} ${base.b}`

  return vars
}

export function applyTheme(vars) {
  const root = document.documentElement
  for (const [key, value] of Object.entries(vars)) {
    root.style.setProperty(key, value)
  }
}
