@echo off
chcp 65001 >nul
echo ========================================
echo   BiliMusic Electron 客户端调试启动
echo ========================================
echo.
cd /d "%~dp0frontend"
if not exist "node_modules" (
    echo [信息] 检测到未安装依赖，正在安装...
    call npm install
    if errorlevel 1 (
        echo [错误] 依赖安装失败！
        pause
        exit /b 1
    )
    echo.
)
echo [信息] 正在启动 Electron 开发环境...
echo [提示] 将同时启动 Vite 开发服务器和 Electron 窗口
echo [提示] 按 Ctrl+C 可停止所有进程
echo.
call npm run electron:dev
pause