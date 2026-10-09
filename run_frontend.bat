@echo off
chcp 65001 >nul
echo ========================================
echo   BiliMusic 前端调试启动脚本
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
echo [信息] 正在启动前端开发服务器...
echo [提示] 服务器将在 http://127.0.0.1:3000 启动（端口由 vite.config.js 固定）
echo [提示] 请使用上面的地址访问；/api 请求会由开发服务器自动代理到后端 127.0.0.1:12180
echo [提示] 按 Ctrl+C 可停止服务器
echo.
call npm run dev
pause