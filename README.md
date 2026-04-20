# BiliMusic

<div align="center">

  <img src="frontend/public/icon.png" width="120" alt="BiliMusic Logo">
  <h1>BiliMusic</h1>

![Version](https://img.shields.io/badge/version-1.0.17-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![Vue](https://img.shields.io/badge/Vue-3.4-42b883)
![Python](https://img.shields.io/badge/Python-3.11-3776ab)

**一款基于 Bilibili 内容的音乐播放器**

结合现代化的前端界面和稳定的后端服务，提供流畅的 B 站音频收听体验

[快速开始](#-安装指南) · [功能介绍](#-核心功能) · [更新日志](CHANGELOG.md)

</div>

---

## 📑 目录

- [项目特色](#-项目特色)
- [核心功能](#-核心功能)
- [技术栈](#️-技术栈)
- [安装指南](#-安装指南)
- [使用说明](#-使用说明)
- [配置选项](#-配置选项)
- [构建发布](#-构建发布)
- [贡献指南](#-贡献指南)
- [常见问题](#-常见问题)
- [开源协议](#-开源协议)

---

## ✨ 项目特色

### 🎵 B 站内容集成
- 直接同步 Bilibili 收藏夹内容
- 支持在线播放和本地缓存
- 自动获取视频信息和封面

### 📚 本地媒体管理
- 导入本地音频/视频文件
- 创建和管理媒体夹
- 标签系统和评分功能

### 🎨 播放体验
- 沉浸式播放界面
- 多种可视化效果
- 支持多种播放模式（列表、随机、权重）

### 🎭 主题定制
- 内置多款精美主题
- 支持自定义背景和贴图
- 深色/浅色模式切换

### 📊 数据统计
- 播放记录统计
- 作息曲线分析
- 视频排行榜

---

## 🎯 核心功能

### B 站内容管理
- **收藏夹同步**：一键同步 B 站收藏夹到本地媒体库
- **视频导入**：支持通过 BV 号或链接添加视频
- **在线播放**：直接播放 B 站视频，无需下载
- **本地缓存**：支持下载视频到本地，离线播放

### 本地媒体库
- **文件导入**：支持导入本地音频和视频文件
- **媒体夹管理**：创建多个媒体夹分类管理内容
- **标签系统**：为视频添加自定义标签
- **评分功能**：对视频进行 1-10 分评分
- **搜索过滤**：支持标题、UP主、BV号等多种搜索方式

### 播放器功能
- **播放模式**：列表循环、随机播放、单曲循环、权重播放
- **播放队列**：灵活的队列管理和过滤功能
- **进度控制**：支持拖拽进度条和快捷键控制
- **音量调节**：支持音量淡入淡出效果
- **裁剪功能**：设置视频的播放起止时间

### 界面定制
- **主题切换**：多款内置主题可选
- **背景定制**：支持自定义背景图片
- **贴图系统**：在界面添加装饰贴图
- **可视化效果**：多种音频可视化效果
- **布局调整**：支持迷你播放器和沉浸式模式

### 高级功能
- **权重播放**：根据评分智能推荐下一首
- **播放统计**：记录播放历史和时长
- **数据分析**：生成播放作息曲线
- **数据备份**：导出/导入媒体库数据
- **剪贴板监听**：自动检测复制的 BV 号

---

## 🛠️ 技术栈

### 前端技术
- **框架**：Vue 3 - 渐进式 JavaScript 框架
- **构建工具**：Vite - 快速的前端构建工具
- **状态管理**：Pinia - Vue 3 官方推荐的状态管理库
- **路由**：Vue Router - 官方路由管理器
- **UI 框架**：Tailwind CSS - 实用优先的 CSS 框架
- **图标**：Heroicons - 精美的 SVG 图标库
- **图表**：ECharts - 数据可视化图表库
- **桌面端**：Electron - 跨平台桌面应用框架

### 后端技术
- **框架**：FastAPI - 现代化的 Python Web 框架
- **数据库**：SQLite - 轻量级关系型数据库
- **ORM**：SQLAlchemy - Python SQL 工具包
- **视频处理**：yt-dlp - 视频下载工具
- **网络请求**：requests / httpx - HTTP 客户端库

### 开发工具
- **包管理**：npm (前端) / pip (后端)
- **打包工具**：Electron Builder / PyInstaller
- **代码规范**：ESLint / Prettier

---

## 📦 安装指南

### 用户安装

#### 系统要求
- **操作系统**：Windows 10/11 (64 位)
- **内存**：建议 4GB 以上
- **磁盘空间**：至少 500MB 可用空间

#### 安装步骤
1. 从 [Releases](https://github.com/XK-SZG/BiliMusic/releases) 页面下载最新版本的安装包
2. 运行安装程序，按照提示完成安装
3. 首次启动时需要扫码登录 Bilibili 账号（可选）

### 开发环境搭建

#### 环境要求
- **Node.js**：v18 或更高版本
- **Python**：3.8 - 3.11 (推荐 3.11)
- **Git**：用于克隆仓库

#### 安装步骤

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
   
   # 运行后端服务
   python run_backend.py
   ```
   后端服务将在 `http://127.0.0.1:12243` 启动

3. **前端设置**
   ```bash
   cd frontend
   
   # 安装依赖
   npm install
   
   # 启动开发环境
   npm run electron:dev
   ```

---

## 📖 使用说明

### 快速开始

1. **登录 B 站账号**（可选）
   - 扫描二维码登录
   - 登录后可同步收藏夹

2. **添加视频**
   - **从 B 站**：点击"添加 B 站视频"，输入 BV 号或链接
   - **从本地**：点击"导入本地资源"，选择音频/视频文件

3. **创建媒体夹**
   - 在左侧媒体库区域点击 "+" 按钮
   - 输入媒体夹名称
   - 将视频添加到媒体夹

4. **开始播放**
   - 点击视频卡片上的播放按钮
   - 或右键选择"播放"/"添加到队列"

### 常用快捷键

| 快捷键 | 功能 |
|--------|------|
| `Space` | 播放/暂停 |
| `[` | 上一首 |
| `]` | 下一首 |
| `↑` | 音量增加 |
| `↓` | 音量减少 |
| `→` | 快进 5 秒 |
| `←` | 快退 5 秒 |
| `M` | 静音/取消静音 |
| `F` | 全屏 |
| `I` | 沉浸式模式 |
| `Enter` | 切换 UI 显示 |
| `T` | 切换主题 |

### 播放模式说明

- **列表循环**：按顺序播放，播放完最后一首后回到第一首
- **列表播放**：按顺序播放，播放完最后一首后停止
- **随机播放**：随机选择下一首播放
- **单曲循环**：重复播放当前歌曲
- **权重播放**：根据评分概率选择下一首（评分越高概率越大）

---

## 🔧 配置选项

### 播放设置
- **在线播放质量**：选择在线播放时的视频质量（360P - 1080P）
- **缓存下载质量**：选择下载缓存时的视频质量（720P - 4K）
- **默认音量**：设置启动时的默认音量
- **音量淡入淡出**：播放开始/结束时的音量渐变效果

### 界面设置
- **启动页面**：选择应用启动时显示的页面
- **UI 过渡动画**：界面切换时的动画效果
- **空闲超时**：无操作后自动隐藏 UI 的时间

### 主题设置
- **主题选择**：选择预设主题或自定义主题
- **背景效果**：选择背景动画效果（浮动、波纹、旋转等）
- **可视化样式**：选择音频可视化效果
- **背景模糊度**：调整背景模糊程度
- **背景不透明度**：调整背景透明度

### 高级设置
- **剪贴板监听**：自动检测复制的 BV 号
- **权重灵敏度**：调整权重播放的评分影响程度
- **时长控制**：限制播放队列的总时长或歌曲数量
- **自动关机**：播放完成后自动关闭系统

---

## 🚀 构建发布

### 开发构建

```bash
# 前端开发构建
cd frontend
npm run build

# 后端开发运行
python run_backend.py
```

### 生产构建

运行根目录下的 `build.bat` 脚本进行自动化构建：

```bash
build.bat
```

构建脚本会自动完成以下步骤：
1. 使用 PyInstaller 打包后端为独立可执行文件
2. 使用 Vite 构建前端生产版本
3. 使用 Electron Builder 打包桌面应用
4. 生成 Windows 安装程序

构建产物位于：
- 后端：`dist/backend/backend.exe`
- 前端：`frontend/dist/`
- 安装包：`frontend/release/`

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request 来帮助改进本项目！

### 提交 Issue
- 使用清晰的标题描述问题
- 提供详细的复现步骤
- 附上相关的截图或日志

### 提交 Pull Request
1. Fork 本仓库
2. 创建你的特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交你的更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启一个 Pull Request

### 代码规范
- 前端代码遵循 ESLint 规范
- 后端代码遵循 PEP 8 规范
- 提交信息使用清晰的中文描述

---

## ❓ 常见问题

### 安装问题

**Q: 安装时提示缺少依赖？**  
A: 确保已安装 Python 3.8+ 和 Node.js 18+，并正确配置环境变量。

**Q: 后端服务启动失败？**  
A: 检查 12243 端口是否被占用，可以在 `config.yaml` 中修改端口。

### 使用问题

**Q: 无法登录 B 站账号？**  
A: 确保网络连接正常，使用 Bilibili 手机 APP 扫描二维码登录。

**Q: 视频播放卡顿？**  
A: 可以尝试降低播放质量，或下载到本地后播放。

**Q: 下载的视频在哪里？**  
A: 默认保存在 `backend/data/downloads/` 目录下。

### 技术问题

**Q: 如何清除缓存数据？**  
A: 在设置页面选择"重置软件"，或手动删除 `backend/data/` 目录。

**Q: 支持哪些视频格式？**  
A: 支持常见的音视频格式，包括 MP4、MP3、M4A、FLAC 等。

**Q: 如何备份数据？**  
A: 在设置页面使用"导出媒体库"功能，可以导出所有数据和缓存文件。

---

## 📄 开源协议

本项目采用 [MIT License](LICENSE) 开源协议。

### 第三方依赖
- Vue.js - MIT License
- FastAPI - MIT License
- Electron - MIT License
- Tailwind CSS - MIT License
- 其他依赖详见 `package.json` 和 `requirements.txt`

---

## 🙏 致谢

### 开发工具
- 本项目使用 Gemini、Claude 等 LLM 模型辅助开发

### 开源项目
感谢以下开源项目的支持：
- [Vue.js](https://vuejs.org/) - 渐进式 JavaScript 框架
- [FastAPI](https://fastapi.tiangolo.com/) - 现代化 Python Web 框架
- [Electron](https://www.electronjs.org/) - 跨平台桌面应用框架
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - 视频下载工具
- [Tailwind CSS](https://tailwindcss.com/) - CSS 框架

### 特别感谢
- 感谢所有提交 Issue 和 PR 的贡献者
- 感谢 Bilibili 提供的优质内容平台

---

<div align="center">

**如果这个项目对你有帮助，欢迎 Star ⭐**

Made with ❤️ by [XK](https://github.com/XK-SZG)

</div>