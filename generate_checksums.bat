@echo off
chcp 65001 >nul
echo ==========================================
echo       BiliMusic 校验和生成脚本
echo ==========================================

set RELEASE_DIR=frontend\release
set OUTPUT_FILE=%RELEASE_DIR%\sha256.txt

if not exist %RELEASE_DIR% (
    echo [错误] 找不到目录: %RELEASE_DIR%
    echo 请先运行 build.bat 进行打包。
    pause
    exit /b 1
)

echo.
echo 正在为 %RELEASE_DIR% 中的安装包生成 SHA256...

if exist "%OUTPUT_FILE%" del "%OUTPUT_FILE%"

powershell -Command "Get-ChildItem '%RELEASE_DIR%\*.exe' | ForEach-Object { $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(); $line = $hash + '  ' + $_.Name; echo $line; $line | Out-File -Append -FilePath '%OUTPUT_FILE%' -Encoding ascii }"

echo.
echo ==========================================
echo 生成完成！校验和已保存至: %OUTPUT_FILE%
echo ==========================================
pause
