// 负向测试：把 getDebugAudit 还原成「漏传令牌」的写法，
// 验证 tests/check_api_wiring.cjs 能否检出该问题，随后恢复文件。
const fs = require('fs')
const path = require('path')
const { execFileSync } = require('child_process')

const target = path.join(__dirname, '..', 'frontend', 'src', 'api', 'system.js')
const original = fs.readFileSync(target, 'utf8')

// 用「按行定位 + 整行替换」的方式，避免依赖具体换行符
const lines = original.split('\n')
const startIndex = lines.findIndex((l) => l.includes('getDebugAudit:'))
if (startIndex < 0) {
  console.error('未找到 getDebugAudit 定义，请检查 api/system.js')
  process.exit(2)
}
// 该方法的定义占两行：签名行 + 请求行
const fixedLines = lines.slice(startIndex, startIndex + 2)
if (!fixedLines[1] || !fixedLines[1].includes('debugHeaders(token)')) {
  console.error('getDebugAudit 的写法与预期不符：', JSON.stringify(fixedLines))
  process.exit(2)
}

const brokenLines = [
  '  getDebugAudit: (limit = 100) => request.get(' + "'" + '/debug/audit' + "'" + ', { params: { limit } }),'
]
const brokenText = lines.slice(0, startIndex)
  .concat(brokenLines, lines.slice(startIndex + 2)).join('\n')

let exitWithBug = null
let outputWithBug = ''
try {
  fs.writeFileSync(target, brokenText)
  console.log('已还原为「漏传令牌」的写法，运行检查...\n')
  outputWithBug = execFileSync(process.execPath,
    [path.join(__dirname, 'check_api_wiring.cjs')],
    { cwd: path.join(__dirname, '..'), encoding: 'utf8' })
  exitWithBug = 0
} catch (e) {
  exitWithBug = e.status === undefined ? -1 : e.status
  outputWithBug = (e.stdout || '') + (e.stderr || '')
} finally {
  fs.writeFileSync(target, original)
  console.log('已恢复修复版本\n')
}

console.log('--- 漏传令牌时的检查输出 ---')
console.log(outputWithBug.trim())
console.log()

const detected = exitWithBug !== 0 && /未携带 X-Debug-Token|首个参数不是调试令牌/.test(outputWithBug)
console.log(detected
  ? `[PASS] 负向测试通过：检查脚本成功检出该缺陷（退出码 ${exitWithBug}）`
  : `[FAIL] 负向测试失败：检查脚本未能检出该缺陷（退出码 ${exitWithBug}）`)

// 恢复后再次确认一切正常
try {
  const out = execFileSync(process.execPath,
    [path.join(__dirname, 'check_api_wiring.cjs')],
    { cwd: path.join(__dirname, '..'), encoding: 'utf8' })
  console.log(out.trim())
  console.log('[PASS] 恢复后检查通过')
} catch (e) {
  console.log('[FAIL] 恢复后检查未通过：')
  console.log(((e.stdout || '') + (e.stderr || '')).trim())
  process.exit(1)
}

process.exit(detected ? 0 : 1)
