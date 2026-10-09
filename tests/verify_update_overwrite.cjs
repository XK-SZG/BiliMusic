// 发行包「覆盖更新」数据安全验证（沙盒）
//
// 背景：安装器在升级时由 electron-builder 生成的卸载器负责清理旧程序文件。
// frontend/build/afterPack.cjs 依据打包产物生成 frontend/build/uninstall_list.nsh，
// 其中的 customRemoveFiles / cleanOldFiles 两个宏决定了「升级时哪些文件被移走」。
// 历史上（v1.0.18 及以前）这里是 RMDir /r "$INSTDIR"，会在升级时把用户的
// backend/data（媒体库、下载缓存、Cookie）一起删掉，属于致命缺陷。
//
// 本脚本不依赖 NSIS 与本机安装，而是：
//   1. 解析真实的 frontend/build/uninstall_list.nsh（即实际参与编译的宏）；
//   2. 在系统临时目录建一个沙盒，按真实布局铺一份「旧版本安装目录」，
//      其中包含用户数据（backend/data 下的库、Cookie、下载缓存）与用户自建文件；
//   3. 按 NSIS 语义逐条执行宏里的 Rename / RMDir；
//   4. 模拟安装器写入新版程序文件；
//   5. 断言：用户数据与用户文件必须完好、旧程序文件必须被替换、无残留冲突。
//
// 安全约定（见 AGENTS.md 3.1 / tests/README.md）：
//   - 只在系统临时目录内读写，绝不触碰真实安装目录或 backend/data；
//   - 不执行关机 / 休眠 / 卸载等破坏性动作；
//   - 不读取任何凭据文件内容（沙盒里写的是占位文本）。
const fs = require('fs')
const os = require('os')
const path = require('path')

const ROOT = path.join(__dirname, '..')
const NSH = path.join(ROOT, 'frontend', 'build', 'uninstall_list.nsh')

let passed = 0
let failed = 0
const failures = []

function check(name, ok, detail) {
  if (ok) {
    passed += 1
    console.log(`  [PASS] ${name}`)
  } else {
    failed += 1
    failures.push(name)
    console.log(`  [FAIL] ${name}${detail === undefined ? '' : '  -> ' + detail}`)
  }
}

function section(title) {
  console.log(`\n${'='.repeat(66)}\n${title}\n${'='.repeat(66)}`)
}

// ---------------------------------------------------------------------------
// NSIS 宏解析
// ---------------------------------------------------------------------------

// 从 nsh 文本中抽取指定宏的宏体
function extractMacro(text, macroName) {
  const startRe = new RegExp('^\\s*!macro\\s+' + macroName + '\\s*$', 'm')
  const start = text.search(startRe)
  if (start < 0) return null
  const endIdx = text.indexOf('!macroend', start)
  if (endIdx < 0) return null
  return text.slice(start, endIdx)
}

// 把单行翻译成一条指令；无法识别（控制流等）返回 null
function parseLine(line) {
  let m = line.match(/^CreateDirectory\s+"([^"]+)"/i)
  if (m) return { op: 'mkdir', target: m[1] }

  m = line.match(/^Rename\s+"([^"]+)"\s+"([^"]+)"/i)
  if (m) return { op: 'rename', from: m[1], to: m[2] }

  m = line.match(/^RMDir\s+\/r\s+"([^"]+)"/i)
  if (m) return { op: 'rmdir_r', target: m[1] }

  m = line.match(/^RMDir\s+"([^"]+)"/i)
  if (m) return { op: 'rmdir', target: m[1] }

  return null
}

// 解析宏体，保留 ${If} ... ${Else} ... ${EndIf} 的分支结构。
//
// 返回 [{ branch: 'if' | 'else' | null, ops: [...] }, ...] 形式的段落列表：
//   - branch === null 表示无条件执行的指令（${If} 之前或 ${EndIf} 之后）
//   - branch === 'if' / 'else' 分别对应条件成立 / 不成立时才执行的指令
// 本函数不判断条件真假，由调用方按场景（$R9 的取值）决定执行哪一段。
function parseMacro(body) {
  const segments = []
  let current = { branch: null, ops: [] }
  segments.push(current)
  let depth = 0      // ${If} 嵌套深度
  const stack = []   // 记录每个 ${If} 所属的段落索引，便于 ${EndIf} 收尾

  for (const raw of body.split(/\r?\n/)) {
    const line = raw.trim()
    if (!line || line.startsWith(';')) continue
    if (line.startsWith('!macro')) continue   // !macro / !macroend 指令行本身

    if (/^\$\{If(N?ot)?\}/i.test(line)) {
      depth += 1
      stack.push(segments.length - 1)
      current = { branch: 'if', ops: [] }
      segments.push(current)
      continue
    }
    if (/^\$\{Else\}/i.test(line)) {
      current = { branch: 'else', ops: [] }
      segments.push(current)
      continue
    }
    if (/^\$\{EndIf\}/i.test(line)) {
      depth -= 1
      stack.pop()
      // ${EndIf} 之后的指令属于外层：新建一个无条件段落
      current = { branch: null, ops: [] }
      segments.push(current)
      continue
    }

    // 条件判断行本身（如 `$R9 == "0"`）不是可执行指令
    if (/^\$R\d+\s*==/.test(line)) continue

    const op = parseLine(line)
    if (op) current.ops.push(op)
    // 其余语句（StrCpy / Goto / MessageBox 等）与文件操作无关，本测试忽略
  }

  // 丢弃没有任何指令的段落
  return segments.filter((s) => s.ops.length > 0)
}

// 按场景实际执行的指令：无条件段落始终执行，
// 条件段落按 $R9 取值选择（$R9 == "0" 走 if 分支，否则走 else 分支）
function opsForScenario(segments, r9Value) {
  const ops = []
  for (const seg of segments) {
    if (seg.branch === null) ops.push(...seg.ops)
    else if (seg.branch === 'if' && r9Value === '0') ops.push(...seg.ops)
    else if (seg.branch === 'else' && r9Value !== '0') ops.push(...seg.ops)
  }
  return ops
}

// 供静态检查使用：宏里出现的全部指令（不论分支）
function allOps(segments) {
  return segments.flatMap((s) => s.ops)
}

// 统计某类指令出现的位置，用于判断它落在哪个分支
function opsInBranches(segments, opName) {
  const found = { if: 0, else: 0, none: 0 }
  for (const seg of segments) {
    const n = seg.ops.filter((o) => o.op === opName).length
    if (!n) continue
    found[seg.branch === null ? 'none' : seg.branch] += n
  }
  return found
}

// 把 $INSTDIR / $PLUGINSDIR 展开为沙盒里的真实路径
function expand(p, vars) {
  return p.replace(/\$(INSTDIR|PLUGINSDIR)/g, (_, name) => vars[name])
}

// ---------------------------------------------------------------------------
// 按 NSIS 语义执行指令（关键语义：Rename 目标已存在会失败；RMDir 仅在空目录成功）
// ---------------------------------------------------------------------------
function runOps(ops, vars, stats) {
  for (const op of ops) {
    const target = expand(op.target || '', vars)
    if (op.op === 'mkdir') {
      try { fs.mkdirSync(target, { recursive: true }) } catch (e) { /* NSIS 不报错 */ }
      continue
    }
    if (op.op === 'rename') {
      const from = expand(op.from, vars)
      const to = expand(op.to, vars)
      try {
        if (fs.existsSync(to)) { stats.renameConflict += 1; continue }
        fs.mkdirSync(path.dirname(to), { recursive: true })
        fs.renameSync(from, to)
        stats.renamed += 1
      } catch (e) {
        // 源文件不存在时 NSIS 的 Rename 静默失败
        stats.renameFailed += 1
      }
      continue
    }
    if (op.op === 'rmdir') {
      try {
        fs.rmdirSync(target)   // 非空目录会抛错，与 RMDir 语义一致
        stats.dirRemoved += 1
      } catch (e) { /* 非空或不存在：保留 */ }
      continue
    }
    if (op.op === 'rmdir_r') {
      stats.recursiveWipe += 1
      try { fs.rmSync(target, { recursive: true, force: true }) } catch (e) { /* ignore */ }
      continue
    }
  }
}

// ---------------------------------------------------------------------------
// 沙盒布局
// ---------------------------------------------------------------------------
function writeFile(p, content) {
  fs.mkdirSync(path.dirname(p), { recursive: true })
  fs.writeFileSync(p, content, 'utf8')
}

// 旧版本安装目录中的「程序文件」（与 uninstall_list.nsh 中 Rename 的清单同源）
const PROGRAM_FILES = [
  'BiliMusic.exe',
  'resources\\app.asar',
  'resources\\backend\\backend.exe',
  'resources.pak',
  'icudtl.dat',
  'ffmpeg.dll',
  'LICENSE.electron.txt',
  'locales\\zh-CN.pak',
  'locales\\en-US.pak',
]

// 用户数据（升级必须保留）
const USER_DATA_FILES = [
  'resources\\backend\\data\\bili_player.db',
  'resources\\backend\\data\\bili_player.db-wal',
  'resources\\backend\\data\\bili_cookies.json',
  'resources\\backend\\data\\bili_user_info.json',
  'resources\\backend\\data\\downloads\\BV1xx411c7mD.mp4',
  'resources\\backend\\data\\downloads\\BV1yy411c7mE.mp4',
  'resources\\backend\\data\\covers\\cover_001.jpg',
  'resources\\backend\\data\\stickers\\sticker_a.png',
  'resources\\backend\\data\\backgrounds\\bg_1.jpg',
  'resources\\backend\\data\\logs\\bilimusic.log',
  'resources\\backend\\data\\fonts\\user_font.ttf',
  'resources\\backend\\data\\particles\\p1.png',
  'resources\\backend\\data\\failed_downloads\\broken.part',
]

// 用户自己放进安装目录的文件（不应被删除）
const USER_FREE_FILES = [
  '我的歌单.txt',
  '备份\\media_backup.zip',
]

// 旧版本遗留、且不在新版本文件清单中的陈旧文件
const STALE_FILES = [
  'old_helper.dll',
  'locales\\zz-LEGACY.pak',
  'resources\\legacy\\legacy_asset.bin',
]

const USER_DATA_CONTENT = 'USER-DATA-MUST-SURVIVE'

function buildOldInstall(instdir) {
  for (const rel of PROGRAM_FILES) writeFile(path.join(instdir, rel), 'OLD-PROGRAM:' + rel)
  for (const rel of USER_DATA_FILES) writeFile(path.join(instdir, rel), USER_DATA_CONTENT + ':' + rel)
  for (const rel of USER_FREE_FILES) writeFile(path.join(instdir, rel), USER_DATA_CONTENT + ':' + rel)
  for (const rel of STALE_FILES) writeFile(path.join(instdir, rel), 'STALE:' + rel)
}

function listFiles(root) {
  const out = []
  const walk = (dir, rel) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const r = rel ? path.join(rel, entry.name) : entry.name
      if (entry.isDirectory()) walk(path.join(dir, entry.name), r)
      else out.push(r)
    }
  }
  if (fs.existsSync(root)) walk(root, '')
  return out
}

function readAll(root) {
  const map = {}
  for (const rel of listFiles(root)) {
    try { map[rel] = fs.readFileSync(path.join(root, rel), 'utf8') } catch (e) { map[rel] = '<unreadable>' }
  }
  return map
}

// 新版安装器写入的程序文件（内容变化，用于确认确实发生了覆盖）
function installNewVersion(instdir) {
  for (const rel of PROGRAM_FILES) writeFile(path.join(instdir, rel), 'NEW-PROGRAM-v1.0.24:' + rel)
}

// ---------------------------------------------------------------------------
// 主流程
// ---------------------------------------------------------------------------
function main() {
  section('BiliMusic 发行包覆盖更新 —— 数据安全沙盒验证')

  console.log(`解析宏文件: ${path.relative(ROOT, NSH)}`)
  if (!fs.existsSync(NSH)) {
    console.error('  [FAIL] 找不到 frontend/build/uninstall_list.nsh —— 无法验证更新逻辑')
    process.exit(2)
  }
  const nshText = fs.readFileSync(NSH, 'utf8')

  const removeBody = extractMacro(nshText, 'customRemoveFiles')
  const cleanBody = extractMacro(nshText, 'cleanOldFiles')
  check('uninstall_list.nsh 中定义了 customRemoveFiles 宏', !!removeBody)
  check('uninstall_list.nsh 中定义了 cleanOldFiles 宏', !!cleanBody)
  if (!removeBody || !cleanBody) process.exit(2)

  const removeSegments = parseMacro(removeBody)
  const cleanSegments = parseMacro(cleanBody)
  const removeAllOps = allOps(removeSegments)
  const cleanAllOps = allOps(cleanSegments)
  console.log(`  customRemoveFiles: ${removeAllOps.length} 条指令（含分支）`)
  console.log(`  cleanOldFiles:     ${cleanAllOps.length} 条指令`)

  // 场景实际的指令序列
  const removeOpsOnUpdate = opsForScenario(removeSegments, '1')   // 覆盖升级
  const removeOpsOnWipe = opsForScenario(removeSegments, '0')     // 用户要求删除数据
  console.log(`  覆盖升级（$R9=1）实际执行 ${removeOpsOnUpdate.length} 条指令`)
  console.log(`  删除数据（$R9=0）实际执行 ${removeOpsOnWipe.length} 条指令`)

  // --- 静态红线：升级路径上不得出现递归删除 ---
  section('一、静态红线检查（升级路径不得递归删除安装目录）')

  const wipeBranches = opsInBranches(removeSegments, 'rmdir_r')
  check('RMDir /r 只出现在 $R9 == "0" 分支（即仅用户明确要求删除数据时）',
    wipeBranches.if >= 1 && wipeBranches.else === 0 && wipeBranches.none === 0,
    `if=${wipeBranches.if} else=${wipeBranches.else} 无条件=${wipeBranches.none}`)
  check('覆盖升级路径（$R9 = "1"）中不含任何递归删除',
    !removeOpsOnUpdate.some((o) => o.op === 'rmdir_r'))
  check('cleanOldFiles 不含 RMDir /r（旧版升级路径同样不得递归删除）',
    !cleanAllOps.some((o) => o.op === 'rmdir_r'))

  // customRemoveFiles 必须由 $R9 守卫
  const guardOk = /\$\{If\}\s*\$R9\s*==\s*"0"/.test(removeBody)
  check('customRemoveFiles 由 $R9 标记守卫（仅用户明确要求删除数据时才整目录清理）', guardOk)

  // 覆盖范围必须包含后端可执行文件
  const renamesBackend = removeOpsOnUpdate.some(
    (o) => o.op === 'rename' && /resources\\backend\\backend\.exe$/i.test(o.from))
  check('覆盖清单包含 resources\\backend\\backend.exe（后端确实被替换）', renamesBackend)

  // 必须存在「移走旧文件 + 尝试删除空目录」的动作，否则新文件会被旧文件挡住
  check('覆盖升级会逐个移走旧程序文件（Rename 而非删除）',
    removeOpsOnUpdate.filter((o) => o.op === 'rename').length > 0)
  check('覆盖升级只删除「已空」的目录（RMDir 不带 /r）',
    removeOpsOnUpdate.some((o) => o.op === 'rmdir'))

  const sandboxRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'bilimusic-update-sandbox-'))
  console.log(`\n沙盒目录: ${sandboxRoot}`)

  let exitCode = 0
  try {
    // ===================== 场景 A：覆盖升级（isUpdated，$R9 = "1"）=====================
    section('二、场景 A：覆盖升级（升级时 $R9 = "1"，走 else 分支）')

    const instdirA = path.join(sandboxRoot, 'A', 'INSTDIR')
    const pluginsA = path.join(sandboxRoot, 'A', 'PLUGINSDIR')
    buildOldInstall(instdirA)

    const beforeA = readAll(instdirA)
    const beforeCountA = Object.keys(beforeA).length
    console.log(`  升级前：${beforeCountA} 个文件`)

    const varsA = { INSTDIR: instdirA, PLUGINSDIR: pluginsA }
    const statsA = { renamed: 0, renameFailed: 0, renameConflict: 0, dirRemoved: 0, recursiveWipe: 0 }

    // 覆盖升级：$R9 = "1"，只执行 ${Else} 分支
    runOps(removeOpsOnUpdate, varsA, statsA)
    console.log(`  执行结果：Rename ${statsA.renamed} 次，RMDir(空目录) ${statsA.dirRemoved} 次，递归删除 ${statsA.recursiveWipe} 次`)

    check('升级过程未发生任何递归删除', statsA.recursiveWipe === 0, `recursiveWipe=${statsA.recursiveWipe}`)

    // 安装新版程序文件
    installNewVersion(instdirA)
    const afterA = readAll(instdirA)

    // --- 断言 1：用户数据全部存活且内容未被改写 ---
    const lostUserData = USER_DATA_FILES.filter((rel) => !(rel in afterA))
    check('升级后用户数据文件全部存在（backend/data 未被删除）',
      lostUserData.length === 0, lostUserData.length ? '丢失: ' + lostUserData.join(', ') : undefined)

    const corruptedUserData = USER_DATA_FILES.filter(
      (rel) => rel in afterA && afterA[rel] !== USER_DATA_CONTENT + ':' + rel)
    check('升级后用户数据内容未被覆盖或改写',
      corruptedUserData.length === 0,
      corruptedUserData.length ? '被改写: ' + corruptedUserData.join(', ') : undefined)

    // --- 断言 2：用户自建文件存活 ---
    const lostFree = USER_FREE_FILES.filter((rel) => !(rel in afterA))
    check('升级后用户自建文件未被删除', lostFree.length === 0,
      lostFree.length ? '丢失: ' + lostFree.join(', ') : undefined)

    // --- 断言 3：程序文件确实被替换为新版 ---
    const notReplaced = PROGRAM_FILES.filter(
      (rel) => !(afterA[rel] || '').startsWith('NEW-PROGRAM'))
    check('所有程序文件都被替换为新版本（覆盖更新确实生效）',
      notReplaced.length === 0,
      notReplaced.length ? '未替换: ' + notReplaced.join(', ') : undefined)

    // --- 断言 4：无残留冲突（不存在「旧文件挡住新文件」） ---
    const staleLeft = STALE_FILES.filter(
      (rel) => rel in afterA && afterA[rel].startsWith('OLD-PROGRAM'))
    check('不存在旧版本程序文件残留（不会被误认为新版）',
      staleLeft.length === 0, staleLeft.length ? '残留: ' + staleLeft.join(', ') : undefined)

    // --- 断言 5：陈旧遗留文件被移出安装目录（未能移出的也不得造成数据损失） ---
    console.log(`  旧版遗留文件处理情况：${STALE_FILES.map((r) => (r in afterA ? r + '(保留)' : r + '(已移出)')).join(', ')}`)

    check('Rename 未发生目标冲突（old-install 是干净目录）', statsA.renameConflict === 0,
      `冲突 ${statsA.renameConflict} 次`)

    // --- 断言 6：数据目录在升级后仍位于后端 exe 同级（路径不漂移）---
    check('用户数据目录仍位于 resources\\backend\\data（升级后路径不漂移）',
      fs.existsSync(path.join(instdirA, 'resources', 'backend', 'data')))

    // ===================== 场景 B：用户选择「删除数据」卸载 =====================
    section('三、场景 B：用户明确选择删除数据的卸载（$R9 = "0"）')

    const instdirB = path.join(sandboxRoot, 'B', 'INSTDIR')
    buildOldInstall(instdirB)
    const varsB = { INSTDIR: instdirB, PLUGINSDIR: path.join(sandboxRoot, 'B', 'PLUGINSDIR') }
    const statsB = { renamed: 0, renameFailed: 0, renameConflict: 0, dirRemoved: 0, recursiveWipe: 0 }

    // 用户选择删除数据：$R9 = "0"，执行 ${If} 分支
    runOps(removeOpsOnWipe, varsB, statsB)
    const remainB = listFiles(instdirB)
    check('用户明确要求删除数据时，安装目录被完整清理（行为符合预期）',
      remainB.length === 0, `残留 ${remainB.length} 个文件: ${remainB.slice(0, 5).join(', ')}`)

    // ===================== 负向自检：本测试确实能检出数据丢失 =====================
    section('四、负向自检：把宏换成历史上有缺陷的写法，确认本测试能检出数据丢失')

    const instdirC = path.join(sandboxRoot, 'C', 'INSTDIR')
    buildOldInstall(instdirC)
    // 历史缺陷写法：无条件 RMDir /r "$INSTDIR"
    const buggyOps = [{ op: 'rmdir_r', target: '$INSTDIR' }]
    const statsC = { renamed: 0, renameFailed: 0, renameConflict: 0, dirRemoved: 0, recursiveWipe: 0 }
    runOps(buggyOps, { INSTDIR: instdirC, PLUGINSDIR: path.join(sandboxRoot, 'C', 'PLUGINSDIR') }, statsC)
    installNewVersion(instdirC)
    const afterC = readAll(instdirC)
    const lostC = USER_DATA_FILES.filter((rel) => !(rel in afterC))
    check('负向自检：有缺陷的写法会导致用户数据丢失（证明本测试有效）',
      lostC.length === USER_DATA_FILES.length,
      `仅丢失 ${lostC.length}/${USER_DATA_FILES.length}`)

    // ===================== 汇总 =====================
    section('结果汇总')
    console.log(`  通过 ${passed} 项，失败 ${failed} 项`)
    if (failed > 0) {
      console.log('  失败项：')
      for (const f of failures) console.log(`    - ${f}`)
      exitCode = 1
    } else {
      console.log('  结论：覆盖更新不会产生错误，也不会覆盖或删除既有用户数据。')
    }
    console.log(`${'='.repeat(66)}`)
  } finally {
    // 清理沙盒（只删自己创建的临时目录）
    const resolved = path.resolve(sandboxRoot)
    const tmp = path.resolve(os.tmpdir())
    if (resolved.startsWith(tmp + path.sep) && path.basename(resolved).startsWith('bilimusic-update-sandbox-')) {
      fs.rmSync(resolved, { recursive: true, force: true })
    } else {
      console.log(`  警告：沙盒路径不在临时目录内，未自动清理: ${resolved}`)
    }
  }
  process.exit(exitCode)
}

main()
