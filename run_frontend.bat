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
echo [提示] 服务器将在 http://localhost:5173 启动
echo [提示] 按 Ctrl+C 可停止服务器
echo.
call npm run dev
pause