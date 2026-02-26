# BiliMusic

BiliMusic 是一款基于 Bilibili 内容的音乐播放器，结合了强大的后端处理能力和现代化的前端界面，旨在提供流畅的 B 站音频收听体验。

## 🤖 LLM编程

- 全程借助 Gemini 3 系列 LLM 模型进行氛围编程开发。

## 🚀 功能特性

- **B 站集成**：直接访问和播放 Bilibili 的音频内容。
- **本地库管理**：支持管理本地音乐文件。
- **沉浸式播放器**：精美的前端界面，支持可视化效果。
- **主题定制**：内置多种主题，支持自定义皮肤。
- **跨平台支持**：基于 Electron 构建，支持 Windows 等平台。
- **后端驱动**：使用 Python FastAPI 提供高效的 API 服务。

## 🛠️ 技术栈

- **前端**：Vue 3, Vite, Pinia, Tailwind CSS, Electron
- **后端**：Python, FastAPI, SQLite
- **打包**：PyInstaller (后端), Electron-builder (前端)

## 📦 安装与运行

### 环境要求

- Node.js (建议 v18+)
- Python 3.8+ (建议 3.11)

### 快速开始

1. **克隆仓库**
   ```bash
   git clone https://github.com/XK-SZG/BiliMusic.git
   cd BiliMusic
   ```

2. **后端设置**
   ```bash
   # 创建虚拟环境
   python -m venv .venv
   # 激活虚拟环境 (Windows)
   .venv\Scripts\activate
   # 安装依赖
   pip install -r requirements.txt
   # 运行后端
   python run_backend.py
   ```

3. **前端设置**
   ```bash
   cd frontend
   # 安装依赖
   npm install
   # 启动开发环境
   npm run electron:dev
   ```

## 🔨 构建发布

运行根目录下的 `build.bat` 脚本进行自动化构建。

## 📄 开源协议

本项目采用 [MIT License](LICENSE) 开源协议。

## 🤝 贡献

欢迎提交 Issue 或 Pull Request 来帮助改进本项目！
