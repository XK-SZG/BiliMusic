@echo off
chcp 65001 >nul
echo ==========================================
echo       BiliMusic 打包构建脚本
echo ==========================================

echo.
echo [1/3] 正在打包 Python 后端 (PyInstaller)...
call .venv\Scripts\activate
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --name backend --distpath dist/backend --add-data "backend/data;data" --add-data "config.yaml;." --hidden-import uvicorn --hidden-import fastapi --hidden-import starlette --hidden-import pydantic --hidden-import sqlalchemy --hidden-import sqlite3 --hidden-import mutagen --hidden-import pyperclip --exclude-module matplotlib --exclude-module numpy --exclude-module tkinter --exclude-module PyQt5 --exclude-module PySide6 --exclude-module IPython --exclude-module jupyter --exclude-module scipy --exclude-module pandas run_backend.py
if %errorlevel% neq 0 (
    echo 后端打包失败�?
    pause
    exit /b %errorlevel%
)

echo.
echo [2/3] 正在安装前端依赖...
cd frontend
call npm install
if %errorlevel% neq 0 (
    echo 前端依赖安装失败�?
    pause
    exit /b %errorlevel%
)

echo.
echo [3/3] 正在打包 Electron 应用...
call npm run electron:build
if %errorlevel% neq 0 (
    echo Electron 打包失败�?
    pause
    exit /b %errorlevel%
)

echo.
echo ==========================================
echo 构建完成！安装包位于 frontend
elease 目录下�?
echo ==========================================
pause
