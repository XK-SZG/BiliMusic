// 前端 ↔ 后端 接线静态校验
//
// 覆盖两类曾经真实发生过的缺陷：
//
//   A. `systemApi.getStats is not a function`
//      —— 接口实现被写进 api/logs.js，组件却仍在 systemApi 上调用。
//      构建能通过，只在运行时以 TypeError 暴露。
//
//   B. 审计日志 403「令牌校验失败」
//      —— 后端接口受 require_debug_token 保护，前端调用时却漏传 X-Debug-Token。
//
// 用法（在项目根目录或 frontend 目录下均可）：
//     node tests/check_api_wiring.cjs
// 退出码：全部通过为 0，存在问题为 1，环境不满足为 2。
const fs = require('fs')
const path = require('path')

const root = process.cwd()
const hasFrontendHere = fs.existsSync(path.join(root, 'src', 'api'))
const SRC = hasFrontendHere ? path.join(root, 'src') : path.join(root, 'frontend', 'src')
const PROJECT = hasFrontendHere ? path.join(root, '..') : root

if (!fs.existsSync(SRC)) {
  console.error('找不到前端源码目录，请在项目根目录或 frontend 目录下执行')
  process.exit(2)
}

let problems = 0
let checked = 0

// ============================================================
// 检查 A：组件调用的 api 方法必须在对应模块中导出
// ============================================================

function readModuleMethods(relPath) {
  const full = path.join(SRC, relPath)
  if (!fs.existsSync(full)) return new Set()
  const text = fs.readFileSync(full, 'utf8')
  const methods = new Set()
  // 匹配 `name: (` / `name: async (` / `async name(` 形式的对象方法
  const re = /^\s{2}(?:async\s+)?([A-Za-z_$][\w$]*)\s*[:(]/gm
  let m
  while ((m = re.exec(text)) !== null) methods.add(m[1])
  return methods
}

function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) walk(full, out)
    else if (/\.(vue|js)$/.test(entry.name)) out.push(full)
  }
  return out
}

const importRe = /import\s+(\w+)\s+from\s+['"][^'"]*api\/(\w+)['"]/g

console.log('【检查 A】组件调用的 API 方法是否存在于对应模块')
for (const file of walk(SRC)) {
  const text = fs.readFileSync(file, 'utf8')
  const aliasMap = {}
  let im
  importRe.lastIndex = 0
  while ((im = importRe.exec(text)) !== null) {
    const alias = im[1]
    const mod = `api/${im[2]}.js`
    aliasMap[alias] = { mod, methods: readModuleMethods(mod) }
  }

  for (const alias of Object.keys(aliasMap)) {
    const { mod, methods } = aliasMap[alias]
    const callRe = new RegExp(`\\b${alias}\\.([A-Za-z_$][\\w$]*)`, 'g')
    let cm
    while ((cm = callRe.exec(text)) !== null) {
      const method = cm[1]
      checked++
      if (!methods.has(method)) {
        const line = text.slice(0, cm.index).split('\n').length
        console.log(`  [FAIL] ${path.relative(root, file)}:${line}  调用 ${alias}.${method}()，但 ${mod} 未导出该方法`)
        problems++
      }
    }
  }
}
console.log(`  → 共校验 ${checked} 处 API 调用`)

// ============================================================
// 检查 B：受 require_debug_token 保护的后端接口，前端必须传令牌
// ============================================================

console.log()
console.log('【检查 B】受令牌保护的调试接口，前端是否携带 X-Debug-Token')

const debugRouter = path.join(PROJECT, 'backend', 'routers', 'debug.py')
const systemApiFile = path.join(SRC, 'api', 'system.js')

if (!fs.existsSync(debugRouter) || !fs.existsSync(systemApiFile)) {
  console.log('  （跳过：找不到 backend/routers/debug.py 或 src/api/system.js）')
} else {
  const routerText = fs.readFileSync(debugRouter, 'utf8')
  const apiText = fs.readFileSync(systemApiFile, 'utf8')
  const apiLines = apiText.split('\n')

  // 1) 找出所有参数里出现 require_debug_token 的处理函数名
  const protectedFns = new Set()
  const fnRe = /def\s+(\w+)\s*\(([\s\S]*?)\)\s*:/g
  let fm
  while ((fm = fnRe.exec(routerText)) !== null) {
    if (fm[2].includes('require_debug_token')) protectedFns.add(fm[1])
  }

  // 2) 收集「路由装饰器 -> 处理函数名」的映射
  const routes = []
  const routeRe = /@router\.(get|post|delete|put)\(\s*'([^']+)'[\s\S]*?\)\s*\n(?:@[^\n]*\n)*def\s+(\w+)\s*\(/g
  let rm
  while ((rm = routeRe.exec(routerText)) !== null) {
    routes.push({ method: rm[1].toUpperCase(), routePath: rm[2], fn: rm[3] })
  }

  const protectedRoutes = routes.filter((r) => protectedFns.has(r.fn))

  // 3) 对每个受保护路由，在 api/system.js 中定位调用它的方法
  //    方法索引：以「行首两个空格 + 方法名 + 冒号」界定方法块
  const methodStarts = []
  apiLines.forEach((line, index) => {
    const m = /^\s{2}(\w+)\s*:/.exec(line)
    if (m) methodStarts.push({ name: m[1], start: index })
  })

  function methodBlockAt(lineIndex) {
    let current = null
    for (const item of methodStarts) {
      if (item.start <= lineIndex) current = item
      else break
    }
    if (!current) return null
    const next = methodStarts.find((i) => i.start > current.start)
    const end = next ? next.start : apiLines.length
    return { name: current.name, body: apiLines.slice(current.start, end).join('\n') }
  }

  let located = 0
  let missingToken = 0

  for (const route of protectedRoutes) {
    // 路由装饰器里的路径是「相对 router 前缀」的，而前端写的是完整路径
    // （本项目的调试路由统一挂在 /api/debug 下），因此这里补上前缀再匹配。
    const fullPath = '/debug' + route.routePath
    const needle = "'" + fullPath + "'"
    const hitIndex = apiLines.findIndex((line) => line.includes(needle))
    if (hitIndex < 0) continue
    const block = methodBlockAt(hitIndex)
    if (!block) continue
    located++

    const hasToken = /debugHeaders\(/.test(block.body) || /X-Debug-Token/.test(block.body)
    if (!hasToken) {
      console.log(`  [FAIL] api/system.js 的 ${block.name}() 调用受保护的 `
        + `${route.method} ${fullPath}，但未携带 X-Debug-Token`)
      missingToken++
      problems++
    }

    // 4) 确认调用方确实传入了令牌参数（不能是数字/字符串字面量）
    const callersRe = new RegExp(`\\bsystemApi\\.${block.name}\\(([^)]*)`, 'g')
    for (const file of walk(SRC)) {
      const text = fs.readFileSync(file, 'utf8')
      let cm
      while ((cm = callersRe.exec(text)) !== null) {
        const args = cm[1].trim()
        const firstArg = args.split(',')[0].trim()
        if (!firstArg || /^\d+$/.test(firstArg) || /^['"]/.test(firstArg)) {
          const line = text.slice(0, cm.index).split('\n').length
          console.log(`  [FAIL] ${path.relative(root, file)}:${line}  `
            + `${block.name}() 首个参数不是调试令牌（实际：${firstArg || '空'}）`)
          problems++
        }
      }
    }
  }

  console.log(`  → 受保护路由 ${protectedRoutes.length} 个，`
    + `在前端定位到 ${located} 个（缺令牌 ${missingToken} 个）`)
}

console.log()
console.log(problems
  ? `检查未通过：发现 ${problems} 处接线问题`
  : '检查通过：未发现接线问题')
process.exit(problems ? 1 : 0)
