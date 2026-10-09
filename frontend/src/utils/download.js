/**
 * 文件保存工具
 *
 * 应用可能运行在三种环境中：
 *   1. Electron 打包环境（file:// + nodeIntegration）—— 优先直接写入系统下载目录，
 *      避免 Chromium 对 blob URL 的静默拦截；
 *   2. Electron 开发环境（http://localhost:3000 + nodeIntegration）—— 同上；
 *   3. 纯浏览器 —— 回退到 <a download> 方式。
 */

/**
 * 保存 Blob / 文本到本地。
 * @param {Blob|string} content 内容
 * @param {string} filename 文件名
 * @param {string} mimeType content 为字符串时的 MIME 类型
 * @returns {Promise<{saved: boolean, path?: string, method: string}>}
 */
export async function saveAs(content, filename, mimeType = 'text/plain;charset=utf-8') {
  const blob = content instanceof Blob ? content : new Blob([content], { type: mimeType })

  // ---- 路径 1：Electron 直写磁盘 ----
  const fs = getElectronFs()
  if (fs) {
    try {
      const path = getElectronPath()
      const os = getElectronOs()
      const dir = path.join(os.homedir() || '.', 'Downloads')
      if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true })
      const target = path.join(dir, sanitize(filename))
      const buffer = Buffer.from(await blob.arrayBuffer())
      fs.writeFileSync(target, buffer)
      return { saved: true, path: target, method: 'electron' }
    } catch (e) {
      console.warn('[下载] 直接写盘失败，回退到浏览器下载：', e)
    }
  }

  // ---- 路径 2：浏览器下载 ----
  try {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = sanitize(filename)
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 10000)
    return { saved: true, method: 'browser' }
  } catch (e) {
    console.error('[下载] 保存失败：', e)
    return { saved: false, method: 'failed' }
  }
}

/**
 * 通过「另存为」对话框保存（Electron 环境）。
 * @returns {Promise<string|null>} 用户选择的路径，取消则返回 null
 */
export async function saveWithDialog(content, defaultFilename, mimeType = 'application/octet-stream') {
  const blob = content instanceof Blob ? content : new Blob([content], { type: mimeType })
  const fs = getElectronFs()
  const ipc = getElectronIpc()

  if (fs && ipc) {
    try {
      const target = await ipc.invoke('show-save-dialog', {
        defaultPath: sanitize(defaultFilename),
        filters: [{ name: '文件', extensions: [extensionOf(defaultFilename)] }]
      })
      if (!target) return null
      fs.writeFileSync(target, Buffer.from(await blob.arrayBuffer()))
      return target
    } catch (e) {
      console.warn('[下载] 另存为失败，回退到默认下载：', e)
    }
  }

  const result = await saveAs(blob, defaultFilename, mimeType)
  return result.saved ? (result.path || result.method) : null
}

/**
 * 复制文本到剪贴板（优先使用 Electron 剪贴板，回退到 navigator.clipboard）。
 */
export async function copyText(text) {
  const clipboard = getElectronClipboard()
  if (clipboard) {
    try {
      clipboard.writeText(text)
      return true
    } catch (e) {
      console.warn('[剪贴板] Electron 写入失败：', e)
    }
  }
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch (e) {
    console.warn('[剪贴板] navigator.clipboard 写入失败：', e)
  }
  // 最后的兜底：临时 textarea
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch (e) {
    return false
  }
}

// ---------------- 内部工具 ----------------

function sanitize(filename) {
  return String(filename || 'download.bin').replace(/[\\/:*?"<>|]/g, '_')
}

function extensionOf(filename) {
  const parts = String(filename || '').split('.')
  return parts.length > 1 ? parts.pop() : 'bin'
}

function getElectronRequire() {
  return typeof window !== 'undefined' && typeof window.require === 'function' ? window.require : null
}

function getElectronFs() {
  const req = getElectronRequire()
  if (!req) return null
  try {
    return req('fs')
  } catch (e) {
    return null
  }
}

function getElectronPath() {
  const req = getElectronRequire()
  if (!req) return null
  try {
    return req('path')
  } catch (e) {
    return null
  }
}

function getElectronOs() {
  const req = getElectronRequire()
  if (!req) return null
  try {
    return req('os')
  } catch (e) {
    return null
  }
}

function getElectronIpc() {
  const req = getElectronRequire()
  if (!req) return null
  try {
    const { ipcRenderer } = req('electron')
    return ipcRenderer && typeof ipcRenderer.invoke === 'function' ? ipcRenderer : null
  } catch (e) {
    return null
  }
}

function getElectronClipboard() {
  const req = getElectronRequire()
  if (!req) return null
  try {
    const { clipboard } = req('electron')
    return clipboard || null
  } catch (e) {
    return null
  }
}
