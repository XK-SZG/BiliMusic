@echo off
chcp 65001 >nul
echo ==========================================
echo       BiliMusic 图标一键更新脚本
echo ==========================================

set ICON_SOURCE=frontend\public\icon.png

if not exist "%ICON_SOURCE%" (
    echo [错误] 找不到源图标文件: %ICON_SOURCE%
    echo 请确保你已经将新的 1024x1024 PNG 图标放置在该路径。
    pause
    exit /b 1
)

echo.
echo [1/3] 正在生成多尺寸图标文件...
cd frontend
call npx electron-icon-builder --input=./public/icon.png --output=./public --flatten

if %errorlevel% neq 0 (
    echo [错误] 图标生成失败，请检查是否安装了 Node.js。
    pause
    exit /b %errorlevel%
)

echo.
echo [2/3] 正在同步图标到构建目录...
if not exist "icons" mkdir icons
if not exist "build" mkdir build

copy /y "public\icons\icon.ico" "icons\icon.ico" >nul
copy /y "public\icons\icon.ico" "build\icon.ico" >nul

echo.
echo [3/3] 正在尝试刷新 Windows 图标缓存...
echo (注意：如果图标没变，请尝试将生成的 exe 移动到新文件夹查看)
ie4uinit.exe -show
taskkill /IM explorer.exe /F >nul 2>&1
timeout /t 2 /nobreak >nul
start explorer.exe

echo.
echo ==========================================
echo 图标更新完成！现在可以运行 build.bat 进行打包。
echo ==========================================
pause
