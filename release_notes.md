# BiliMusic v1.0.18 发行说明 (Release Notes)

🎉 我们很高兴地宣布 BiliMusic v1.0.18 正式发布！

本次更新是一次**紧急修复版本**，重点解决了两个致命缺陷：缓存清理机制导致的视频幽灵化问题，以及打包后因日志模块缺失导致的后端无法启动问题。同时新增了内置系统日志控制台，方便在脱离开发环境时排查问题。

---

## 🌟 核心亮点 (Highlights)

- **🛡️ 致命缺陷修复**：修复了缓存超限清理时，因文件被占用导致异常回滚，造成物理文件已删除但数据库状态未更新的"幽灵视频"问题。重构了清理服务的事务安全机制。
- **🔧 打包稳定性修复**：修复了新增的内存日志处理器（`log_manager`）未被 PyInstaller 打包，导致打包后后端服务静默崩溃、无法启动的 0day 漏洞。添加了多层容错降级机制。
- **📊 内置日志控制台**：新增系统日志面板，支持在软件内实时查看后端运行日志，无需打开开发者工具或查看文件。

---

## 🐛 致命缺陷修复 (Critical Bug Fixes)

### 缓存清理导致视频幽灵化
- **问题**：`cleanup_service.py` 的 `_enforce_cache_limit()` 将循环内所有数据库更新放入一个大事务，`db.commit()` 在循环最外层。当某个视频文件被播放器占用导致 `os.remove()` 失败时，异常触发 `db.rollback()`，导致在此之前已成功删除的文件无法恢复，但其状态更新也被一并回滚。
- **修复**：解耦文件删除与数据库更新——先尝试删除物理文件，成功后再逐条更新数据库并立即提交。文件被占用时跳过该视频继续处理下一个。同时为孤立文件清理添加异常捕获。

### 打包后后端无法启动
- **问题**：`backend/core/log_manager.py` 未被 PyInstaller 的 `hiddenimports` 声明，且 `backend/main.py` 中对该模块的导入在 `logging.basicConfig()` 之前，导致模块初始化失败时整个应用静默崩溃。
- **修复**：
  - `backend/main.py`：将 `logging.basicConfig()` 提前到所有可能失败的导入之前，并对 `log_manager` 导入添加 `try-except` 容错。
  - `backend/routers/system.py`：对 `memory_handler` 导入添加容错，失败时返回空日志数组和警告信息。
  - `build.bat` 和 `backend.spec`：添加 `backend.core.log_manager` 到 `hidden-import`/`hiddenimports` 列表。

---

## ✨ 新功能 (New Features)

### 内置系统日志控制台
- **后端**（`backend/core/log_manager.py`）：实现基于内存环形队列的 `MemoryLogHandler`（容量 500 条），自动捕获所有级别的日志。
- **API**（`backend/routers/system.py`）：新增 `GET /api/system/logs` 接口，返回格式化日志数据。
- **前端**（`frontend/src/views/Settings.vue`）：在系统设置页新增"系统日志"导航项与专属面板，支持点击刷新、颜色分级（错误红/警告黄/信息蓝）、时间戳显示。

---

## 🔧 受影响文件

| 文件 | 变更类型 |
|------|----------|
| `backend/services/cleanup_service.py` | 重构缓存清理事务安全机制 |
| `backend/core/log_manager.py` | **新建** — 内存日志管理器 |
| `backend/main.py` | 容错导入 + 日志初始化顺序调整 |
| `backend/routers/system.py` | 新增 `/api/system/logs` 接口 + 容错 |
| `backend.spec` | 添加 `hiddenimport` |
| `build.bat` | 添加 `--hidden-import` 参数 |
| `frontend/src/api/system.js` | 新增 `getLogs()` 方法 |
| `frontend/src/views/Settings.vue` | 新增系统日志面板 |
| `frontend/package.json` | 版本号更新至 1.0.18 |
| `README.md` | 版本号更新至 1.0.18 |
| `CHANGELOG.md` | 新增 v1.0.18 更新日志 |

---

## ⚠️ 升级须知 (Upgrade Notes)

1. **重新打包**：如果您正在使用打包版本，请务必使用更新后的 `build.bat` 或 `backend.spec` 重新构建后端 exe，以确保 `log_manager` 模块被正确包含。
2. **配置文件**：本版本配置无需变更，与 v1.0.17 完全兼容。
3. **日志查看**：安装后若遇到问题，可在"系统设置 → 系统日志"面板中查看后端运行日志，便于快速定位问题。

---

## 📥 下载地址

- Windows 安装包 (64-bit): [BiliMusic_Setup_1.0.18_x64.exe](附件链接)

*非常感谢所有提供反馈的用户，您的支持是我们前进的最大动力！*
