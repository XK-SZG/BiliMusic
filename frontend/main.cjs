const { app, BrowserWindow, ipcMain, shell, dialog } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const fs = require('fs')
const net = require('net')

let mainWindow
let pythonProcess = null

// 检查端口是否被占用
function checkPortInUse(port) {
  return new Promise((resolve) => {
    const server = net.createServer()
    server.once('error', (err) => {
      if (err.code === 'EADDRINUSE') {
        resolve(true)
      } else {
        resolve(false)
      }
    })
    server.once('listening', () => {
      server.close()
      resolve(false)
    })
    server.listen(port)
  })
}

// 启动 Python 后端
async function startPythonBackend() {
  const port = 12180
  const isPortInUse = await checkPortInUse(port)
  
  if (isPortInUse) {
    console.log(`Port ${port} is already in use. Assuming backend is already running.`)
    return
  }

  const isDev = !app.isPackaged
  
  let scriptPath
  if (isDev) {
    // 开发环境下，使用 python 运行 main.py
    scriptPath = path.join(__dirname, '..', 'backend', 'main.py')
    console.log('Starting Python backend in dev mode:', scriptPath)
    
    const venvPythonWin = path.join(__dirname, '..', '.venv', 'Scripts', 'python.exe')
    const venvPythonMac = path.join(__dirname, '..', '.venv', 'bin', 'python')
    let pythonCmd = 'python'
    if (fs.existsSync(venvPythonWin)) {
      pythonCmd = venvPythonWin
    } else if (fs.existsSync(venvPythonMac)) {
      pythonCmd = venvPythonMac
    }
    
    pythonProcess = spawn(pythonCmd, ['-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', port.toString()], {
      cwd: path.join(__dirname, '..')
    })
  } else {
    // 生产环境下，运行打包后的 exe
    scriptPath = path.join(process.resourcesPath, 'backend', 'backend.exe')
    console.log('Starting Python backend in prod mode:', scriptPath)
    pythonProcess = spawn(scriptPath, [port.toString()], {
      cwd: path.join(process.resourcesPath, 'backend'),
      windowsHide: true
    })
  }

  const logPath = path.join(app.getPath('userData'), 'backend.log')
  const startMsg = `\n${'='.repeat(60)}\n启动时间: ${new Date().toISOString()}\n后端路径: ${scriptPath}\n监听端口: ${port}\n开发模式: ${isDev}\n${'='.repeat(60)}\n`
  fs.appendFileSync(logPath, startMsg)
  console.log(`📝 后端日志文件: ${logPath}`)

  pythonProcess.stdout.on('data', (data) => {
    const msg = `[STDOUT] ${data}`
    console.log(msg)
    fs.appendFileSync(logPath, msg + '\n')
  })

  pythonProcess.stderr.on('data', (data) => {
    const msg = `[STDERR] ${data}`
    console.error(msg)
    fs.appendFileSync(logPath, msg + '\n')
  })

  pythonProcess.on('close', (code) => {
    const msg = `[EXIT] Python process exited with code ${code} at ${new Date().toISOString()}`
    console.log(msg)
    fs.appendFileSync(logPath, msg + '\n')
    pythonProcess = null
  })

  pythonProcess.on('error', (err) => {
    const msg = `[ERROR] Failed to start Python process: ${err.message}\nStack: ${err.stack}`
    console.error(msg)
    fs.appendFileSync(logPath, msg + '\n')
  })
  
  console.log(`✅ 后端进程已启动 (PID: ${pythonProcess.pid})`)
}

function createWindow() {
  mainWindow = new BrowserWindow({
    title: 'BiliMusic',
    width: 1200,
    height: 800,
    minWidth: 880,
    minHeight: 600,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
      webSecurity: false // 允许跨域请求和加载本地资源
    },
    autoHideMenuBar: true,
    frame: false,
    icon: path.join(__dirname, 'public', 'icons', 'icon.ico')
  })

  const isDev = !app.isPackaged

  if (isDev) {
    // 开发环境下，加载 Vite 开发服务器
    mainWindow.loadURL('http://localhost:3000')
    mainWindow.webContents.openDevTools()
  } else {
    // 生产环境下，加载打包后的 index.html
    mainWindow.loadFile(path.join(__dirname, 'dist', 'index.html'))
  }

  // 拦截新窗口打开请求，使用系统默认浏览器打开
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  // 拦截页面内的导航跳转
  mainWindow.webContents.on('will-navigate', (event, url) => {
    const isLocalUrl = url.startsWith('http://localhost') || url.startsWith('file://')
    if (!isLocalUrl) {
      event.preventDefault()
      shell.openExternal(url)
    }
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })

  let isMiniMode = false
  let preMiniBounds = null
  let preMiniMaximized = false

  // 监听最小化模式切换
  ipcMain.on('toggle-mini-mode', (event, isMini) => {
    isMiniMode = isMini
    if (isMini) {
      preMiniMaximized = mainWindow.isMaximized()
      if (preMiniMaximized) {
        mainWindow.unmaximize()
      }
      preMiniBounds = mainWindow.getBounds()
      
      if (mainWindow.isFullScreen()) {
        mainWindow.setFullScreen(false)
      }
      mainWindow.setMinimumSize(450, 80)
      mainWindow.setSize(450, 80)
      mainWindow.setAlwaysOnTop(true)
      mainWindow.setResizable(false)
      mainWindow.setMaximizable(true)
    } else {
      mainWindow.setMinimumSize(800, 600)
      mainWindow.setResizable(true)
      mainWindow.setMaximizable(true)
      mainWindow.setAlwaysOnTop(false)
      
      if (preMiniBounds) {
        mainWindow.setBounds(preMiniBounds)
      } else {
        mainWindow.setSize(1200, 800)
      }
      
      if (preMiniMaximized) {
        mainWindow.maximize()
      }
    }
  })

  mainWindow.on('maximize', () => {
    if (isMiniMode) {
      mainWindow.unmaximize()
      preMiniMaximized = true
      mainWindow.webContents.send('force-exit-mini-mode')
    } else {
      mainWindow.webContents.send('window-maximized')
    }
  })

  mainWindow.on('unmaximize', () => {
    mainWindow.webContents.send('window-unmaximized')
  })

  // 窗口控制 IPC
  ipcMain.on('window-minimize', () => {
    if (mainWindow) mainWindow.minimize()
  })
  
  ipcMain.on('window-maximize', () => {
    if (mainWindow) {
      if (mainWindow.isMaximized()) {
        mainWindow.unmaximize()
      } else {
        mainWindow.maximize()
      }
    }
  })
  
  ipcMain.on('window-close', () => {
    if (mainWindow) mainWindow.close()
  })

  ipcMain.on('uninstall-app', () => {
    const { exec } = require('child_process')
    const exeDir = path.dirname(app.getPath('exe'))
    const uninstallerPath = path.join(exeDir, 'Uninstall BiliMusic.exe')
    
    if (fs.existsSync(uninstallerPath)) {
      exec(`"${uninstallerPath}"`)
      app.quit()
    } else {
      // 尝试在 resources 同级目录找（某些打包结构）
      const altPath = path.join(exeDir, '..', 'Uninstall BiliMusic.exe')
      if (fs.existsSync(altPath)) {
        exec(`"${altPath}"`)
        app.quit()
      }
    }
  })

  ipcMain.on('create-desktop-shortcut', () => {
    const exePath = app.getPath('exe')
    const desktopPath = app.getPath('desktop')
    const shortcutPath = path.join(desktopPath, 'BiliMusic.lnk')
    shell.writeShortcutLink(shortcutPath, 'create', {
      target: exePath,
      description: 'BiliMusic - A Bilibili Music Player'
    })
  })

  ipcMain.on('force-focus-window', () => {
    if (mainWindow) {
      mainWindow.setAlwaysOnTop(true, 'screen-saver')
      mainWindow.show()
      mainWindow.focus()
    }
  })

  ipcMain.on('cancel-force-focus', () => {
    if (mainWindow) {
      // 恢复原来的 alwaysOnTop 状态（如果是 mini 模式则保持 true）
      mainWindow.setAlwaysOnTop(isMiniMode)
    }
  })

  // 在系统文件管理器中打开目录。
  // 后端（Python）在「隐藏窗口」方式启动时，os.startfile 可能返回 WinError 5（拒绝访问），
  // 交由 Electron 主进程调用 shell.openPath 更稳妥。
  ipcMain.handle('open-directory', async (event, dirPath) => {
    try {
      if (!dirPath || typeof dirPath !== 'string') {
        return { ok: false, error: '目录路径无效' }
      }
      const errorMsg = await shell.openPath(dirPath)
      if (errorMsg) {
        // openPath 返回非空字符串表示失败原因
        return { ok: false, error: errorMsg }
      }
      return { ok: true, path: dirPath }
    } catch (e) {
      return { ok: false, error: e && e.message ? e.message : String(e) }
    }
  })

  ipcMain.handle('show-save-dialog', async (event, options) => {
    const result = await dialog.showSaveDialog(mainWindow, options)
    return result.canceled ? null : result.filePath
  })
}

app.whenReady().then(async () => {
  await startPythonBackend()
  
  // 给后端一点启动时间
  setTimeout(() => {
    createWindow()
  }, 2000)

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('will-quit', () => {
  // 确保在应用退出时关闭 Python 后端进程
  if (pythonProcess) {
    console.log('Killing Python backend process...')
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', pythonProcess.pid, '/f', '/t'])
    } else {
      pythonProcess.kill('SIGTERM')
    }
  }
})
