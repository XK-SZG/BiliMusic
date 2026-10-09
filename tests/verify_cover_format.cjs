// 前端 formatImg / normalizePic 行为验证（复刻 stores/modules/player.js 的实现）
//
// 复现 v1.0.22 修复的封面双重代理缺陷：
//   .png 开发环境下 API_BASE 由绝对地址改为同源相对路径 '/api'，
//   formatImg 旧实现会把 '/api/proxy/image?url=...' 当作协议相对地址拼成
//   'https:///api/proxy/image?url=...'（三斜杠、无主机名）。
//
// 用法（项目根目录）：node tests/verify_cover_format.cjs

const API_BASE = '/api' // 开发环境（vite 代理）下的取值
const ORIGIN = 'http://127.0.0.1:3000'

// ===== 与 player.js 中保持一致的实现 =====
function formatImg(url, size = null) {
  if (!url) return ''
  let raw = String(url)

  if (raw.startsWith('/') && !raw.startsWith('//')) return raw

  if (raw.startsWith('/local_covers/') || raw.startsWith('/local_stickers/')) {
    return `${API_BASE.replace('/api', '')}${raw}`
  }

  let cleanUrl = raw.replace(/^https?:/, '')
  let result = cleanUrl.startsWith('//') ? `https:${cleanUrl}` : `https://${cleanUrl}`

  let guard = 0
  while (result.includes('/proxy/image?url=') && guard++ < 5) {
    try {
      const parsed = new URL(result, ORIGIN)
      const inner = parsed.searchParams.get('url')
      if (!inner) break
      result = decodeURIComponent(inner)
    } catch (e) {
      break
    }
  }

  if (result.startsWith('/') && !result.startsWith('//')) return result

  if (result.includes('hdslb.com') || result.includes('biliimg.com')) {
    const queryIndex = result.indexOf('?')
    const baseUrl = (queryIndex >= 0 ? result.slice(0, queryIndex) : result).split('@')[0]
    const targetSize = size || '640w_360h_1c_1s.webp'
    const processedUrl = `${baseUrl}@${targetSize}`
    return `${API_BASE}/proxy/image?url=${encodeURIComponent(processedUrl)}`
  }

  return result
}

function normalizePic(url) {
  if (!url) return ''
  let raw = String(url)

  let guard = 0
  while (raw.includes('/proxy/image?url=') && guard++ < 5) {
    try {
      const parsed = new URL(raw, ORIGIN)
      const inner = parsed.searchParams.get('url')
      if (!inner) break
      raw = decodeURIComponent(inner)
    } catch (e) {
      break
    }
  }

  if (/^https?:\/{0,2}(\/|$)/.test(raw) && !/^https?:\/\/[\w.-]+/i.test(raw)) return ''
  if (raw.startsWith('/proxy/image') || raw.startsWith('/api/proxy/image')) return ''

  return raw
}

// ===== 断言工具 =====
const PASSED = []
const FAILED = []
function check(name, cond, detail = '') {
  if (cond) { PASSED.push(name); console.log(`  [PASS] ${name}${detail ? ' -> ' + detail : ''}`) }
  else { FAILED.push(`${name} | ${detail}`); console.log(`  [FAIL] ${name}${detail ? ' -> ' + detail : ''}`) }
}

const BILI = 'https://i0.hdslb.com/bfs/archive/cead6822bd20099ac651ecef9c1d478b1a9c675e.jpg'
const SIZE = '640w_360h_1c_1s.webp'
const BILI_SIZED = `${BILI}@${SIZE}`

console.log()
console.log('='.repeat(66))
console.log('  前端封面地址处理（formatImg / normalizePic）')
console.log('='.repeat(66))

// ---------- 1. 正常情况下应产出单层代理路径 ----------
const normal = formatImg(BILI)
check('原始 B 站直链 → 单层代理相对路径',
  normal === `/api/proxy/image?url=${encodeURIComponent(BILI_SIZED)}`, normal)
check('产出的是同源相对路径（不以 https: 开头）', normal.startsWith('/api/'), normal.slice(0, 40))

// ---------- 2. 【核心回归】数据库里的脏值必须能被正确修复 ----------
const dirtyStored = `/api/proxy/image?url=${encodeURIComponent(BILI_SIZED)}`
const fixed = formatImg(dirtyStored)
check('脏数据(存了单层代理)不再产生 https:/// 畸形地址',
  !fixed.startsWith('https:///'), fixed.slice(0, 60))
check('脏数据被还原为单层正确代理路径',
  fixed === `/api/proxy/image?url=${encodeURIComponent(BILI_SIZED)}`, fixed)

// 完全复刻日志中的双重代理坏地址
const doubleBroken = `https:///api/proxy/image?url=${encodeURIComponent(
  `https:///api/proxy/image?url=${encodeURIComponent(BILI_SIZED)}`)}`
const fixedDouble = formatImg(doubleBroken)
// 断言方式：把最终结果解码后统计代理路径出现的次数。
// 正确结果应当只有「外层一次」代理，内层必须已还原成 hdslb 直链。
const decodedFinal = decodeURIComponent(fixedDouble)
const proxyOccurrences = (decodedFinal.match(/proxy\/image/g) || []).length
check('日志中的双重代理坏地址被修复（只剩一层代理）',
  fixedDouble.startsWith('/api/proxy/image?url=') && proxyOccurrences === 1,
  `proxy/image 出现 ${proxyOccurrences} 次`)
check('日志坏地址还原出的是 hdslb 直链',
  decodedFinal.includes('i0.hdslb.com/bfs/archive/'), decodedFinal.slice(0, 90))
check('日志坏地址不再含三斜杠畸形前缀',
  !decodedFinal.includes('https:///'), decodedFinal.slice(0, 60))

// ---------- 3. 本地路径 ----------
check('本地封面相对路径原样保留',
  formatImg('/local_covers/BV1xx_cover.jpg') === '/local_covers/BV1xx_cover.jpg',
  formatImg('/local_covers/BV1xx_cover.jpg'))
check('本地贴纸相对路径原样保留',
  formatImg('/local_stickers/s1.png') === '/local_stickers/s1.png')
check('协议相对地址仍按 https 处理',
  formatImg('//i0.hdslb.com/bfs/archive/x.jpg').startsWith('/api/proxy/image?url=https'),
  formatImg('//i0.hdslb.com/bfs/archive/x.jpg').slice(0, 50))

// ---------- 4. 尺寸后缀处理 ----------
const withQuery = `${BILI}?v=1`
check('带查询串的地址不会截错位置',
  formatImg(withQuery).includes(encodeURIComponent(`${BILI}@${SIZE}`)),
  decodeURIComponent(formatImg(withQuery).split('url=')[1] || ''))

// ---------- 5. normalizePic：写库地址绝不带代理包装 ----------
check('normalizePic 从脏数据还原出原始直链', normalizePic(dirtyStored) === BILI_SIZED,
  normalizePic(dirtyStored))
check('normalizePic 产出不含 /proxy/image', !normalizePic(dirtyStored).includes('/proxy/image'))
check('normalizePic 对畸形地址返回空串（避免写入脏数据）',
  normalizePic('https:///api/proxy/image?url=') === '',
  JSON.stringify(normalizePic('https:///api/proxy/image?url=')))
check('normalizePic 保留本地相对路径',
  normalizePic('/local_covers/a.jpg') === '/local_covers/a.jpg')
check('normalizePic 保留原始 B 站直链', normalizePic(BILI_SIZED) === BILI_SIZED)
check('normalizePic 与 formatImg 组合后仍是单层代理',
  formatImg(normalizePic(dirtyStored)) === `/api/proxy/image?url=${encodeURIComponent(BILI_SIZED)}`,
  formatImg(normalizePic(dirtyStored)))

// ---------- 6. 【关键不变量】formatImg 结果写库再读出来仍可用 ----------
// 这是缺陷的根因路径：展示地址被写库 → 下次读出来又被当作协议相对地址
const roundTrip = formatImg(formatImg(BILI))
check('formatImg 二次处理不会叠加代理层（幂等性）',
  (roundTrip.match(/proxy\/image/g) || []).length === 1,
  `proxy/image 出现 ${(roundTrip.match(/proxy\/image/g) || []).length} 次`)

console.log()
console.log('='.repeat(66))
console.log(`  通过 ${PASSED.length} 项，失败 ${FAILED.length} 项`)
if (FAILED.length) FAILED.forEach((f) => console.log(`   - ${f}`))
console.log('='.repeat(66))
process.exit(FAILED.length ? 1 : 0)
