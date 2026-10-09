# AGENTS.md

本文件面向 AI 编码助手（LLM Agent），描述 BiliMusic 项目的真实结构、既有约定与不可触碰的红线。

**文档语言**：本项目全部既有文档（`README.md`、`CHANGELOG.md`、`docs/*.md`、`tests/README.md`）均为中文，代码注释与 docstring 亦为中文，因此本文件使用中文。

**阅读须知**：本文档所有路径、命令、约定均来自仓库中实际存在的文件。凡是仓库中无法找到依据的信息，一律标注「(待补充：…)」，请勿据本文档臆造未列出的命令或路径。

**关于「找不到文件」的环境陷阱**（踩过，请注意）：

1. **`.git/` 会被文件枚举工具跳过**。仓库**是**真实的 Git 仓库（`.git/` 为隐藏目录），但 glob / ripgrep 类工具默认不返回 `.git/` 下的任何内容，直接按绝对路径读取才能访问。不要因为搜索不到就断言仓库未初始化。
2. **括号展开模式（如 `*.{md,yaml}`）会静默漏掉根目录文件**，请改用单一扩展名的 glob 模式（如 `*.bat`），或用 `pwsh` 的 `Get-ChildItem -Force`。

**关于 `git` 与 `pwsh` 的可用性（已更新，勿再引用旧结论）**：

早期版本的本文档称「本机 `pwsh` 与 `git` 命令在当前沙箱中无法启动（`[exit code: 3221225794]`）」。
该结论**已不成立**：在 `danger-full-access` 文件策略下，`pwsh` 与
`C:\Program Files\Git\cmd\git.exe`（git 2.47.0.windows.2）均可正常执行，实测
`git status`、`git log`、`git check-ignore`、`git add`、`git commit` 均成功。

因此本文件第四章的仓库事实**可以直接用 git 命令复核**：

```powershell
& 'C:\Program Files\Git\cmd\git.exe' status --porcelain=v1 -uall
& 'C:\Program Files\Git\cmd\git.exe' log --oneline -5
```

仍然成立的注意事项：`git` 可能不在当前会话的 PATH 中（`Get-Command git` 可能无输出），
此时请使用上方的**绝对路径**调用。

---

## 一、项目说明

### 1.1 项目用途

BiliMusic 是一款基于 Bilibili 内容的 Windows 桌面音乐播放器（依据 `README.md` 第 14-16 行、`frontend/package.json` 第 5 行 `"description": "BiliMusic - A Bilibili Music Player"`）。

核心能力（依据 `README.md`「核心功能」章节）：

- B 站收藏夹同步、扫码登录、在线播放与本地缓存下载
- 本地媒体库导入、媒体夹分类、标签与评分
- 播放队列与多种播放模式（列表、随机、单曲、权重播放）
- 主题定制、背景、贴纸、音频可视化、迷你播放器与沉浸式模式
- 数据统计：播放记录、作息曲线、排行榜
- 剪贴板监听：自动识别复制的 BV 号

### 1.2 技术栈

| 层 | 技术 | 依据 |
|---|---|---|
| 后端 | Python 3.11 + FastAPI + SQLAlchemy + SQLite | `README.md` 第 118-124、150 行；`backend/main.py`；`backend/database/db.py` |
| 前端 | Vue 3 + Vite + Vue Router + Pinia + Tailwind CSS | `frontend/package.json` 第 16-38 行 |
| 桌面壳 | Electron + Electron Builder | `frontend/package.json` 第 32-33、39-75 行；`frontend/main.cjs` |
| 下载 | yt-dlp | `backend/services/download_service.py` 第 4 行；`requirements.txt` 第 10 行 |
| 打包 | PyInstaller（后端）+ Electron Builder / NSIS（前端） | `build.bat` 第 11 行；`frontend/package.json` 第 63-74 行 |
| 包管理 | pip（后端，`requirements.txt`）/ npm（前端，`package-lock.json`） | `requirements.txt`；`frontend/package-lock.json` |

### 1.3 目录职责

```
BiliMusic/
├── .git/                      # Git 仓库（隐藏目录，仅 main 分支，跟踪 origin/main；详见第四章）
├── .gitignore                 # 忽略 backend/data/、config.yaml、dist/、*.spec、.venv/ 等
├── README.md                  # 项目主文档（中文）
├── CHANGELOG.md               # 更新日志，Keep-a-Changelog 风格
├── LICENSE                    # MIT，Copyright (c) 2024 XK-SZG
├── AGENTS.md                  # 本文件
├── requirements.txt           # 后端 Python 依赖清单
├── config.yaml                # 后端运行时配置（已被 .gitignore 忽略）
├── run_backend.py             # 后端启动入口（含崩溃诊断日志、配置文件查找）
├── backend.spec               # PyInstaller 规格文件（已被 .gitignore 忽略）
├── build.bat                  # 一键生产构建：后端 exe → 前端 → 安装包
├── run_frontend.bat           # 前端开发服务器启动脚本
├── update_icon.bat            # 图标多尺寸生成与缓存刷新
├── generate_checksums.bat     # 为 frontend/release/*.exe 生成 sha256.txt
├── backend/                   # 后端 Python 包（含 __init__.py）
│   ├── main.py                # FastAPI 应用装配：lifespan、CORS、静态目录、路由注册（10 个路由）
│   ├── dependencies.py        # 全局单例（BiliManager / Downloader / PlaybackManager）
│   ├── migrate_db.py          # 轻量 SQLite 迁移（PRAGMA table_info + ALTER TABLE）
│   ├── core/                  # 基础设施：config / paths / log_manager / error_manager /
│   │                          #          debug_service / bili_manager / async_metrics
│   ├── database/              # models.py（ORM 模型）、db.py（engine、连接池、get_db）
│   ├── routers/               # HTTP 路由层，按业务域拆分（auth/bili/local/play/system/theme/stats/download/logs/debug）
│   ├── services/              # 业务逻辑层（下载、清理、剪贴板、主题、封面缓存、备份、同步…）
│   └── data/                  # 运行时数据（默认贴纸/粒子资源、SQLite 库；已 gitignore）
│       ├── logs/              # 物理日志目录（三级轮转回收，已 gitignore）
│       ├── failed_downloads/  # 下载失败残留隔离区（已 gitignore）
│       └── debug_consent.json # 调试协议确认记录（已 gitignore）
├── frontend/                  # Electron + Vue 3 前端
│   ├── main.cjs               # Electron 主进程：拉起 Python 后端、窗口与 IPC
│   ├── start-electron.cjs     # 开发模式下启动 Electron
│   ├── vite.config.js         # Vite 配置（端口 3000、/api 代理到后端、__APP_VERSION__ 注入）
│   ├── tailwind.config.cjs    # Tailwind 配置（darkMode: 'class'、primary 色板变量）
│   ├── postcss.config.cjs     # PostCSS 配置
│   ├── installer.nsh          # NSIS 自定义安装脚本
│   ├── build/                 # 打包资源：afterPack.cjs、uninstall_list.nsh、icon.ico
│   ├── public/                # 静态资源（图标等）
│   ├── src/
│   │   ├── main.js            # 应用入口：Pinia、Router、v-click-outside 指令
│   │   ├── App.vue            # 根组件（订阅 SSE，含错误系统弹窗）
│   │   ├── router.js          # 路由表（hash 模式，6 个页面）
│   │   ├── style.css          # 全局样式（Tailwind 入口）
│   │   ├── api/               # 后端接口封装（request.js 导出唯一 API_BASE；logs.js 含 SSE）
│   │   ├── stores/            # Pinia：modules/ 下为领域 store，playerStore.js 为聚合入口
│   │   ├── views/             # 页面级组件（Home / BiliLibrary / LocalLibrary / PlayQueue / Statistics / Settings）
│   │   ├── components/        # 复用组件（PlayerBar、Sidebar、UniversalModal、ErrorDialog…）
│   │   ├── hooks/             # 组合式函数（useShortcuts.js）
│   │   ├── utils/             # 工具（db.js、theme.js、weightedPlayEngine.js、download.js）
│   │   └── assets/            # 图标与内联数据
│   └── release/               # 打包产物（已 gitignore）
├── docs/                      # 中文文档：用户协议与隐私政策、配置说明、日志与错误系统、调试系统说明书
├── tests/                     # 自检与静态校验脚本（无测试框架，见 2.5）
└── dist/                      # 后端打包产物 dist/backend/backend.exe（已 gitignore）
```

### 1.4 关键入口

| 入口 | 路径 | 说明 |
|---|---|---|
| 后端启动 | `run_backend.py` | 生产/开发统一入口：初始化崩溃日志 → 导入 `backend.main:app` → 查找 `config.yaml` → 启动 uvicorn |
| 后端应用 | `backend/main.py` | `app = FastAPI(title="BiliMusic API", lifespan=lifespan)`，注册 10 个路由与静态挂载 |
| 后端工具入口 | `backend/main.py` 的 `if __name__ == "__main__"` | 直接 `python -m backend.main` 时以 `server_config` 的 host/port 启动 uvicorn |
| 全局单例 | `backend/dependencies.py` | `bili` / `downloader` / `playback` 三个进程级单例 |
| 桌面主进程 | `frontend/main.cjs` | 检测 12180 端口 → 拉起 Python 后端 → 创建 BrowserWindow → 处理 IPC |
| 前端入口 | `frontend/src/main.js` | 创建 Vue 应用、注册 Pinia/Router/全局指令 |
| 路由表 | `frontend/src/router.js` | `/`、`/bili`、`/local`、`/queue`、`/statistics`、`/settings` |
| HTTP 客户端 | `frontend/src/api/request.js` | axios 实例，响应拦截器直接返回 `response.data`；**唯一** `API_BASE` 来源 |
| 日志系统 | `backend/core/log_manager.py` | 内存环形缓冲 + 物理文件轮转 + 三级回收 + 心跳分类 |
| 错误系统 | `backend/core/error_manager.py` | 错误目录、分类、一键修复注册、诊断包生成 |
| 调试系统 | `backend/core/debug_service.py` | 协议闸门、调试会话、令牌、受限执行沙箱、审计 |

### 1.5 运行与构建命令

**环境要求**（`README.md` 第 148-151 行）：Node.js ≥ 18、Python 3.8–3.11（推荐 3.11）。

后端（在项目根目录执行）：

```bash
# 创建并激活虚拟环境（Windows）
python -m venv .venv
.venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 启动后端服务（默认 http://127.0.0.1:12180）
python run_backend.py
```

前端（在 `frontend/` 目录执行，依据 `frontend/package.json` 第 9-15 行）：

```bash
npm install

npm run dev            # 仅启动 Vite 开发服务器（vite.config.js 指定端口 3000）
npm run build          # Vite 生产构建，输出 frontend/dist/
npm run electron:dev   # 并行启动 Vite + Electron（wait-on 等待 http://localhost:3000）
npm run electron:build # npm run build && electron-builder，输出 frontend/release/
```

一键生产构建（项目根目录，依据 `build.bat`）：

```bat
build.bat
```

`build.bat` 依次执行：PyInstaller 打包后端为 `dist/backend/backend.exe` → `cd frontend && npm install` → `npm run electron:build`。

其他脚本：

```bat
run_frontend.bat        :: 启动前端开发服务器（提示 http://127.0.0.1:3000）
update_icon.bat         :: 由 frontend/public/icon.png 生成多尺寸图标并刷新 Windows 图标缓存
generate_checksums.bat  :: 为 frontend/release/*.exe 生成 SHA256 到 frontend/release/sha256.txt
```

**项目自检脚本**（无需测试框架，见 2.5）：

```powershell
# 后端自检（进程内 TestClient + 临时 uvicorn 验证 SSE），148 项断言
.venv\Scripts\python.exe tests\verify_backend_v1021.py

# 前端 ↔ 后端接线静态校验（API 方法是否存在、令牌是否携带）
node tests\check_api_wiring.cjs
node tests\check_api_wiring_selftest.cjs   # 校验脚本自身的负向自检

# 封面地址相关（v1.0.23 新增）
.venv\Scripts\python.exe tests\verify_cover_url.py
.venv\Scripts\python.exe tests\verify_proxy_image.py
node tests\verify_cover_format.cjs

# 发行包「覆盖更新」数据安全沙盒验证（v1.0.24 新增）
node tests\verify_update_overwrite.cjs
```

**改动前后都应跑一遍**：本项目没有 CI，上述脚本是**唯一**的自动化门禁。

> 端口说明：后端默认端口为 `12180`（`config.yaml`、`backend/core/config.py` 第 39 行、`frontend/main.cjs` 第 31 行一致）；`frontend/vite.config.js` 第 21 行将开发服务器端口固定为 `3000` 且 `strictPort: true`。`run_frontend.bat` 的提示文案已与 `vite.config.js` 对齐（历史版本误写为 `5173`）。

### 1.6 前后端通信约定

- 后端路由统一挂载在 `/api` 前缀下，共 **10 个路由模块**（依据 `backend/main.py` 第 200-210 行的注册顺序与各 `APIRouter(prefix=...)`）：

  | 模块 | 前缀 | 备注 |
  |---|---|---|
  | `auth` | `/api/auth` | 扫码登录、登录状态 |
  | `bili` | `/api/bili` | 收藏夹、视频信息 |
  | `local` | 无前缀 | 装饰器内完整书写 `/api/local/...` |
  | `play` | `/api/play` | 播放、流媒体代理 |
  | `system` | `/api/system` | 系统设置、字体/贴画/背景、**错误系统**、SSE 事件总线 |
  | `theme` | `/api/themes` | 主题 |
  | `stats` | `/api/stats` | 统计 |
  | `download` | `/api/download` | 下载队列（含 `/retry/{bvid}` 手动重试） |
  | `logs` | `/api/logs` | **日志系统**：查询/筛选/导出/SSE/物理文件/保留策略 |
  | `debug` | `/api/debug` | **调试系统**：协议闸门、令牌、远程调试（详见 2.6） |

- 另有 `GET /api/proxy/image` 用于代理 B 站图片以绕过防盗链。
- 静态目录挂载（`backend/main.py`）：`/local_covers`、`/local_stickers`、`/local_backgrounds`、`/downloads`。
- **`API_BASE` 唯一来源**：`frontend/src/api/request.js` 导出的 `API_BASE`（第 8-25 行的 `resolveApiBase()`）。解析顺序：
  1. `import.meta.env.VITE_API_URL`（若设置）
  2. 本地 http 且端口非 `12180`（即开发服务器）→ **同源相对路径 `/api`**，由 `vite.config.js` 的 proxy 转发到后端
  3. Electron 打包环境（`file:` 协议）→ `http://127.0.0.1:12180/api`
  4. 其它情况 → `${window.location.origin}/api`

  **不要**再在其它文件里重复这段表达式（历史上曾在 `request.js`、`system.js`、`stores/modules/player.js` 三处重复，改漏一处即导致请求发往错误地址）。需要时 `import { API_BASE } from './request'`。SSE（`EventSource`）不走 axios，因此 `api/logs.js` 与 `api/system.js` 复用同一个 `API_BASE`。
- 后端错误以 `HTTPException(status_code=..., detail=...)` 返回，前端在 `request.js` 响应拦截器中读取 `error.response.data.detail` 作为提示文案。

### 1.7 实时事件（SSE）

两个 SSE 端点，均为**增量拉取**模型（服务端按自增序号推送，断开重连不丢日志）：

| 端点 | 事件 | 用途 |
|---|---|---|
| `/api/logs/stream` | `ready`、`log` | 日志面板实时输出；支持 `hide_heartbeat` / `hide_heartbeat_categories` / `levels` / `keyword` / `exclude` 服务端筛选 |
| `/api/system/events` | `clipboard_pending`、`download_status`、`error`、`error_resolved` | 全局事件总线；`error` 是**错误弹窗的数据源**，连接时会补发当前未处理的错误 |

前端订阅入口：`frontend/src/api/system.js` 的 `initSSE()`（`App.vue` 调用）与 `frontend/src/api/logs.js` 的 `initLogStream()`（`Settings.vue` 调用）。

> 注意：`error` 是 SSE 的**自定义事件名**，与 `EventSource` 自身的连接错误事件同名，但两者通过 `addEventListener('error', ...)` 与 `onerror` 区分，互不影响。

---

## 二、代码规范

> 说明：仓库**未配置**任何可执行的 lint/format 工具（详见 2.5）。以下条款仅归纳自现有代码与配置中**可验证**的事实，以及 `README.md`「贡献指南」中明示的目标。

### 2.1 通用

- 代码注释、docstring、日志文案一律使用中文（全仓库一致，如 `backend/main.py`、`backend/services/cleanup_service.py`、`frontend/src/api/request.js`）。
- 提交信息使用清晰的中文描述（`README.md` 第 319 行），类型前缀与多行格式见 4.2。
- 前端代码遵循 ESLint 规范、后端代码遵循 PEP 8 规范（`README.md` 第 317-318 行声明；工具未落地，见 2.5）。
- 修改业务逻辑时，同步在 `CHANGELOG.md` 按现有格式追加条目（`CHANGELOG.md` 已有 1.0.0 → 1.0.20 的连续条目，每条含「问题描述 / 修复方案」或「优化方案」及受影响文件列表）。
- 版本号单一真实来源为 `frontend/package.json` 的 `version`：`frontend/vite.config.js` 第 7-17 行读取该字段并注入全局常量 `__APP_VERSION__`。**不要**在代码中硬编码版本号。

### 2.2 后端（Python）

- **缩进**：4 空格。
- **命名**（Python 惯例，与现有代码一致）：
  - 模块/文件：`snake_case`（`download_service.py`、`bili_manager.py`、`log_manager.py`）
  - 函数/方法/变量：`snake_case`（`get_thread_safe_db_session`、`run_cleanup_scheduler`）
  - 类：`PascalCase`（`BiliManager`、`Downloader`、`PlaybackManager`、`Config`）
  - Pydantic 请求模型：`PascalCase` + `Req` 后缀（`ImportVideoReq`，`backend/routers/local.py` 第 23 行）
  - 模块级常量：`UPPER_SNAKE_CASE`（`DATA_DIR`、`BASE_DIR`、`DOWNLOAD_PATH`、`CACHE_LIMIT_BYTES`、`DATABASE_URL`）
  - 私有辅助函数/方法：前导下划线（`_diag`、`_clean_orphan_files`、`_enforce_cache_limit`、`_worker`）
- **文档字符串**：函数/方法首行使用中文三引号 docstring 说明职责。
- **日志**：模块级 `logger = logging.getLogger(__name__)`（`backend/main.py` 第 31 行、`backend/database/db.py` 等）；服务层也用 `logging.info(...)` 直接记录带 `[模块名]` 前缀的中文日志（`backend/services/cleanup_service.py` 第 26-28 行）。
- **导入组织**：标准库 → 第三方 → 应用内相对导入。包内统一使用**相对导入**（`from ..core.paths import DATA_DIR`、`from .services import cleanup_service`）。注意 `backend/database/db.py` 第 4、17 行使用了绝对导入 `from backend.core...`，因此后端必须以项目根目录为工作目录运行，或通过 `run_backend.py` 启动。
- **路由层约定**：
  - 每个业务域一个文件，模块级 `router = APIRouter(prefix="/api/<域>", tags=["<域>"])`。
  - 数据库会话通过 `db_session: Session = Depends(db.get_db)` 注入；B 站单例通过 `bili: BiliManager = Depends(get_bili)` 注入。
  - 业务逻辑写在 `backend/services/`，路由只做参数校验与编排。
  - 注意：`backend/routers/__init__.py` 导出了 `*_router` 别名，但 `backend/main.py` 第 200-207 行实际使用的是 `from .routers import auth, ...` 后 `app.include_router(auth.router)`，新增路由时以 `main.py` 的注册方式为准并保持同步。
- **数据库**：
  - ORM 模型集中于 `backend/database/models.py`，共享同一个 `Base = declarative_base()`。
  - 表结构变更需在 `backend/migrate_db.py` 的 `run_migrations()` 中追加幂等的 `PRAGMA table_info` 检查 + `ALTER TABLE`（不要依赖重建库）。
  - 引擎与连接池参数从 `config.yaml` 的 `database` 段读取（`backend/database/db.py` 第 19-35 行），并保持 `pool_pre_ping=True` 与 WAL/journal pragma。
  - 后台线程使用 `get_thread_safe_db_session()` 获取会话（`backend/services/clipboard_service.py`）。
- **配置读取**：统一通过 `backend/core/config.py` 的 `get_config()` 与该类的 `get_*_config()` / 点号键 `config.get('download.max_workers', 3)`，不要新增硬编码常量。
- **路径**：统一使用 `backend/core/paths.py` 的 `DATA_DIR` / `BASE_DIR`，不要在业务代码里拼接相对路径（`paths.py` 同时兼容开发目录与 PyInstaller 冻结环境）。
- **路径拼接安全（v1.0.24 补，务必遵守）**：**任何来自请求体 / 上传文件名 / 压缩包成员名 / 数据库里历史脏数据的字符串，都不得直接作为路径分量使用**。
  项目里已修过三类真实缺陷，都是同一个根因：
  1. `os.path.join(base, user_value)` —— 当 `user_value` 是绝对路径时会**丢弃 `base`**，是 `..\..\` 之外的第二种逃逸方式（`/api/system/fonts/upload`、主题包导入、备份恢复三处均中过招）；
  2. 只按 `/` 拆分压缩包成员名 —— Windows 上 `..\..\x` 仍能逃逸，必须 `os.path.basename(name.replace("\\", "/"))`；
  3. 用 `abspath(...).startswith(dir)` 做归属校验 —— 前缀匹配会被兄弟目录（如 `backgrounds_backup`）绕过，应改为比较 `os.path.dirname(target) == os.path.abspath(dir)` 或用 `os.path.commonpath`。
  另外两条配套要求：
  - **删除操作必须收口**：`shutil.rmtree` / `RMDir /r` 之类只能作用于「自己刚刚创建、且名字可预期」的临时目录；`backup_service.remove_temp_file()` 会校验目标必须位于系统临时目录且带导入前缀，是这个模式的参考实现；
  - **上传前先建目录、写完再校验体积**：不要对未做上限的 `zf.read(member)` 直接落盘（zip 炸弹）。
- **长任务**：耗时/周期性任务放入后台守护线程，并在 `backend/main.py` 的 `lifespan` 中启动（现有：`VerifyDownloadsThread`、`CleanupThread`、`ClipboardThread`），线程需带 `name=` 且 `daemon=True`。

### 2.3 前端（JavaScript / Vue）

- **语言**：全部为 JavaScript，**不使用 TypeScript**（无 `.ts` 文件、无 `tsconfig.json`）。
- **组件**：一律使用 `<script setup>` 单文件组件（23 个 `.vue` 文件全部采用，如 `App.vue` 第 1 行）。
- **命名**：
  - 组件与视图文件：`PascalCase.vue`（`PlayerBar.vue`、`BiliLibrary.vue`、`UniversalModal.vue`）
  - `src/api/`、`src/utils/`、`src/hooks/`、`src/stores/`：`camelCase.js`（`request.js`、`weightedPlayEngine.js`、`useShortcuts.js`、`playerStore.js`）
  - Pinia store：`defineStore('player', ...)` 风格，领域模块放在 `src/stores/modules/`（`player.js`、`settings.js`、`theme.js`、`constants.js`）
- **样式**：Tailwind CSS 工具类优先，全局 `src/style.css`；深色模式通过 `darkMode: 'class'`（`tailwind.config.cjs` 第 4 行）与 `dark:` 变体实现，例如 `text-gray-800 dark:text-white`。主题色使用 `primary` 色板的 CSS 变量（`rgb(var(--color-primary-*) / <alpha-value>)`），不要写死颜色值。
- **API 层**：在 `src/api/<域>.js` 中以默认导出对象聚合方法（`export default { getVideos: () => request.get('/local/videos'), ... }`）；请求路径写**不含 `/api`** 的相对路径，因为 `baseURL` 已包含 `/api`。响应拦截器已解包 `response.data`，调用处直接拿业务数据。
- **图与窗口**：图表统一使用 ECharts（`frontend/package.json` 第 20 行；`Statistics.vue`）。
- **路由**：`createWebHashHistory`，新增页面在 `src/router.js` 中注册，并在 `src/views/` 下新增 PascalCase 视图文件。
- **Pinia 初始化顺序**：`src/main.js` 第 17-19 行要求在任何路由逻辑前初始化 `usePlayerStore()`，调整入口时不要破坏该顺序。
- **弹窗与动画**：使用既有 `UniversalModal.vue`，遵守 `CHANGELOG.md` 第 493-495 行确立的动画命名规范（`toast-fade` 用于浮窗、`modal-fade` 用于全屏弹窗、`fade` 用于简单淡入淡出），并保持遮罩层与内容分离。
- **依赖新增**：前端新增依赖写入 `frontend/package.json` 并提交更新后的 `package-lock.json`；后端写入 `requirements.txt`，并同步 `build.bat` 与 `backend.spec` 的 `hiddenimports`（当该依赖为运行时动态导入时）。

### 2.4 文档与注释

- `CHANGELOG.md`：按版本倒序，标题格式 `## [x.y.z] - YYYY-MM-DD`，使用既有的「🚀 新功能」「🐛 问题修复」「🔧 技术改进」「📚 文档更新」等小节标题（与 `README.md` 徽章、`package.json` 版本号保持同步）。
- `docs/`：面向用户的中文说明文档（配置说明、用户协议与隐私政策）。
- 涉及危险操作、性能优化或踩坑修复时，在代码内以中文注释标明原因（现有代码普遍采用 `# [性能优化]`、`# [修复历史遗留问题]` 等标记）。

### 2.5 测试与自检（重要，勿臆造）

- **仓库没有测试框架配置**：不存在 `pytest.ini`、`pyproject.toml`、`setup.cfg`、`tox.ini`、`jest.config.*`，也没有 `test_*.py` / `*.test.js`。**没有 CI**（无 `.github/` 目录），因此**没有自动化门禁**——`tests/` 下的脚本是本项目**唯一**的自动化防线，改动后必须手工跑。
- `tests/` 下现有 **7 份可运行的自检／校验脚本**（`tests/README.md` 与之同步）：

  | 脚本 | 作用 | 通过标准 |
  |---|---|---|
  | `tests/verify_backend_v1021.py` | 后端自检：进程内 `TestClient` 启动应用 + 临时 `uvicorn`（端口 12199）验证 SSE；覆盖日志/错误/调试/下载修复/脱敏/路径穿越防护/轮转共 **148 项断言** | 输出「通过 148 项，失败 0 项」，退出码 `0` |
  | `tests/verify_update_overwrite.cjs` | **发行包覆盖更新数据安全沙盒验证**：解析真实参与编译的 `frontend/build/uninstall_list.nsh`，按 NSIS 语义在系统临时目录重演一次升级，断言用户数据完好、程序文件被替换；内置负向自检 | 输出「通过 19 项，失败 0 项」，退出码 `0` |
  | `tests/check_api_wiring.cjs` | 前端↔后端接线静态校验：①组件调用的 `xxxApi.method()` 是否真的导出；②受 `require_debug_token` 保护的路由，前端是否携带 `X-Debug-Token` | 输出「检查通过」，退出码 `0` |
  | `tests/check_api_wiring_selftest.cjs` | 上述校验脚本的**负向自检**：临时把 `getDebugAudit` 改回漏传令牌，确认能被检出，然后自动恢复 | 输出「负向测试通过」+「恢复后检查通过」 |
  | `tests/verify_cover_url.py` | 后端封面地址净化逻辑（24 项） | 「通过 24 项，失败 0 项」 |
  | `tests/verify_cover_format.cjs` | 前端 `formatImg` / `normalizePic`（18 项） | 「通过 18 项，失败 0 项」 |
  | `tests/verify_proxy_image.py` | `/api/proxy/image` 健壮性（10 项） | 「通过 10 项，失败 0 项」 |

  改前端 `api/*.js` 后**务必**跑一遍 `check_api_wiring.cjs`——历史上两次真实缺陷
  （`systemApi.getStats is not a function`、审计日志 403 令牌校验失败）都是
  「构建通过、运行期才炸」，正是该脚本要拦的类型。
  改**安装器 / 打包配置**（`frontend/installer.nsh`、`frontend/build/afterPack.cjs`、
  `frontend/package.json` 的 `build` 段）后**务必**跑 `verify_update_overwrite.cjs`，
  它是「升级不丢用户数据」这条红线的唯一自动化守卫。

- 手工验证手段：启动后端调接口（`python run_backend.py`，`http://127.0.0.1:12180/docs` 有自动生成的接口文档）；前端 `npm run dev` 观察界面；`cd frontend && npm run build` 验证所有 SFC 可编译。
- 自检脚本的**安全约定**（新增脚本时必须遵守）：
  - 不得触发关机 / 休眠 / 重置软件 / 卸载等破坏性操作；
  - 不得读取或输出 `backend/data/` 下的凭据类文件（见 3.1）；
  - 涉及长连接（SSE）的验证必须用真实 `uvicorn` 子进程 + `requests` 流式读取，
    **不要**用 `TestClient`（长连接无法安全中断，会让脚本挂起）；
  - 关键字断言要避开「请求日志中间件会记录查询 URL 自身」这一自我匹配陷阱；
  - **只在系统临时目录里建沙盒**，不要为了「干净环境」去删改真实用户数据；
  - 输出标记统一用 `[PASS]` / `[FAIL]`（ASCII），便于在 GBK 控制台与 CI 日志中稳定阅读。

- **`tests/README.md` 已重写为与当前脚本一致**；其中提及的 `simple_test.py`、`load_test.py`、`realistic_load_test.py` 是 v1.0.20 被有意移除的旧压测脚本，**不要**试图恢复或臆造。
- 「(待补充：测试框架与最低覆盖率要求)」——如需引入正式测试框架，请先与维护者确认。

### 2.6 调试系统：开放接口（v1.0.21 新增，务必遵守）

调试系统对外暴露一组**本机 HTTP 接口**，供开发者与 AI 编码助手（Vibe Coding）远程读取状态、排查问题。
它是本项目**唯一「可对外执行动作」的接口面**，因此有三道闸门与能力白名单，改动时不得放宽。

**实现位置**：`backend/core/debug_service.py`（会话 / 协议 / 沙箱）、`backend/routers/debug.py`（路由）；
前端入口为「设置 → 调试系统」（`frontend/src/views/Settings.vue`）；用户文档见 [`docs/调试系统说明书.md`](docs/调试系统说明书.md)。

#### 2.6.1 三道闸门

| 闸门 | 机制 | 代码依据 |
|---|---|---|
| ① 协议闸门 | 必须逐项勾选 `CONSENT_CHECKLIST` 的 **5 个确认项**；确认记录（含 `CONSENT_VERSION` 与时间）持久化到 `backend/data/debug_consent.json`；**协议版本号变更后旧确认自动失效** | `debug_service.accept_consent()` / `CONSENT_VERSION` |
| ② 显式开关 | 默认关闭，必须用户主动开启；`disable()` 立即销毁令牌；**进程重启不自动恢复**（令牌仅存内存） | `DebugSession.enable()` / `disable()` |
| ③ 令牌 + 能力开关 | 所有「远程调试接口」需请求头 `X-Debug-Token`；`allow_python`（表达式）与 `allow_shell`（命令）默认 `false`，需单独勾选 | `require_debug_token` 依赖；`DebugSession.allow_*` |

#### 2.6.2 接口清单

**无需令牌**（供界面自身管理）：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/debug/status` | 调试状态；`include_token=true` 时返回令牌（**仅界面使用**） |
| GET | `/api/debug/agreement` | 协议全文 + 确认项 |
| POST | `/api/debug/consent` | 提交逐项确认，body `{"checklist": ["read","risk","liability","lawful","privacy"]}` |
| DELETE | `/api/debug/consent` | 撤回确认（同时关闭调试模式） |
| POST | `/api/debug/enable` | 开启，body `{"allow_python":bool,"allow_shell":bool}`，**返回令牌** |
| POST | `/api/debug/disable` | 关闭并销毁令牌 |
| POST | `/api/debug/token/rotate` | 轮换令牌（旧令牌立即失效） |

**需要令牌**（缺失或错误统一 `403 {"detail": "调试令牌无效"}`，并记入审计 `auth_failed`）：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/ping` | 连通性与能力探测（返回 `capabilities`） |
| GET | `/help` | **自描述文档**，便于 AI 助手自动发现能力；**新增接口时必须同步此表** |
| GET | `/scene` | 运行场景快照（进程 / 线程 / 内存 / 数据库统计 / 下载队列 / 日志状态 / **标准流健康度**） |
| GET | `/logs` | 读取日志，支持 `levels` `keyword` `exclude` `hide_heartbeat` `since_seq` `limit` |
| GET | `/errors` | 错误记录 + 错误百科 |
| POST | `/errors/{id}/repair` | 一键修复指定错误 |
| POST | `/errors/{id}/bypass` | 绕过指定错误 |
| POST | `/action` | 执行受限动作（见 2.6.3） |
| GET | `/audit` | 审计日志（内存保留 500 条） |
| DELETE | `/audit` | 清空审计日志 |
| POST | `/report-test-error` | 注入测试错误，用于验证前端弹窗链路 |

#### 2.6.3 受限动作白名单（`POST /action`）

请求体统一为 `{"action": "...", "payload": {...}}`，`action` 仅限 `ALLOWED_ACTIONS = ('python', 'shell', 'db_query')`。

| action | 前置能力 | 约束 |
|---|---|---|
| `python` | `allow_python` | **命名空间隔离 + 关键词黑名单双重校验**：沙箱只注入 `PYTHON_SAFE_NAMESPACES` 里显式列出的**只读属性**（如 `os.getcwd`、`os.sep`），**不注入模块对象本身**；黑名单 `PYTHON_FORBIDDEN` 作第一道粗筛；**禁止**下划线开头的私有属性访问（阻断 `__class__` / `__globals__` 逃逸）；沙箱 `__builtins__` 仅暴露安全内建 |
| `shell` | `allow_shell` | 必须整体匹配 `SHELL_WHITELIST` 正则（`ipconfig` / `systeminfo` / `tasklist` / `netstat` / `ver` / `where` / `ping -n` / `nslookup` / `dir` / `echo`）；**禁止** `& \| ; > < \` $` 与换行；硬超时 `COMMAND_TIMEOUT = 20` 秒；输出截断 `OUTPUT_LIMIT = 20000` 字符 |
| `db_query` | 无（默认允许） | 仅单条 `SELECT`；命中 `_FORBIDDEN_SQL`（insert/update/delete/drop/alter/create/pragma/vacuum/…）或出现多语句一律拒绝；最多返回 200 行 |

> **为什么 `python` 动作必须做命名空间隔离（v1.0.24 血泪教训）**
>
> 早期实现把**完整模块对象**注入 `eval` 命名空间，再用关键词黑名单拦截危险写法。
> 这在一开始就注定不安全：黑名单只逐词匹配了 `subprocess.popen`（小写），
> 而 `subprocess` 模块本身是可用的，于是
> `subprocess.run("shutdown /s /t 0", shell=True)` 通过了全部检查 ——
> **仅开启「表达式执行」即可执行任意系统命令**，彻底绕过独立的「命令执行」闸门
> （`SHELL_WHITELIST`、`COMMAND_TIMEOUT`、审计标签全部失效）。
>
> 结论（新增受控执行能力时必须遵守）：
> 1. **白名单要落在「值」上，不能落在「名字」上**：决定暴露哪个具体函数，而不是暴露模块后去猜有哪些危险方法；
> 2. **黑名单只能当粗筛**，字符串匹配极易被大小写、拼接、属性链绕过，永远不能作为唯一防线；
> 3. 新增 allowlist 模块时，**必须同时**在 `PYTHON_SAFE_NAMESPACES` 中逐项列出允许的属性，
>    并在 `tests/verify_backend_v1021.py` 第 3 节补一条「越权必须被拒绝」的断言
>    （现有断言：`subprocess.run` / `subprocess.Popen` / `subprocess.check_output` /
>    `os.popen` / `shutil.rmtree` / `sys.modules` 六种逃逸必须全部返回 400）。

**改动白名单时必须同步**：`debug_service.ALLOWED_ACTIONS` / `SHELL_WHITELIST` / `PYTHON_MODULE_ALLOWLIST` / `PYTHON_SAFE_NAMESPACES` / `PYTHON_FORBIDDEN`，
以及 `tests/verify_backend_v1021.py` 第 3 节的对应断言（危险表达式拦截、非白名单命令拦截、写操作 SQL 拦截）。

#### 2.6.4 安全红线

- **仅监听 `127.0.0.1`**，不得新增对外暴露的监听地址（与 3.3 一致）。
- 令牌为 `secrets.token_urlsafe(32)`，比对必须用 `hmac.compare_digest`（防时序攻击）；**只存内存、不落盘**。
- 每一次受保护请求都要写审计（动作 / 耗时 / 成败），并输出 `[调试审计]` 前缀日志。
- **不得**为调试接口新增任何数据外传通道；`/scene`、`/logs` 等返回内容不得包含 Cookie / SESSDATA / 用户媒体库原文。
- 前端调用受保护接口时**必须**传令牌（`debugHeaders(token)`），且调用方首个参数必须是令牌——
  `tests/check_api_wiring.cjs` 的「检查 B」会静态拦截漏传（历史缺陷：审计日志 403「令牌校验失败」）。
- 关闭调试模式 / 轮换令牌后，界面必须能感知令牌失效（403 时刷新 `/status`），**不得静默失败**。

### 2.7 日志系统约定

- **统一装配入口**：`backend/core/log_manager.py` 的 `setup_logging()`，在 `backend/main.py` **最早期**调用（必须早于任何可能失败的导入）。
  任何模块都**不要**再调用 `logging.basicConfig()`（历史死锁缺陷见 `CHANGELOG.md` 1.0.19）。
- **时间戳**：一律 `datetime.fromtimestamp(ts).astimezone()`，格式 `%Y-%m-%d %H:%M:%S`。
  内存日志对外字段为 `{ts(epoch秒), time(可读字符串), level, logger, message, heartbeat, heartbeat_category, seq}`——
  **不要把 epoch 秒当毫秒交给前端**（历史缺陷：界面显示 1970 年）。
- **三级轮转回收**：`RotatingSizeFileHandler` 按「单文件体积 `max_file_mb` → 文件数量 `max_files` → 总占用 `max_total_mb`」回收；
  归档命名 `bilimusic-YYYYmmdd-HHMMSS.log`，当前文件固定 `bilimusic.log`。策略取自 `config.yaml` 的 `logging` 段，可在界面热改。
- **心跳分类**：噪声日志由 `classify_heartbeat()` 归为 `request` / `login` / `polling`（HTTP 请求 / 登录验证 / 前端轮询），
  支持**按类别**屏蔽。新增高频日志时请同步加入 `HEARTBEAT_CATEGORIES`，否则会污染日志面板。
- **禁止**：把剪贴板内容、Cookie、用户媒体库原文写入日志（与 3.3 一致）；
  日志中间件不得记录日志查询接口自身的 URL（否则被查询的关键字会出现在它自己的日志里，看起来像「筛选失效」）。

### 2.8 错误系统约定

- **错误码必须先登记**：在 `backend/core/error_manager.py` 的 `ERROR_CATALOG` 中通过 `_register(ErrorSpec(...))` 登记
  错误码、标题、`summary`（这是什么）、`causes`（可能原因）、`solutions`（怎么解决）、是否可一键修复；
  **未登记的错误码会回落到 `UNKNOWN_ERROR`**。
- **分类**：`classify_exception(exc, context)` 把异常映射到错误码，`context['scope']` 影响归类（如 `'download'`）。
  新增异常类型时在此处补匹配规则，并同步 `tests/verify_backend_v1021.py` 的分类断言。
- **上报**：`get_error_manager().report(...)` / `report_exception(...)`；`dedupe_key` 用于合并同源未处理错误（防批量下载刷屏）。
  仅当错误会**终止业务逻辑**时 `popup=True`（默认），纯诊断信息用 `popup=False`。
- **一键修复**：`register_repair(code, handler)` 注册回调，签名 `handler(record) -> (ok, message)`；
  动作必须**幂等且可解释**，成功时把错误置为 `resolved`。
- **诊断包隐私红线**：`build_diagnostics()` 产出的 ZIP 必须经 `redact()` 脱敏，**不得**包含
  Cookie / SESSDATA / 账号信息 / 媒体库内容 / 播放记录；**不得**新增任何自动上传逻辑
  （与 `docs/用户协议与隐私政策.md` 的「零遥测」承诺一致，见 3.3）。
- 错误事件经 `/api/system/events` 的 `error` 事件推给前端；前端消费入口是 `player` store 的
  `handleErrorMessage()`，弹窗组件为 `frontend/src/components/ErrorDialog.vue`。

---

## 三、安全边界

### 3.1 绝对禁止读取、修改、提交或删除的文件

以下文件包含**用户凭据或私有运行时数据**，位于 `backend/data/`（已被 `.gitignore` 第 31 行整体忽略）：

| 路径 | 内容 | 依据 |
|---|---|---|
| `backend/data/bili_cookies.json` | B 站登录 Cookie（含 `SESSDATA`、`bili_jct`），等同于账号凭据 | `backend/core/bili_manager.py` 第 24、310-316 行 |
| `backend/data/bili_user_info.json` | 登录用户信息缓存 | `backend/services/system_service.py` 第 81 行 |
| `backend/data/bili_player.db`（及 `-wal` / `-shm`） | 用户媒体库、播放记录、统计等全部业务数据 | `backend/database/db.py` 第 11 行 |
| `backend/data/downloads/` | 用户缓存的音视频文件 | `backend/services/cleanup_service.py` 第 15 行 |
| `backend/data/covers/`、`stickers/`、`backgrounds/`、`particles/`、`fonts/`、`img_cache/` | 用户数据与缓存 | `backend/main.py` 第 76-80 行；`backend/services/system_service.py` 第 57 行 |
| `config.yaml` | 运行时配置（被 `.gitignore` 第 33 行忽略） | `.gitignore`；`backend/core/config.py` |
| `.venv/` | Python 虚拟环境 | `.gitignore` 第 5 行 |

**硬性约束**：

- 不得输出、复制、回显、打印或以任何方式外传 `bili_cookies.json` / `bili_user_info.json` 的内容（其中 `SESSDATA` 可直接接管用户 B 站账号）。
- 不得删除或重置 `backend/data/` 下的任何文件来「清理环境」。需要干净数据时，请新建独立的临时目录，而不是动用户数据。
- 不得为了调试而修改 `config.yaml` 后留在磁盘上；如需临时改端口，使用 `run_backend.py` 支持的命令行端口参数（`run_backend.py` 第 193-198 行）。
- `frontend/release/`、`frontend/dist/`、`dist/`、`node_modules/`、`__pycache__/` 为构建/依赖产物，不要手工编辑，也不要提交。

### 3.2 破坏性操作：必须由人类确认后才可执行

以下操作会不可逆地影响用户系统或数据，Agent **不得自行触发**：

- **系统级指令**（`backend/services/system_service.py`）：
  - `execute_system_shutdown()` → `shutdown /s /t 0`（Windows）/ `sudo -n shutdown -h now`
  - `execute_system_sleep()` → `rundll32.exe powrprof.dll,SetSuspendState` / `pmset sleepnow` / `systemctl suspend`
  - 对应 HTTP 接口：`POST /api/system/shutdown`、`POST /api/system/sleep`
- **恢复出厂设置**：`POST /api/system/factory-reset` → `execute_factory_reset()`，会遍历删除 `DATA_DIR` 下 stickers/backgrounds/particles/covers/downloads/fonts/img_cache 中的文件，并清空 `Video`、`Collection`、`Tag`、非默认 `Theme`、`PlayRecord`、`DailyStat` 表，同时删除 Cookie 与用户信息文件（`backend/services/system_service.py` 第 33-95 行）。
- **卸载应用**：Electron IPC `uninstall-app` 会调用同目录下的 `Uninstall BiliMusic.exe`（`frontend/main.cjs` 第 222-238 行）。
- **卸载时删除 AppData**：`frontend/installer.nsh` 的 `customUnInstall` 只有在用户于弹窗中**明确选择删除数据**（`$R9 = "0"`）时才执行 `RMDir /r "$APPDATA\BiliMusic"`。
  **不要**在 `frontend/package.json` 的 `nsis` 段重新加回 `"deleteAppDataOnUninstall": true`：该开关会定义 `DELETE_APP_DATA_ON_UNINSTALL`，
  使 electron-builder 模板**无条件**清空 `%APPDATA%\BiliMusic`（它从不读取 `$R9`），于是用户「保留数据」的选择被静默忽略，
  丢掉的正是 `localStorage` 中的设置/主题/播放队列与 IndexedDB `BiliMusicDB`。v1.0.24 已移除该开关，改为以显式弹窗 + `$R9` 为准。
- **删除用户媒体文件**：`os.remove` / `RMDir` 相关逻辑，包括 `cleanup_service` 的缓存清理与 `system_service` 的重置流程。
- **安装器清理宏**：`frontend/build/afterPack.cjs` 生成 `frontend/build/uninstall_list.nsh` 中的 `customRemoveFiles` / `cleanOldFiles` 宏。
  **正确形态**：`RMDir /r "$INSTDIR"` **只允许出现在 `customRemoveFiles` 的 `$R9 == "0"` 分支内**（即用户明确要求删除数据）；
  正常升级路径（`$R9 == "1"`）必须走 `${Else}` 分支——逐个 `Rename` 旧程序文件到 `$PLUGINSDIR\old-install`，再用**不带 `/r`** 的 `RMDir` 清理已空目录。
  `cleanOldFiles`（旧版不支持保留数据时的降级路径）**同样不得**包含 `RMDir /r`。
  用户数据位于 `$INSTDIR\resources\backend\data`；正因为 `RMDir` 不带 `/r`、且该目录非空，升级才删不掉它。
  这两条不变量由 `tests/verify_update_overwrite.cjs` 断言，改完必须跑。
- **Git 破坏性命令**：`git reset --hard`、`git push --force`（`--force-with-lease` 亦然）、`git clean -fdx`、`git rebase` / `commit --amend` 改写已推送历史、`git branch -D`。仓库是真实的 Git 仓库并跟踪 `origin/main`，且 `.git/logs/HEAD` 显示历史上**已发生过 6 次 `reset` 丢弃提交**（被放弃的提交包括 `629b9d72`、`e2d75bec`、`6210a067`），说明这类操作在本项目中确实造成了内容丢失。Agent **不应**自行执行上述命令；确有必要时，先向维护者说明将丢弃哪些提交。

### 3.3 网络安全边界

- 后端**必须**保持监听 `127.0.0.1`。`docs/配置说明.md` 第 28 行明确要求「不要设置为 `0.0.0.0`（允许外部访问）以确保安全」。**不要**把 host 改成 `0.0.0.0`。
- 后端 CORS 当前为 `allow_origins=["*"]` + `allow_credentials=True`（`backend/main.py` 第 185-191 行）。这是既有实现，**不要以此为由进一步放宽**（例如新增对外暴露的监听地址或去掉本地绑定）。如确需收紧，作为独立改动提出并说明影响。
- Electron 窗口当前配置 `nodeIntegration: true`、`contextIsolation: false`、`webSecurity: false`（`frontend/main.cjs` 第 109-113 行）。这是既有实现，属于已知的安全权衡；**不要**扩大其影响面（例如加载远程页面或注入远程脚本）。
- **不得新增任何向外部服务器上报数据的代码**。项目对外有硬性隐私承诺：「我们没有、也不会部署任何中心化的遥测（Telemetry）服务器，不收集任何用户行为数据、崩溃日志、设备指纹或使用统计」（`docs/用户协议与隐私政策.md` 第 51 行）。引入任何分析/统计 SDK 都属于违约。
- 登录凭证「仅会……保存在您本机的相对目录或配置文件中……**绝对不会上传给开发者或任何第三方服务器**」（同上，第 57 行）。不要新增把 Cookie 或用户信息发往外部端点的逻辑。
- 剪贴板监听必须保持「完全、彻底地在本地离线内存中进行」，未匹配的内容「会被瞬间丢弃，绝不会被存储、记录或外传」（同上，第 63-67 行；实现见 `backend/services/clipboard_service.py`）。**不要**为剪贴板内容增加落盘、日志输出或上传。

#### 3.3.1 调试系统的额外边界（v1.0.21 新增）

调试系统是本项目唯一的「可对外执行动作」接口面，除遵守上述全部条款外，还须：

- **不得放宽三道闸门**（协议逐项确认 / 显式开关 / 令牌 + 能力开关），详见 2.6.1。特别是：
  不要为图省事而「记住上次确认」「自动开启」「令牌持久化到磁盘」。
- 令牌仅存内存、进程重启即失效；`/api/debug/status?include_token=true` 会返回明文令牌，
  **不得**把该接口的返回内容写入日志、错误记录或诊断包。
- 调试接口的返回内容（`/scene`、`/logs`、`/errors`）可能包含文件路径与媒体标题，
  但**不得**包含 Cookie / SESSDATA / `bili_user_info.json` 内容 / 用户媒体库原文。
- **不得**新增任何默认放行的动作类型；新增 `action` 必须同时提供白名单校验与审计记录，
  并在 `tests/verify_backend_v1021.py` 中补充「越权必须被拒绝」的断言。
- 新功能若会改变前端对受保护接口的调用方式，必须同步
  `frontend/src/api/system.js`（`debugHeaders(token)`）并跑 `node tests/check_api_wiring.cjs`。
- 风险与责任划分的用户可见文案（`AGREEMENT_TEXT`、`CONSENT_CHECKLIST`）如需修改，
  必须递增 `CONSENT_VERSION`，使既有确认记录失效并触发重新确认。

### 3.4 应当遵守的版权与内容边界

- 本应用仅面向用户**个人合法使用**的 B 站内容。不要新增绕过 B 站会员/付费/版权限制、批量抓取或再分发内容的功能。
- B 站接口调用需保留 `Referer` / `Origin` / `User-Agent` 头（`backend/core/bili_manager.py` 第 31-35 行），不要为了「简化」而移除。

---

## 四、Git 规范

> **说明**：仓库已初始化 Git，`.git/` 为隐藏目录。常规的文件枚举工具（glob / ripgrep）会**跳过 `.git/`**，因此不能用它们来判断仓库是否存在。
> `git` 与 `pwsh` **在本环境中可正常执行**（见文首说明），本节结论既可用 git 命令复核，也可直接读取 `.git/HEAD`、`.git/config`、`.git/logs/HEAD`、`.git/refs/...`。

### 4.1 仓库事实（已从 `.git/` 元数据验证）

| 项 | 值 | 依据 |
|---|---|---|
| 默认分支 | `main`（由 `master` 重命名而来） | `.git/HEAD` = `ref: refs/heads/main`；`.git/logs/HEAD` 第 2 行「renamed refs/heads/master to refs/heads/main」 |
| 本地分支 | **仅 `main` 一个** | `.git/refs/heads/` 下只有 `main`；不存在 `master`、`develop`、`feature/*` 等分支 |
| 远程 | `origin` = `https://github.com/XK-SZG/BiliMusic.git` | `.git/config` 第 7-9 行 |
| 上游跟踪 | `main` 跟踪 `origin/main` | `.git/config` 第 10-12 行 |
| 当前 HEAD | `92780a83`（与 `origin/main` 一致，无未推送提交） | `.git/refs/heads/main` 与 `.git/refs/remotes/origin/main` 值相同 |
| 标签 | **无任何 tag** | `.git/logs/HEAD` 的 24 条记录中，操作类型只有 `commit`、`Branch`、`reset`，**无任何 `tag:` 记录**（Git 会在创建 tag 时写入 reflog，故可据此判定）。`.git/refs/tags/` 目录本身存在但为空 |
| Git hooks | **无启用的 hook**（仅 `.sample` 模板） | `.git/hooks/pre-commit.sample` 等均为样例文件，无同名可执行 hook |
| 提交作者 | `XK <kangxu346@gmail.com>` | `.git/logs/HEAD` 全部条目 |
| 提交时区 | `+0800` | `.git/logs/HEAD` |

### 4.2 提交信息格式（依据真实提交历史）

从 `.git/logs/HEAD` 可读取全部历史提交信息，实际用法如下：

- **主格式：`<英文类型前缀>: <中文描述>`**。历史中实际出现过的类型前缀**只有以下 5 个**，不要臆造 `feat:`、`perf:`、`refactor:`、`test:` 等本仓库未使用过的前缀：
  - `fix:` —— 如 `fix: 修复打包后无法连接后端的问题并增强日志系统 (v1.0.17)`、`fix: 将端口从12280改为12180，避免被系统占用`
  - `docs:` —— 如 `docs: specify 64-bit system requirement in README`、`docs: 补充 v1.0.18 CHANGELOG 中 log_manager 打包修复条目`
  - `chore:` —— 如 `chore: 发布 v1.0.20，清理测试文件，移除调试日志，修复端口冲突`
  - `build:` —— 如 `build: 打包生成 1.0.17 安装包`
  - `release:` —— 如 `release: v1.0.17 - 性能优化与功能增强`、`release: v1.0.19 - 修复后端日志系统死锁导致启动挂起的致命缺陷`
- **描述部分使用中文**（与 `README.md` 第 319 行的要求一致）。
- **发版提交**除 `release:` 前缀外，也存在直接以版本号作标题的写法：`v1.0.20`、`v1.0.20: 全方位清理与端口修复`。
- **多行提交信息**：当一次提交包含多项改动时，首行为摘要，空行后以 `-` 逐条列出。现行 HEAD 提交（`.git/COMMIT_EDITMSG`）即为范例：

  ```
  v1.0.20: 全方位清理与端口修复

  - 修复安装器更新导致数据丢失的问题
  - 修复本地媒体库视频裁剪预览失败的问题
  - 统一后端端口为 12180，解决端口冲突问题
  - 清理测试脚本、无用资源及调试日志
  ```

- **一致性提示**：历史中存在少数「一整句中文无前缀」的提交（如 `修复软件更新数据丢失问题；修复视频裁剪预览失效问题；…`）。因此类型前缀是**推荐惯例而非强制**；新增提交建议沿用前缀 + 中文描述的写法。
- 「(待补充：是否允许在提交信息中引用 issue 编号)」——现有历史中**从未出现** issue 编号。

### 4.3 分支与协作流程

- **维护者实际流程**：全部提交**直接落在 `main`**，不创建特性分支、不合并分支，完成后推送到 `origin/main`（`.git/logs/refs/remotes/origin/main` 中 7 条 `update by push` 记录）。这是单分支主干开发模式。
- **`README.md` 对外部贡献者的声明**（第 300-319 行，与维护者自身习惯不同，但应遵守）：Fork → `git checkout -b feature/AmazingFeature` → 提交 → `git push origin feature/AmazingFeature` → 开 Pull Request。
- **Agent 行为建议**：除非人类明确要求，**不要**自行创建分支、推送或开 PR；也不要自行执行合并。改动留在工作区交由维护者提交。
- 上游仓库地址：`https://github.com/XK-SZG/BiliMusic`（`.git/config` 与 `README.md` 第 142、157 行一致）。
- 许可证：MIT，Copyright (c) 2024 XK-SZG（`LICENSE`）。新增文件请勿更改许可证声明。

### 4.4 提交内容约定（从项目文件推断）

- **版本号同步**：发版提交（`release:` 或 `vX.Y.Z`）应同时更新 `frontend/package.json` 的 `version`（版本号单一真实来源，见 2.1）、`CHANGELOG.md` 的新条目标题、以及 `README.md` 第 8 行徽章。**这三处必须一致**——历史上 `README.md` 徽章曾长期停留在 `1.0.19` 而 `package.json` 已到 `1.0.20`，v1.0.24 已一并对齐为 `1.0.24`，请勿再让它们漂移。
- **必须同步更新的文件**：修改用户可见行为时更新 `CHANGELOG.md`（历史上存在专门的 `docs:` 提交用于补齐 CHANGELOG）；修改配置项时同步 `config.yaml`、`config.yaml.example`、`docs/配置说明.md` 与 `backend/core/config.py` 的 `_get_default_config()`——**默认值必须与 `config.yaml.example` 逐键一致**（`logging` 整段曾在默认值里缺失，导致回退到默认配置时日志保留策略静默失效）。
- **不要提交**：`frontend/node_modules/`、`frontend/dist/`、`frontend/release/`、`dist/`、`.venv/`、`__pycache__/`、`*.log`、`config.yaml`、`backend/data/`（依据根 `.gitignore`）。其中 `config.yaml` 与 `backend/data/` 的忽略是**有意的凭据保护**（见 3.1），不要用 `git add -f` 强行加入。
- **注意 `.gitignore` 与已跟踪文件的区别**：`.gitignore` 对**已被跟踪**的文件无效。根 `.gitignore` 的 `*.spec` 会阻止新增 spec 文件被跟踪，但已存在的 `backend.spec` 属于 PyInstaller 自动生成物（`build.bat` 通过命令行参数而非 `.spec` 打包），**不要把它当作构建的权威配置**——真正的打包定义在 `build.bat`。
- **`frontend/build/` 的特例（v1.0.24 修复）**：根 `.gitignore` 的 `build/` 规则会**连带忽略 `frontend/build/`**，而该目录放着打包必需资源。因此 `.gitignore` 末尾有显式的反向规则，**只放开两个文件**：
  - `!frontend/build/afterPack.cjs` —— `frontend/package.json` 的 `build.afterPack` 直接引用，缺失时 electron-builder **打包直接失败**；
  - `!frontend/build/icon.ico` —— `buildResources` 目录资源。
  而 `frontend/build/uninstall_list.nsh` 是 `afterPack.cjs` 的**生成物**，被显式忽略且**不应入库**（electron-builder 先跑 `afterPack` 再编译 NSIS，新旧不一致的清单反而会导致升级行为与代码不符）。
  **不要**把 `frontend/build/` 整体加回忽略列表，也不要把生成的 `.nsh` 提交进去。

### 4.5 无法确认、需维护者补充的项目

以下内容在仓库中**找不到任何依据**，请勿臆造：

- 「(待补充：是否存在 `CONTRIBUTING.md`、`.gitmessage`、PR/Issue 模板)」——经检索均不存在。
- 「(待补充：是否要求 rebase / squash 合并、`main` 是否受保护)」——仅从本地元数据无法判断远程仓库的分支保护与合并策略。
- 「(待补充：CI 校验规则)」——不存在任何 CI 配置（无 `.github/` 目录），因此**没有**自动化门禁（无 lint、无测试、无构建校验）。
- 「(待补充：代码所有者与 review 要求)」——无 `CODEOWNERS` 文件。
- 「(待补充：发布流程)」——无任何 tag，`generate_checksums.bat` 会为 `frontend/release/*.exe` 生成 `sha256.txt`，但打 tag 与上传 GitHub Release 的流程无明文记载。
- 「(待补充：被 `reset` 放弃的提交是否还应保留其内容)」——`.git/logs/HEAD` 显示 `629b9d72`、`e2d75bec`、`6210a067` 等提交已被放弃，其内容是否需要恢复请先询问维护者。

---

## 五、给 Agent 的工作提示

1. **先读后改**：改动前先阅读目标文件及其直接依赖。本项目的关键约束往往写在代码注释里（例如 `backend/main.py` 第 29 行要求日志必须在任何可能失败的导入之前初始化；`frontend/main.cjs` 第 56 行决定了开发模式的后端启动方式）。
2. **改动后端 API 时**：同时更新 `backend/routers/<域>.py`、对应 `frontend/src/api/<域>.js`，并检查 `frontend/src/stores/` 中的调用点。
3. **改动配置项时**：同步 `config.yaml`、`backend/core/config.py` 的 `_get_default_config()`、`docs/配置说明.md` 三处。
4. **改动数据库模型时**：在 `backend/migrate_db.py` 追加迁移，并考虑 `backend/services/system_service.py` 的重置逻辑是否需要覆盖新表（历史缺陷：重置软件后新增统计表未清空，见 `CHANGELOG.md` 1.0.14）。
5. **性能敏感路径**：播放队列持久化、SQLite 并发、封面缓存、流媒体代理在 `CHANGELOG.md` 1.0.16 中做过专门优化，改动前先读该条目，避免回退既有优化（如已废弃的 `with_for_update()` 悲观锁、`JSON.parse(JSON.stringify())` 深拷贝）。
6. **无法验证时**：标注「(待补充：…)」并向维护者确认，不要臆造命令、路径或规范。
7. **不要扩大改动范围**：除被明确要求的文件外，不要顺手重构、格式化或「清理」无关代码；本项目没有自动格式化门禁，大范围重排会造成无法审阅的 diff。
